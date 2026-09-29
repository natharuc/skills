"""Bounded, read-only adapter for Cursor Desktop's observed local SQLite schema.

The schema is reverse-engineered, not a public Cursor API. Only recognized
per-bubble counters are totals; other candidate fields are never interpreted.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
import time

from reportkit.common import diagnostic, empty_result, iso_time, parse_time

MAX_RECORDS = 10000
MAX_VALUE = 4 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,180}\Z")


def roots(home: Path, env: dict, system: str) -> list[Path]:
    """Return only the current OS's known desktop database location."""
    if system == "Windows":
        user = Path(env.get("APPDATA") or home / "AppData/Roaming") / "Cursor/User"
    elif system == "Darwin":
        user = home / "Library/Application Support/Cursor/User"
    else:
        user = Path(env.get("XDG_CONFIG_HOME") or home / ".config") / "Cursor/User"
    return [user / "globalStorage/state.vscdb"]


@contextmanager
def _database(source):
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError("Cursor database not found")
    con = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        con.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 15
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        con.execute("BEGIN")  # Consistent snapshot, including the live WAL.
        yield con
    finally:
        con.close()


def _columns(con, table):
    # table is always one of the hard-coded names below.
    return {r[1] for r in con.execute('PRAGMA table_info("' + table + '")')}


def _time(value, milliseconds=False):
    if milliseconds and type(value) in (int, float):
        try:
            if not math.isfinite(value):
                return None
            return datetime.fromtimestamp(value / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    return parse_time(value) if isinstance(value, str) else None


def _json(raw):
    if not isinstance(raw, (str, bytes)):
        raise ValueError("Unsupported SQLite value")
    def invalid_constant(_):
        raise ValueError("Nonfinite number")
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite number")
        return result
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    result = json.loads(raw, parse_constant=invalid_constant, parse_float=number,
                        object_pairs_hook=pairs)
    if not isinstance(result, dict):
        raise ValueError("Record is not an object")
    return result


def sessions(source: Path, limit: int = 100) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= MAX_RECORDS:
        raise ValueError("Session limit must be between 1 and 10000")
    found = []
    try:
        with _database(source) as con:
            if not {"key", "value"} <= _columns(con, "cursorDiskKV"):
                return []
            columns = _columns(con, "composerHeaders")
            if "composerId" in columns:
                created = 'h."createdAt"' if "createdAt" in columns else "NULL"
                query = ('SELECT h."composerId", ' + created + ' FROM composerHeaders h '
                         'WHERE EXISTS (SELECT 1 FROM cursorDiskKV b WHERE '
                         'b.key >= \'bubbleId:\' || h.composerId || \':\' AND '
                         'b.key < \'bubbleId:\' || h.composerId || \':\' || char(65535)) '
                         'ORDER BY h.composerId LIMIT ?')
                rows = con.execute(query, (limit,))
            else:
                # Older stores: discover composer keys without parsing payloads.
                rows = ((r[0][13:], None) for r in con.execute(
                    'SELECT key FROM cursorDiskKV WHERE key >= ? AND key < ? '
                    'ORDER BY key LIMIT ?', ('composerData:', 'composerData:\uffff', limit)))
            for cid, created in rows:
                if not isinstance(cid, str) or not ID.fullmatch(cid):
                    continue
                item = {"session_id": cid, "source": str(Path(source))}
                started = _time(created, milliseconds=True)
                if started:
                    item["started_at"] = iso_time(started)
                found.append(item)
    except (sqlite3.Error, OSError, ValueError):
        return []
    return found


def collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict:
    if not isinstance(session_id, str) or not ID.fullmatch(session_id):
        raise ValueError("An exact, valid Cursor composer ID is required")
    until = parse_time(cutoff) if cutoff is not None else None
    if cutoff is not None and until is None:
        raise ValueError("Cutoff must be an ISO timestamp with timezone")
    result = empty_result("cursor", session_id, source)
    seen_codes = set()
    def note(code, message):
        if code not in seen_codes:
            diagnostic(result, code, message)
            seen_codes.add(code)
    timestamps = []
    starts = []
    accepted_usage = []
    exact = "composerData:" + session_id
    prefix = "bubbleId:" + session_id + ":"
    found = False
    canonical = None
    canonical_invalid = False
    bubbles = []
    try:
        with _database(source) as con:
            columns = _columns(con, "cursorDiskKV")
            if not {"key", "value"} <= columns:
                note("unsupported_schema", "The database has no supported cursorDiskKV table.")
                return result
            hcols = _columns(con, "composerHeaders")
            if "composerId" in hcols:
                selected = sorted(hcols & {"createdAt", "lastUpdatedAt"})
                names = ", ".join('"' + name + '"' for name in selected) or '"composerId"'
                header = con.execute("SELECT " + names + " FROM composerHeaders WHERE composerId=? LIMIT 1",
                                     (session_id,)).fetchone()
                if header is not None:
                    found = True
                    for field, value in zip(selected, header):
                        stamp = _time(value, milliseconds=True)
                        if stamp and (until is None or stamp <= until):
                            timestamps.append(stamp)
                            if field == "createdAt":
                                starts.append(stamp)
            query = ('SELECT key, length(CAST(value AS BLOB)), '
                     'CASE WHEN length(CAST(value AS BLOB)) <= ? THEN value END '
                     'FROM cursorDiskKV WHERE key=? OR (key>=? AND key<?) '
                     'ORDER BY key LIMIT ?')
            total_bytes = 0
            for index, (key, size, raw) in enumerate(con.execute(
                    query, (MAX_VALUE, exact, prefix, prefix + "\uffff", MAX_RECORDS + 1))):
                if index == MAX_RECORDS:
                    note("record_limit", "The 10000-record safety limit was reached; coverage is partial.")
                    break
                found = True
                if size is None or raw is None:
                    note("oversized_record", "A null record or record over 4 MiB was skipped.")
                    continue
                total_bytes += size
                if total_bytes > MAX_TOTAL:
                    note("byte_limit", "The 64 MiB safety limit was reached; coverage is partial.")
                    break
                try:
                    obj = _json(raw)
                except (ValueError, UnicodeError, RecursionError, TypeError):
                    note("malformed_record", "A malformed or unsupported JSON record was skipped.")
                    continue
                if "composerId" in obj and obj["composerId"] != session_id:
                    # A key/payload mismatch makes attribution unsafe for the whole selection.
                    raise ValueError("Session identity mismatch in Cursor record")
                if key == exact:
                    created = _time(obj.get("createdAt"), milliseconds=True)
                    if created and (until is None or created <= until):
                        timestamps.append(created)
                        starts.append(created)
                    headers = obj.get("fullConversationHeadersOnly")
                    if headers is not None:
                        if (isinstance(headers, list) and len(headers) <= MAX_RECORDS
                                and all(isinstance(h, dict) and isinstance(h.get("bubbleId"), str)
                                        and ID.fullmatch(h["bubbleId"]) for h in headers)):
                            canonical = {h["bubbleId"] for h in headers}
                        else:
                            canonical_invalid = True
                            note("unsupported_bubble_index", "The active conversation bubble index is unsupported; usage was withheld.")
                    continue
                bid = key[len(prefix):] if isinstance(key, str) and key.startswith(prefix) else ""
                if not ID.fullmatch(bid) or ("bubbleId" in obj and obj["bubbleId"] != bid):
                    note("bubble_identity_mismatch", "A bubble with an inconsistent identity was skipped.")
                    continue
                # Store only the fixed metadata fields required for aggregation.
                bubbles.append((bid, obj.get("_v"), obj.get("type"),
                                obj.get("createdAt"), obj.get("tokenCount")))
    except FileNotFoundError:
        note("source_missing", "The Cursor Desktop database was not found on this machine.")
        return result
    except (sqlite3.Error, OSError):
        note("source_unreadable", "The database could not be read within the read-only safety limits.")
        return result

    if not found:
        note("session_not_found", "The selected composer ID was not found in the supported tables.")
        return result
    for bid, version, kind, raw_time, counts in bubbles:
        if canonical is not None and bid not in canonical:
            continue
        stamp = _time(raw_time)
        if until is not None and stamp is None:
            note("untimed_at_cutoff", "Records without a usable timestamp were excluded from the cutoff report.")
            continue
        if stamp is not None and until is not None and stamp > until:
            continue
        result["event_count"] += 1
        if stamp is not None:
            timestamps.append(stamp)
        if type(kind) is not int or kind != 2 or canonical_invalid:
            continue
        if type(version) is not int or version != 3:
            note("unsupported_bubble_version", "Usage is supported only for the observed version-3 assistant bubble schema.")
            continue
        if not isinstance(counts, dict):
            note("missing_usage", "Some assistant bubbles contain no usable token counters.")
            continue
        input_count, output_count = counts.get("inputTokens"), counts.get("outputTokens")
        if not all(type(v) is int and 0 <= v < 2**63 for v in (input_count, output_count)):
            note("invalid_usage", "A token counter was missing, negative, non-integer, or outside the supported range.")
            continue
        if input_count == 0 and output_count == 0:
            note("default_zero_usage", "All-zero per-bubble token counters are unverified serializer defaults, not evidence of zero consumption.")
            continue
        accepted_usage.append((input_count, output_count))
    if accepted_usage:
        result["tokens"]["total"] = sum(a + b for a, b in accepted_usage)
        result["tokens"]["output"] = sum(b for _, b in accepted_usage)
        result["token_coverage"] = "partial"
        note("native_bubble_usage", "Populated version-3 per-bubble input/output counters were summed once per stored bubble; these are partial native counters, not verified billed-request totals.")
        note("cache_split_unknown", "Cursor's observed bubble counters do not establish a cache split; uncached input and cache categories remain unavailable.")
    else:
        note("usage_unavailable", "No supported, populated token counters were available for the selected session and cutoff.")
    if timestamps:
        result["started_at"] = iso_time(min(starts or timestamps))
        result["observed_until"] = iso_time(max(timestamps))
    note("undocumented_schema", "Cursor Desktop's local schema is undocumented; this adapter supports observed composerHeaders/cursorDiskKV records and always reports partial usage coverage.")
    note("time_not_execution", "Header/message timestamps describe an observed calendar period; they do not measure agent execution or human attention.")
    note("billing_unavailable", "These local records provide no verified session-attributed monetary charge.")
    return result
