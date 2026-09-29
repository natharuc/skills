# Local adapter contract

The bundled command runner calls adapter modules in `scripts/reportkit/adapters/`.
Each module exposes:

- `roots(home: Path, env: dict, system: str) -> list[Path]`: known data locations only;
  `system` is `Windows`, `Linux`, or `Darwin`. Do not recursively scan the computer.
- `sessions(source: Path, limit: int = 100) -> list[dict]`: descriptors containing
  `session_id` and `source` (a concrete file path), with optional `started_at`.
  Never choose the newest session implicitly or print conversation text.
- `collect(source: Path, session_id: str, cutoff: str | None = None, *, strict_cutoff: bool = False) -> dict`:
  read one session up to an ISO timestamp with timezone; return the envelope below.
  Reject mismatched identities; unsupported data returns diagnostics, never invented
  usage. Read database sources in read-only mode and preserve their WAL view.

Envelope (`reportkit.common.empty_result` supplies defaults):

```json
{
  "schema_version": 1,
  "harness": "codex",
  "session_id": "session-id",
  "source": "/local/path",
  "source_kind": "native",
  "started_at": null,
  "observed_until": null,
  "tokens": {
    "input_uncached": null, "cache_read": null,
    "cache_write_short": null, "cache_write_long": null,
    "output": null, "total": null
  },
  "token_coverage": "unavailable",
  "model_usage": [],
  "intervals": [],
  "time_basis": "none",
  "time_coverage": "unavailable",
  "billing": [],
  "event_count": 0,
  "diagnostics": []
}
```

`tokens` contains observed totals/subtotals for the selected session, deduplicated
according to the source's schema. `token_coverage` is `complete`, `partial`, or
`unavailable`; default to partial unless complete observation is evidenced. Missing
values remain null. Preserve a reliable native `total` even if its categories are
incomplete. Cache categories are disjoint and reasoning already in output is not
added again. Do not sum cumulative snapshots.

`model_usage` entries contain `model`, `tokens` (the same six keys), and `coverage`.
Omit the breakdown if models cannot be associated reliably. `intervals` contain
`start`, `end`, and `agent_id`, all tied to the selected session. Only emit complete
intervals with explicit source events. `time_basis` is `gross_turn`, `request`, or
`none`; end-to-end message spans do not measure agent execution. Main and child
spans must not duplicate one another. Do not infer human time.

`billing` entries contain `currency`, decimal-string `amount`, `kind` (`attributed`
or `reference`), and `coverage`. Use this only for money present in the source with
verified session attribution, never subscription quotas or credits. Diagnostics are
objects with a machine-readable `code` and English `message`; exclude prompts,
credentials, tool results, and arbitrary source strings.

Helpers provided by `reportkit.common`: `empty_result(harness, session_id, source)`,
`diagnostic(result, code, message)`, `parse_time(value)` (aware datetime or None),
`iso_time(value)` (UTC ISO or None), `read_jsonl(path)` (bounded `(line_number, dict)`
iterator raising `ValueError` on malformed data), and `TOKEN_KEYS` (six keys).
Adapters must bound scans and refuse unknown binary formats. Source-specific
references explain supported schemas and evidence.

The runner supplies its invocation time as `cutoff`. An explicit user cutoff sets
`strict_cutoff=True`. Undated, explicitly selected native result exports may retain
their usage as an undated snapshot when strict mode is false, with a diagnostic and
no fabricated start/end times. Strict mode must exclude or reject such snapshots.
Dated native events always honor the supplied cutoff. `time_coverage` is complete,
partial, or unavailable independently of token coverage.
