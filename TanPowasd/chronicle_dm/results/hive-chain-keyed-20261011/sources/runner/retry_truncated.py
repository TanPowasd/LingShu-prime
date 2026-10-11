"""Repair token-truncated / failed transport questions, preserving initial readings.

Each phase reuses exact request caches, then increases its limit to 16000/32000
only if the provider explicitly returned finish_reason=length.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import threading
import time

from run_keyed import dump, read


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--bench', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.repo, args.bench, args.out = [p.resolve() for p in (args.repo, args.bench, args.out)]
    initial_dir = args.out / 'initial_8000'
    initial_dir.mkdir(exist_ok=True)
    for name in ('keyed_readings.json', 'errors.json', 'metadata.json', 'progress.json'):
        if not (initial_dir / name).exists():
            shutil.copy2(args.out / name, initial_dir / name)
    initial, original_errors = read(initial_dir / 'keyed_readings.json'), read(initial_dir / 'errors.json')
    truncated = {e['qid'] for e in original_errors if e.get('message') == 'Model output reached token limit'}
    transport = {e['qid'] for e in original_errors if e['stage'] in ('reader', 'extraction')
                 and e.get('message', '').startswith(('chat failed:', 'Timed out waiting', 'No usable keys:'))}
    todo = truncated | transport
    src = args.repo / 'TanPowasd/discriminative_memory/nl_eval'
    sys.path.insert(0, str(src))
    import chain_bench as CB
    import chain_llm as CL
    import chain_reader_on_memory as CR
    from cline_pool import ClinePool, MODEL
    client = ClinePool()
    started = time.perf_counter()
    questions, corpus = read(args.out / 'data/keys.json'), read(args.out / 'data/corpus.json')
    tasks = [{name: k[name] for name in ('qid', 'question', 'doc')} for k in questions if k['qid'] in todo]
    by_cid, n_seq = {c['cid']: c for c in corpus}, {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    sysmsg = CL.load_official(args.bench)
    arm_dir = args.out / 'runs' / f"chain_{initial['arm']}"
    cache_dir = args.out / 'responses/by_prompt'
    locks, locks_guard, counters, counters_guard = {}, threading.Lock(), Counter(), threading.Lock()
    print(json.dumps({'repair_questions': len(tasks), 'truncated': len(truncated), 'transport': len(transport),
                      'token_limits': [8000, 16000, 32000],
                      'workers': client.workers, 'model': MODEL}), flush=True)
    runner_dir = args.out / 'sources/runner'
    runner_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__), runner_dir / Path(__file__).name)

    def request(messages, phase, qid):
        for limit in (8000, 16000, 32000):
            payload = dict(model=MODEL, messages=messages, temperature=0, max_tokens=limit)
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            with locks_guard:
                lock = locks.setdefault(digest, threading.Lock())
            with lock:
                path = cache_dir / f'{digest}.json'
                cached = path.exists()
                if cached:
                    result = read(path)
                    if result['request_sha256'] != digest:
                        raise RuntimeError('Cache fingerprint mismatch')
                else:
                    t0 = time.perf_counter()
                    result = dict(request_sha256=digest,
                                  response=client.complete(messages, max_tokens=limit),
                                  latency_seconds=round(time.perf_counter() - t0, 3),
                                  saved_at=datetime.now(timezone.utc).isoformat())
                    dump(path, result)
                with counters_guard:
                    counters['cached_responses' if cached else 'new_responses'] += 1
                if result['response']['choices'][0].get('finish_reason') == 'length':
                    print(json.dumps({'truncated': qid, 'phase': phase, 'limit': limit}), flush=True)
                    continue
                dump(args.out / 'responses' / phase / f'{qid}.json',
                     dict(**result, cache_hit=cached, phase=phase, max_tokens=limit, repair=True))
                return result['response']['choices'][0]['message']['content']
        raise RuntimeError('Model output reached token limit after escalation')

    def one(q):
        stage = 'extraction'
        try:
            mat = read(args.out / 'runs/chain_rrf3v11/retrieval' / f"{q['qid']}.json")['material']
            _, _, ent, fac = CB.parse_q(q['question'], n_seq[q['doc']])
            raw = request(CL.build_extract_prompt(ent, fac, mat), stage, q['qid'])
            match = re.search(r'\[.*\]', raw, re.S)
            if not match or not isinstance(json.loads(match.group()), list):
                raise ValueError('Invalid extraction array')
            events = CL.parse_events(raw)
            dump(args.out / 'runs/chain_llm_dm_v11/events' / f"{q['qid']}.json", events)
            (args.out / 'llm_raw/llm_dm_v11' / f"{q['qid']}.txt").write_text(raw, encoding='utf-8')
            stage = 'memory'
            material = CR.material_for('llm_chronicle_dm_reader', events, q, n_seq[q['doc']], by_cid)
            dump(arm_dir / 'retrieval' / f"{q['qid']}.json", {'qid': q['qid'], 'material': material})
            stage = 'reader'
            messages = CL.build_prompt(sysmsg, q['qid'], q['question'], material)
            dump(args.out / 'prompts/reader' / f"{q['qid']}.json", messages)
            raw = request(messages, stage, q['qid'])
            json.loads(re.search(r'\{.*\}', raw, re.S).group())
            dump(arm_dir / 'sut/out' / f"{q['qid']}.json", CL.parse_answer(raw, q['qid']))
            return q['qid'], None
        except Exception as exc:
            return q['qid'], dict(qid=q['qid'], stage=stage, error_type=type(exc).__name__,
                                  message=str(exc)[:160] if isinstance(exc, RuntimeError) else 'Invalid stage output')

    errors = [e for e in original_errors if e['qid'] not in todo]
    repaired = 0
    with ThreadPoolExecutor(client.workers) as ex:
        futures = [ex.submit(one, q) for q in tasks]
        for done, f in enumerate(as_completed(futures), 1):
            qid, error = f.result()
            if error:
                errors.append(error)
            else:
                repaired += 1
            state = dict(completed=done, total=len(tasks), repaired=repaired, failed=len(errors),
                         repair_http_attempts=client.calls, per_key_attempts=client.report(),
                         elapsed_seconds=round(time.perf_counter() - started, 1), **dict(counters))
            dump(args.out / 'repair_progress.json', state)
            print(json.dumps(state), flush=True)

    sys.path.insert(0, str(args.bench / 'chain/tools'))
    import probe_judge as J
    J.OUT, J.RUNS = args.out / 'data', args.out / 'runs'
    _, doc_norms, decoys = J._corpus_index()
    readings = {split: J.judge_arm(initial['arm'], ks, doc_norms, decoys) for split, ks in (
        ('all', questions), ('test', [k for k in questions if k['doc_id'] not in CB.DEV]),
        ('dev', [k for k in questions if k['doc_id'] in CB.DEV]))}
    usage = Counter()
    for p in cache_dir.glob('*.json'):
        for name, value in (read(p)['response'].get('usage') or {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                usage[name] += value
    attempts = initial['actual_http_attempts'] + client.calls
    output = dict(initial, readings=readings, failures=len(errors), actual_http_attempts=attempts,
                  successful_unique_cached_responses=len(list(cache_dir.glob('*.json'))),
                  usage_successful_responses_only=dict(usage),
                  per_key_attempts=dict(Counter(initial['per_key_attempts']) + Counter(client.report())),
                  elapsed_seconds=round(initial['elapsed_seconds'] + time.perf_counter() - started, 1),
                  truncation_repair=dict(questions=len(tasks), repaired=repaired, http_attempts=client.calls,
                                         truncated_questions=len(truncated), transport_questions=len(transport),
                                         max_tokens_schedule=[8000, 16000, 32000]))
    dump(args.out / 'keyed_readings.json', output)
    dump(args.out / 'errors.json', errors)
    dump(arm_dir / 'manifest.json', dict(arm=initial['arm'], keys_fp=J.keys_fp(questions), limit=0,
                                       llm_calls=attempts, failures=len(errors), model=MODEL))
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
