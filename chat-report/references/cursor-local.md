# Cursor data collection

Contents: [identify the session](#1-identify-the-machine-and-conversation),
[locate sources](#2-locate-the-sources), [read-only inspection](#3-inspect-in-read-only-mode),
[interpret fields](#4-interpret-the-fields-found),
[usage and billing](#5-supplement-usage-and-billing-when-possible),
[gap diagnosis](#6-required-gap-diagnosis), [sources](#sources-and-scope-of-evidence).

Perform this collection before reporting on a Cursor session. The goal is to
establish what exists in the correct installation, without assuming all data is
in the transcript. Access to the conversation context is not equivalent to access
to billing telemetry.

## 1. Identify the machine and conversation

Determine whether the terminal is on the machine running the Cursor interface,
in WSL, over SSH, or in a remote environment. A missing database on a server does
not demonstrate its absence on the computer hosting the interface. Identify the
profile, version, and custom data directory, if any; do not substitute an invented
path for the user's home directory.

Obtain the current conversation's composer ID from available metadata or the
corresponding transcript, and validate its association with the project. Do not
choose the account's most recent conversation or an ID from another task. If only
the project is known, inspect workspace metadata indexes before asking the user
to search manually.

## 2. Locate the sources

| System | Initial candidate for the conversation database |
|---|---|
| Windows | `%APPDATA%\Cursor\User\globalStorage\state.vscdb` |
| macOS | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Linux | `~/.config/Cursor/User/globalStorage/state.vscdb`, respecting `XDG_CONFIG_HOME` |

Resolve variables from the actual environment. If a custom data directory or
another profile exists, use its known path. Use the corresponding workspace's
`User/workspaceStorage/<workspace>/workspace.json` and `state.vscdb` only when
needed for association or an older schema. Do not scan all drives or dump other
conversations.

Treat the transcript as a content source. Treat edit-attribution records as
supplementary evidence of code events, without converting them into every request
or all time spent on the task. The absence of tokens in these two sources alone
does not end the investigation.

## 3. Inspect in read-only mode

Run the collector bundled with the skill on the computer containing the database:

```text
python <skill-directory>/scripts/inspect_cursor.py --conversation <composer-id>
```

For a confirmed path or custom profile:

```text
python <skill-directory>/scripts/inspect_cursor.py --conversation <composer-id> --db "<full-path>/state.vscdb"
```

On Windows, use `py -3` if that is the available executable. The script requires
no external libraries and prints JSON. It does not need to create a file, access
the network, read credentials, close Cursor, or modify the database. Without
Python, run equivalent queries using an already available SQLite tool; do not
abandon collection merely because the script cannot run.

The collector uses `mode=ro`, a read transaction, ID filters, and explicit limits.
Avoid `immutable=1` on a live database because it may ignore the WAL. If a snapshot
is needed, use a consistent SQLite backup or an equivalent mechanism that
preserves the WAL view; do not copy only the main file while it is in use. Do not
run migrations, cleanup, checkpoints, or `VACUUM`.

Detect the existing tables. In schemas observed by independent parsers,
`cursorDiskKV` stores `composerData:<id>` and `bubbleId:<id>:<bubble-id>`. Recent
versions may also have `composerHeaders`, which can be queried by `composerId`.
Older versions may have indexes in `ItemTable` (`composer.composerData` or
`composer.composerHeaders`). These internal formats are not a stable API; if a
different schema exists, inspect it without claiming the session has disappeared.

The script covers the KV store and recent headers. If it returns
`conversation_not_found_in_supported_tables`, check the machine/profile/ID
association and older indexes before concluding that no records exist. To locate
an older index, read only its known key and filter the JSON by composer ID; do
not print the entire index. If access is impossible, record the precise limitation.

## 4. Interpret the fields found

- Treat each `candidate_fields` entry as raw evidence that still needs semantics,
  units, and coverage. The collector does not automatically turn candidates into
  a report.
- Check `tokenCount` and any usage fields that are actually present. **Counters
  filled with zero may be default values**, especially when the whole
  conversation is zeroed. Do not present this as zero consumption or calculate
  zero cost.
- Do not convert `contextUsagePercent`, context occupancy, or a limit into
  accumulated usage. A positive per-bubble counter still requires request-level
  reconciliation; a response may contain multiple segments.
- Preserve timestamps in their source format. Header timestamps may use epoch
  milliseconds; message timestamps may use RFC3339. Validate dates, timezones,
  and units. Do not assume every number named `time` is a wall-clock timestamp.
- If request start/end timestamps share the same clock, validate their meaning,
  deduplicate, clip at the cutoff, and merge intervals. Do not subtract a
  monotonic clock from epoch time. Call the result the duration of observed
  requests, without assuming coverage of the agent's entire execution.
- If only message timestamps exist, state the known period. When the user asks
  for an activity approximation, apply the windowing rule in SKILL.md and label
  it as an estimate. Human effort still depends on markers or attributed
  activity, not the message database.
- File timestamps and `lastUpdatedAt` are not active duration. Open records,
  truncated values, unread large blobs, timeouts, and unknown schemas make the
  inspection partial.

The collector does not print prompt bodies, responses, or tool results; it
records only an allowlist of known metric and time fields. Text model names are
not emitted. An empty list does not prove that a new schema has no other metadata:
inspect the structure locally when it differs. Do not paste a complete database
dump into external tools. If content must be read to disambiguate identity, do
so locally and only for the target conversation.

## 5. Supplement usage and billing when possible

If the official SDK is already available, the agent's identity has been verified,
and access is authorized, check the existing usage query, such as
`Agent.getUsage()`. Do not assume the API accepts every IDE composer ID; confirm
the mapping and supported surface. Do not create another agent to query earlier
usage, or search for or expose authentication tokens.

The SDK distinguishes live counts from billed usage and may return a cost that
is still missing while it settles. Preserve these distinctions. Alternatively,
use an already accessible usage export/dashboard or Admin API. Link records by
verifiable ID; matching time/model is not enough for exact attribution. Do not
require an administrative account as the first option for an individual user.

For data the agent cannot access, request only the record/export needed to close
the remaining gap. Do not promise that the local database contains cache
breakdowns, costs, or human attention data.

## 6. Required gap diagnosis

Briefly record the following in the report:

| Source | Inspection result | Consequence |
|---|---|---|
| Conversation database | Path, table, composer found or reason for failure | Identity and coverage verified or pending |
| Messages | Number inspected, available time and usage fields | Usable or missing periods/counters |
| Usage/billing | Source consulted, ID linkage, and availability | Attributed cost or a specific gap |

Distinguish **not collected**, **inaccessible in this environment**,
**unsupported format**, **missing field**, **unreliable default counter**, and
**available measurement**. Do not make the absolute claim “Cursor does not have
this information” based on a single transcript or installation.

Only claim the new collection resolved the actual case after running it on the
user's machine/session. Tests with synthetic databases validate the code, not
the presence of metrics in that installation.

## Sources and scope of evidence

- [Cursor SDK — getUsage](https://cursor.com/docs/sdk/typescript): official
  agent usage API; confirm version, identity, and access.
- [Cursor — Admin API](https://cursor.com/docs/account/teams/admin-api):
  per-event usage, when available for the account.
- [txcript — Cursor Desktop format](https://github.com/skillsynchq/txcript/blob/main/docs/formats/cursor-desktop.md):
  a parser author's documentation of schema, timestamps, and `tokenCount`;
  evidence from an independent implementation, not an official Cursor contract.
- [cursaves — storage](https://github.com/Callum-Ward/cursaves/blob/main/docs/how-cursor-stores-chats.md):
  the author's investigation of storage/indexes in earlier versions; the same
  compatibility caveat applies.

Verified on 2026-09-29. Revalidate formats in the target installation before
calculating.
