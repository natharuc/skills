"""Synthetic Cursor fixtures: attribution, bounds, WAL, and conservative metrics."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reportkit.adapters import cursor


class CursorAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "state.vscdb"
        self.con = sqlite3.connect(self.db)
        self.addCleanup(self.con.close)
        self.con.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value BLOB)")
        self.con.execute("CREATE TABLE composerHeaders (composerId TEXT PRIMARY KEY, createdAt INTEGER, lastUpdatedAt INTEGER)")

    def put(self, key, obj):
        raw = json.dumps(obj) if isinstance(obj, dict) else obj
        self.con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?, ?)", (key, raw))
        self.con.commit()

    def header(self, cid="chosen"):
        self.con.execute("INSERT INTO composerHeaders VALUES (?, ?, ?)",
                         (cid, 1788256800000, 1788257400000))  # 2026-09-01 10:00–10:10Z
        self.con.commit()

    def bubble(self, bid="b1", cid="chosen", when="2026-09-01T10:01:00Z", inp=20, out=10, **extra):
        value = {"_v": 3, "type": 2, "bubbleId": bid, "createdAt": when,
                 "tokenCount": {"inputTokens": inp, "outputTokens": out},
                 "text": "PRIVATE_PROMPT_NEVER_OUTPUT", "toolFormerData": {"result": "PRIVATE_TOOL_RESULT"}}
        value.update(extra)
        self.put("bubbleId:" + cid + ":" + bid, value)

    def test_totals_identity_dedup_and_no_disclosure(self):
        self.header()
        self.bubble()
        self.bubble("b2", inp=5, out=2)
        self.bubble("unused", inp=500, out=500)
        self.bubble(cid="chosen-other", inp=999, out=999)
        self.put("composerData:chosen", {"composerId": "chosen", "fullConversationHeadersOnly":
                 [{"bubbleId": "b1"}, {"bubbleId": "b1"}, {"bubbleId": "b2"}]})
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        report = cursor.collect(self.db, "chosen")
        self.assertEqual(report["tokens"]["total"], 37)
        self.assertEqual(report["tokens"]["output"], 12)
        self.assertIsNone(report["tokens"]["input_uncached"])
        self.assertIsNone(report["tokens"]["cache_read"])
        self.assertEqual(report["token_coverage"], "partial")
        self.assertEqual(report["event_count"], 2)
        self.assertEqual(report["time_basis"], "none")
        self.assertEqual(report["intervals"], [])
        self.assertEqual(report["billing"], [])
        self.assertNotIn("PRIVATE_", json.dumps(report))
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)

    def test_default_zero_is_unavailable(self):
        self.bubble(inp=0, out=0)
        report = cursor.collect(self.db, "chosen")
        self.assertTrue(all(v is None for v in report["tokens"].values()))
        self.assertEqual(report["token_coverage"], "unavailable")
        self.assertIn("default_zero_usage", {d["code"] for d in report["diagnostics"]})

    def test_cutoff_excludes_future_and_untimed_usage(self):
        self.header()
        self.bubble()
        self.bubble("future", when="2026-09-01T10:05:00Z", inp=999, out=999)
        self.bubble("untimed", when=None, inp=999, out=999)
        report = cursor.collect(self.db, "chosen", "2026-09-01T10:02:00Z")
        self.assertEqual(report["tokens"]["total"], 30)
        self.assertEqual(report["started_at"], "2026-09-01T10:00:00Z")
        self.assertEqual(report["observed_until"], "2026-09-01T10:01:00Z")

    def test_malformed_and_nonfinite_values_are_skipped(self):
        for bid, value in (("badjson", "{"), ("integer", 20), ("nan", '{"type":NaN}'),
                           ("inf", '{"type":1e999}'), ("duplicate", '{"type":2,"type":1}')):
            self.put("bubbleId:chosen:" + bid, value)
        self.bubble(inp=-1)
        report = cursor.collect(self.db, "chosen")
        self.assertIsNone(report["tokens"]["total"])
        self.assertIn("malformed_record", {d["code"] for d in report["diagnostics"]})
        self.assertIn("invalid_usage", {d["code"] for d in report["diagnostics"]})

    def test_identity_mismatch_is_rejected(self):
        self.bubble(composerId="another")
        with self.assertRaises(ValueError):
            cursor.collect(self.db, "chosen")
        with self.assertRaises(ValueError):
            cursor.collect(self.db, "chosen:prefix")

    def test_unknown_version_does_not_invent_usage(self):
        self.bubble(_v=200)
        report = cursor.collect(self.db, "chosen")
        self.assertIsNone(report["tokens"]["total"])
        self.assertIn("unsupported_bubble_version", {d["code"] for d in report["diagnostics"]})

    def test_bounds_produce_partial_diagnostics(self):
        self.bubble("a")
        self.bubble("b")
        self.bubble("c")
        with patch.object(cursor, "MAX_RECORDS", 2):
            report = cursor.collect(self.db, "chosen")
        self.assertEqual(report["tokens"]["total"], 60)
        self.assertIn("record_limit", {d["code"] for d in report["diagnostics"]})
        self.put("bubbleId:chosen:a", "x" * (cursor.MAX_VALUE + 1))
        report = cursor.collect(self.db, "chosen")
        self.assertIn("oversized_record", {d["code"] for d in report["diagnostics"]})

    def test_huge_timestamp_and_invalid_cutoff(self):
        self.put("composerData:chosen", {"createdAt": 10 ** 999})
        self.bubble()
        self.assertEqual(cursor.collect(self.db, "chosen")["tokens"]["total"], 30)
        with self.assertRaises(ValueError):
            cursor.collect(self.db, "chosen", "2026-09-01T10:00:00")

    def test_missing_source_does_not_create_database(self):
        missing = self.db.parent / "missing.vscdb"
        report = cursor.collect(missing, "chosen")
        self.assertFalse(missing.exists())
        self.assertEqual(report["diagnostics"][0]["code"], "source_missing")
        self.assertEqual(cursor.sessions(missing), [])

    def test_discovery_is_bounded_and_does_not_print_prompts(self):
        self.header()
        self.bubble()
        self.header("draft")
        self.header("another")
        self.bubble(cid="another")
        listed = cursor.sessions(self.db, 1)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["session_id"], "another")
        self.assertNotIn("PRIVATE_", json.dumps(listed))
        self.assertNotIn("draft", [s["session_id"] for s in cursor.sessions(self.db)])

    def test_discovery_without_header_table(self):
        self.con.execute("DROP TABLE composerHeaders")
        self.put("composerData:chosen", {"composerId": "chosen"})
        self.assertEqual(cursor.sessions(self.db)[0]["session_id"], "chosen")

    def test_live_wal_is_seen_without_checkpoint(self):
        self.con.execute("PRAGMA journal_mode=WAL")
        self.bubble()
        self.assertTrue(Path(str(self.db) + "-wal").exists())
        report = cursor.collect(self.db, "chosen")
        self.assertEqual(report["tokens"]["total"], 30)

    def test_known_roots(self):
        home = Path("/home/test")
        self.assertEqual(cursor.roots(home, {}, "Linux"), [home / ".config/Cursor/User/globalStorage/state.vscdb"])
        self.assertEqual(cursor.roots(home, {"XDG_CONFIG_HOME": "/cfg"}, "Linux"),
                         [Path("/cfg/Cursor/User/globalStorage/state.vscdb")])
        self.assertEqual(cursor.roots(home, {}, "Darwin"), [home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"])
        self.assertEqual(cursor.roots(home, {"APPDATA": "/roaming"}, "Windows"),
                         [Path("/roaming/Cursor/User/globalStorage/state.vscdb")])


if __name__ == "__main__":
    unittest.main()
