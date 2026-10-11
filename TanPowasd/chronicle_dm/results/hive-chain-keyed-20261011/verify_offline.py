"""Verify the published result bundle without credentials or network access."""
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parent
NETWORK_ATTEMPTS = 0


def deny_network(*args, **kwargs):
    global NETWORK_ATTEMPTS
    NETWORK_ATTEMPTS += 1
    raise RuntimeError('Network access is forbidden during offline verification')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify():
    socket.socket = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    result, audit, metadata = [read(ROOT / n) for n in ('keyed_readings.json', 'audit.json', 'metadata.json')]
    manifest = read(ROOT / 'publication_manifest.json')
    exclusions = {'publication_manifest.json', 'verification.json'}
    actual_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
                    if p.is_file() and p.relative_to(ROOT).as_posix() not in exclusions}
    require(actual_files == set(manifest['files_sha256']), 'Published file inventory differs from manifest')
    for rel, expected in manifest['files_sha256'].items():
        path = (ROOT / rel).resolve()
        require(path.is_relative_to(ROOT), 'Manifest path escapes result directory')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'File hash mismatch: {rel}')
    for rel, expected in metadata['source_sha256'].items():
        path = (ROOT / 'sources' / rel.replace('\\', '/')).resolve()
        require(path.is_relative_to(ROOT / 'sources'), 'Source path escapes snapshot directory')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Source snapshot differs: {rel}')

    judge_path = ROOT / 'sources/benchmark/probe_judge.py'
    spec = importlib.util.spec_from_file_location('frozen_probe_judge', judge_path)
    judge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(judge)
    judge.OUT, judge.RUNS = ROOT / 'data', ROOT / 'runs'
    questions, norms, decoys = judge._corpus_index()
    require(len(questions) == 642, 'Expected 642 benchmark questions')
    arm = result['arm']
    arm_root = judge.RUNS / f'chain_{arm}'
    qids = {q['qid'] for q in questions}
    for directory in (arm_root / 'sut/out', arm_root / 'retrieval', ROOT / 'extractions'):
        require({p.stem for p in directory.glob('*.json')} == qids, f'Missing or unexpected question files: {directory.name}')
    saved_manifest = read(arm_root / 'manifest.json')
    require(saved_manifest['keys_fp'] == judge.keys_fp(questions), 'Answer-key fingerprint mismatch')
    require(saved_manifest['limit'] == 0, 'Result was generated with a question limit')
    splits = {'all': questions,
              'test': [q for q in questions if q['doc_id'] not in {'A1', 'B1'}],
              'dev': [q for q in questions if q['doc_id'] in {'A1', 'B1'}]}
    for split, qs in splits.items():
        actual = judge.judge_arm(arm, qs, norms, decoys)
        require(actual == result['readings'][split], f'Final {split} score differs from frozen judge')
    require(result['readings']['all']['n'] == 625 and result['readings']['test']['n'] == 419,
            'Scoring denominator differs')
    require(result['failures'] == 0 and read(ROOT / 'errors.json') == [], 'Final run has failed questions')

    # The initial successful answers were cached unchanged. Its failed jobs were
    # placeholders; reconstruct only those placeholders from the saved error log.
    initial = read(ROOT / 'initial_8000/keyed_readings.json')
    initial_errors = read(ROOT / 'initial_8000/errors.json')
    initial_failed = {e['qid']: e['stage'] for e in initial_errors}
    real_answer = judge._ans_of
    def initial_answer(arm_name, qid):
        if qid in initial_failed:
            return dict(qid=qid, value=None, state=None, at_seq=None, chain=[], basis=[],
                        confidence='unknown', _json_ok=False, _run_failure=initial_failed[qid])
        return real_answer(arm_name, qid)
    judge._ans_of = initial_answer
    try:
        for split, qs in splits.items():
            require(judge.judge_arm(arm, qs, norms, decoys) == initial['readings'][split],
                    f'Initial {split} score differs from saved answers and failure log')
    finally:
        judge._ans_of = real_answer

    corpus_ids = {c['cid'] for c in read(ROOT / 'data/corpus.json')}
    raw_hits, raw_total = 0, 0
    examples = read(ROOT / 'failure_examples.json')
    verified_examples = set()
    history_errors, history_format_errors, state_errors = 0, 0, 0
    for q in splits['test']:
        if q['reconstructible']:
            continue
        raw_total += 1
        answer = real_answer(arm, q['qid'])
        require(not answer.get('_run_failure'), 'Unexpected final placeholder answer')
        mats = read(arm_root / 'retrieval' / f"{q['qid']}.json")['material']
        raw = {m['cid']: m['text'] for m in mats if m.get('cid') in corpus_ids}
        hit = False
        for b in answer.get('basis') or []:
            if not isinstance(b, dict) or not isinstance(b.get('quote'), str):
                continue
            cid, quote = b.get('file'), judge.norm(b['quote'])
            try:
                same = cid in raw and int(cid.rsplit('#', 1)[1]) == int(b.get('line'))
            except (TypeError, ValueError, AttributeError):
                same = False
            if same and len(quote) >= 8 and quote in judge.norm(raw[cid]):
                hit = True
        raw_hits += hit
        bad_history = q['type'] == '历史' and q['answer']['value'] is not None and not judge.value_correct(answer, q)
        bad_state = q['type'] == '状态归属' and not judge.eq(answer.get('state'), q['answer']['state'])
        if bad_history:
            history_errors += 1
            history_format_errors += q['answer']['state'] == answer.get('state') == 'unresolved'
        state_errors += bad_state
        if bad_history or bad_state:
            verified_examples.add(q['qid'])
    require(raw_total == 419 and raw_hits == audit['raw_source_citation']['hits'], 'Raw-source citation score differs')
    require(round(raw_hits / raw_total, 4) == audit['raw_source_citation']['rate'], 'Raw-source citation rate differs')
    require({e['qid'] for e in examples} == verified_examples, 'Failure-example inventory differs')
    require(history_errors == 11 and history_format_errors == 10 and state_errors == 2, 'Error diagnostics differ')

    index = read(ROOT / 'response_index.json')
    require(len(index) == result['successful_unique_cached_responses'], 'Response count differs')
    require(len({r['request_sha256'] for r in index}) == len(index), 'Duplicate response-cache fingerprints')
    models, finishes, usage = Counter(), Counter(), Counter()
    for response in index:
        models[response['model']] += 1
        finishes[response['finish_reason']] += 1
        for key, val in (response.get('usage') or {}).items():
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                usage[key] += val
        usage['reasoning_tokens'] += ((response.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens', 0)
    require(dict(models) == audit['provider_models'], 'Provider route counts differ')
    require(dict(finishes) == audit['provider_finish_reasons'], 'Finish-reason counts differ')
    require(set(usage) == set(audit['usage_saved_responses_only']), 'Usage fields differ')
    for key, val in usage.items():
        require(math.isclose(val, audit['usage_saved_responses_only'][key], rel_tol=1e-12, abs_tol=1e-9),
                f'Usage total differs: {key}')
    require(NETWORK_ATTEMPTS == 0, 'Verifier attempted network access')
    verification = dict(verified=True, questions=642, scored_all=625, scored_test=419,
                        final_and_initial_scores_recomputed=True, raw_source_citation_hits=raw_hits,
                        source_snapshots_verified=len(metadata['source_sha256']),
                        artifact_files_verified=len(actual_files), response_records_verified=len(index),
                        network_attempts=NETWORK_ATTEMPTS, model_calls=0)
    (ROOT / 'verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == '__main__':
    verify()
