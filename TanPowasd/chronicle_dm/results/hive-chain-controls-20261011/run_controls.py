"""Official closed/version-blind reader controls for the saved ChronicleDM SUT.

Uses frozen prompts and judge, fresh control response caches, and no SUT answers
as generation inputs. The version-blind latest-state corpus is the official
control construction, not an extraction from historical answer keys.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import threading
import time


ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--keys-file', type=Path)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--retry-failed', action='store_true')
    args = ap.parse_args()
    src = ROOT / 'sources/TanPowasd/discriminative_memory/nl_eval'
    sys.path[:0] = [str(src), str(ROOT / 'sources/benchmark')]
    import chain_llm as CL
    import chain_bench as CB
    from cline_pool import ClinePool, MODEL
    namespace = dict(json=json, OUT=ROOT / 'data')
    # load_official expects <bench>/chain/tools; the frozen reader SYS is instead
    # obtained directly by AST, without importing the upstream external harness.
    runner_path = ROOT / 'sources/benchmark/probe_runner.py'
    tree = ast.parse(runner_path.read_text(encoding='utf-8'))
    namespace['CHAIN_SYS'] = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                                 and getattr(n.targets[0], 'id', '') == 'CHAIN_SYS')
    definitions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('versionblind_corpus', 'build_prompt', 'build_closed_prompt')]
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(runner_path), 'exec'), namespace)
    vb_corpus = namespace['versionblind_corpus']()
    dump(ROOT / 'versionblind_corpus.json', vb_corpus)
    questions = read(ROOT / 'data/keys.json')
    bm = CB.BM25(vb_corpus)
    tasks = []
    arms = ('llm_closed', 'llm_versionblind')
    for k in questions:
        # Gold answers remain available only to the judge below.
        q = {name: k[name] for name in ('qid', 'question')}
        blind = CB.cap_material(bm.top(q['question'], CB.CHAIN_K if k['type'] == '变更' else CB.K),
                                CB.CHAIN_CAP if k['type'] == '变更' else CB.CAP)
        for arm in arms:
            material = [] if arm == 'llm_closed' else blind
            messages = namespace['build_closed_prompt'](q['qid'], q['question']) if arm == 'llm_closed' else namespace['build_prompt'](q['qid'], q['question'], material)
            matching = CL.build_closed_prompt(q['qid'], q['question']) if arm == 'llm_closed' else CL.build_prompt(namespace['CHAIN_SYS'], q['qid'], q['question'], material)
            if messages != matching:
                raise RuntimeError('Frozen official and SUT-reader prompts differ')
            dump(ROOT / 'runs' / f'chain_{arm}' / 'retrieval' / f"{q['qid']}.json", dict(qid=q['qid'], material=material))
            dump(ROOT / 'prompts' / arm / f"{q['qid']}.json", messages)
            tasks.append((arm, q['qid'], messages))
    if args.retry_failed:
        failed = {(e['arm'], e['qid']) for e in read(ROOT / 'errors.json')}
        tasks = [task for task in tasks if task[:2] in failed]
    plan = dict(arms=arms, questions_per_arm=642, scored_all=625, scored_test=419,
                logical_reader_calls=len(tasks), model=MODEL, per_key_concurrency=4,
                token_limits=[8000, 16000, 32000], versionblind_protocol='official latest snapshot + BM25 + official LLM reader',
                closed_protocol='official closed-book prompt',
                sut='saved RRF3 v1.1 -> LLM extraction -> ChronicleDM -> official reader',
                sut_rerun=False, strict_internal_pipeline_ablation=False)
    dump(ROOT / 'plan.json', plan)
    print(json.dumps(plan, ensure_ascii=False), flush=True)
    if args.dry:
        return
    if args.keys_file is None:
        ap.error('--keys-file is required for live controls')
    pool = ClinePool(keys_file=args.keys_file, per_key_concurrency=4)
    plan['workers'] = pool.workers
    dump(ROOT / 'metadata.json', dict(**plan, started_at=datetime.now(timezone.utc).isoformat(),
                                    benchmark_commit=read(ROOT / 'sut_metadata.json')['bench_commit'],
                                    source_sha256={p.relative_to(ROOT / 'sources').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                                   for p in (ROOT / 'sources').rglob('*.py')}))
    started = time.perf_counter()
    guard, locks, counters = threading.Lock(), {}, Counter()

    def request(arm, qid, messages):
        for limit in (8000, 16000, 32000):
            payload = dict(model=MODEL, messages=messages, temperature=0, max_tokens=limit)
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            with guard:
                lock = locks.setdefault(digest, threading.Lock())
            with lock:
                path = ROOT / 'responses/by_prompt' / f'{digest}.json'
                cached = path.exists()
                if cached:
                    record = read(path)
                    if record['request_sha256'] != digest:
                        raise RuntimeError('Control-cache fingerprint mismatch')
                else:
                    t0 = time.perf_counter()
                    record = dict(request_sha256=digest, response=pool.complete(messages, max_tokens=limit),
                                  latency_seconds=round(time.perf_counter()-t0, 3), max_tokens=limit,
                                  saved_at=datetime.now(timezone.utc).isoformat())
                    dump(path, record)
                with guard:
                    counters['cache_hits' if cached else 'new_responses'] += 1
                if record['response']['choices'][0].get('finish_reason') == 'length':
                    continue
                dump(ROOT / 'responses' / arm / f'{qid}.json', dict(**record, cache_hit=cached))
                return record['response']['choices'][0]['message']['content']
        raise RuntimeError('Control output reached token limit after escalation')

    def one(task):
        arm, qid, messages = task
        try:
            raw = request(arm, qid, messages)
            match = re.search(r'\{.*\}', raw, re.S)
            if not match or not isinstance(json.loads(match.group()), dict):
                raise ValueError('Invalid JSON answer')
            answer = CL.parse_answer(raw, qid)
            dump(ROOT / 'runs' / f'chain_{arm}' / 'sut/out' / f'{qid}.json', answer)
            return None
        except Exception as exc:
            dump(ROOT / 'runs' / f'chain_{arm}' / 'sut/out' / f'{qid}.json',
                 dict(qid=qid, value=None, state=None, at_seq=None, chain=[], basis=[], confidence='unknown', _run_failure=True))
            return dict(arm=arm, qid=qid, type=type(exc).__name__,
                        message=str(exc)[:160] if isinstance(exc, RuntimeError) else 'Invalid control output')

    previous = read(ROOT / 'control_readings.json') if args.retry_failed else None
    errors = []
    with ThreadPoolExecutor(pool.workers) as executor:
        for done, future in enumerate(as_completed([executor.submit(one, t) for t in tasks]), 1):
            error = future.result()
            if error:
                errors.append(error)
                print(json.dumps({'failed':error}), flush=True)
            if done % 20 == 0 or done == len(tasks):
                state = dict(completed=done, total=len(tasks), failed=len(errors), model_http_attempts=pool.calls,
                             per_key_attempts=pool.report(), elapsed_seconds=round(time.perf_counter()-started, 1), **dict(counters))
                dump(ROOT / 'progress.json', state)
                print(json.dumps(state), flush=True)
    dump(ROOT / 'errors.json', errors)
    spec = importlib.util.spec_from_file_location('frozen_judge', ROOT / 'sources/benchmark/probe_judge.py')
    J = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(J)
    J.OUT, J.RUNS = ROOT / 'data', ROOT / 'runs'
    for arm in arms:
        dump(ROOT / 'runs' / f'chain_{arm}' / 'manifest.json',
             dict(arm=arm, keys_fp=J.keys_fp(questions), limit=0, model=MODEL))
    _, norms, decoys = J._corpus_index()
    sut = read(ROOT / 'sut_readings.json')['arm']
    readings = {arm:{split:J.judge_arm(arm, qs, norms, decoys) for split,qs in (
        ('all',questions),('test',[q for q in questions if q['doc_id'] not in CB.DEV]),
        ('dev',[q for q in questions if q['doc_id'] in CB.DEV]))} for arm in (*arms,sut)}
    require_sut = read(ROOT / 'sut_readings.json')['readings']
    if readings[sut] != require_sut:
        raise RuntimeError('Saved SUT scores changed during calibration')
    calibration = J.calibration([readings[a]['all'] for a in (*arms,sut)], sut_arm=sut,
                                control_arms=('llm_versionblind','llm_closed'))
    usage, routes = Counter(), Counter()
    for p in (ROOT / 'responses/by_prompt').glob('*.json'):
        response = read(p)['response']
        routes[response.get('model')] += 1
        for key,value in (response.get('usage') or {}).items():
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                usage[key] += value
    result = dict(readings=readings, calibration=calibration, failures=len(errors), model=MODEL,
                  model_http_attempts=pool.calls+(previous['model_http_attempts'] if previous else 0),
                  usage_saved_responses_only=dict(usage), provider_routes=dict(routes),
                  per_key_attempts=dict(Counter(pool.report())+Counter(previous['per_key_attempts'] if previous else {})))
    dump(ROOT / 'control_readings.json',result)
    print(json.dumps(result, ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
