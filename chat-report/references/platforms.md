# Sources and integration by agent

Contents: [installation](#local-installation-and-invocation), [Cursor](#cursor),
[Claude Code](#claude-code), [Codex and ChatGPT](#codex-and-chatgpt),
[GitHub Copilot](#github-copilot), [other environments](#unlisted-agent-or-restricted-environment).

Use this as a discovery guide, not a guarantee of access. Verified on 2026-09-29.
Confirm the installed version and current documentation when the schema differs.
Do not create an administrative integration or enable telemetry as a side effect
of producing a report.

## Local installation and invocation

Copy the entire folder under the name `chat-report`, preserving `SKILL.md`,
`references/`, `scripts/`, and `assets/`. Use only one location per
installation to avoid duplicates. Resolve `~` to the operating system's home
directory; do not assume Bash is available on Windows. If distributing only
`SKILL.md`, retain its rules and omit unavailable resources without claiming to
have executed them.

| Host | Project directory | Personal alternative | Invocation |
|---|---|---|---|
| Cursor | `.cursor/skills/chat-report/` or `.agents/skills/chat-report/` | `~/.cursor/skills/chat-report/` | `/chat-report` |
| Claude Code | `.claude/skills/chat-report/` | `~/.claude/skills/chat-report/` | `/chat-report` |
| Codex CLI/IDE | `.agents/skills/chat-report/` | `~/.agents/skills/chat-report/` | `$chat-report` or selection through `/skills` |
| Copilot CLI | `.github/skills/chat-report/` or `.agents/skills/chat-report/` | `~/.copilot/skills/chat-report/` | `/chat-report` |
| ChatGPT with the skill installed | The host's own skills directory | Managed by the host | Select `@chat-report` |
| Other agent | Location documented by the host | As supported | Load SKILL.md as a skill, command, or instructions |

Do not claim the skill is installed on the user's computer merely because it was
saved in another environment. Local Cursor skills do not automatically reach
remote sessions. Do not generalize Copilot CLI support to every IDE. Verify host
discovery before promising that a command will work. `agents/openai.yaml` is
optional metadata; other agents may ignore it.

Installation sources:
- [Cursor — Skills](https://cursor.com/docs/skills)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills)
- [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills)
- [GitHub — Copilot CLI skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)

## Cursor

Follow [cursor-local.md](cursor-local.md) before concluding that data is
unavailable. Use `scripts/inspect_cursor.py` to read only the correct composer's
metadata in `state.vscdb`, with schema detection. The transcript and
`ai-code-tracking.db` alone do not exhaust local sources. The collector returns
candidates, not billed totals, and does not guarantee that the installed version
has populated counters.

Prioritize usage exports and session logs that are actually available. When
authorized access to the Admin API exists, check `conversationId`, which may be
absent; without a conversation link, do not attribute events precisely to this
chat. Token data is also optional. Distinguish `chargedCents` (attributed amount,
including any applicable fee) from model cost in `tokenUsage.totalCents`. Check
the usage and billing type: usage included in the plan does not demonstrate an
additional payment. Respect source delays and update limits; do not treat a
recent absence as zero.

Do not assume every user or plan has Admin API access. In the CLI, inspect the
available structured output; do not use `duration_api_ms` as an independent
measurement of `duration_ms` when the implementation makes them equal. Without
usage fields, do not reconstruct tokens from duration.

Sources:
- [Cursor — Admin API](https://cursor.com/docs/account/teams/admin-api)
- [Cursor CLI — Output format](https://cursor.com/docs/cli/reference/output-format)

## Claude Code

Consult the usage summary available in the installed version, such as `/usage`
in the currently documented versions, or data exported by the user. Keep
estimated cost labeled as an estimate, including under subscriptions. Check
session boundaries, resumptions, and resets before using totals; do not treat
older command names as a universal interface.

When OpenTelemetry is already enabled, look for token, cost, duration, and ID
metrics/events to associate the session and subagents. Inspect the semantics of
`claude_code.active_time.total` and its `type` dimension; activity recorded by
the CLI does not prove the human was exclusively attending to this task. A
`total_tokens` counter in a subagent completion event may represent only its last
request, not its entire execution.

In the statusline, do not interpret `context_window.total_input_tokens` and
`total_output_tokens` as accumulated billed usage without checking the schema:
the current documentation describes them relative to the context/last response.
Separate session duration from API duration.

Sources:
- [Claude Code — Costs](https://code.claude.com/docs/en/costs)
- [Claude Code — Monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Claude Code — Statusline](https://code.claude.com/docs/en/statusline)

## Codex and ChatGPT

Use the usage/rollout data that the host actually exposes for the correct thread.
In app-server, `thread/tokenUsage/updated` provides usage updates;
`turn/started`, `turn/completed`, and item events contain IDs useful for
reconstruction. Inspect the schema and distinguish cumulative usage from the
last turn; do not add both together.

A tool with `durationMs` does not demonstrate the duration of the entire session.
Associate child sessions through collaboration links. Do not assume the ChatGPT
interface exposes rollouts, private metrics, or local files. Subscription-limit
percentages are not tokens or money. If only the visible conversation is
available, produce a partial report.

Sources:
- [OpenAI — App server](https://learn.chatgpt.com/docs/app-server)
- [OpenAI — Codex pricing](https://developers.openai.com/codex/pricing)

## GitHub Copilot

Identify the surface: CLI, SDK, or IDE chat. In the CLI, consult `/usage` when
available, preserving tokens by model and credits in their original unit. If
using OpenTelemetry that is already enabled, do not interpret
`github.copilot.cost` as money: the CLI documentation describes it as a billing
multiplier.

In the SDK, check the version: `assistant.usage` events may be ephemeral and may
not reappear when resuming a session. Totals from `session.usage.getMetrics`
depend on experimental support. Do not interpret
`session.usage_info.currentTokens` as accumulated usage. Without a complete
history, declare partial coverage even if the session resumes normally.

Sources:
- [GitHub — Copilot CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [GitHub — SDK usage and billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing)

## Unlisted agent or restricted environment

Inspect available resources without assuming paths or database names. If an
official usage source is available, adapt it to the categories in SKILL.md and
record the mapping. Without a terminal, calculate using an available native
capability or present reliable counters without unverifiable aggregation.
Without telemetry/timestamps, report evidenced deliverables and mark missing
metrics as unavailable.

Look up current sources for rates and exchange rates only when the calculation
requires them. Do not use these integration pages as evidence of a particular
rate. For future tracking, use the manual markers in SKILL.md or propose separate
instrumentation when requested; do not promise to recover data that was never
recorded.
