# GitHub Copilot and Antigravity collectors

Contents: [GitHub Copilot CLI](#github-copilot-cli), [Google Antigravity](#google-antigravity), [Sources and verification](#sources-and-verification).

These adapters read local files with the bundled command runner. They do not
launch new agent conversations to recover old usage, contact hidden local APIs,
read authentication stores, or guess binary formats. Discovery is bounded to
known directories; the caller selects an exact session identifier.

## GitHub Copilot CLI

Supported source: `$COPILOT_HOME/session-state/<session-id>/events.jsonl`, or
`~/.copilot/session-state/<session-id>/events.jsonl` when `COPILOT_HOME` is unset.
This layout is home-relative on Windows, Linux, and macOS. Custom `--config-dir`
locations require an explicit `--source`; no configuration file containing
credentials is read.

```powershell
# SkillRoot is the installed chat-report folder.
& "$SkillRoot/chat-report.ps1" sessions --harness github-copilot
& "$SkillRoot/chat-report.ps1" report --harness github-copilot --session "<session-id>" --source "$HOME/.copilot/session-state/<session-id>/events.jsonl" --output "./copilot-report.html" --open
```

On macOS/Linux without PowerShell, use `"$SkillRoot/chat-report.sh"` with the same
arguments. The `copilot` harness alias also resolves to `github-copilot`.

The implementation requires `session.start.data.sessionId` and rejects another
identity anywhere in the file. It reads:

- The latest durable `session.shutdown.data.modelMetrics` usage snapshot. It
  keeps that snapshot instead of adding repeated cumulative summaries.
- Captured `assistant.usage` events when there is no shutdown summary, deduplicated
  by API call identifier or event identifier. These events are normally ephemeral
  and may be absent from persisted history.
- Durable `assistant.message.data.outputTokens` only as an output-only fallback.
- Matching main-agent `assistant.turn_start` / `assistant.turn_end` pairs. Gross
  turn time includes tools and possible approval waits. Child spans are excluded
  because the parent may enclose them. Resumes split the turn identifier namespace.

The adapter preserves output and cache-read counters. It does not assert a common
cache-inclusive input definition across providers, so `input_uncached`, cache-write
buckets, and a computed total stay unknown. Reasoning is already included in output.
If a snapshot decreases after a resume, the last snapshot stays partial and the
report flags the reset. Activity after a snapshot is also flagged.

`session.usage_info.currentTokens` is context occupancy. Cost multipliers, premium
request counts, and nano-AI units are not currency charges. None is relabeled as
total token consumption or money.

### Copilot in VS Code, Visual Studio, or another IDE

The CLI session store is not the IDE chat store. This adapter does not claim that
Copilot CLI paths contain an IDE conversation. For IDE data, use a session-attributed
export through the runner's structured import contract. Supplying an IDE database
to this adapter returns `unsupported_native_schema`; it does not silently query an
unrelated CLI session. No IDE token extractor is currently bundled.

## Google Antigravity

Known data roots on all three OS families:

- `~/.gemini/antigravity/`
- `~/.gemini/antigravity-cli/`
- `~/.gemini/antigravity-ide/`

The official hooks documentation identifies those application directories. The
documented transcript layout is
`brain/<conversation-id>/.system_generated/logs/transcript.jsonl` underneath the
application directory. Discovery reports existing transcript paths without assuming
their content uses the headless format. Unknown transcript records or legacy binary
stores produce an explicit unsupported-schema result.

### Supported machine-readable input

The adapter directly consumes a saved official `agy --output-format json` result,
or `--output-format stream-json` output. Pass that existing export to the runner:

```powershell
& "$SkillRoot/chat-report.ps1" sessions --harness antigravity
& "$SkillRoot/chat-report.ps1" sessions --harness antigravity --source "./agy-result.json"
& "$SkillRoot/chat-report.ps1" report --harness antigravity --session "<conversation-id>" --source "./agy-result.json" --output "./antigravity-report.html" --open
```

Use `--output-format json` or `--output-format stream-json` when capturing an
already-authorized new Antigravity task. Those options run the task; they are not
read-only commands for exporting an old conversation. The report command itself
only reads a saved file and never starts a fresh Antigravity run.

The adapter matches `conversation_id`, preserves the last cumulative result's
`usage.total_tokens` and `usage.output_tokens`, and skips per-step counters to
avoid double counting. It never adds `thinking_tokens` again. Published examples
do not establish a consistent cache-inclusive split, so input/cache categories
remain unknown. Native `total_tokens` keeps its provider definition rather than
being reconstructed from ambiguous categories.

Repeated results are cumulative snapshots, not independent requests. Decreasing
counters or turn numbers trigger a reset diagnostic. Coverage remains partial
because continuation across separate processes may need additional evidence.

Official result examples are undated. The default report can include an **undated
export snapshot**, without inventing start or observation timestamps. An explicit
historical `--cutoff` excludes undated results. `duration_seconds` is cumulative
wall-clock metadata and does not supply dated active-time intervals. A valid finite,
nonnegative value appears in the report's evidence diagnostics as
`reported_run_duration`, explicitly labeled as reported run elapsed duration with
no dated execution interval. Malformed values are excluded. These exports do not
establish human work or an attributed currency charge.

Status-line JSON is also documented, but its `context_window` is not consumed-token
accounting. It is not substituted for the headless result. No settings or hooks are
automatically changed by discovery or report generation.

## Sources and verification

Primary sources checked on 2026-09-29:

- [GitHub Copilot CLI configuration directory](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)
- [GitHub Copilot SDK event reference](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/streaming-events)
- [GitHub Copilot SDK generated event schema](https://github.com/github/copilot-sdk/blob/main/nodejs/src/generated/session-events.ts)
  (retrieved blob `96f6f247c595b9056847cbcba304e36d3467a1dc`; specifically
  `StartData`, `ShutdownData`, `ShutdownModelMetricUsage`, and `AssistantUsageData`).
- [Antigravity headless JSON and streaming schema](https://antigravity.google/docs/cli/headless/)
- [Antigravity hooks and application directories](https://antigravity.google/docs/hooks/)
- [Antigravity status-line payload and transcript path](https://antigravity.google/docs/cli/statusline/)

Synthetic fixture tests cover source identity, duplicated calls, summary resets,
cumulative result selection, partial/cutoff behavior, main/child spans, read-only
collection, malformed tails, and removal of conversation content from output.
These tests are not a claim of validation against every released harness build.
