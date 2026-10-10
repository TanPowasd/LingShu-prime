"""Offline publication checks; historical experiments are preserved, not rerun."""
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / 'results/original-20261010'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    for key in tuple(os.environ):
        if key.endswith('API_KEY') or key.startswith('LINGSHU_NG_'):
            os.environ.pop(key)
    attempts = []

    def deny(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError('All publication verification is offline')

    stream = io.StringIO()
    with patch.object(socket.socket, 'connect', deny), \
         patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket, 'create_connection', deny):
        suite = unittest.TestLoader().discover(str(ROOT), pattern='test_*.py', top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
        assert result.wasSuccessful(), stream.getvalue()
        assert result.testsRun == 48
        manifest = read(ROOT / 'publication_manifest.json')
        packaged = {path: digest(ROOT / path) == value for path, value in manifest['packaged_sha256'].items()}
        assert all(packaged.values()), packaged
        references = {
            path: hashlib.sha256((ROOT / path).read_text(encoding='utf-8').encode('utf-8')).hexdigest() == value
            for path, value in manifest['reference_sha256_lf'].items()
        }
        assert all(references.values()), references
        readings = read(ARCHIVE / 'readings.json')
        originals = {
            PureWindowsPath(path).name: digest(ARCHIVE / 'frozen_sources' / PureWindowsPath(path).name) == value
            for path, value in readings['metadata']['frozen_hashes'].items()
        }
        assert all(originals.values()), originals
        historical = read(ARCHIVE / 'verification.json')
        assert historical['tests_run'] == 177 and historical['failures'] == historical['errors'] == 0
        assert readings['metadata']['model_calls'] == readings['metadata']['network_attempts'] == 0
        assert readings['temporal']['correct'] == readings['temporal']['queries'] == 800
        assert readings['temporal']['entities'] == 24 and readings['temporal']['slots'] == 72
        assert readings['packing']['schema_renaming_checks'] == 60
        assert readings['packing']['duplicate_case_checks'] == 150
        assert readings['hive_raw_smoke']['confirmed_claims_inferred'] == 0
        for row in readings['packing']['details']:
            assert row['budget_used'] <= row['budget'] and 0 <= row['coverage'] <= 1

        from bench_discriminative import make_case, PARAMETERS, ARMS
        from discriminative_memory import solve, coverage, cost
        assert read(ROOT / 'parameters.json') == readings['metadata']['parameters'] == PARAMETERS
        assert digest(ROOT / 'temporal_facts.py') == digest(ARCHIVE / 'frozen_sources/temporal_facts.py')
        old_core = (ARCHIVE / 'frozen_sources/discriminative_memory.py').read_text(encoding='utf-8')
        relocated_core = (ROOT / 'discriminative_memory.py').read_text(encoding='utf-8')
        relocated_core = relocated_core.replace(
            'if __package__:\n    from .temporal_facts import TemporalFacts, UNSET\nelse:\n    from temporal_facts import TemporalFacts, UNSET',
            "sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'guarded-agm-20261010'))\nfrom temporal_facts import TemporalFacts, UNSET")
        relocated_core = relocated_core.replace(
            "bench=Path(__file__).resolve().parent.parent/'agm/bench'",
            "bench=Path(__file__).resolve().parent.parent.parent/'LingShu-prime/TanPowasd/agm/bench'")
        assert relocated_core == old_core, 'Core changes must be limited to portable module lookup'
        recorded = {(r['case'], r['arm'], r['budget']): r for r in readings['packing']['details']}
        contexts = 0
        for index in (0, 37, 91, 149):
            memory, problem, expected, _ = make_case(index)
            try:
                for budget in PARAMETERS['budgets']:
                    for arm, (strategy, improve) in ARMS.items():
                        value = solve(problem, budget, strategy=strategy, improve=improve)
                        selected = frozenset(value['selected'])
                        assert value['budget_used'] == cost(problem, selected) == len(value['context']) <= budget
                        assert set(value['covered']) == set(coverage(problem, selected))
                        assert all(value['answers'][name]['value'] == expected[name] for name in value['covered'])
                        old = recorded[index, arm, budget]
                        assert value['selected'] == old['selected'], (index, arm, budget)
                        assert value['budget_used'] == old['budget_used'], (index, arm, budget)
                        assert abs(value['weighted_coverage'] - old['coverage']) < 1e-12
                        contexts += 1
            finally:
                memory.close()
        assert not attempts

    report = {
        'tests_run': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'network_attempts': len(attempts), 'model_calls': 0,
        'packaged_hashes_match': packaged,
        'reference_hashes_match_after_lf_normalization': references,
        'historical_frozen_hashes_match': originals,
        'historical_test_count_not_rerun': historical['tests_run'],
        'independently_rebuilt_contexts': contexts,
        'sampled_contexts_match_historical_results': True,
        'core_diff_is_only_module_lookup': True,
        'note': '48 bundled tests and targeted artifact checks only; no new full benchmark or natural-language memory score.',
    }
    (ROOT / 'publication_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(stream.getvalue().strip())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if os.environ.get('PYTHONHASHSEED') != '0':
        raise SystemExit(subprocess.call([sys.executable, '-B', '-X', 'utf8', __file__],
                                         env={**os.environ, 'PYTHONHASHSEED': '0'}))
    main()
