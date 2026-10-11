"""Isolated keyed ChronicleDM run. Uses existing prompts, memory adapter and judge.

Fresh RRF3 v1.1 material, exact-prompt response cache, one request per key at a time.
No answer values, states or gold timelines enter generation prompts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--bench', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    args.repo, args.bench, args.out = [p.resolve() for p in (args.repo, args.bench, args.out)]
    src = args.repo / 'TanPowasd' / 'discriminative_memory' / 'nl_eval'
    sys.path.insert(0, str(src))
    import chain_bench as CB
    import chain_llm as CL
    import chain_reader_on_memory as CR
    from cline_pool import ClinePool, MODEL, API

    data = args.out / 'data'
    corpus, questions = read(data / 'corpus.json'), read(data / 'keys.json')
    by_cid = {c['cid']: c for c in corpus}
    n_seq = {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    sysmsg = CL.load_official(args.bench)
    arm = 'llm_chronicle_dm_reader_v11'
    arm_dir = args.out / 'runs' / f'chain_{arm}'
    extract_dir = args.out / 'runs' / 'chain_llm_dm_v11'
    tasks = []
    extraction_hashes = set()
    for k in questions:
        # Deliberately retain only question inputs here, never the gold answer.
        q = {name: k[name] for name in ('qid', 'question', 'doc')}
        mat = read(args.out / 'runs' / 'chain_rrf3v11' / 'retrieval' / f"{q['qid']}.json")['material']
        _, _, ent, fac = CB.parse_q(q['question'], n_seq[q['doc']])
        messages = CL.build_extract_prompt(ent, fac, mat)
        extraction_hashes.add(hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest())
        tasks.append((q, mat, messages))
    plan = dict(model=MODEL, algorithm='RRF3 v1.1 -> LLM extraction -> ChronicleDM -> official LLM reader',
                total_questions=len(tasks), scored_questions=sum(not k['reconstructible'] for k in questions),
                test_questions=sum(not k['reconstructible'] and k['doc_id'] not in CB.DEV for k in questions),
                unique_extraction_prompts=len(extraction_hashes), reader_prompts=len(tasks),
                max_logical_calls=len(extraction_hashes) + len(tasks), per_key_concurrency=1,
                extraction_prompt='existing EXTRACT_SYS, unchanged', extraction_reasons=False,
                original_retrieval_source='rrf3v11', cache_policy='exact request hash, no imported old responses')
    dump(args.out / 'plan.json', plan)
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if args.dry:
        return

    client = ClinePool()
    plan['workers'] = client.workers
    started = time.perf_counter()
    counters, errors = Counter(), []
    cache_lock = threading.Lock()
    hash_locks = {}
    counters_lock = threading.Lock()
    cached_dir = args.out / 'responses' / 'by_prompt'

    def request(messages, phase, qid):
        payload = dict(model=MODEL, messages=messages, temperature=0, max_tokens=8000)
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with cache_lock:
            lock = hash_locks.setdefault(digest, threading.Lock())
        with lock:
            path = cached_dir / f'{digest}.json'
            cached = path.exists()
            if cached:
                result = read(path)
                if result['request_sha256'] != digest:
                    raise RuntimeError('Response-cache fingerprint mismatch')
            else:
                t0 = time.perf_counter()
                response = client.complete(messages, max_tokens=8000)
                result = dict(request_sha256=digest, response=response,
                              latency_seconds=round(time.perf_counter() - t0, 3),
                              saved_at=datetime.now(timezone.utc).isoformat())
                dump(path, result)
            dump(args.out / 'responses' / phase / f'{qid}.json',
                 dict(**result, cache_hit=cached, phase=phase))
            with counters_lock:
                counters[f'{phase}_cache_hits' if cached else f'{phase}_new_responses'] += 1
            choice = result['response']['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise RuntimeError('Model output reached token limit')
            return choice['message']['content']

    def one(task):
        q, original_material, extraction_prompt = task
        stage = 'extraction'
        try:
            raw = request(extraction_prompt, stage, q['qid'])
            match = re.search(r'\[.*\]', raw, re.S)
            if not match or not isinstance(json.loads(match.group()), list):
                raise ValueError('Extraction did not return a JSON array')
            events = CL.parse_events(raw)
            dump(extract_dir / 'events' / f"{q['qid']}.json", events)
            (args.out / 'llm_raw' / 'llm_dm_v11').mkdir(parents=True, exist_ok=True)
            (args.out / 'llm_raw' / 'llm_dm_v11' / f"{q['qid']}.txt").write_text(raw, encoding='utf-8')
            # Adapter and prompts are the repository implementation, not a new interpreter.
            stage = 'memory'
            material = CR.material_for('llm_chronicle_dm_reader', events, q, n_seq[q['doc']], by_cid)
            dump(arm_dir / 'retrieval' / f"{q['qid']}.json", {'qid': q['qid'], 'material': material})
            stage = 'reader'
            messages = CL.build_prompt(sysmsg, q['qid'], q['question'], material)
            dump(args.out / 'prompts' / 'reader' / f"{q['qid']}.json", messages)
            raw = request(messages, stage, q['qid'])
            answer = CL.parse_answer(raw, q['qid'])
            if not answer['_json_ok']:
                raise ValueError('Reader did not return a JSON object')
            # Detect syntactically invalid JSON even if the legacy parser found braces.
            json.loads(re.search(r'\{.*\}', raw, re.S).group())
            dump(arm_dir / 'sut' / 'out' / f"{q['qid']}.json", answer)
            return q['qid'], None
        except Exception as exc:
            # Never allow missing answers to shrink official metric denominators.
            dump(arm_dir / 'sut' / 'out' / f"{q['qid']}.json",
                 dict(qid=q['qid'], value=None, state=None, at_seq=None, chain=[], basis=[],
                      confidence='unknown', _json_ok=False, _run_failure=stage))
            return q['qid'], dict(qid=q['qid'], stage=stage, error_type=type(exc).__name__,
                                  message=str(exc)[:160] if isinstance(exc, RuntimeError) else 'Invalid stage output')

    def checkpoint(done):
        with counters_lock:
            state = dict(counters)
        state.update(completed=done, total=len(tasks), failed=len(errors), actual_http_attempts=client.calls,
                     per_key_attempts=client.report(), elapsed_seconds=round(time.perf_counter() - started, 1))
        dump(args.out / 'progress.json', state)
        print(json.dumps(state, ensure_ascii=False), flush=True)

    # Freeze code and revisions used by this run; local key configuration is excluded.
    source_paths = [p for folder in ('TanPowasd/chronicle', 'TanPowasd/chronicle_dm',
                                    'TanPowasd/discriminative_memory', 'TanPowasd/agm/rrf3')
                    for p in (args.repo / folder).glob('*.py')]
    source_paths += list(src.glob('*.py')) + [args.bench / 'chain/tools/probe_judge.py']
    fingerprints = {}
    for path in source_paths:
        rel = path.relative_to(args.repo) if path.is_relative_to(args.repo) else Path('benchmark/probe_judge.py')
        target = args.out / 'sources' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        fingerprints[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    def revision(root):
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    metadata = dict(**plan, started_at=datetime.now(timezone.utc).isoformat(), endpoint=API,
                    repo_commit=revision(args.repo), bench_commit=revision(args.bench),
                    source_sha256=fingerprints, fresh_responses=True, temperature=0, max_tokens=8000)
    dump(args.out / 'metadata.json', metadata)
    checkpoint(0)
    with ThreadPoolExecutor(max_workers=client.workers) as ex:
        futures = [ex.submit(one, task) for task in tasks]
        for done, future in enumerate(as_completed(futures), 1):
            qid, error = future.result()
            if error:
                errors.append(error)
                print(json.dumps({'failed': error}, ensure_ascii=False), flush=True)
            if done % 10 == 0 or done == len(tasks):
                checkpoint(done)

    dump(args.out / 'errors.json', errors)
    sys.path.insert(0, str(args.bench / 'chain' / 'tools'))
    import probe_judge as J
    J.OUT, J.RUNS = data, args.out / 'runs'
    dump(arm_dir / 'manifest.json', dict(arm=arm, keys_fp=J.keys_fp(questions), limit=0,
                                       llm_calls=client.calls, failures=len(errors), model=MODEL))
    _, doc_norms, decoys = J._corpus_index()
    readings = {split: J.judge_arm(arm, ks, doc_norms, decoys) for split, ks in (
        ('all', questions), ('test', [k for k in questions if k['doc_id'] not in CB.DEV]),
        ('dev', [k for k in questions if k['doc_id'] in CB.DEV]))}
    usage = Counter()
    for p in cached_dir.glob('*.json'):
        for name, value in (read(p)['response'].get('usage') or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[name] += value
    output = dict(model=MODEL, arm=arm, readings=readings, failures=len(errors),
                  actual_http_attempts=client.calls, successful_unique_cached_responses=len(list(cached_dir.glob('*.json'))),
                  usage_successful_responses_only=dict(usage), per_key_attempts=client.report(),
                  elapsed_seconds=round(time.perf_counter() - started, 1),
                  calibration='No keyed control arms; no claim of passing the full calibration gate')
    dump(args.out / 'keyed_readings.json', output)
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
