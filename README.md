# Skills

Portable skills for coding agents.

## chat-report

Generate a **complete, responsive, offline HTML report** for a conversation or task, covering:

- input, output, and cache tokens according to available telemetry;
- human work time, agent execution, and elapsed time as separate measures;
- attributed charges, API reference costs, and human labor costs without conflating them;
- sources, coverage, and concrete limitations;
- packaged read-only adapters for Cursor, Codex, Claude Code, Copilot CLI, and Antigravity.

The skill displays the report using the agent's available preview. When the interface cannot display HTML, it delivers the complete file and explains the limitation.

Instructions and documentation are written in English. Reports support English and Brazilian Portuguese.

### Installation

Copy the complete [chat-report](./chat-report) folder, including its resources, to your agent's skill location:

| Agent | Project folder |
|---|---|
| Cursor | `.cursor/skills/chat-report/` |
| Claude Code | `.claude/skills/chat-report/` |
| Codex CLI/IDE | `.agents/skills/chat-report/` |
| Copilot CLI | `.github/skills/chat-report/` |

See [integrations and alternatives](./chat-report/references/platforms.md).

### Usage

```text
/chat-report
/chat-report detailed
/chat-report diagnose
```

In Codex CLI, invoke it as `$chat-report`. To track human work time manually, use `start`, `pause`, `resume`, and `stop` after the skill name.

Existing Portuguese aliases remain supported: `detalhado`, `diagnosticar`, `iniciar`, `pausar`, `retomar`, and `encerrar`.

### Bundled commands

The agent invokes a fixed command suite; it does not write temporary collectors or report generators.

```powershell
# Windows PowerShell 5.1 or PowerShell 7, from the skill folder
& .\chat-report.ps1 doctor
& .\chat-report.ps1 sessions --harness cursor
& .\chat-report.ps1 report --harness cursor --session "SESSION_ID" --language pt-BR --open
```

```sh
# Linux/macOS; PowerShell 7 is also supported when installed
sh /path/to/chat-report/chat-report.sh report --harness codex --session "SESSION_ID" --language en --open
```

Commands: `doctor`, `sessions`, `collect`, `report`, `render`, `track`, and `open`.
The `report` command compiles standalone HTML plus evidence and presentation JSON. `--fragment` adds a host-preview fragment. `--open` requests the local OS browser; the agent uses its native HTML preview when available.

Both launchers require **Python 3.10+**, with no pip packages. No runtime installation, execution-policy changes, network collection, or price downloads happen automatically. Explicit rate cards and manual human-work timers are supported.

| Adapter | Recognized sources |
|---|---|
| Cursor | Local SQLite composer records and supported bubble counters |
| Codex | Local rollout JSONL usage snapshots and turn events |
| Claude Code | Session JSONL and supported SDK result records |
| GitHub Copilot | Copilot CLI event logs; does not claim VS Code IDE telemetry |
| Antigravity | Official headless JSON/stream JSON results and recognized local transcript discovery |

Unknown schemas and unavailable metrics produce diagnostics. Run on the computer holding the session data, or pass a supported export with `--source`.

### Resources

- [Full instructions](./chat-report/SKILL.md)
- [Command reference and rate-card schema](./chat-report/references/commands.md)
- [Cursor collection](./chat-report/references/cursor-local.md)
- [Codex and Claude collection](./chat-report/references/codex-claude.md)
- [Copilot and Antigravity collection](./chat-report/references/copilot-antigravity.md)
- [Auditable calculations](./chat-report/references/calculation.md)
- [HTML generation and display](./chat-report/references/html-report.md)

The Python engine and shell launcher have synthetic regression coverage on Linux. Windows/macOS path rules are covered by fixtures; native execution on those operating systems still requires verification.

The skill cannot recover data that was never recorded. Zero-valued local counters, context occupancy, and time with a chat open do not establish zero consumption, billed tokens, or human work hours. Collection must be verified against the actual installation.
