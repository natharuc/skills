# Skills

Portable skills for coding agents.

## chat-report

Generate a **complete, responsive, offline HTML report** for a conversation or task, covering:

- input, output, and cache tokens according to available telemetry;
- human work time, agent execution, and elapsed time as separate measures;
- attributed charges, API reference costs, and human labor costs without conflating them;
- sources, coverage, deliverables, and limitations;
- read-only collection of local Cursor metadata.

The skill displays the report using the agent's available preview. When the interface cannot display HTML, it delivers the complete file and explains the limitation.

Instructions and documentation are written in English. Reports follow the user's requested language or the conversation language, with English as the fallback.

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

### Resources

- [Full instructions](./chat-report/SKILL.md)
- [Cursor collection](./chat-report/references/cursor-local.md)
- [Auditable calculations](./chat-report/references/calculation.md)
- [HTML generation and display](./chat-report/references/html-report.md)

The optional scripts use Python 3 with no external dependencies. The agent can perform an equivalent workflow when Python is unavailable.

The skill cannot recover data that was never recorded. Zero-valued local counters, context occupancy, and time with a chat open do not establish zero consumption, billed tokens, or human work hours. Collection must be verified against the actual installation.
