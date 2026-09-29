#!/usr/bin/env python3
"""Read only Cursor metadata for one composer; output candidates, never billed totals."""
import argparse
import json
import math
from datetime import datetime
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

TIME_KEYS = {"timestamp", "createdat", "lastupdatedat", "updatedat", "startedat", "completedat", "starttime", "endtime", "duration", "durationms", "elapsed", "elapsedms", "clientstarttime", "clientendtime", "clientrpcsendtime", "recency"}
USAGE_KEYS = {"input", "output", "total", "inputtokens", "outputtokens", "totaltokens", "totalinputtokens", "totaloutputtokens", "cachedinputtokens", "cachedtokens", "cachereadtokens", "cachewritetokens", "cachecreationinputtokens", "cachereadinputtokens", "reasoningtokens", "cost", "costusd", "totalcost", "chargedcents", "rawcostcents", "totalcents", "contexttokensused", "contextusagepercent"}
CONTAINERS = {"usage", "usagedata", "tokenusage", "tokencount", "timinginfo", "timings", "modelinfo", "modelconfig", "conversationmap", "conversation", "header"}
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)")
ID = re.compile(r"[A-Za-z0-9_-]{1,180}")
MAX_BYTES = 4 * 1024 * 1024

def defaults():
    home = Path.home()
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(home / "AppData/Roaming"))) / "Cursor/User"
    elif sys.platform == "darwin":
        root = home / "Library/Application Support/Cursor/User"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))) / "Cursor/User"
    return [root / "globalStorage/state.vscdb"]

def finite_number(value):
    return type(value) is int or (type(value) is float and math.isfinite(value))

def reject_constant(value):
    raise ValueError("nonfinite JSON constant")

def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite JSON number")
    return number

def metadata(obj):
    out, limited = [], False
    def walk(value, path="", depth=0):
        nonlocal limited
        if depth > 12 or len(out) >= 100:
            limited = True
            return
        if isinstance(value, dict):
            for key, child in value.items():
                name = str(key).replace("_", "").lower()
                # Only known metadata keys are emitted, never arbitrary payload keys.
                if name not in TIME_KEYS | USAGE_KEYS | CONTAINERS:
                    continue
                p = path + "." + name if path else name
                if name in CONTAINERS and isinstance(child, (dict, list)):
                    if name == "conversationmap" and isinstance(child, dict):
                        for i, bubble in enumerate(list(child.values())[:200]):
                            walk(bubble, p + "[" + str(i) + "]", depth + 1)
                        limited = limited or len(child) > 200
                    else:
                        walk(child, p, depth + 1)
                elif finite_number(child):
                    out.append({"field": p, "raw": child})
                elif isinstance(child, str) and name in TIME_KEYS and ISO.fullmatch(child):
                    try:
                        datetime.fromisoformat(child.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    out.append({"field": p, "raw": child})
                if len(out) >= 100:
                    limited = True
                    break
        elif isinstance(value, list):
            for i, child in enumerate(value[:200]):
                walk(child, path + "[" + str(i) + "]", depth + 1)
            limited = limited or len(value) > 200
    walk(obj)
    return out, limited

def inspect(db, cid, limit):
    result = {"db": str(db), "conversation_id": cid, "records": [], "warnings": []}
    if not db.is_file():
        result["status"] = "database_not_found"
        return result
    connection = None
    try:
        connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        connection.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 15
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        connection.execute("BEGIN")
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result["known_tables_present"] = sorted(tables & {"ItemTable", "cursorDiskKV", "composerHeaders"})
        rows = []
        if "cursorDiskKV" in tables:
            cols = {r[1] for r in connection.execute('PRAGMA table_info("cursorDiskKV")')}
            if {"key", "value"} <= cols:
                exact = "composerData:" + cid
                prefix = "bubbleId:" + cid + ":"
                # Range lookup uses key index and cannot match another composer.
                sql = "SELECT key, length(CAST(value AS BLOB)), CASE WHEN length(CAST(value AS BLOB)) <= ? THEN value END FROM cursorDiskKV WHERE key=? OR (key>=? AND key<?) ORDER BY key LIMIT ?"
                rows = connection.execute(sql, (MAX_BYTES, exact, prefix, prefix + "\uffff", limit + 1))
                total = 0
                for i, (key, size, raw) in enumerate(rows):
                    if i == limit:
                        result["warnings"].append("record_limit_reached; coverage_partial")
                        break
                    safe_key = key if key == exact or (isinstance(key, str) and key.startswith(prefix) and ID.fullmatch(key[len(prefix):])) else "bubbleId:" + cid + ":[unrecognized-key]"
                    rec = {"key": safe_key, "bytes": size}
                    if raw is None:
                        rec["status"] = "value_too_large_or_null"
                        result["records"].append(rec)
                        continue
                    total += size
                    if total > 64 * 1024 * 1024:
                        result["warnings"].append("byte_limit_reached; coverage_partial")
                        break
                    try:
                        obj = json.loads(raw, parse_constant=reject_constant, parse_float=finite_float)
                        rec["candidate_fields"], capped = metadata(obj)
                        rec["status"] = "metadata_only"
                        if isinstance(obj, dict):
                            rec["bubble_type"] = obj.get("type") if type(obj.get("type")) is int else None
                            token = obj.get("tokenCount")
                            if isinstance(token, dict):
                                values = [v for v in token.values() if finite_number(v)]
                                rec["token_count_state"] = ("nonzero_candidates" if any(v != 0 for v in values)
                                                            else "all_zero_unverified" if values else "empty")
                        if capped:
                            rec["metadata_truncated"] = True
                    except (ValueError, UnicodeError, RecursionError, TypeError):
                        rec["status"] = "unparsed_value"
                    result["records"].append(rec)
            else:
                result["warnings"].append("cursorDiskKV_schema_not_supported")
        if "composerHeaders" in tables:
            cols = {r[1] for r in connection.execute('PRAGMA table_info("composerHeaders")')}
            if "composerId" in cols:
                chosen = sorted(cols & {"composerId", "createdAt", "lastUpdatedAt", "recency"})
                selected = ", ".join('"' + c + '"' for c in chosen)
                row = connection.execute("SELECT " + selected + " FROM composerHeaders WHERE composerId=? LIMIT 1", (cid,)).fetchone()
                if row:
                    fields, capped = metadata(dict(zip(chosen, row)))
                    result["header"] = {"candidate_fields": fields}
            else:
                result["warnings"].append("composerHeaders_schema_not_supported")
        result["records_found"] = len(result["records"])
        result["status"] = "candidates_found" if result["records"] or result.get("header") else "conversation_not_found_in_supported_tables"
        if "cursorDiskKV" not in tables:
            result["warnings"].append("cursorDiskKV_not_present")
        result["warnings"].append("Candidate fields require schema validation; zero counters are not proof of zero usage. Message timestamps do not measure human attention.")
    except (sqlite3.Error, OSError, ValueError) as exc:
        result["status"] = "read_error"
        result["error"] = str(exc)
    finally:
        if connection is not None:
            connection.close()
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", required=True, help="Exact composer ID, not project-wide search")
    parser.add_argument("--db", action="append", type=Path, help="Explicit state.vscdb path; repeat for known profiles")
    parser.add_argument("--max-records", type=int, default=1000)
    args = parser.parse_args()
    if not ID.fullmatch(args.conversation) or not 1 <= args.max_records <= 10000:
        parser.error("Use a valid composer ID and max-records between 1 and 10000")
    output = {
        "collector": "cursor_metadata_readonly_v1",
        "scope": "local machine only; explicit conversation; no transcript text emitted",
        "interpretation": "Discovery evidence, NOT a token/time/cost report. Inspect timestamps, coverage, defaults and billing semantics before calculating.",
        "sources": [inspect(p, args.conversation, args.max_records) for p in (args.db or defaults())],
    }
    print(json.dumps(output, ensure_ascii=True, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
