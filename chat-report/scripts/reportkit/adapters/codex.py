"""Read bounded, explicitly selected Codex rollout JSONL without transcript output."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from reportkit.common import TOKEN_KEYS, diagnostic, empty_result, iso_time, parse_time, read_jsonl

MAX_SCAN = 5000
_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


def roots(home: Path, env: dict, system: str) -> list[Path]:
    base = Path(env.get("CODEX_HOME") or home / ".codex").expanduser()
    return [base / "sessions", base / "archived_sessions"]


def _files(source: Path):
    if source.is_file():
        if source.suffix.lower() == ".jsonl":
            yield source
        return
    if not source.is_dir():
        return
    scanned = 0
    # Native active storage is sessions/YYYY/MM/DD; archived files may be flat.
    for parent, dirs, names in os.walk(source, followlinks=False):
        depth = len(Path(parent).relative_to(source).parts)
        dirs[:] = sorted(d for d in dirs if not (Path(parent) / d).is_symlink()) if depth < 3 else []
        scanned += len(dirs) + len(names)
        if scanned > MAX_SCAN:
            return
        for name in sorted(names):
            path = Path(parent) / name
            if name.endswith(".jsonl") and not path.is_symlink():
                yield path


def _header(path: Path):
    for index, row in read_jsonl(path):
        if index > 32:
            return None
        if row.get("type") == "session_meta" and isinstance(row.get("payload"), dict):
            return row["payload"]
    return None


def sessions(source: Path, limit: int = 100) -> list[dict]:
    if not 1 <= limit <= 1000:
        raise ValueError("Session limit must be between 1 and 1000.")
    found = []
    for path in _files(Path(source)):
        try:
            meta = _header(path)
        except (OSError, ValueError):
            continue
        if meta and isinstance(meta.get("id"), str) and _ID.fullmatch(meta["id"]):
            found.append({"session_id": meta["id"], "source": str(path),
                          "started_at": iso_time(meta.get("timestamp"))})
        if len(found) >= limit:
            break
    return found


def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 2**63 - 1 else None


def _usage(raw):
    if not isinstance(raw, dict):
        return None
    fields = {key: _count(raw.get(key)) for key in
              ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "total_tokens")}
    if not any(value is not None for value in fields.values()):
        return None
    inp, cache, write = (fields[k] for k in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens"))
    if inp is not None and cache is not None and cache > inp:
        return None
    out = {key: None for key in TOKEN_KEYS}
    out.update(cache_read=cache, output=fields["output_tokens"], total=fields["total_tokens"])
    # A nonzero write count has no verified disjoint-input/TTL mapping in this adapter.
    if inp is not None and cache is not None and write in (None, 0):
        out["input_uncached"] = inp - cache
    if write == 0:
        out["cache_write_short"] = out["cache_write_long"] = 0
    return out


def _event_time(value):
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    return parse_time(value)


def collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict:
    source = Path(source)
    result = empty_result("codex", session_id, source)
    if not _ID.fullmatch(session_id):
        raise ValueError("Invalid session identifier.")
    bound = parse_time(cutoff) if cutoff is not None else None
    if cutoff is not None and bound is None:
        raise ValueError("Cutoff must be an ISO timestamp with timezone.")
    if source.suffix.lower() != ".jsonl" or not source.is_file():
        diagnostic(result, "source_unavailable", "Select one existing Codex rollout JSONL file.")
        return result
    meta = _header(source)
    if not meta or meta.get("id") != session_id:
        raise ValueError("The rollout metadata does not match the selected session.")
    result["started_at"] = iso_time(meta.get("timestamp"))
    if bound is not None and result["started_at"] and parse_time(result["started_at"]) > bound:
        result["started_at"] = None
    ancestry = any(meta.get(k) is not None for k in
                   ("forked_from_id", "history_base", "subagent_history_start_ordinal", "parent_thread_id"))
    if ancestry:
        diagnostic(result, "inherited_history_unsupported", "This rollout inherits or forks history; token ownership and copied turn boundaries cannot be separated safely by this adapter.")
    latest = None
    previous_native = None
    starts = {}
    closed = set()
    models = set()
    current_model = None
    reset = False
    known_usage_models = set()
    for _, row in read_jsonl(source):
        if row.get("type") == "session_meta":
            owner = row.get("payload", {})
            if not isinstance(owner, dict) or owner.get("id") != session_id:
                raise ValueError("Conflicting session metadata in rollout.")
        when = parse_time(row.get("timestamp"))
        if bound is not None and ((when is None and strict_cutoff) or (when is not None and when > bound)):
            if when is None:
                diagnostic(result, "undated_event_skipped", "An undated record was excluded from the cutoff report.")
            continue
        if when is None and bound is not None:
            diagnostic(result, "undated_snapshot", "An explicitly selected undated record was retained; its period and cutoff cannot be verified. Use strict cutoff to exclude it.")
        result["event_count"] += 1
        if when is not None and (result["observed_until"] is None or when > parse_time(result["observed_until"])):
            result["observed_until"] = iso_time(when)
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        kind = row.get("type")
        if kind == "turn_context":
            candidate = payload.get("model")
            current_model = candidate if isinstance(candidate, str) and _MODEL.fullmatch(candidate) else None
            if current_model:
                models.add(current_model)
        if kind == "compacted" or (kind == "event_msg" and payload.get("type") in ("context_compacted", "thread_rolled_back")):
            diagnostic(result, "history_boundary", "Compaction or rollback appears in the rollout; retained usage is an observed subtotal and missing history is not reconstructed.")
        if kind != "event_msg":
            continue
        event = payload.get("type")
        if event in ("task_started", "turn_started") and not ancestry:
            turn = payload.get("turn_id")
            at = _event_time(payload.get("started_at")) or when
            if isinstance(turn, str) and at is not None:
                starts.setdefault(turn, at)
        elif event in ("task_complete", "turn_complete", "turn_aborted") and not ancestry:
            turn = payload.get("turn_id")
            if isinstance(turn, str) and turn not in closed:
                end = _event_time(payload.get("completed_at")) or when
                begin = _event_time(payload.get("started_at")) or starts.get(turn)
                if begin is not None and end is not None and begin <= end and (bound is None or end <= bound):
                    result["intervals"].append({"start": iso_time(begin), "end": iso_time(end), "agent_id": session_id})
                    closed.add(turn)
                    starts.pop(turn, None)
        elif event == "token_count" and not ancestry:
            info = payload.get("info")
            if not isinstance(info, dict):
                continue
            raw = info.get("total_token_usage")
            usage = _usage(raw)
            if usage is None:
                diagnostic(result, "unsupported_usage", "A token snapshot had absent or invalid counters and was excluded.")
                continue
            # Core can fill the context window with an artificial total after overflow.
            if (usage["total"] and isinstance(raw, dict)
                and all(_count(raw.get(k)) == 0 for k in ("input_tokens", "cached_input_tokens", "output_tokens"))):
                diagnostic(result, "context_capacity_snapshot", "A total-only context-capacity snapshot was excluded because it is not measured token consumption.")
                continue
            if previous_native is not None:
                shared = [k for k in TOKEN_KEYS if usage[k] is not None and previous_native[k] is not None]
                if any(usage[k] < previous_native[k] for k in shared):
                    reset = True
                    known_usage_models.clear()
                    diagnostic(result, "cumulative_reset", "Cumulative counters decreased; only the latest segment is reported and segments are not added without a verified reset boundary.")
            latest, previous_native = usage, usage
            known_usage_models.add(current_model)
            if _count(raw.get("cache_write_input_tokens")) not in (None, 0):
                diagnostic(result, "cache_write_unsplit", "Native cache-write usage lacks a verified TTL/disjoint-input mapping; the native total is preserved and those categories remain unknown.")
    if latest is not None:
        result["tokens"] = latest
        result["token_coverage"] = "partial"
        diagnostic(result, "native_snapshot", "Usage is the latest observed cumulative snapshot, never a sum of snapshots; unrecorded requests and external child sessions may be absent.")
        if len(known_usage_models) == 1 and None not in known_usage_models and len(models) == 1 and not reset:
            result["model_usage"] = [{"model": next(iter(known_usage_models)), "tokens": dict(latest), "coverage": "partial"}]
    else:
        diagnostic(result, "usage_unavailable", "No attributable measured token snapshot was found in the selected rollout.")
    if result["intervals"]:
        result["time_basis"] = "gross_turn"
        result["time_coverage"] = "partial"
        diagnostic(result, "gross_turn_time", "Explicit turn spans include tool execution and possible approval waits; they do not measure human attention or pure model compute.")
    if starts:
        diagnostic(result, "open_turn", "A turn has no observed completion; its unfinished span was excluded.")
    return result
