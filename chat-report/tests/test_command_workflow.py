"""End-to-end command fixtures and manual timer state transitions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / 'scripts'))
from reportkit import tracking

SID = 'fixture-session'
T0 = '2020-01-01T10:00:00Z'
T1 = '2020-01-01T10:01:00Z'
T2 = '2020-01-01T10:02:00Z'
T3 = '2020-01-01T10:03:00Z'


class CommandWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='chat report ')
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source with spaces' / 'sessions' / 'rollout.jsonl'
        self.source.parent.mkdir(parents=True)
        rows = [
            {'timestamp': T0, 'type': 'session_meta', 'payload': {'id': SID, 'timestamp': T0}},
            {'timestamp': T0, 'type': 'turn_context', 'payload': {'model': 'fixture-model'}},
            {'timestamp': T0, 'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 't1'}},
            {'timestamp': T1, 'type': 'event_msg', 'payload': {'type': 'token_count', 'info': {
                'total_token_usage': {'input_tokens': 100, 'cached_input_tokens': 20,
                                     'output_tokens': 30, 'total_tokens': 130}}}},
            {'timestamp': T2, 'type': 'event_msg', 'payload': {'type': 'task_complete', 'turn_id': 't1'}},
            {'timestamp': T2, 'type': 'response_item', 'payload': {'text': 'PRIVATE_TRANSCRIPT_SENTINEL'}},
        ]
        self.source.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', CODEX_HOME=str(self.source.parent.parent), CODEX_THREAD_ID=SID)

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, *args, expected=0, shell=False):
        command = ['sh', str(SKILL / 'chat-report.sh')] if shell else [sys.executable, str(SKILL / 'scripts/chat_report.py')]
        result = subprocess.run(command + list(args), cwd=self.root, env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def test_directory_source_generates_report_and_reproducible_sidecars(self):
        output = self.root / 'reports' / 'task report.html'
        before = self.source.read_bytes()
        result = self.run_command('report', '--harness', 'codex', '--session', SID,
                                  '--source', str(self.source.parent), '--cutoff', T3,
                                  '--output', str(output), '--language', 'pt-BR', '--fragment', shell=True)
        self.assertEqual(len(result['files']), 4)
        self.assertEqual(self.source.read_bytes(), before)
        evidence = json.loads(output.with_suffix('.evidence.json').read_text())
        self.assertEqual(evidence['tokens']['total'], 130)
        self.assertNotIn('PRIVATE_TRANSCRIPT_SENTINEL', output.with_suffix('.evidence.json').read_text())
        self.assertIn('lang="pt-BR"', output.read_text())
        self.assertIn('130', output.read_text())
        self.run_command('render', '--input', str(output.with_suffix('.evidence.json')),
                         '--output', str(self.root / 'reproduced.html'), '--language', 'pt-BR')
        self.assertEqual(output.read_text(), (self.root / 'reproduced.html').read_text())
        self.run_command('render', '--input', str(output.with_suffix('.evidence.json')),
                         '--output', str(output), expected=2)

    def test_default_scope_uses_existing_codex_thread_and_root(self):
        result = self.run_command('collect')
        self.assertEqual(result['session_id'], SID)
        self.assertEqual(result['tokens']['total'], 130)

    def test_ambiguous_source_requires_selection_and_scan_limit_is_bounded(self):
        (self.source.parent / 'second.jsonl').write_bytes(self.source.read_bytes())
        result = self.run_command('collect', '--harness', 'codex', '--session', SID, expected=2)
        self.assertIn('Several sources', result['error'])
        self.run_command('sessions', '--limit', '1001', expected=2)

    def test_no_source_overwrite_or_unknown_session(self):
        before = self.source.read_bytes()
        result = self.run_command('collect', '--harness', 'codex', '--session', SID,
                                  '--source', str(self.source), '--output', str(self.source),
                                  '--overwrite', expected=2)
        self.assertIn('overwrite', result['error'])
        self.assertEqual(self.source.read_bytes(), before)
        self.run_command('collect', '--harness', 'codex', '--session', 'wrong',
                         '--source', str(self.source), expected=2)


class ManualTimer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_timer_is_unavailable_including_stop_and_pause(self):
        for action in ['status', 'pause', 'stop']:
            result = tracking.track(action, self.root, SID, T0)
            self.assertEqual(result['status'], 'not_started')
            self.assertIsNone(result['human'])
        self.assertFalse(tracking.state_path(self.root, SID).exists())

    def test_idempotence_cutoff_and_resumed_intervals(self):
        tracking.track('start', self.root, SID, T0)
        tracking.track('start', self.root, SID, T1)
        tracking.track('pause', self.root, SID, T2)
        tracking.track('pause', self.root, SID, T3)
        self.assertEqual(tracking.summary(self.root, SID, T1)['seconds'], '60.0')
        self.assertEqual(tracking.summary(self.root, SID, T3)['seconds'], '120.0')
        self.assertIsNone(tracking.summary(self.root, SID, '2020-01-01T09:59:59Z'))
        tracking.track('resume', self.root, SID, T3)
        result = tracking.track('status', self.root, SID, '2020-01-01T10:04:00Z')
        self.assertTrue(result['human']['open'])
        self.assertEqual(result['human']['seconds'], '180.0')

    def test_backwards_clock_preserves_state(self):
        tracking.track('start', self.root, SID, T2)
        before = tracking.state_path(self.root, SID).read_bytes()
        with self.assertRaises(ValueError):
            tracking.track('stop', self.root, SID, T0)
        self.assertEqual(tracking.state_path(self.root, SID).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
