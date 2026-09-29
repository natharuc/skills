"""Read official Antigravity headless JSON and stream-json result envelopes.

Discovery locates documented transcript paths. Their presence does not imply a
supported transcript schema. Unknown or binary stores are never decoded by guess.
"""
from __future__ import annotations

import itertools
import json
import math
import os
import re
from pathlib import Path

from reportkit.common import diagnostic, empty_result, iso_time, parse_time, read_jsonl

MAX_DISCOVERY = 5000
MAX_JSON_BYTES = 64 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
TRANSCRIPT = Path(".system_generated") / "logs" / "transcript.jsonl"
RESULT_STATUS = {"SUCCESS", "ERROR", "CANCELED", "INTERRUPTED", "INVALID", "WAITING", "RUNNING"}


def roots(home: Path, env: dict, system: str) -> list[Path]:
    # Official hooks docs define the same home-relative data roots on each OS.
    return [home / ".gemini" / name for name in ("antigravity", "antigravity-cli", "antigravity-ide")]


def _identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value > 2**53 - 1 or int(value) != value:
        return None
    return int(value)


def _reject_constant(_):
    raise ValueError("nonfinite JSON number")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result


def _objects(path):
    if path.suffix.lower() == ".json":
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ValueError("JSON resource limit")
        with path.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("JSON resource limit")
        value = json.loads(raw.decode("utf-8-sig"), parse_constant=_reject_constant, object_pairs_hook=_pairs)
        if not isinstance(value, dict):
            raise ValueError("JSON object required")
        yield 1, value
    else:
        yield from read_jsonl(path)


def _envelope(item):
    if item.get("event") == "result":
        return item.get("result") if isinstance(item.get("result"), dict) else None
    if "event" not in item and "conversation_id" in item and "status" in item and isinstance(item.get("usage"), dict):
        return item
    return None


def _event_identity(item):
    if "event" not in item:
        return item.get("conversation_id")
    if item.get("event") == "init":
        return item.get("conversation_id")
    child = item.get(item.get("event")) if isinstance(item.get("event"), str) else None
    return child.get("conversation_id") if isinstance(child, dict) else None


def _file_identity(path):
    for _, item in itertools.islice(_objects(path), 256):
        identity = _identifier(_event_identity(item))
        if identity:
            return identity
    return None


def sessions(source: Path, limit: int = 100) -> list[dict]:
    source = Path(source)
    limit = max(0, min(int(limit), 1000))
    if not limit or not source.exists():
        return []
    if source.is_file():
        if source.suffix.lower() not in (".json", ".jsonl", ".ndjson"):
            return []
        try:
            identity = _file_identity(source)
        except (ValueError, OSError, UnicodeError):
            return []
        return [{"session_id": identity, "source": str(source)}] if identity else []
    if (source / TRANSCRIPT).is_file() and _identifier(source.name):
        return [{"session_id": source.name, "source": str(source / TRANSCRIPT)}]
    base = source / "brain" if (source / "brain").is_dir() else source
    found = []
    with os.scandir(base) as entries:
        for entry in itertools.islice(entries, MAX_DISCOVERY):
            if not entry.is_dir(follow_symlinks=False) or not _identifier(entry.name):
                continue
            path = Path(entry.path) / TRANSCRIPT
            if path.is_file() and not path.is_symlink():
                found.append({"session_id": entry.name, "source": str(path)})
                if len(found) >= limit:
                    break
    return sorted(found, key=lambda item: (item["session_id"], item["source"]))


def _failure(source, session_id, code, message):
    result = empty_result("antigravity", session_id, source)
    diagnostic(result, code, message)
    return result


def collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict:
    source = Path(source)
    if source.is_dir():
        source = source / TRANSCRIPT
    result = empty_result("antigravity", session_id, source)
    if not _identifier(session_id):
        raise ValueError("session_id must be a bounded identifier")
    end = parse_time(cutoff) if cutoff is not None else None
    if cutoff is not None and end is None:
        raise ValueError("cutoff must be an ISO timestamp with a timezone")
    if not source.is_file():
        return _failure(source, session_id, "source_missing", "The selected Antigravity source is missing or is not a regular file.")
    if source.suffix.lower() not in (".json", ".jsonl", ".ndjson"):
        return _failure(source, session_id, "unsupported_native_schema", "Binary and undocumented Antigravity stores are not decoded. Supply a saved official headless JSON/stream-json result or a structured report export.")
    # A documented transcript directory is an identity hint, never a format claim.
    if source.name == "transcript.jsonl" and source.parent.name == "logs" and source.parent.parent.name == ".system_generated":
        if source.parent.parent.parent.name != session_id:
            return _failure(source, session_id, "session_identity_mismatch", "The documented transcript directory does not match the requested conversation.")
    selected = None
    identity_seen = False
    saw_unknown = False
    saw_steps = False
    no_timestamps = False
    undated_snapshot = False
    reset = False
    previous = None
    invalid = False
    reported_duration = None
    invalid_duration = False
    incomplete = False
    timestamps = []
    try:
        for _, item in _objects(source):
            identity = _event_identity(item)
            if identity is not None and identity != session_id:
                return _failure(source, session_id, "mixed_session_source", "The source contains another conversation identity; no metrics were collected.")
            if identity == session_id:
                identity_seen = True
            envelope = _envelope(item)
            if not envelope:
                if item.get("event") == "step_update":
                    saw_steps = True
                elif item.get("event") != "init":
                    saw_unknown = True
                continue
            if envelope.get("conversation_id") != session_id:
                return _failure(source, session_id, "session_identity_mismatch", "The result envelope does not match the requested conversation.")
            if envelope.get("status") not in RESULT_STATUS or not isinstance(envelope.get("usage"), dict):
                saw_unknown = True
                continue
            # Official results currently have no event timestamps. Never use
            # filesystem mtime or fabricate a start/end from duration_seconds.
            stamp = parse_time(item.get("timestamp")) or parse_time(envelope.get("timestamp"))
            if end and ((stamp is None and strict_cutoff) or (stamp is not None and stamp > end)):
                no_timestamps = no_timestamps or stamp is None
                continue
            undated_snapshot = undated_snapshot or stamp is None
            result["event_count"] += 1
            if stamp:
                timestamps.append(stamp)
            usage = envelope["usage"]
            values = {"total": _number(usage.get("total_tokens")), "output": _number(usage.get("output_tokens"))}
            invalid = invalid or any(usage.get(key) is not None and _number(usage[key]) is None for key in ("input_tokens", "output_tokens", "thinking_tokens", "cache_read_tokens", "total_tokens"))
            if values["total"] is not None and values["output"] is not None and values["total"] < values["output"]:
                invalid = True
                continue
            turns = _number(envelope.get("num_turns"))
            if previous:
                if any(values[key] is not None and previous[0][key] is not None and values[key] < previous[0][key] for key in values) or (turns is not None and previous[1] is not None and turns < previous[1]):
                    reset = True
            previous = (values, turns)
            selected = values
            duration = envelope.get("duration_seconds")
            reported_duration = None
            if duration is not None:
                if type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 2**53 - 1:
                    reported_duration = duration
                else:
                    invalid_duration = True
    except (OSError, ValueError, UnicodeError, RecursionError):
        incomplete = True
    if not identity_seen:
        return _failure(source, session_id, "unsupported_native_schema", "The selected file has no supported Antigravity headless conversation identity. Native transcript formats are not assumed to match headless JSON; use an official saved result or structured export.")
    if selected:
        result["source_kind"] = "export"
        result["tokens"].update(selected)
        result["token_coverage"] = "partial" if any(value is not None for value in selected.values()) else "unavailable"
        diagnostic(result, "cumulative_result_snapshot", "The last official result envelope was retained; cumulative result snapshots and per-step usage were not summed. Whole-session coverage across restarted processes is not assumed.")
        diagnostic(result, "native_total_semantics", "total_tokens is preserved exactly as reported by Antigravity. Documented examples do not establish a consistent cache-inclusive input split; input and cache buckets stay unavailable. Thinking tokens are not added to output again.")
    else:
        diagnostic(result, "usage_result_missing", "No eligible official result with usage was found; step updates and context-window snapshots are not substituted for a cumulative result.")
    if timestamps:
        result["observed_until"] = iso_time(max(timestamps))
    diagnostic(result, "time_requires_timestamps", "Headless duration_seconds is cumulative wall-clock metadata without dated start/end events; it cannot form auditable active-time intervals. Human work is not inferred.")
    if reported_duration is not None:
        diagnostic(result, "reported_run_duration", f"Antigravity reports {reported_duration} seconds as reported run elapsed duration; no dated execution interval. This cumulative snapshot is not human work or pure model inference time.")
    if invalid_duration:
        diagnostic(result, "invalid_reported_run_duration", "Malformed, non-finite or out-of-range reported run duration was excluded; no execution interval was inferred.")
    diagnostic(result, "currency_charge_unavailable", "The supported result schema does not supply an attributed currency charge; quota fractions and AI credits are not converted to money.")
    if reset:
        diagnostic(result, "summary_counter_reset", "Cumulative counters or turn numbers decreased; only the last snapshot was kept. Earlier runs require separate attributed exports.")
    if saw_steps:
        diagnostic(result, "step_usage_not_added", "Per-step usage was excluded to prevent counting the same tokens again alongside cumulative results.")
    if no_timestamps:
        diagnostic(result, "cutoff_unverifiable", "The requested historical cutoff cannot be applied to undated result exports; those exports were excluded. Use an explicitly dated structured export for historical reports.")
    if undated_snapshot:
        diagnostic(result, "undated_export_snapshot", "The export has no native result timestamp. Its counters are an undated snapshot read for this report; no start time, observation time or historical coverage is invented.")
    if saw_unknown:
        diagnostic(result, "unknown_events", "Unrecognized records were ignored; their metric coverage is unknown.")
    if invalid:
        diagnostic(result, "invalid_counters", "Malformed, inconsistent or out-of-range counters were excluded.")
    if incomplete:
        diagnostic(result, "source_incomplete", "Reading stopped at malformed data or a resource limit; retained snapshot coverage is partial.")
    return result
