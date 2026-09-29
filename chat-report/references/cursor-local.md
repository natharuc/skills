# Cursor Desktop adapter

Contents: [Commands](#commands), [Known locations](#known-locations), [Supported deterministic rules](#supported-deterministic-rules), [Diagnostics and gaps](#diagnostics-and-gaps), [Evidence and compatibility](#evidence-and-compatibility).

Use the bundled `cursor` adapter through the standard commands. It performs
session discovery, read-only collection, deterministic normalization, and HTML
generation. Do not ask the agent to invent SQL, interpret arbitrary metric names,
or construct a new collector during a report.

## Commands

Run on the computer and profile hosting the Cursor interface. From the installed
skill directory in PowerShell:

```powershell
& .\chat-report.ps1 doctor
& .\chat-report.ps1 sessions --harness cursor --limit 20
& .\chat-report.ps1 report --harness cursor --session "COMPOSER_ID" --output ".\reports\chat-report.html" --language en --open
```

For a custom data directory, pass the exact database path:

```powershell
& .\chat-report.ps1 report --harness cursor --session "COMPOSER_ID" --source "C:\CustomCursor\User\globalStorage\state.vscdb" --output ".\reports\chat-report.html" --language en
```

Linux/macOS use the same arguments with `sh /path/to/chat-report/chat-report.sh`;
PowerShell 7 is also supported there. See [commands](commands.md) for collecting
JSON evidence, declared human work timers, cutoffs, and rendering saved evidence.

Use the current conversation's exact composer ID from harness metadata or the
session list. Discovery emits IDs, concrete source paths, and available creation
timestamps. It never chooses the most recent conversation automatically or
prints conversation titles, prompts, responses, or tool results.

## Known locations

| System | Default database |
|---|---|
| Windows | `%APPDATA%\Cursor\User\globalStorage\state.vscdb` |
| macOS | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Linux | `$XDG_CONFIG_HOME/Cursor/User/globalStorage/state.vscdb`, or `~/.config/Cursor/User/globalStorage/state.vscdb` |

A WSL instance, SSH host, container, or cloud agent can have different data from
the machine hosting the UI. Use `--source` only for an explicitly available
source. A missing database on a remote host is an access/location limitation,
not proof that the desktop has no records. The adapter does not search all drives,
credentials, private language-server endpoints, or unrelated application stores.

This adapter covers Cursor **Desktop** SQLite storage. Cursor CLI storage and
cloud agents are different surfaces and are not silently treated as this format.

## Supported deterministic rules

- Discovery reads `composerHeaders.composerId` and requires a matching bubble;
  older KV stores fall back to bounded `composerData:` key discovery.
- Collection selects `composerData:<id>` and `bubbleId:<id>:<bubble-id>` by exact
  ID and delimited key range. A composer identity mismatch is rejected. When a
  valid `fullConversationHeadersOnly` index exists, only its bubbles contribute.
- Each stored version-3 assistant bubble contributes its populated integer
  `tokenCount.inputTokens` and `outputTokens` once. The observed sum is a **partial
  native token subtotal**, not an assertion of complete billed-request usage.
  Duplicate index entries do not duplicate counters.
- All-zero counters are unverified serializer defaults. Missing, malformed,
  negative, unsupported-version, and unrecognized counters remain unavailable.
- The subtotal preserves total and output. Uncached input, cache splits, and
  model breakdowns remain unavailable because this schema does not establish
  their accounting semantics reliably enough for this adapter.
- Header epoch-millisecond timestamps and timezone-aware message timestamps
  describe the observed calendar period. They do not measure active agent time,
  human attention, or time spent thinking. No execution intervals are invented.
- A cutoff excludes later events and untimed bubbles. Future header updates are
  ignored rather than assigned an invented timestamp at the cutoff.
- No session-attributed monetary charge is inferred from local counters, context
  occupancy, subscription quotas, credits, or project code-edit records.

The SQL reader uses `mode=ro`, `query_only`, and one transaction, preserving the
live WAL view. It limits collection to 10,000 records, 4 MiB per JSON value,
64 MiB per selection, and 15 seconds of SQLite execution. Unknown or truncated
records produce diagnostics and never trigger ad hoc migrations or writes.
Do not use `immutable=1` or copy only the main database file while the app is
running; either can omit live WAL data.

## Diagnostics and gaps

The report retains explicit reasons such as `source_missing`, `source_unreadable`,
`unsupported_schema`, `session_not_found`, `default_zero_usage`, `missing_usage`,
`unsupported_bubble_version`, and reader limits. Read these results instead of
converting gaps into zeros or asking the agent to reverse-engineer the installed
application during the reporting flow.

Use the bundled `track` commands for declared human work. Tokens, request timing,
and charges absent from the supported native source need an explicitly available
attributed export, not guesses. Official Cursor SDK usage and billing APIs are
separate, authenticated surfaces; a desktop composer ID is not automatically an
SDK agent ID. This offline adapter does not create agents, request billing access,
read tokens, or call those APIs.

The older `scripts/inspect_cursor.py` remains available as an explicit diagnostic
utility. It emits candidate metadata only and is not the default report path.
The new adapter performs the supported interpretation inside the bundled code.

## Evidence and compatibility

The desktop storage format has no public Cursor specification. Support for its
schema and populated per-bubble counters is based on the independent parser
author's [Cursor Desktop format documentation](https://github.com/skillsynchq/txcript/blob/main/docs/formats/cursor-desktop.md).
This is evidence from an implementation, not an official Cursor compatibility
guarantee. The [cursaves storage investigation](https://github.com/Callum-Ward/cursaves/blob/main/docs/how-cursor-stores-chats.md)
documents older store/index layouts. Unknown changes are reported explicitly.

Official references for separate usage surfaces:
[Cursor SDK](https://cursor.com/docs/sdk/typescript) and
[Cursor Admin API](https://cursor.com/docs/account/teams/admin-api).

Reviewed 2026-09-29. Synthetic fixtures verify identity filtering, default-zero
handling, malformed input, cutoff, bounds, WAL visibility, and read-only behavior.
They do not prove that the user's installation records these metrics.
