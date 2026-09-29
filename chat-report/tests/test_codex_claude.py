"""Synthetic accounting fixtures: never read a real user's conversation files."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reportkit.adapters import claude, codex
from reportkit.common import validate_collection

SID = '11111111-2222-3333-4444-555555555555'
T0 = '2026-09-29T10:00:00Z'
T1 = '2026-09-29T10:00:10Z'
T2 = '2026-09-29T10:00:20Z'
T3 = '2026-09-29T10:00:30Z'


def codex_header(**extra):
    return {'timestamp': T0, 'type': 'session_meta', 'payload': {'id': SID, 'timestamp': T0, **extra}}


def codex_event(kind, timestamp=T1, **extra):
    return {'timestamp': timestamp, 'type': 'event_msg', 'payload': {'type': kind, **extra}}


def codex_usage(inp, cached, out, timestamp=T1, **extra):
    usage = dict(input_tokens=inp, cached_input_tokens=cached, output_tokens=out,
                 reasoning_output_tokens=out//2, total_tokens=inp+out, **extra)
    return codex_event('token_count', timestamp, info={'total_token_usage': usage, 'last_token_usage': usage})


def assistant(mid='msg_1', req='req_1', timestamp=T1, **usage):
    return {'type': 'assistant', 'sessionId': SID, 'requestId': req, 'timestamp': timestamp,
            'uuid': 'uuid_' + mid, 'message': {'id': mid, 'model': 'claude-example',
            'content': [{'type': 'text', 'text': 'PRIVATE_PROMPT_SENTINEL'}],
            'usage': dict(input_tokens=30, output_tokens=1, cache_read_input_tokens=50,
                          cache_creation_input_tokens=20, **usage)}}


def model_result(uuid, inp=30, out=12, timestamp=T2):
    return {'type': 'result', 'session_id': SID, 'uuid': uuid, 'timestamp': timestamp,
            'modelUsage': {'claude-example': {'inputTokens': inp, 'cacheReadInputTokens': 50,
                          'cacheCreationInputTokens': 20, 'outputTokens': out}},
            'total_cost_usd': 0.002, 'duration_ms': 10000}


class NativeCollectors(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, rows, name='session.jsonl'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        return path

    def checked(self, module, rows, cutoff=None):
        path = self.write(rows)
        before = path.read_bytes()
        result = module.collect(path, SID, cutoff)
        self.assertEqual(path.read_bytes(), before)
        validate_collection(result)
        self.assertNotIn('PRIVATE_PROMPT_SENTINEL', json.dumps(result))
        return result

    def test_roots_honor_custom_configs(self):
        for os_name in ('Windows', 'Darwin', 'Linux'):
            self.assertEqual(codex.roots(self.root, {}, os_name)[0], self.root / '.codex/sessions')
            self.assertEqual(claude.roots(self.root, {}, os_name), [self.root / '.claude/projects'])
        self.assertEqual(codex.roots(self.root, {'CODEX_HOME': str(self.root/'custom')}, 'Linux')[0], self.root/'custom/sessions')
        self.assertEqual(claude.roots(self.root, {'CLAUDE_CONFIG_DIR': str(self.root/'custom')}, 'Linux')[0], self.root/'custom/projects')

    def test_codex_cumulative_duplicates_and_reasoning(self):
        rows = [codex_header(), {'timestamp': T0, 'type': 'turn_context', 'payload': {'model': 'gpt-example'}},
                codex_event('task_started', T0, turn_id='t1'), codex_usage(100, 30, 20),
                codex_usage(100, 30, 20), codex_usage(160, 40, 30, T2),
                codex_event('task_complete', T3, turn_id='t1'),
                codex_event('task_complete', T3, turn_id='t1')]
        r = self.checked(codex, rows)
        self.assertEqual(r['tokens']['total'], 190)
        self.assertEqual(r['tokens']['input_uncached'], 120)
        self.assertEqual(r['tokens']['output'], 30)
        self.assertEqual(len(r['intervals']), 1)
        self.assertEqual(r['time_basis'], 'gross_turn')
        self.assertEqual(len(r['model_usage']), 1)

    def test_codex_decrease_is_not_summed(self):
        r = self.checked(codex, [codex_header(), codex_usage(100, 10, 20), codex_usage(20, 5, 4, T2)])
        self.assertEqual(r['tokens']['total'], 24)
        self.assertIn('cumulative_reset', [d['code'] for d in r['diagnostics']])

    def test_codex_fork_rejects_inherited_accounting(self):
        r = self.checked(codex, [codex_header(forked_from_id='parent'), codex_usage(100, 10, 20)])
        self.assertIsNone(r['tokens']['total'])
        self.assertIn('inherited_history_unsupported', [d['code'] for d in r['diagnostics']])

    def test_codex_capacity_not_usage_and_unknown_write_ttl(self):
        raw = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0, 'total_tokens': 200000}
        r = self.checked(codex, [codex_header(), codex_usage(100, 10, 20, cache_write_input_tokens=5),
                                codex_event('token_count', T2, info={'total_token_usage': raw})])
        self.assertEqual(r['tokens']['total'], 120)
        self.assertIsNone(r['tokens']['input_uncached'])
        self.assertIsNone(r['tokens']['cache_write_short'])

    def test_cutoff_preserves_selected_snapshot_and_open_turn(self):
        r = self.checked(codex, [codex_header(), codex_event('task_started', T0, turn_id='t'),
                                codex_usage(100, 10, 20), codex_usage(300, 10, 40, T3),
                                codex_event('task_complete', T3, turn_id='t')], T2)
        self.assertEqual(r['tokens']['total'], 120)
        self.assertEqual(r['intervals'], [])

    def test_identity_mismatch_fails(self):
        for module, rows in ((codex, [codex_header(id='other')]),
                             (claude, [{'type':'user','sessionId':'other','timestamp':T0}])):
            with self.assertRaises(ValueError):
                module.collect(self.write(rows), SID)

    def test_native_total_only_is_preserved_and_pre_session_cutoff_is_empty(self):
        rows = [codex_header(), codex_event('token_count', info={'total_token_usage': {'total_tokens': 123}})]
        r = self.checked(codex, rows)
        self.assertEqual(r['tokens']['total'], 123)
        self.assertIsNone(r['tokens']['input_uncached'])
        r = self.checked(codex, rows, '2026-09-29T09:59:59Z')
        self.assertIsNone(r['started_at'])
        self.assertIsNone(r['tokens']['total'])

    def test_claude_assistant_dedup_and_cache_split(self):
        row = assistant(cache_creation={'ephemeral_5m_input_tokens': 12, 'ephemeral_1h_input_tokens': 8})
        r = self.checked(claude, [row, row, {**row, 'uuid': 'another'}])
        self.assertEqual(r['tokens']['input_uncached'], 30)
        self.assertEqual(r['tokens']['cache_read'], 50)
        self.assertEqual(r['tokens']['cache_write_short'], 12)
        self.assertEqual(r['tokens']['cache_write_long'], 8)
        self.assertIsNone(r['tokens']['output'])
        self.assertIsNone(r['tokens']['total'])

    def test_claude_result_snapshots_are_not_summed(self):
        r = self.checked(claude, [assistant(), model_result('r1'), model_result('r1'),
                                  model_result('r2', inp=60, out=24, timestamp=T3)])
        self.assertEqual(r['tokens']['total'], 154)
        self.assertEqual(r['tokens']['output'], 24)
        self.assertEqual(r['billing'][0]['kind'], 'reference')
        self.assertEqual(r['billing'][0]['amount'], '0.002')
        self.assertIsNone(r['tokens']['cache_write_long'])
        self.assertEqual(len(r['intervals']), 2)

    def test_claude_per_turn_result_and_sidechain(self):
        def result(uid, out):
            return {'type':'result','session_id':SID,'uuid':uid,'timestamp':T2,
                    'usage': {'input_tokens': 10, 'cache_read_input_tokens':0,
                              'cache_creation_input_tokens':0,'output_tokens':out}}
        rows = [assistant(), {**assistant('msg_child','req_child'), 'isSidechain': True},
                result('r1', 5), result('r1', 5), result('r2', 6)]
        r = self.checked(claude, rows)
        self.assertEqual(r['tokens']['total'], 31)
        self.assertEqual(r['tokens']['output'], 11)

    def test_claude_zero_error_result_retains_observation(self):
        error = model_result('r2', inp=0, out=0)
        error['modelUsage']['claude-example'].update(cacheReadInputTokens=0, cacheCreationInputTokens=0)
        error.update(is_error=True, total_cost_usd=0)
        r = self.checked(claude, [model_result('r1'), error])
        self.assertEqual(r['tokens']['total'], 112)
        self.assertEqual(r['billing'][0]['amount'], '0.002')

    def test_discovery_validates_content_and_avoids_children(self):
        self.write([codex_header()], '2026/09/29/rollout.jsonl')
        self.write([{'type':'other','content':'PRIVATE_PROMPT_SENTINEL'}], 'ignored.jsonl')
        self.assertEqual(len(codex.sessions(self.root)), 1)
        self.write([assistant()], 'project/main.jsonl')
        self.write([assistant()], 'project/session/subagents/agent-child.jsonl')
        discovered = claude.sessions(self.root)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0]['session_id'], SID)

    def test_undated_sdk_snapshot_requires_strict_cutoff_to_exclude(self):
        row = model_result('r1')
        row.pop('timestamp')
        path = self.write([row])
        retained = claude.collect(path, SID, T3)
        self.assertEqual(retained['tokens']['total'], 112)
        self.assertIn('undated_snapshot', [d['code'] for d in retained['diagnostics']])
        excluded = claude.collect(path, SID, T3, strict_cutoff=True)
        self.assertIsNone(excluded['tokens']['total'])
        validate_collection(retained)
        validate_collection(excluded)

    def test_unknown_schema_missing_and_malformed_do_not_invent(self):
        r = codex.collect(self.root/'missing.jsonl', SID)
        self.assertFalse((self.root/'missing.jsonl').exists())
        self.assertIsNone(r['tokens']['total'])
        path = self.root/'bad.jsonl'
        path.write_text('{"type":NaN}\n')
        with self.assertRaises(ValueError):
            claude.collect(path, SID)
        row = {'type':'user','sessionId':SID,'timestamp':T0,'message':{'tokens':999}}
        self.assertIsNone(self.checked(claude,[row])['tokens']['total'])


if __name__ == '__main__':
    unittest.main()
