"""Synthetic fixtures modeled on the linked official event contracts."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reportkit.adapters import antigravity, copilot
from reportkit.common import validate_collection


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_lines(self, name, events):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
        return path

    def event(self, number, kind, data, second=0, **fields):
        return {"id": f"event-{number}", "type": kind, "timestamp": f"2026-09-29T10:00:{second:02d}Z", "data": data, **fields}

    def start(self, identity="session-a"):
        return self.event("start", "session.start", {"sessionId": identity, "startTime": "2026-09-29T10:00:00Z", "producer": "copilot-agent", "version": 1})

    def shutdown(self, number, output, second=10, **extra):
        return self.event(number, "session.shutdown", {
            "shutdownType": "routine", "modelMetrics": {
                "test-model": {"usage": {"inputTokens": 200, "outputTokens": output, "cacheReadTokens": 50, "cacheWriteTokens": 0}, "requests": {"count": 2, "cost": 1.5}}
            }, "totalNanoAiu": 55555, **extra,
        }, second)

    def codes(self, report):
        validate_collection(report)
        return {item["code"] for item in report["diagnostics"]}

    def test_copilot_roots_are_platform_neutral_with_override(self):
        for platform in ("Windows", "Linux", "Darwin"):
            self.assertEqual(copilot.roots(self.root, {}, platform), [self.root / ".copilot" / "session-state"])
        self.assertEqual(copilot.roots(self.root, {"COPILOT_HOME": str(self.root / "custom")}, "Windows"), [self.root / "custom" / "session-state"])

    def test_copilot_last_durable_snapshot_does_not_add_ephemeral_or_reasoning(self):
        path = self.write_lines("session-state/session-a/events.jsonl", [self.start(), self.shutdown(1, 10), self.event(2, "assistant.usage", {"model": "test-model", "apiCallId": "api-1", "inputTokens": 200, "outputTokens": 15, "reasoningTokens": 7, "cacheReadTokens": 50, "cost": 1.5}, 15), self.shutdown(3, 25, 20)])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        report = copilot.collect(path, "session-a")
        self.assertEqual(report["tokens"]["output"], 25)
        self.assertEqual(report["tokens"]["cache_read"], 50)
        self.assertIsNone(report["tokens"]["input_uncached"])
        self.assertIsNone(report["tokens"]["total"])
        self.assertEqual(report["billing"], [])
        self.assertIn("shutdown_snapshot", self.codes(report))
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_copilot_ephemeral_usage_deduplicates_by_api_call(self):
        usage = {"model": "test-model", "apiCallId": "api-one", "inputTokens": 200, "outputTokens": 12, "cacheReadTokens": 60, "reasoningTokens": 6, "cost": 99}
        path = self.write_lines("capture.jsonl", [self.start(), self.event(1, "assistant.usage", usage, 1), self.event(2, "assistant.usage", usage, 2), self.event(3, "assistant.message", {"messageId": "m-1", "outputTokens": 12, "content": "SECRET_PROMPT"}, 3)])
        report = copilot.collect(path, "session-a")
        self.assertEqual(report["tokens"]["output"], 12)
        self.assertEqual(report["model_usage"][0]["tokens"]["output"], 12)
        self.assertNotIn("SECRET_PROMPT", json.dumps(report))
        self.assertIn("captured_usage_partial", self.codes(report))

    def test_copilot_main_turns_exclude_child_spans_and_historical_tail(self):
        events = [self.start(), self.event(1, "assistant.turn_start", {"turnId": "1"}, 1), self.event(2, "assistant.turn_start", {"turnId": "1"}, 2, agentId="child-1"), self.event(3, "assistant.turn_end", {"turnId": "1"}, 5, agentId="child-1"), self.event(4, "assistant.turn_end", {"turnId": "1"}, 8), self.event(5, "assistant.turn_start", {"turnId": "2"}, 9), self.event(6, "assistant.turn_end", {"turnId": "2"}, 20)]
        path = self.write_lines("capture.jsonl", events)
        report = copilot.collect(path, "session-a", "2026-09-29T10:00:10Z")
        self.assertEqual(len(report["intervals"]), 1)
        self.assertEqual(report["intervals"][0]["end"], "2026-09-29T10:00:08Z")
        self.assertEqual(report["time_basis"], "gross_turn")
        self.assertIn("unfinished_turns", self.codes(report))
        self.assertIn("child_spans_excluded", self.codes(report))

    def test_copilot_resume_reused_turn_id_and_summary_reset(self):
        path = self.write_lines("capture.jsonl", [self.start(), self.event(1, "assistant.turn_start", {"turnId": "1"}, 1), self.event(2, "assistant.turn_end", {"turnId": "1"}, 2), self.shutdown(3, 100, 3), self.event(4, "session.resume", {}, 4), self.event(5, "assistant.turn_start", {"turnId": "1"}, 5), self.event(6, "assistant.turn_end", {"turnId": "1"}, 6), self.shutdown(7, 20, 7)])
        report = copilot.collect(path, "session-a")
        self.assertEqual(len(report["intervals"]), 2)
        self.assertEqual(report["tokens"]["output"], 20)
        self.assertIn("summary_counter_reset", self.codes(report))

    def test_copilot_exact_identity_and_mixed_file_rejection(self):
        path = self.write_lines("capture.jsonl", [self.start(), self.shutdown(1, 10)])
        self.assertIn("session_identity_mismatch", self.codes(copilot.collect(path, "session-b")))
        path = self.write_lines("mixed.jsonl", [self.start(), self.shutdown(1, 10), self.start("session-b")])
        report = copilot.collect(path, "session-a")
        self.assertIn("mixed_session_source", self.codes(report))
        self.assertTrue(all(value is None for value in report["tokens"].values()))

    def test_copilot_discovery_requires_start_and_validates_directory(self):
        good = self.write_lines("session-state/session-a/events.jsonl", [self.start()])
        self.write_lines("session-state/session-b/events.jsonl", [self.start()])
        self.write_lines("session-state/session-c/events.jsonl", [self.event(1, "session.usage_info", {"currentTokens": 999})])
        self.assertEqual(copilot.sessions(self.root / "session-state"), [{"session_id": "session-a", "source": str(good), "started_at": "2026-09-29T10:00:00Z"}])
        self.assertEqual(copilot.sessions(self.root, 0), [])

    def test_copilot_context_occupancy_is_not_consumed_tokens(self):
        path = self.write_lines("capture.jsonl", [self.start(), self.event(1, "session.usage_info", {"currentTokens": 40000, "tokenLimit": 128000}, 1)])
        report = copilot.collect(path, "session-a")
        self.assertTrue(all(value is None for value in report["tokens"].values()))
        self.assertIn("context_window_not_usage", self.codes(report))

    def test_copilot_malformed_tail_preserves_partial_and_does_not_leak(self):
        path = self.write_lines("capture.jsonl", [self.start(), self.shutdown(1, 10)])
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"secret":"SENSITIVE_BROKEN",\n')
        report = copilot.collect(path, "session-a")
        self.assertEqual(report["tokens"]["output"], 10)
        self.assertIn("source_incomplete", self.codes(report))
        self.assertNotIn("SENSITIVE_BROKEN", json.dumps(report))

    def ag_result(self, total=30670, output=8, turns=2, identity="ag-a"):
        return {"conversation_id": identity, "status": "SUCCESS", "response": "SECRET_RESPONSE", "duration_seconds": 2.54, "num_turns": turns, "usage": {"input_tokens": total - output, "output_tokens": output, "thinking_tokens": 3, "cache_read_tokens": 30214, "total_tokens": total}}

    def test_antigravity_json_preserves_native_total_without_guessing_cache(self):
        path = self.root / "result.json"
        path.write_text(json.dumps(self.ag_result()), encoding="utf-8")
        report = antigravity.collect(path, "ag-a")
        self.assertEqual(report["tokens"]["total"], 30670)
        self.assertEqual(report["tokens"]["output"], 8)
        self.assertIsNone(report["tokens"]["input_uncached"])
        self.assertIsNone(report["tokens"]["cache_read"])
        self.assertEqual(report["intervals"], [])
        self.assertEqual(report["billing"], [])
        self.assertNotIn("SECRET_RESPONSE", json.dumps(report))
        self.assertIn("native_total_semantics", self.codes(report))

    def test_antigravity_stream_uses_last_cumulative_result_not_sum(self):
        path = self.write_lines("stream.jsonl", [{"event": "init", "conversation_id": "ag-a", "init": {"cwd": "/private"}}, {"event": "step_update", "step_update": {"conversation_id": "ag-a", "step_index": 1, "state": "DONE", "usage": {"total_tokens": 30388}}}, {"event": "result", "result": self.ag_result(30388, 4, 1)}, {"event": "result", "result": self.ag_result()}])
        report = antigravity.collect(path, "ag-a")
        self.assertEqual(report["tokens"]["total"], 30670)
        self.assertEqual(report["event_count"], 2)
        self.assertIn("step_usage_not_added", self.codes(report))

    def test_antigravity_reported_duration_is_visible_without_invented_dates(self):
        path = self.root / "result.json"
        path.write_text(json.dumps(self.ag_result()), encoding="utf-8")
        report = antigravity.collect(path, "ag-a")
        self.assertIn("reported_run_duration", self.codes(report))
        duration = next(item["message"] for item in report["diagnostics"] if item["code"] == "reported_run_duration")
        self.assertIn("2.54 seconds", duration)
        self.assertIn("reported run elapsed duration; no dated execution interval", duration)
        self.assertIsNone(report["started_at"])
        self.assertIsNone(report["observed_until"])
        self.assertEqual(report["intervals"], [])

    def test_antigravity_invalid_duration_is_not_exposed(self):
        path = self.root / "result.json"
        for bad in ("SECRET_DURATION", True, -1, 2**60):
            value = self.ag_result()
            value["duration_seconds"] = bad
            path.write_text(json.dumps(value), encoding="utf-8")
            report = antigravity.collect(path, "ag-a")
            self.assertIn("invalid_reported_run_duration", self.codes(report))
            self.assertNotIn("reported_run_duration", self.codes(report))
            self.assertNotIn("SECRET_DURATION", json.dumps(report))
        value["duration_seconds"] = "overflow-number"
        path.write_text(json.dumps(value).replace('"overflow-number"', "1e999"), encoding="utf-8")
        report = antigravity.collect(path, "ag-a")
        self.assertIn("invalid_reported_run_duration", self.codes(report))
        self.assertNotIn("reported_run_duration", self.codes(report))

    def test_antigravity_restarted_or_reset_snapshots_remain_partial(self):
        path = self.write_lines("reset.jsonl", [{"event": "result", "result": self.ag_result()}, {"event": "result", "result": self.ag_result(100, 2, 1)}])
        report = antigravity.collect(path, "ag-a")
        self.assertEqual(report["tokens"]["total"], 100)
        self.assertIn("summary_counter_reset", self.codes(report))

    def test_antigravity_rejects_mixed_session_stream(self):
        path = self.write_lines("mixed.jsonl", [{"event": "result", "result": self.ag_result()}, {"event": "result", "result": self.ag_result(identity="ag-b")}])
        report = antigravity.collect(path, "ag-a")
        self.assertIn("mixed_session_source", self.codes(report))
        self.assertIsNone(report["tokens"]["total"])

    def test_antigravity_historical_cutoff_does_not_use_file_mtime(self):
        path = self.root / "result.json"
        path.write_text(json.dumps(self.ag_result()), encoding="utf-8")
        report = antigravity.collect(path, "ag-a", "2026-09-29T20:00:00Z", strict_cutoff=True)
        self.assertIsNone(report["tokens"]["total"])
        self.assertIn("cutoff_unverifiable", self.codes(report))

    def test_antigravity_native_discovery_does_not_claim_schema_support(self):
        path = self.write_lines("brain/ag-a/.system_generated/logs/transcript.jsonl", [{"role": "assistant", "text": "SECRET_TRANSCRIPT"}])
        self.assertEqual(antigravity.sessions(self.root), [{"session_id": "ag-a", "source": str(path)}])
        report = antigravity.collect(path, "ag-a")
        self.assertIn("unsupported_native_schema", self.codes(report))
        self.assertNotIn("SECRET_TRANSCRIPT", json.dumps(report))

    def test_antigravity_unknown_binary_and_missing_sources_are_read_only(self):
        path = self.root / "ag-a.pb"
        path.write_bytes(b"\x00SECRET_BINARY")
        self.assertIn("unsupported_native_schema", self.codes(antigravity.collect(path, "ag-a")))
        absent = self.root / "absent.json"
        self.assertIn("source_missing", self.codes(antigravity.collect(absent, "ag-a")))
        self.assertFalse(absent.exists())

    def test_antigravity_invalid_counters_and_duplicate_keys_rejected(self):
        value = self.ag_result()
        value["usage"]["total_tokens"] = True
        path = self.root / "result.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        report = antigravity.collect(path, "ag-a")
        self.assertIsNone(report["tokens"]["total"])
        self.assertIn("invalid_counters", self.codes(report))
        path.write_text('{"conversation_id":"ag-a","conversation_id":"ag-b"}', encoding="utf-8")
        report = antigravity.collect(path, "ag-a")
        self.assertIn("unsupported_native_schema", self.codes(report))


if __name__ == "__main__":
    unittest.main()
