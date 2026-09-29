# Codex and Claude local adapters

Contents: [Discovery and selection](#discovery-and-selection), [Codex rollout support](#codex-rollout-support), [Claude Code and Agent SDK support](#claude-code-and-agent-sdk-support), [Evidence and compatibility](#evidence-and-compatibility).

The command runner calls these bundled adapters. The agent does not write an ad hoc
collector, estimate missing counters, or resume a paid model run just to obtain a
report. All examples below use a selected, exact session ID and a local source.

## Discovery and selection

| Harness | Default native root on Windows, Linux, and macOS | Override |
| --- | --- | --- |
| Codex | `~/.codex/sessions` and `~/.codex/archived_sessions` | `CODEX_HOME` |
| Claude Code | `~/.claude/projects` | `CLAUDE_CONFIG_DIR` |

`~` means the account running the command. A Windows installation and a WSL/SSH
installation can have different homes; run the command where the actual harness
writes data or supply a concrete source path. This adapter does not search other
users, remote computers, the whole drive, browser storage, or credential files.

Codex discovery searches known date-folder depths. Claude discovery searches the
project-folder level, excluding nested child-agent logs. Both cap directory/file
entries at 5,000, return at most the requested limit (1–1,000), and inspect only a
bounded header to list session identity and time. A file's content, rather than
its filename alone, must verify its identity. The newest file is never selected
automatically. A truncated listing may require passing a narrower directory or
an exact file path.

Reads use the common limits: 128 MiB/file, 4 MiB/line and 250,000 JSONL records.
Malformed, binary, excessively nested, duplicate-key or nonfinite JSON is rejected.
Sources are read without mutation. Reports contain selected numeric metadata,
model identifiers and diagnostic codes; message text and tool results are omitted.

## Codex rollout support

Supported records are `session_meta`, `turn_context` and `event_msg` in native
rollout JSONL. `session_meta.payload.id` must exactly match the selected thread.
The root `session_id` in a multi-agent rollout is not used as a substitute for the
thread ID, because multiple threads can share that root ID.

- `token_count.info.total_token_usage` is a cumulative snapshot. Only the latest
  observed snapshot is used, including repeats; neither snapshots nor
  `last_token_usage` are added to it.
- Cache-read tokens are part of native input, so disjoint noncached input is
  `input_tokens - cached_input_tokens`. Reasoning is already inside output and
  is not added a second time.
- A nonzero `cache_write_input_tokens` has no verified TTL/disjoint-input mapping
  in this adapter. Preserve its native total, known output and cache-read counts;
  keep uncached input and cache-write TTL buckets unknown. An explicit zero can
  populate both write buckets with zero; absence cannot.
- A decrease in any shared cumulative category emits `cumulative_reset`. Report
  the latest segment as partial. Do not sum earlier segment peaks: a reset can
  mean compaction, restored state or an ownership boundary rather than new spend.
- Codex can fill context usage with an artificial capacity total after overflow.
  A nonzero total with explicit zero input/cache/output is excluded, so context
  capacity does not become measured consumption. Missing breakdown fields are
  distinct from explicit zero: a native total-only snapshot may be retained.
- Forks, inherited `history_base`, projected subagent histories and explicit
  parent-thread ownership are diagnosed as unsupported accounting boundaries.
  The adapter does not attribute copied parent counters or turn spans to a child.
- Compaction and rollback markers keep coverage partial. Separate child sessions
  are not scanned or added. Single-model attribution is provided only when the
  observed contexts and snapshots agree; uncertain breakdowns are omitted.

For time, matching `task_started`/`task_complete` (and newer
`turn_started`/`turn_complete`) events with a `turn_id` establish a gross turn
span. Explicit native epoch start/end fields take priority over JSONL timestamps.
An explicitly identified aborted turn can close a span. Repeated completion
events are deduplicated. Open turns are excluded. These spans can include tools,
approval waits and scheduling; they do not measure human attention or pure
inference time. Subscription credits and rate-limit percentages are never money.

## Claude Code and Agent SDK support

Native Claude Code transcript JSONL uses `sessionId`; Agent SDK records use
`session_id`. Every message used for accounting must carry the exact selected
identity. A file with conflicting session identities is rejected, even if its
filename matches. Custom transcript-storage backends and mixed-session streams
must be exported as a single attributable session first.

### Transcript-only observations

Assistant input/cache usage is read only from the documented message usage object.
`message.id`/`message_id` and `requestId`/`request_id` aliases deduplicate repeated
streaming snapshots and parallel-tool messages. Rows without a deduplication
identity are excluded. Later explicit counter snapshots supersede earlier values;
a downward correction is diagnosed. No arbitrary recursive token-key search runs.

Anthropic input is exclusive of cache reads and writes. Cache-write TTL buckets
are populated only when `cache_creation.ephemeral_5m_input_tokens` and
`ephemeral_1h_input_tokens` have a consistent split. An aggregate nonzero write
count alone cannot become a made-up TTL split. Missing fields remain unknown.

Current official Agent SDK guidance warns that assistant per-step output counts
can be placeholders. Transcript-only output and total therefore remain unknown
until a supported result record provides reliable output. The adapter still
reports measured input/cache observations. It does not tokenize conversation
text and label it consumed tokens. Explicit sidechains, team messages and
`parent_tool_use_id` children are excluded from main-loop message accounting.

### Result records

An already available Agent SDK JSONL export can provide result records. Do not
launch an agent request to manufacture such a record after the task.

1. Prefer the latest complete-schema `modelUsage`/`model_usage` result map. Its
   token counters are cumulative and can include subagents; do not sum maps
   across results or add assistant messages to them. Native map values use
   camelCase even with the Python SDK. Unknown write TTL stays unknown, while
   the total can still be computed from the known aggregate write count.
2. Otherwise use `result.usage` for observed main-loop turns, deduplicated by
   result UUID. A result without UUID replaces prior ambiguous result scope;
   it is not guessed to be a new request. This excludes subagents and missing
   earlier turns. Additional assistant activity after the latest result is
   diagnosed and excluded until a new reliable result arrives.
3. `total_cost_usd` is a client-side pricing estimate, recorded as `reference`,
   never as an authoritative charge. Keep the latest value. Recent versions
   restore prior session spend on resume; older versions did not. Decreasing
   cumulative counters stay partial and earlier segments are not guessed.
   A zero error result cannot erase previously observed nonzero usage or cost.

Actual invoices require separately attributable billing evidence. No hardcoded
model price or subscription proration is applied by these adapters.

An explicit native `system/turn_duration` record with `durationMs`, timestamp and
UUID can produce a gross span. A timestamped SDK result with `duration_ms` and
UUID can also do so. Intervals share the selected agent ID, allowing the runner
to union overlapping observations. Untimestamped durations are not positioned
on a timeline using guesses. API duration alone is not human work.

Dated records respect the report cutoff. An explicitly selected undated SDK
snapshot may be retained when using the invocation-time default cutoff, with an
`undated_snapshot` diagnostic: its temporal coverage cannot be verified. An
explicit historical cutoff activates strict filtering and excludes undated
records. No later measurement is interpolated back into an earlier report.

## Evidence and compatibility

Reviewed 2026-09-29. These adapters deliberately target known file/event schemas;
local persistence details can change. Synthetic tests cover identity mismatch,
read-only behavior, deduplication, snapshot decreases, cache splits, native
aggregate totals, compaction/fork exclusions, cutoffs, malformed data, gross time
and zeroed error results. They do not prove compatibility with every installed
version or with a user's unavailable computer.

Primary sources:

- [OpenAI Codex protocol source](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs):
  `SessionMeta`, `TokenUsageInfo`, `TokenUsage`, event aliases and turn timestamps.
- [OpenAI Codex configuration](https://developers.openai.com/codex/config-advanced/):
  the Codex home directory and local configuration.
- [Claude Agent SDK cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking):
  message deduplication, result versus model usage scopes, output placeholders,
  restored totals and the estimated nature of SDK cost fields.
- [Anthropic Python SDK session reader](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/sessions.py):
  `CLAUDE_CONFIG_DIR`, project paths, transcript identities and child-agent layout.
- [Anthropic Python SDK types](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/types.py):
  `AssistantMessage`, `ResultMessage`, `ModelUsage` and native field names.
- [Claude session documentation](https://code.claude.com/docs/en/sessions):
  session storage, branches, compaction and session resumption.
