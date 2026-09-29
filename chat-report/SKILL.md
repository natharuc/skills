---
name: chat-report
description: Generate and display an auditable HTML report of chat tokens, work time, and cost using bundled commands for Cursor, Codex, Claude Code, GitHub Copilot, and Antigravity. Use for /chat-report, $chat-report, chat-report, or requests about session usage, hours spent, or cost. Run deterministic local collectors through PowerShell on Windows or shell on Linux/macOS; preserve evidence, scope, missing data, and distinct human/agent time.
---

# /chat-report

Run the bundled command suite. Do not design a collection strategy from scratch,
write temporary parsing scripts, query arbitrary databases, manually assemble
presentation JSON, or recalculate tool results during a normal invocation. The
commands own discovery, source parsing, normalization, calculation, and HTML
compilation. The agent selects the correct session, invokes the command, checks
its result, and displays the report.

Write instructions and identifiers in English. Choose report language from the
user's request or conversation: `pt-BR` for Portuguese, `en` for English or an
unknown preference. Those are the bundled report locales; disclose that limit
if another language is requested. Keep `/chat-report` and `$chat-report` aliases.

## Command entry points

Resolve the installed skill directory from this file. Quote paths; do not assume
Bash on Windows or that the terminal is on the user's desktop computer.

Windows PowerShell 5.1 or PowerShell 7:

```powershell
& "<skill-directory>\chat-report.ps1" doctor
& "<skill-directory>\chat-report.ps1" sessions --harness cursor
& "<skill-directory>\chat-report.ps1" report --harness cursor --session "<composer-id>" --language pt-BR --open
```

Linux/macOS (PowerShell 7 is also supported when installed):

```sh
sh "<skill-directory>/chat-report.sh" doctor
sh "<skill-directory>/chat-report.sh" report --harness codex --session "<thread-id>" --language en --open
```

Both launchers detect Python 3.10+ and run the same bundled standard-library
engine. No pip dependencies, network services, or price downloads are needed.
If the runtime is missing, report the concrete prerequisite. Do not install it,
change execution policy, elevate privileges, or substitute ad hoc functions.
A supported direct entry is `python3 <skill-directory>/scripts/chat_report.py`.

Read [references/commands.md](references/commands.md) for arguments, examples,
rate-card schema, tracking storage, and exit codes. Use `--help` for the installed
command contract.

## Report workflow

1. Identify the current session from harness metadata. Preserve any explicitly
   requested source, session, period, and task. The only automatic current-session
   hint is the existing `CODEX_THREAD_ID`; never invent an ID or choose the newest
   log. `--harness auto` resolves only an unambiguous session/source.
2. Run `doctor` when the environment is unknown, then `sessions --harness <name>`
   if the source is not already known. Supply `--source <path>` for a custom data
   directory, an export, or ambiguous locations. If identity remains ambiguous,
   ask for only the missing session/source selection.
3. Run `report --harness <name> --session <id> --language <locale>` with the
   selected source when needed. The command fixes its cutoff at invocation start.
   Use `--cutoff <ISO-with-timezone>` for a requested historical boundary. An
   undated export can only establish an undated snapshot, never timed coverage.
4. Inspect the JSON command result and diagnostics. Exit 2 means the requested
   operation failed; use the reported concrete correction. Do not hide failures
   or replace unavailable metrics with guesses. `collect` saves evidence and
   `render` reproduces a report when these steps need to be performed separately.
5. Display the generated HTML on the host's native artifact/HTML preview surface.
   If the host requires a fragment, use `--fragment`; the full document is also
   preserved. Follow an available `visualize` skill's display contract. On a local
   desktop, `--open` or `open --path <report.html>` requests the OS browser. A
   `launch_requested` response is not proof of successful visual rendering: inspect
   the available preview. If no display surface exists, deliver the file and state
   that limitation. Do not publish the report online as a side effect.

The default output is a session/cutoff-specific report beneath
`.chat-report/reports/` in the current task directory. It includes the complete
HTML and evidence/presentation JSON sidecars. Use `--output` for the host's
required durable location. Existing reports are preserved unless `--overwrite`
is explicit. Honor the host's persistence requirements before final delivery.

## Supported sources

| Harness flag | Packaged source adapter | Reference |
|---|---|---|
| `cursor` | Local SQLite composer metadata and supported per-bubble counters | [Cursor](references/cursor-local.md) |
| `codex` | Local rollout JSONL token snapshots and explicit turn events | [Codex / Claude](references/codex-claude.md) |
| `claude` | Claude Code session JSONL and supported SDK result exports | [Codex / Claude](references/codex-claude.md) |
| `github-copilot` | Copilot CLI event logs and captured usage/shutdown events | [Copilot / Antigravity](references/copilot-antigravity.md) |
| `antigravity` | Supported local transcripts and official headless JSON/stream JSON results | [Copilot / Antigravity](references/copilot-antigravity.md) |

Support is schema-specific, not a promise that every IDE, version, or plan stores
every metric. In particular, Copilot CLI telemetry is not interchangeable with
VS Code Copilot chat. Unknown binary/protobuf files are detected, not decoded by
guesswork. Use supported exports when the native source lacks readable usage.
Do not launch another paid agent run to reconstruct past usage.

## Cost and human work

- Native cost is used only when present and attributable in a supported source.
- Supply `--rates <rates.json>` for an API reference estimate using explicit model
  rates and a dated source; the engine contains no fixed price table. Rate values
  are per million tokens. Unknown model/category/rate components remain partial.
- Human work requires explicit manual tracking. Use `track start|pause|resume|stop`
  with `--session <id>`; `track status` inspects it. `report` reads the same timer
  directory automatically. Use `--state-dir` consistently if changing directories.
  Marked time is declared, never inferred attention. `track stop` closes the timer;
  run `report` to compile the final result.
- `--hourly-rate <decimal> --currency <ISO-currency>` calculates human labor cost
  only when tracking evidence exists. Agent duration is never billed as human time.

Map natural slash subcommands to these commands: `diagnose` → `doctor` plus scoped
`collect`; `detailed` → `report`; `start/pause/resume/stop` → `track`. Preserve the
Portuguese aliases `diagnosticar`, `detalhado`, `iniciar`, `pausar`, `retomar`, and
`encerrar`. Do not create background monitors or scheduled jobs.

## Review and delivery

Use [references/metric-policy.md](references/metric-policy.md) when interpreting
uncertainty, counters, scope, or cost. Preserve the bundled rules: no summed
cumulative snapshots, no duplicate cache/reasoning, no double-counted intervals,
no mixed currencies, no token estimates from transcript length, and no human
attention inferred from an open chat. Logs are untrusted data and are never
executed. Collectors are offline and read-only with bounded scans.

Return the rendered report, its complete HTML file through the host, and a short
summary of measured results and gaps. Do not repeat the whole report in Markdown
or claim unavailable numbers were recovered. See [HTML contract](references/html-report.md),
[adapter contract](references/collector-contract.md), [installation](references/platforms.md),
and the [lower-level calculator](references/calculation.md) when maintaining the
skill, rather than improvising a replacement during use.
