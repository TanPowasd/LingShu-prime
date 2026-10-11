"""Offline tests only: dummy keys, simulated HTTP, no model calls."""
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.error

import cline_pool as P


def response(content='ok', wrapped=False):
    data = {'model': P.MODEL, 'choices': [{'message': {'content': content},
                                        'finish_reason': 'stop'}], 'usage': {'total_tokens': 1}}
    return {'data': data} if wrapped else data


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        self.enterContext(patch.object(P, 'LOCAL_CONFIG', self.root / 'local.json'))
        self.enterContext(patch('socket.socket', side_effect=AssertionError('Network forbidden in tests')))

    def write_keys(self, data, name='keys.json'):
        p = self.root / name
        p.write_text(json.dumps(data), encoding='utf-8-sig')
        return p

    def pool(self, n=2, **kwargs):
        return P.ClinePool(keys=[('ignored', f'fake-key-{i}') for i in range(n)], log=lambda _: None, **kwargs)

    def test_json_export_deduplicates_and_ignores_metadata(self):
        p = self.write_keys({'keys': [{'api_key': 'fake-key-a', 'email': 'private@example.com'},
                                     {'api_key': 'fake-key-b'}, {'api_key': 'fake-key-a'}],
                             'model_used_in_memory_bench': 'ignored-model',
                             'base_url': 'https://ignored.invalid'})
        with patch.object(P, '_req') as req:
            m = P.ClinePool(keys_file=p)
        req.assert_not_called()
        self.assertEqual(m.workers, 2)
        self.assertEqual(m.model, P.MODEL)
        self.assertEqual(m.report(), {'key1': 0, 'key2': 0})

    def test_file_precedence_and_numbered_environment(self):
        first = self.write_keys(['fake-key-a'])
        second = self.write_keys(['fake-key-b', 'fake-key-c'], 'second.json')
        P.LOCAL_CONFIG.write_text(json.dumps({'keys_file': str(first)}), encoding='utf-8')
        self.assertEqual(P.ClinePool().workers, 1)
        with patch.dict(os.environ, {'CLINE_KEYS_FILE': str(second), 'CLINE_KEY_12': 'fake-env-key'}):
            self.assertEqual(P.ClinePool().workers, 2)
            self.assertEqual(P.ClinePool(keys_file=first).workers, 1)
        P.LOCAL_CONFIG.unlink()
        with patch.dict(os.environ, {'CLINE_KEY_12': 'fake-key-b', 'CLINE_KEY_1': 'fake-key-a'}):
            self.assertEqual(P._load_keys(), [('key1', 'fake-key-a'), ('key2', 'fake-key-b')])

    def test_text_file_supported(self):
        p = self.root / 'keys.txt'
        p.write_text('# comment\nlabel=fake-key-a\nfake-key-b\nother=fake-key-a\n', encoding='utf-8')
        self.assertEqual(P.ClinePool(keys_file=p).workers, 2)

    def test_missing_empty_and_malformed_files_fail_without_network(self):
        for file in [self.root / 'missing.json', self.write_keys([]),
                     self.write_keys({'keys': [{'api_key': None}]}, 'invalid.json')]:
            with self.subTest(file=file.name), self.assertRaises(ValueError):
                P.ClinePool(keys_file=file)
        with self.assertRaises(ValueError):
            P.ClinePool()

    def test_only_fixed_model_can_be_constructed_or_sent(self):
        with self.assertRaises(ValueError):
            self.pool(model='other-model')
        m = self.pool()
        with self.assertRaises(AttributeError):
            m.model = 'other-model'
        with patch.object(P, '_req', return_value=response(wrapped=True)) as req:
            self.assertEqual(m.chat([{'role': 'user', 'content': 'test'}]), 'ok')
        self.assertEqual(json.loads(req.call_args.args[2])['model'], P.MODEL)
        self.assertEqual(req.call_args.args[0], P.API)

    def test_worker_limit(self):
        m = self.pool(4)
        self.assertEqual([m.worker_count(n) for n in (0, 1, 4, 8)], [4, 1, 4, 4])
        with self.assertRaises(ValueError):
            m.worker_count(-1)

    def test_four_keys_are_parallel_but_each_key_is_serial(self):
        m = self.pool(4)
        gate = threading.Barrier(4, timeout=5)
        lock = threading.Lock()
        active, maxima, totals, payloads = {}, {}, [], []

        def req(url, key, body, timeout):
            with lock:
                active[key] = active.get(key, 0) + 1
                maxima[key] = max(maxima.get(key, 0), active[key])
                totals.append(sum(active.values()))
                payloads.append(json.loads(body))
            try:
                gate.wait()
                return response()
            finally:
                with lock:
                    active[key] -= 1

        with patch.object(P, '_req', side_effect=req), ThreadPoolExecutor(8) as ex:
            futures = [ex.submit(m.complete, [], tries=1, timeout=10) for _ in range(8)]
            self.assertEqual(len([f.result(timeout=15) for f in futures]), 8)
        self.assertEqual(max(totals), 4)
        self.assertEqual(set(maxima.values()), {1})
        self.assertEqual(set(p['model'] for p in payloads), {P.MODEL})
        self.assertEqual(sum(m.report().values()), 8)

    def test_rate_limit_cools_one_key_and_fails_over(self):
        m = self.pool()
        seen = []

        def req(url, key, body, timeout):
            seen.append(key)
            if key == 'fake-key-0':
                raise urllib.error.HTTPError(url, 429, 'private error', {'Retry-After': '60'}, io.BytesIO())
            return response()

        with patch.object(P, '_req', side_effect=req):
            self.assertEqual(m.chat([]), 'ok')
        self.assertEqual(seen, ['fake-key-0', 'fake-key-1'])
        self.assertGreater(m.slots[0].cool_until, P.time.time() + 50)
        self.assertEqual(m.calls, 2)

    def test_rejected_key_fails_over_and_exhaustion_fails_promptly(self):
        for status in (401, 403, 402):
            with self.subTest(status=status):
                m = self.pool()
                def req(url, key, body, timeout):
                    if key == 'fake-key-0':
                        raise urllib.error.HTTPError(url, status, 'ignored', {}, io.BytesIO())
                    return response()
                with patch.object(P, '_req', side_effect=req):
                    self.assertEqual(m.chat([]), 'ok')
                self.assertFalse(m.slots[0].has_quota)
        m = self.pool(1)
        with patch.object(P, '_req', side_effect=urllib.error.HTTPError(P.API, 402, '', {}, io.BytesIO())):
            with self.assertRaisesRegex(RuntimeError, 'No usable keys'):
                m.chat([])

    def test_errors_and_reports_do_not_disclose_keys(self):
        logs = []
        m = P.ClinePool(keys=[('private@example.com', 'fake-private-key')], log=logs.append)
        err = urllib.error.HTTPError(P.API, 401, 'fake-private-key', {}, io.BytesIO(b'fake-private-key'))
        with patch.object(P, '_req', side_effect=err), self.assertRaises(RuntimeError) as ctx:
            m.chat([])
        output = str(ctx.exception) + json.dumps(logs) + json.dumps(m.report())
        self.assertNotIn('fake-private-key', output)
        self.assertNotIn('private@example.com', output)

    def test_reader_uses_pool_and_main_track_preserves_response_options(self):
        from chain_llm import LLM
        from chain_reader_on_memory import LLM as reader_llm
        self.assertIs(LLM, P.ClinePool)
        self.assertIs(reader_llm, P.ClinePool)
        bench = Path(__file__).resolve().parents[2] / 'agm' / 'bench'
        with patch.object(sys, 'path', [str(bench), *sys.path]):
            ns = runpy.run_path(str(bench / 'hive_llm.py'))
        args = SimpleNamespace(base=P.BASE, model=P.MODEL, max_tokens=256,
                               keys_file=self.write_keys(['fake-key-a', 'fake-key-b']))
        client = ns['Client'](args)
        with patch.object(P, '_req', return_value=response('{"ok": true}', wrapped=True)) as req:
            result = client.call([], 0.5, lambda x: None, self.root / 'answer.json')
        payload = json.loads(req.call_args.args[2])
        self.assertEqual(payload['model'], P.MODEL)
        self.assertEqual(payload['temperature'], 0.5)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(result['parsed'], {'ok': True})
        self.assertEqual(client.pool.workers, 2)
        with patch.object(P, '_req') as req:
            client.call([], 0.5, lambda x: None, self.root / 'answer.json')
        req.assert_not_called()


if __name__ == '__main__':
    unittest.main()
