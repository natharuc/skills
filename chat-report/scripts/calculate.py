#!/usr/bin/env python3
"""Calculate conservative report metrics from normalized JSON; no log collection."""

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, Inexact, localcontext
import json
from pathlib import Path
import re
import sys


CATEGORIES = (
    "input_uncached", "cache_read", "cache_write_short", "cache_write_long", "output"
)
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])")
RATE = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def fields(value, required, optional, path):
    check(isinstance(value, dict), path + " must be an object")
    check(set(required) <= value.keys(), path + " is missing required fields")
    check(value.keys() <= set(required) | set(optional), path + " has unknown fields")


def nonempty(value, path):
    check(isinstance(value, str) and bool(value.strip()), path + " must be a nonempty string")


def timestamp(value, path):
    check(isinstance(value, str) and STAMP.fullmatch(value), path + " must be ISO8601 with timezone")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError(path + ": invalid timestamp") from exc


def amount(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    return value


def metric(values, complete):
    known = [v for v in values if v is not None]
    subtotal = sum(known) if known else None
    full = bool(values) and len(known) == len(values) and complete
    return {
        "known_subtotal": amount(subtotal),
        "total": amount(subtotal) if full else None,
        "coverage": "complete" if full else "partial" if known else "unavailable",
        "known_values": len(known),
        "missing_values": len(values) - len(known),
    }


def optional_list(data, key):
    if key not in data:
        return []
    check(isinstance(data[key], list), key + " must be a list (or omitted)")
    return data[key]


def duration(start, end):
    delta = end - start
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Decimal(micros) / Decimal(1_000_000)


def union(intervals):
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return merged


def interval_metrics(data, key, start, cutoff, complete):
    intervals = []
    agents = {}
    human = key == "human_intervals"
    for index, entry in enumerate(optional_list(data, key)):
        path = f"{key}[{index}]"
        fields(entry, ("start", "end", "basis") if human else ("start", "end", "agent_id"), (), path)
        if human:
            check(entry["basis"] in ("measured", "declared"), path + ".basis must be measured or declared")
        else:
            nonempty(entry["agent_id"], path + ".agent_id")
        left = timestamp(entry["start"], path + ".start")
        right = timestamp(entry["end"], path + ".end")
        check(left <= right, path + ".end must not precede start")
        check(right <= cutoff and (start is None or left >= start), path + " lies outside the scope")
        intervals.append((left, right))
        if not human:
            agents.setdefault(entry["agent_id"], []).append((left, right))
    result = {
        "interval_count": len(intervals),
        "calendar_seconds": metric([duration(a, b) for a, b in union(intervals)], complete),
    }
    if not human:
        result["agent_count"] = len(agents)
        result["aggregate_agent_seconds"] = metric([
            duration(a, b) for group in agents.values() for a, b in union(group)
        ], complete)
    else:
        result["basis_counts"] = {
            basis: sum(entry["basis"] == basis for entry in optional_list(data, key))
            for basis in ("measured", "declared")
        }
    return result


def validate_request(entry, index):
    path = f"requests[{index}]"
    fields(entry, ("id", "tokens"), ("pricing",), path)
    fields(entry["id"], ("provider", "session", "request"), (), path + ".id")
    for key, value in entry["id"].items():
        nonempty(value, path + ".id." + key)
    fields(entry["tokens"], CATEGORIES, (), path + ".tokens")
    for category, value in entry["tokens"].items():
        check(value is None or (type(value) is int and value >= 0), path + ".tokens." + category + " must be a nonnegative integer or null")
    if "pricing" in entry:
        price = entry["pricing"]
        fields(price, ("currency", "source", "as_of", "per_million"), (), path + ".pricing")
        check(isinstance(price["currency"], str) and re.fullmatch(r"[A-Z]{3}", price["currency"]), path + ".pricing.currency must be a three-letter uppercase code")
        nonempty(price["source"], path + ".pricing.source")
        check(isinstance(price["as_of"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", price["as_of"]), path + ".pricing.as_of must be YYYY-MM-DD")
        date.fromisoformat(price["as_of"])
        fields(price["per_million"], CATEGORIES, (), path + ".pricing.per_million")
        for category, value in price["per_million"].items():
            check(value is None or (isinstance(value, str) and RATE.fullmatch(value)), path + ".pricing.per_million." + category + " must be a nonnegative decimal string or null")


def costs(requests, complete):
    rows = []
    buckets = {}
    unassigned = sum("pricing" not in entry for entry in requests)
    all_values = []
    for entry in requests:
        price = entry.get("pricing")
        values = {}
        for category in CATEGORIES:
            tokens = entry["tokens"][category]
            rate = price["per_million"][category] if price else None
            values[category] = (
                Decimal(tokens) * Decimal(rate) / Decimal(1_000_000)
                if tokens is not None and rate is not None
                else Decimal(0) if tokens == 0 and price else None
            )
        currency = price["currency"] if price else None
        row = {
            "id": entry["id"],
            "currency": currency,
            "by_category": {k: amount(v) for k, v in values.items()},
            **metric(list(values.values()), complete),
        }
        if price:
            row["pricing_source"] = price["source"]
            row["pricing_as_of"] = price["as_of"]
            buckets.setdefault(currency, []).append(values)
        rows.append(row)
        all_values.extend(values.values())
    currency_buckets = {}
    for currency, entries in sorted(buckets.items()):
        currency_buckets[currency] = {
            "request_count": len(entries),
            **metric([v for entry in entries for v in entry.values()], complete and not unassigned),
            "by_category": {
                category: metric([entry[category] for entry in entries], complete and not unassigned)
                for category in CATEGORIES
            },
        }
    known_count = sum(value is not None for value in all_values)
    full = bool(all_values) and known_count == len(all_values) and complete
    return {
        "label": "API reference cost; not a billed charge",
        "coverage": "complete" if full else "partial" if known_count else "unavailable",
        "unassigned_currency_requests": unassigned,
        "currency_buckets": currency_buckets,
        "requests": rows,
    }


def calculate(data):
    fields(data, ("scope", "coverage"), ("coverage_by_metric", "requests", "agent_intervals", "human_intervals"), "input")
    fields(data["scope"], ("label", "cutoff"), ("start",), "scope")
    nonempty(data["scope"]["label"], "scope.label")
    cutoff = timestamp(data["scope"]["cutoff"], "scope.cutoff")
    start = timestamp(data["scope"]["start"], "scope.start") if "start" in data["scope"] else None
    check(start is None or start <= cutoff, "scope.start must not follow cutoff")
    check(data["coverage"] in ("complete", "partial"), "coverage must be complete or partial")
    overrides = data.get("coverage_by_metric", {})
    fields(overrides, (), ("tokens", "agent", "human"), "coverage_by_metric")
    coverage = {key: overrides.get(key, data["coverage"]) for key in ("tokens", "agent", "human")}
    for key, value in coverage.items():
        check(value in ("complete", "partial"), "coverage_by_metric." + key + " must be complete or partial")
    complete = coverage["tokens"] == "complete"
    unique = {}
    source = optional_list(data, "requests")
    for index, entry in enumerate(source):
        validate_request(entry, index)
        key = tuple(entry["id"][k] for k in ("provider", "session", "request"))
        check(key not in unique or unique[key] == entry, f"conflicting duplicate request id: {key!r}")
        unique[key] = entry
    requests = list(unique.values())
    tokens = {
        **metric([v for entry in requests for v in entry["tokens"].values()], complete),
        "by_category": {
            category: metric([entry["tokens"][category] for entry in requests], complete)
            for category in CATEGORIES
        },
    }
    return {
        "scope": data["scope"],
        "coverage": data["coverage"],
        "coverage_by_metric": coverage,
        "unique_requests": len(requests),
        "duplicate_requests_removed": len(source) - len(requests),
        "tokens": tokens,
        "reference_api_cost": costs(requests, complete),
        "time": {
            "elapsed_scope_seconds": amount(duration(start, cutoff)) if start else None,
            "agent": interval_metrics(data, "agent_intervals", start, cutoff, coverage["agent"] == "complete"),
            "human": interval_metrics(data, "human_intervals", start, cutoff, coverage["human"] == "complete"),
        },
    }


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        check(key not in result, "duplicate JSON object key: " + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to normalized JSON; see references/calculation.md")
    args = parser.parse_args()
    try:
        raw = Path(args.input).read_text(encoding="utf-8")
        data = json.loads(raw, parse_float=Decimal, parse_constant=invalid_constant, object_pairs_hook=unique_keys)
        with localcontext() as context:
            # Plain decimal rates make input length a conservative exactness bound.
            context.prec = max(50, len(raw) + 10)
            context.traps[Inexact] = True
            result = calculate(data)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, ArithmeticError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
