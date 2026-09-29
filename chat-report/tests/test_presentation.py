"""Synthetic evidence tests for deterministic report arithmetic and attribution."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reportkit.presentation import CATEGORIES, build_presentation
from render_report import validate


def envelope():
    return {"schema_version": 1, "harness": "codex", "session_id": "synthetic-session",
            "source": "/private/user/project/session.jsonl", "source_kind": "native",
            "started_at": None, "observed_until": None, "cutoff": "2026-09-29T13:00:00Z",
            "tokens": dict.fromkeys(CATEGORIES + ("total",)), "token_coverage": "unavailable",
            "model_usage": [], "intervals": [], "time_basis": "none", "time_coverage": "unavailable",
            "billing": [], "diagnostics": [], "event_count": 0}


def usage(input_tokens=100, output_tokens=20):
    return {"input_uncached": input_tokens, "cache_read": 0, "cache_write_short": 0,
            "cache_write_long": 0, "output": output_tokens, "total": input_tokens + output_tokens}


def card(models=None, currency="USD"):
    return {"as_of": "2026-09-29", "source": "Synthetic user assumption", "currency": currency,
            "models": models or {"model-a": dict.fromkeys(CATEGORIES, "1")}}


def metrics(report):
    return {item["id"]: item for item in report["metrics"]}


class PresentationTests(unittest.TestCase):
    def report(self, collection, **kwargs):
        value = build_presentation(collection, **kwargs)
        validate(value)
        return value

    def test_missing_is_not_zero_and_paths_are_not_disclosed(self):
        data = envelope()
        data["diagnostics"] = [{"code": "unsupported_schema", "message": "/private/user/secret prompt"}]
        report = self.report(data)
        for key in ("human_time", "agent_time", "tokens", "cost"):
            self.assertIsNone(metrics(report)[key]["value"])
            self.assertEqual(metrics(report)[key]["coverage"], "unavailable")
        rendered = json.dumps(report)
        self.assertNotIn("/private", rendered)
        self.assertNotIn("secret prompt", rendered)
        self.assertNotIn("synthetic-session", rendered)
        self.assertNotIn("timeline", report)
        self.assertNotIn("deliverables", report)

    def test_partial_native_total_is_preserved_without_double_counting(self):
        data = envelope()
        data["tokens"].update(total=300, input_uncached=100, cache_read=150, output=50)
        data["token_coverage"] = "partial"
        report = self.report(data)
        self.assertEqual(metrics(report)["tokens"]["value"], "Subtotal: 300")
        self.assertEqual(metrics(report)["tokens"]["status"], "measured")
        self.assertIsNone(metrics(report)["cache_write_short"]["value"])

    def test_partial_category_sum_remains_partial_and_zero_is_evidence(self):
        data = envelope()
        data["tokens"].update(input_uncached=100, output=0)
        data["token_coverage"] = "complete"
        result = metrics(self.report(data))
        self.assertEqual(result["tokens"]["value"], "Subtotal: 100")
        self.assertEqual(result["tokens"]["status"], "calculated")
        self.assertEqual(result["output"]["value"], "0")
        self.assertEqual(result["cache_read"]["value"], None)

    def test_overlap_union_and_aggregate_agents_use_aware_timestamps(self):
        data = envelope()
        data.update(started_at="2026-09-29T08:00:00-03:00", observed_until="2026-09-29T11:20:00Z", time_basis="gross_turn")
        data["intervals"] = [
            {"start": "2026-09-29T08:00:00-03:00", "end": "2026-09-29T08:10:00-03:00", "agent_id": "main"},
            {"start": "2026-09-29T11:05:00Z", "end": "2026-09-29T11:12:00Z", "agent_id": "main"},
            {"start": "2026-09-29T11:10:00Z", "end": "2026-09-29T11:20:00Z", "agent_id": "child"},
        ]
        report = self.report(data)
        result = metrics(report)
        self.assertEqual(result["agent_time"]["value"], "20 min")
        self.assertEqual(result["aggregate_agent"]["value"], "22 min")
        self.assertEqual(result["elapsed"]["value"], "20 min")
        self.assertEqual(result["agent_time"]["coverage"], "partial")
        self.assertIsNone(result["human_time"]["value"])
        self.assertNotIn("child", json.dumps(report))

    def test_cutoff_clips_interval_and_last_observation(self):
        data = envelope()
        data.update(started_at="2026-09-29T12:59:30Z", observed_until="2026-09-29T13:10:00Z", time_basis="request")
        data["intervals"] = [{"start": "2026-09-29T12:59:30Z", "end": "2026-09-29T13:10:00Z", "agent_id": "main"}]
        result = metrics(self.report(data))
        self.assertEqual(result["agent_time"]["value"], "30 s")
        self.assertEqual(result["elapsed"]["value"], "30 s")

    def test_time_without_timezone_or_without_basis_is_rejected(self):
        data = envelope()
        data["started_at"] = "2026-09-29T12:00:00"
        with self.assertRaises(ValueError):
            self.report(data)
        data = envelope()
        data["intervals"] = [{"start": "2026-09-29T12:00:00Z", "end": "2026-09-29T12:01:00Z", "agent_id": "main"}]
        with self.assertRaises(ValueError):
            self.report(data)

    def test_exact_model_category_pricing_and_native_billing_are_separate(self):
        data = envelope()
        data.update(tokens=usage(1000000, 500000), token_coverage="complete")
        data["model_usage"] = [{"model": "model-a", "tokens": data["tokens"], "coverage": "complete"}]
        data["billing"] = [{"currency": "USD", "amount": "2.50", "kind": "attributed", "coverage": "complete"}]
        rates = card({"model-a": {"input_uncached": "2", "cache_read": "0.5", "cache_write_short": "3", "cache_write_long": "4", "output": "8"}})
        report = self.report(data, rates=rates)
        result = metrics(report)
        self.assertEqual(result["cost"]["value"], "USD 2.5")
        self.assertEqual(result["cost"]["status"], "measured")
        self.assertEqual(result["api_reference"]["value"], "USD 6")
        self.assertEqual(result["api_reference"]["status"], "estimated")
        self.assertEqual(result["api_reference"]["coverage"], "complete")
        by_id = {row["id"]: row for row in report["breakdowns"][0]["metrics"]}
        self.assertEqual(by_id["api_input_uncached"]["value"], "USD 2")
        self.assertEqual(by_id["api_output"]["value"], "USD 4")

    def test_unknown_rates_and_models_produce_subtotal_not_zero(self):
        data = envelope()
        data.update(tokens=usage(2000000, 2000000), token_coverage="complete")
        data["model_usage"] = [{"model": name, "tokens": usage(1000000, 1000000), "coverage": "complete"} for name in ("model-a", "model-b")]
        rates = card({"model-a": {"input_uncached": "2", "cache_read": "0", "cache_write_short": "0", "cache_write_long": "0", "output": None}})
        report = self.report(data, rates=rates)
        result = metrics(report)
        self.assertEqual(result["cost"]["value"], "Subtotal: USD 2")
        self.assertEqual(result["cost"]["coverage"], "partial")
        missing = {row["id"]: row for row in report["breakdowns"][1]["metrics"]}
        self.assertIsNone(missing["api_reference"]["value"])
        self.assertEqual(missing["api_reference"]["coverage"], "unavailable")

    def test_unallocated_usage_makes_api_reference_partial(self):
        data = envelope()
        data.update(tokens=usage(2000000, 2000000), token_coverage="complete")
        data["model_usage"] = [{"model": "model-a", "tokens": usage(1000000, 1000000), "coverage": "complete"}]
        report = self.report(data, rates=card())
        self.assertEqual(metrics(report)["cost"]["value"], "Subtotal: USD 2")
        self.assertEqual(metrics(report)["cost"]["coverage"], "partial")

    def test_never_guesses_model_from_only_one_rate_card_entry(self):
        data = envelope()
        data.update(tokens=usage(), token_coverage="complete")
        report = self.report(data, rates=card())
        self.assertIsNone(metrics(report)["cost"]["value"])
        self.assertTrue(any("model allocation" in note for note in report["limitations"]))

    def test_currencies_do_not_add_and_reference_does_not_join_billing(self):
        data = envelope()
        data["billing"] = [
            {"currency": "USD", "amount": "1", "kind": "attributed", "coverage": "complete"},
            {"currency": "USD", "amount": "0.1", "kind": "attributed", "coverage": "partial"},
            {"currency": "BRL", "amount": "5", "kind": "attributed", "coverage": "complete"},
            {"currency": "USD", "amount": "9", "kind": "reference", "coverage": "complete"},
        ]
        result = metrics(self.report(data))
        self.assertIsNone(result["cost"]["value"])
        self.assertEqual(result["billing_attributed_USD"]["value"], "Subtotal: USD 1.1")
        self.assertEqual(result["billing_attributed_BRL"]["value"], "BRL 5")
        self.assertEqual(result["billing_reference_USD"]["value"], "USD 9")

    def test_declared_human_effort_and_labor_are_separate(self):
        report = self.report(envelope(), language="pt-BR", human={"seconds": "5400", "basis": "declared", "coverage": "partial", "open": True}, hourly_rate="100", labor_currency="BRL")
        result = metrics(report)
        self.assertEqual(result["human_time"]["value"], "1 h 30 min")
        self.assertEqual(result["human_time"]["status"], "declared")
        self.assertEqual(result["human_labor"]["value"], "Subtotal: BRL 150")
        self.assertIsNone(result["cost"]["value"])
        self.assertIn("cronômetro", " ".join(report["limitations"]))
        self.assertEqual(report["language"], "pt-BR")

    def test_supplied_labor_rate_does_not_infer_effort(self):
        result = metrics(self.report(envelope(), hourly_rate="10", labor_currency="USD"))
        self.assertIsNone(result["human_time"]["value"])
        self.assertIsNone(result["human_labor"]["value"])

    def test_monetary_rounding_never_displays_a_positive_amount_as_zero(self):
        data = envelope()
        data["billing"] = [{"currency": "USD", "amount": "0.00000000001", "kind": "attributed", "coverage": "complete"}]
        report = self.report(data)
        self.assertEqual(metrics(report)["cost"]["value"], "< USD 0.00000001")
        self.assertTrue(any("eight decimal" in item for item in report["limitations"]))
        human = {"seconds": "1", "basis": "declared", "coverage": "complete"}
        result = metrics(self.report(envelope(), human=human, hourly_rate="1", labor_currency="USD"))
        self.assertEqual(result["human_labor"]["value"], "USD 0.00027778")

    def test_undated_snapshot_has_no_invented_period_or_elapsed_time(self):
        data = envelope()
        data["source_kind"] = "export"
        data["tokens"]["total"] = 500
        data["token_coverage"] = "partial"
        data["diagnostics"] = [{"code": "snapshot_as_exported", "message": "Usage is the snapshot as exported."}]
        report = self.report(data, language="pt-BR")
        self.assertIsNone(report["period"]["start"])
        self.assertIsNone(metrics(report)["elapsed"]["value"])
        self.assertEqual(metrics(report)["tokens"]["value"], "Subtotal: 500")
        self.assertTrue(any("não estabelece quando" in item for item in report["limitations"]))

    def test_reported_run_duration_uses_only_a_validated_fixed_message(self):
        data = envelope()
        data["harness"] = "antigravity"
        template = "Antigravity reports {} seconds as reported run elapsed duration; no dated execution interval. This cumulative snapshot is not human work or pure model inference time."
        data["diagnostics"] = [{"code": "reported_run_duration", "message": template.format("2.54")}]
        for language, expected in (("en", "2.54 seconds"), ("pt-BR", "2,54 segundos")):
            report = self.report(data, language=language)
            self.assertIn(expected, " ".join(report["limitations"]))
            self.assertIsNone(metrics(report)["agent_time"]["value"])
            self.assertIsNone(metrics(report)["human_time"]["value"])
        for message in ("/private/secret 2.54", template.format("NaN"), template.format("-2"), template.format("9007199254740992"), template.format("2.54") + " /private/secret"):
            data["diagnostics"] = [{"code": "reported_run_duration", "message": message},
                                   {"code": "invalid_reported_run_duration", "message": "/private/secret"}]
            report = self.report(data, language="pt-BR")
            combined = " ".join(report["limitations"])
            self.assertNotIn("/private", combined)
            self.assertNotIn("2,54 segundos", combined)
            self.assertIn("duração informada inválida", combined)

    def test_card_and_numeric_validation(self):
        invalid = []
        missing = card(); del missing["models"]["model-a"]["output"]; invalid.append(missing)
        unknown = card(); unknown["secret"] = "x"; invalid.append(unknown)
        bad_date = card(); bad_date["as_of"] = "2026-02-30"; invalid.append(bad_date)
        creds = card(); creds["source"] = "https://user:password@example.com/price"; invalid.append(creds)
        for value in ("NaN", "Infinity", "-1", "1e6", 1, True):
            entry = card(); entry["models"]["model-a"]["output"] = value; invalid.append(entry)
        for rates in invalid:
            with self.subTest(rates=rates), self.assertRaises(ValueError):
                self.report(envelope(), rates=rates)
        for value in (True, -1, 1.5, "NaN"):
            data = envelope(); data["tokens"]["total"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.report(data)

    def test_input_envelope_is_not_mutated(self):
        data = envelope()
        data.update(tokens=usage(), token_coverage="complete")
        data["model_usage"] = [{"model": "model-a", "tokens": data["tokens"], "coverage": "complete"}]
        before = copy.deepcopy(data)
        self.report(data, rates=card())
        self.assertEqual(data, before)


if __name__ == "__main__":
    unittest.main()
