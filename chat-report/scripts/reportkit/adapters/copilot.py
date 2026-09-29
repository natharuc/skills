"""Read GitHub Copilot CLI events; IDE chat stores use a different schema.

Only whitelisted numeric telemetry and lifecycle timestamps leave this module.
See references/copilot-antigravity.md for supported schema and accounting limits.
"""
from __future__ import annotations

import itertools
import math
import os
import re
from pathlib import Path

from reportkit.common import TOKEN_KEYS, diagnostic, empty_result, iso_time, parse_time, read_jsonl

MAX_DISCOVERY = 5000
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+() -]{0,199}\Z")


def roots(home: Path, env: dict, system: str) -> list[Path]:
    """The official CLI uses one home-relative root on all three platforms."""
    return [Path(env.get("COPILOT_HOME") or home / ".copilot") / "session-state"]


def _identifier(value):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value > 2**53 - 1 or int(value) != value:
        return None
    return int(value)


def _identity(path: Path):
    """A persisted session.start proves identity, even for a copied capture."""
    for _, item in itertools.islice(read_jsonl(path), 256):
        if item.get("type") == "session.start" and isinstance(item.get("data"), dict):
            data = item["data"]
            session_id = _identifier(data.get("sessionId"))
            if session_id:
                return session_id, iso_time(data.get("startTime"))
    return None, None


def sessions(source: Path, limit: int = 100) -> list[dict]:
    """Inspect a bounded list of session-state/<id>/events.jsonl candidates."""
    source = Path(source)
    limit = max(0, min(int(limit), 1000))
    if not limit or not source.exists():
        return []
    if source.is_file():
        candidates = [source]
    elif (source / "events.jsonl").is_file():
        candidates = [source / "events.jsonl"]
    else:
        base = source / "session-state" if (source / "session-state").is_dir() else source
        candidates = []
        with os.scandir(base) as entries:
            for entry in itertools.islice(entries, MAX_DISCOVERY):
                if entry.is_dir(follow_symlinks=False) and _identifier(entry.name):
                    path = Path(entry.path) / "events.jsonl"
                    if path.is_file() and not path.is_symlink():
                        candidates.append(path)
    found = []
    for path in sorted(candidates, key=str):
        try:
            identity, start = _identity(path)
        except (OSError, ValueError, UnicodeError):
            continue
        if not identity:
            continue
        if path.name == "events.jsonl" and path.parent.parent.name == "session-state" and identity != path.parent.name:
            continue
        found.append({"session_id": identity, "source": str(path), "started_at": start})
        if len(found) >= limit:
            break
    return found


def _usage(data):
    """Preserve fields whose disjoint meaning is documented.

    inputTokens is not documented as cache-inclusive across every provider. The
    input/cache-write split therefore stays unknown. We never sum it as a total.
    """
    values = {key: None for key in TOKEN_KEYS}
    values["output"] = _number(data.get("outputTokens"))
    values["cache_read"] = _number(data.get("cacheReadTokens"))
    return values


def _merge(values):
    values = list(values)
    result = {key: None for key in TOKEN_KEYS}
    for key in TOKEN_KEYS:
        available = [entry[key] for entry in values if entry[key] is not None]
        if available:
            result[key] = sum(available)
    return result


def _blank_error(source, session_id, code, message):
    result = empty_result("github-copilot", session_id, source)
    diagnostic(result, code, message)
    return result


def collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict:
    source = Path(source)
    if source.is_dir():
        source = source / "events.jsonl"
    result = empty_result("github-copilot", session_id, source)
    end = parse_time(cutoff) if cutoff is not None else None
    if cutoff is not None and end is None:
        raise ValueError("cutoff must be an ISO timestamp with a timezone")
    if not _identifier(session_id):
        raise ValueError("session_id must be a bounded identifier")
    if not source.is_file():
        return _blank_error(source, session_id, "source_missing", "The selected Copilot CLI event file is missing or is not a regular file.")
    if source.suffix.lower() not in (".jsonl", ".ndjson"):
        return _blank_error(source, session_id, "unsupported_native_schema", "This adapter reads Copilot CLI JSONL events, not VS Code or IDE chat storage; use a supported exported report envelope for other surfaces.")
    try:
        identity, start = _identity(source)
    except (OSError, ValueError, UnicodeError):
        return _blank_error(source, session_id, "source_unreadable", "The selected event file could not be read as bounded UTF-8 JSONL.")
    if identity != session_id:
        return _blank_error(source, session_id, "session_identity_mismatch", "A matching session.start event is required; the selected file did not prove the requested identity.")
    if source.name == "events.jsonl" and source.parent.parent.name == "session-state" and source.parent.name != session_id:
        return _blank_error(source, session_id, "session_identity_mismatch", "The session-state directory and event identity disagree.")
    result["started_at"] = start if not end or not parse_time(start) or parse_time(start) <= end else None
    seen = set()
    requests = {}
    messages = {}
    open_turns = {}
    completed_turns = set()
    latest_summary = None
    prior_summary_totals = None
    summary_reset = False
    resume_generation = 0
    intervals = []
    timestamps = []
    unsupported_time = False
    child_turns = False
    invalid_numbers = False
    usage_missing_ids = False
    context_usage = False
    source_incomplete = False
    last_activity = None
    try:
        for line, event in read_jsonl(source):
            data = event.get("data")
            if not isinstance(data, dict):
                continue
            kind = event.get("type")
            if kind == "session.start" and data.get("sessionId") != session_id:
                return _blank_error(source, session_id, "mixed_session_source", "The source contains different session identities; no metrics were collected.")
            if event.get("sessionId") not in (None, session_id):
                return _blank_error(source, session_id, "mixed_session_source", "The source contains a different explicit session identity; no metrics were collected.")
            stamp = parse_time(event.get("timestamp"))
            if end and (stamp is None or stamp > end):
                unsupported_time = unsupported_time or stamp is None
                continue
            event_id = _identifier(event.get("id"))
            if event_id:
                if event_id in seen:
                    continue
                seen.add(event_id)
            result["event_count"] += 1
            if stamp:
                timestamps.append(stamp)
            if kind == "session.resume":
                resume_generation += 1
                # An unfinished turn may have been abandoned during resume.
                open_turns.clear()
            if kind in ("assistant.turn_start", "assistant.message", "assistant.usage"):
                if stamp:
                    last_activity = stamp if last_activity is None else max(last_activity, stamp)
            if kind in ("assistant.turn_start", "assistant.turn_end"):
                # Main turns enclose subagent activity. Emitting both double-counts it.
                if event.get("agentId") or data.get("parentToolCallId"):
                    child_turns = True
                    continue
                turn_id = _identifier(data.get("turnId"))
                if not turn_id or not stamp:
                    unsupported_time = True
                    continue
                key = (resume_generation, turn_id)
                if kind == "assistant.turn_start":
                    if key not in completed_turns:
                        open_turns.setdefault(key, stamp)
                elif key in open_turns:
                    begin = open_turns.pop(key)
                    if begin <= stamp and key not in completed_turns:
                        intervals.append({"start": iso_time(begin), "end": iso_time(stamp), "agent_id": session_id})
                        completed_turns.add(key)
            elif kind == "assistant.usage":
                request_id = _identifier(data.get("apiCallId")) or _identifier(data.get("providerCallId")) or event_id
                if not request_id:
                    usage_missing_ids = True
                    continue
                values = _usage(data)
                invalid_numbers = invalid_numbers or any(data.get(k) is not None and _number(data[k]) is None for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"))
                model = data.get("model")
                model = model if isinstance(model, str) and MODEL.fullmatch(model) else None
                requests.setdefault(request_id, (values, model))
            elif kind == "assistant.message":
                # Durable message-level output is a fallback, never added to usage.
                message_id = _identifier(data.get("messageId"))
                output = _number(data.get("outputTokens"))
                if message_id and output is not None:
                    messages.setdefault(message_id, output)
            elif kind == "session.shutdown" and not event.get("agentId"):
                models = data.get("modelMetrics")
                if isinstance(models, dict) and models:
                    normalized = []
                    for model, metric in models.items():
                        if not isinstance(model, str) or not MODEL.fullmatch(model) or not isinstance(metric, dict) or not isinstance(metric.get("usage"), dict):
                            continue
                        normalized.append({"model": model, "tokens": _usage(metric["usage"]), "coverage": "partial"})
                    if normalized:
                        totals = _merge(entry["tokens"] for entry in normalized)
                        if prior_summary_totals and any(totals[k] is not None and prior_summary_totals[k] is not None and totals[k] < prior_summary_totals[k] for k in TOKEN_KEYS):
                            summary_reset = True
                        prior_summary_totals = totals
                        latest_summary = (normalized, totals, stamp)
            elif kind == "session.usage_info":
                context_usage = True
    except (OSError, ValueError, UnicodeError):
        source_incomplete = True
    if timestamps:
        result["observed_until"] = iso_time(max(timestamps))
    result["intervals"] = intervals
    result["time_basis"] = "gross_turn" if intervals else "none"
    result["time_coverage"] = "partial" if intervals else "unavailable"
    if latest_summary:
        result["model_usage"], result["tokens"], summary_at = latest_summary
        diagnostic(result, "shutdown_snapshot", "Tokens use the last durable session.shutdown model summary; cumulative summaries and request events were not added together.")
        if last_activity and (summary_at is None or last_activity > summary_at):
            diagnostic(result, "usage_after_snapshot", "Activity continues after the last shutdown summary; its token counts cover only the earlier snapshot.")
    elif requests:
        result["tokens"] = _merge(entry[0] for entry in requests.values())
        groups = {}
        for values, model in requests.values():
            if model:
                groups.setdefault(model, []).append(values)
        result["model_usage"] = [{"model": model, "tokens": _merge(values), "coverage": "partial"} for model, values in sorted(groups.items())]
        diagnostic(result, "captured_usage_partial", "Usage reflects deduplicated captured assistant.usage events; those events are normally ephemeral, so whole-session coverage is not assumed.")
    elif messages:
        result["tokens"]["output"] = sum(messages.values())
        diagnostic(result, "message_output_only", "Only durable assistant message output counters were available; input usage and other requests may be missing.")
    else:
        diagnostic(result, "usage_not_persisted", "No supported usage summary or captured API usage was found. Copilot CLI assistant.usage events are normally ephemeral; missing telemetry is not zero usage.")
    if any(value is not None for value in result["tokens"].values()):
        result["token_coverage"] = "partial"
        diagnostic(result, "input_cache_semantics", "Input and cache-write counters lack a verified provider-independent disjoint mapping; input_uncached, cache-write buckets and a computed total remain unavailable. Reasoning is already part of output and is not added again.")
    diagnostic(result, "billing_units_not_money", "Copilot cost multipliers, premium requests and nano-AI units are not an attributed currency charge; this adapter does not convert them to money.")
    if intervals:
        diagnostic(result, "gross_turn_time", "Paired main-agent turn timestamps include tool execution and possible approval waits; they are gross turn time, not human work or pure model inference.")
    if child_turns:
        diagnostic(result, "child_spans_excluded", "Subagent turn spans were excluded because main-agent spans may already enclose them.")
    if open_turns:
        diagnostic(result, "unfinished_turns", "Open turns without matching end events were excluded from measured intervals.")
    if summary_reset:
        diagnostic(result, "summary_counter_reset", "Successive shutdown summaries decreased; only the last snapshot was retained and session coverage is partial.")
    if usage_missing_ids:
        diagnostic(result, "usage_identity_missing", "Usage events without a request or event identifier were excluded to avoid duplicate accounting.")
    if unsupported_time:
        diagnostic(result, "timestamps_missing", "Some events lacked usable timestamps; they could not define intervals or pass a requested cutoff.")
    if invalid_numbers:
        diagnostic(result, "invalid_counters", "Unsupported or invalid numeric counters were excluded.")
    if context_usage:
        diagnostic(result, "context_window_not_usage", "session.usage_info describes the context window and was excluded from consumed-token accounting.")
    if source_incomplete:
        diagnostic(result, "source_incomplete", "Reading stopped at malformed data or a resource limit; all retained results have partial coverage.")
    return result
