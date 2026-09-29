"""Claude Code transcript / timestamped Agent SDK JSONL adapter (stdlib only)."""
from __future__ import annotations

import os
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from reportkit.common import TOKEN_KEYS, diagnostic, empty_result, iso_time, parse_time, read_jsonl

_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
MAX_SCAN = 5000


def roots(home: Path, env: dict, system: str) -> list[Path]:
    return [Path(env.get("CLAUDE_CONFIG_DIR") or home / ".claude").expanduser() / "projects"]


def _files(source):
    if source.is_file():
        if source.suffix.lower() == ".jsonl":
            yield source
        return
    if not source.is_dir():
        return
    scanned = 0
    # Known project directory layout only. Do not recursively include child-agent logs.
    for parent, dirs, names in os.walk(source, followlinks=False):
        depth = len(Path(parent).relative_to(source).parts)
        dirs[:] = sorted(d for d in dirs if not (Path(parent) / d).is_symlink()) if depth < 1 else []
        scanned += len(dirs) + len(names)
        if scanned > MAX_SCAN:
            return
        for name in sorted(names):
            path = Path(parent) / name
            if name.endswith(".jsonl") and not name.startswith("agent-") and not path.is_symlink():
                yield path


def _identity(row):
    return row.get("sessionId", row.get("session_id"))


def sessions(source: Path, limit: int = 100) -> list[dict]:
    if not 1 <= limit <= 1000:
        raise ValueError("Session limit must be between 1 and 1000.")
    found = []
    for path in _files(Path(source)):
        try:
            for number, row in read_jsonl(path):
                if number > 64:
                    break
                sid = _identity(row)
                if isinstance(sid, str) and _ID.fullmatch(sid):
                    found.append({"session_id": sid, "source": str(path),
                                  "started_at": iso_time(row.get("timestamp"))})
                    break
        except (OSError, ValueError):
            continue
        if len(found) >= limit:
            break
    return found


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1 else None


def _normalize(raw, output_reliable=True, camel=False):
    if not isinstance(raw, dict):
        return None
    names = (("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens") if camel else
             ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"))
    inp, read, write, output = [_count(raw.get(k)) for k in names]
    if not output_reliable:
        output = None
    tokens = {key: None for key in TOKEN_KEYS}
    tokens.update(input_uncached=inp, cache_read=read, output=output)
    split = raw.get("cache_creation")
    short = _count(split.get("ephemeral_5m_input_tokens")) if isinstance(split, dict) else None
    long = _count(split.get("ephemeral_1h_input_tokens")) if isinstance(split, dict) else None
    if short is not None and long is not None and (write is None or short + long == write):
        tokens["cache_write_short"], tokens["cache_write_long"] = short, long
        write = short + long
    elif write == 0:
        tokens["cache_write_short"] = tokens["cache_write_long"] = 0
    if all(value is not None for value in (inp, read, write, output)):
        tokens["total"] = inp + read + write + output
    return tokens if any(v is not None for v in tokens.values()) else None


def _sum_tokens(items):
    rows = list(items)
    return {key: sum(row[key] for row in rows if row[key] is not None)
            if rows and all(row[key] is not None for row in rows) else None for key in TOKEN_KEYS}


def _money(value):
    if isinstance(value, bool) or not isinstance(value, (str, float, int, Decimal)):
        return None
    try:
        amount = Decimal(str(value))
        return format(amount, "f") if amount.is_finite() and 0 <= amount <= Decimal("1e12") else None
    except InvalidOperation:
        return None


def collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict:
    source = Path(source)
    result = empty_result("claude", session_id, source)
    if not _ID.fullmatch(session_id):
        raise ValueError("Invalid session identifier.")
    bound = parse_time(cutoff) if cutoff is not None else None
    if cutoff is not None and bound is None:
        raise ValueError("Cutoff must be an ISO timestamp with timezone.")
    if source.suffix.lower() != ".jsonl" or not source.is_file():
        diagnostic(result, "source_unavailable", "Select one existing Claude Code or Agent SDK JSONL file.")
        return result
    matched = False
    messages = {}
    aliases = {}
    latest_models = None
    model_snapshot_stale = False
    latest_cost = None
    result_turns = {}
    result_seen = set()
    timed_seen = set()
    assistant_after_result = False
    has_results = False
    for number, row in read_jsonl(source):
        sid = _identity(row)
        if sid is not None and sid != session_id:
            raise ValueError("The source contains a different session identity; select an unmixed session file.")
        if sid == session_id:
            matched = True
        elif row.get("type") in ("assistant", "result", "user"):
            diagnostic(result, "unattributed_record", "A message without exact session identity was excluded.")
            continue
        when = parse_time(row.get("timestamp"))
        if bound is not None and ((when is None and strict_cutoff) or (when is not None and when > bound)):
            if when is None:
                diagnostic(result, "undated_event_skipped", "An undated record was excluded from the cutoff report.")
            continue
        if when is None and bound is not None:
            diagnostic(result, "undated_snapshot", "An explicitly selected undated record was retained; its period and cutoff cannot be verified. Use strict cutoff to exclude it.")
        result["event_count"] += 1
        if when is not None:
            if result["started_at"] is None or when < parse_time(result["started_at"]):
                result["started_at"] = iso_time(when)
            if result["observed_until"] is None or when > parse_time(result["observed_until"]):
                result["observed_until"] = iso_time(when)
        kind = row.get("type")
        if row.get("isCompactSummary") or (kind == "system" and row.get("subtype") == "compact_boundary"):
            diagnostic(result, "compacted_history", "Compaction is present; missing source history cannot be reconstructed and observations remain partial.")
        if row.get("isSidechain") or row.get("parent_tool_use_id") or row.get("teamName"):
            diagnostic(result, "child_records_excluded", "Child or sidechain records were excluded from main-loop message accounting; cumulative modelUsage may include child work.")
            continue
        if kind == "assistant":
            message = row.get("message") if isinstance(row.get("message"), dict) else row
            raw = message.get("usage")
            mid = message.get("id", row.get("message_id"))
            request = row.get("requestId", row.get("request_id"))
            valid_aliases = [label + value for label, value in (("message:", mid), ("request:", request))
                             if isinstance(value, str) and _ID.fullmatch(value)]
            usage = _normalize(raw, output_reliable=False)
            if usage is None:
                continue
            if not valid_aliases:
                diagnostic(result, "missing_usage_identity", "Usage without a message or request identifier was excluded to prevent duplicate counting.")
                continue
            key = next((aliases[a] for a in valid_aliases if a in aliases), valid_aliases[0])
            if any(a in aliases and aliases[a] != key for a in valid_aliases):
                diagnostic(result, "conflicting_usage_identity", "Conflicting message/request aliases were excluded.")
                continue
            for alias in valid_aliases:
                aliases[alias] = key
            prior = messages.get(key)
            candidate = message.get("model")
            model = candidate if isinstance(candidate, str) and _MODEL.fullmatch(candidate) else None
            if prior:
                if any(usage[k] is not None and prior["tokens"][k] is not None and usage[k] < prior["tokens"][k]
                       for k in TOKEN_KEYS):
                    diagnostic(result, "usage_snapshot_correction", "A repeated request snapshot decreased; the later explicit counters supersede earlier ones.")
                usage = {k: usage[k] if usage[k] is not None else prior["tokens"][k] for k in TOKEN_KEYS}
                model = model or prior["model"]
            messages[key] = {"tokens": usage, "model": model}
            assistant_after_result = has_results
        elif kind == "result":
            has_results = True
            rid = row.get("uuid")
            key = rid if isinstance(rid, str) and _ID.fullmatch(rid) else None
            if key is not None and key in result_seen:
                continue
            if key is not None:
                result_seen.add(key)
            assistant_after_result = False
            model_snapshot_stale = latest_models is not None
            models_raw = row.get("modelUsage", row.get("model_usage"))
            if isinstance(models_raw, dict) and models_raw:
                normalized = []
                for model, raw in models_raw.items():
                    if isinstance(model, str) and _MODEL.fullmatch(model):
                        tokens = _normalize(raw, camel=True)
                        if tokens:
                            normalized.append({"model": model, "tokens": tokens, "coverage": "partial"})
                if normalized and len(normalized) == len(models_raw):
                    candidate = _sum_tokens(item["tokens"] for item in normalized)
                    previous = _sum_tokens(item["tokens"] for item in latest_models) if latest_models else None
                    if previous and previous["total"] is not None and candidate["total"] is not None and candidate["total"] < previous["total"]:
                        diagnostic(result, "cumulative_reset", "Cumulative result counters decreased; only the latest segment is reported without guessing earlier reset or resume semantics.")
                    if row.get("is_error") and candidate["total"] == 0 and previous and previous["total"]:
                        diagnostic(result, "zero_error_result", "A zero-valued error result did not replace previously observed usage.")
                    else:
                        latest_models = normalized
                        model_snapshot_stale = False
            usage = _normalize(row.get("usage"))
            if usage:
                if key is None:
                    diagnostic(result, "result_without_id", "A result without a UUID cannot be summed with other turns; only that latest result scope is available.")
                    result_turns.clear()
                    result_turns["unidentified-latest"] = usage
                else:
                    if "unidentified-latest" in result_turns:
                        result_turns.clear()
                    result_turns[key] = usage
            cost = _money(row.get("total_cost_usd"))
            if cost is not None:
                if row.get("is_error") and Decimal(cost) == 0 and latest_cost is not None and Decimal(latest_cost) > 0:
                    diagnostic(result, "zero_error_cost", "A zero-valued error result did not replace an earlier cost estimate.")
                else:
                    latest_cost = cost
            # Explicit SDK duration plus timestamp is a gross query span, never human work.
            duration = _count(row.get("duration_ms"))
            if duration is not None and when is not None and duration <= 365 * 86400 * 1000 and key is not None:
                begin = when - timedelta(milliseconds=duration)
                result["intervals"].append({"start": iso_time(begin), "end": iso_time(when), "agent_id": session_id})
        elif kind == "system" and row.get("subtype") == "turn_duration":
            duration = _count(row.get("durationMs"))
            tid = row.get("uuid")
            if duration is not None and when is not None and duration <= 365 * 86400 * 1000 and isinstance(tid, str) and _ID.fullmatch(tid) and tid not in timed_seen:
                timed_seen.add(tid)
                result["intervals"].append({"start": iso_time(when - timedelta(milliseconds=duration)), "end": iso_time(when), "agent_id": session_id})
    if not matched:
        raise ValueError("No record verifies the selected session identity.")
    if latest_models is not None:
        result["tokens"] = _sum_tokens(item["tokens"] for item in latest_models)
        result["model_usage"] = latest_models
        diagnostic(result, "native_model_snapshot", "Tokens use the latest cumulative modelUsage result, including reported subagent work; snapshots are never added together. Resume/version boundaries remain partial.")
        if model_snapshot_stale:
            diagnostic(result, "model_snapshot_stale", "A later result lacks a usable cumulative model snapshot; the earlier model totals are retained as partial observations.")
        if assistant_after_result:
            diagnostic(result, "usage_after_snapshot", "Additional assistant activity follows the last cumulative result; this later activity is excluded until a new result is available.")
    elif result_turns:
        result["tokens"] = _sum_tokens(result_turns.values())
        diagnostic(result, "result_main_loop", "Deduplicated result usage covers observed main-loop turns only; unrecorded earlier turns and subagents are excluded.")
        if assistant_after_result:
            diagnostic(result, "usage_after_snapshot", "An unfinished turn follows the recorded result usage and is excluded.")
    elif messages:
        result["tokens"] = _sum_tokens(item["tokens"] for item in messages.values())
        diagnostic(result, "assistant_output_unverified", "Input/cache usage is deduplicated by request/message ID. Per-step output counters can be placeholders, so output and total remain unknown without a result.")
        grouped = {}
        for entry in messages.values():
            if entry["model"]:
                grouped.setdefault(entry["model"], []).append(entry["tokens"])
        if all(item["model"] for item in messages.values()):
            result["model_usage"] = [{"model": model, "tokens": _sum_tokens(rows), "coverage": "partial"} for model, rows in sorted(grouped.items())]
    if any(v is not None for v in result["tokens"].values()):
        result["token_coverage"] = "partial"
    else:
        diagnostic(result, "usage_unavailable", "No supported, attributable usage counters were found.")
    if latest_cost is not None:
        result["billing"] = [{"currency": "USD", "amount": latest_cost, "kind": "reference", "coverage": "partial"}]
        diagnostic(result, "sdk_cost_estimate", "The latest SDK cost is a client-side pricing estimate, not an authoritative bill; it can include subagent work and restored session spend.")
    if result["intervals"]:
        result["time_basis"] = "gross_turn"
        result["time_coverage"] = "partial"
        diagnostic(result, "gross_turn_time", "Recorded durations include tool execution and possible waits. Overlapping spans for this agent are unioned; no human attention is inferred.")
    return result
