# Installation and local harness support

Install the **entire `chat-report` folder**, including both launchers, `SKILL.md`,
`scripts/`, `references/`, `assets/`, and any agent metadata. A standalone
`SKILL.md` is not a working distribution: the bundled commands and resources are
required. Use one installation location per host to avoid duplicate discovery.

The agent follows [SKILL.md](../SKILL.md) and the [command reference](commands.md).
It selects a session, runs the packaged command, checks diagnostics, and displays
the compiled HTML. It does not invent a collector, run loose parsing functions,
query arbitrary databases, or assemble a replacement report during invocation.

## Skill discovery locations

These are installation locations already documented for the named surfaces.
Resolve `~` to the account running that host; verify host skill discovery when
using an unfamiliar version or remote workspace.

| Host | Project directory | Personal alternative | Invocation |
|---|---|---|---|
| Cursor | `.cursor/skills/chat-report/` or `.agents/skills/chat-report/` | `~/.cursor/skills/chat-report/` | `/chat-report` |
| Claude Code | `.claude/skills/chat-report/` | `~/.claude/skills/chat-report/` | `/chat-report` |
| Codex CLI/IDE | `.agents/skills/chat-report/` | `~/.agents/skills/chat-report/` | `$chat-report` or selection through `/skills` |
| Copilot CLI | `.github/skills/chat-report/` or `.agents/skills/chat-report/` | `~/.copilot/skills/chat-report/` | `/chat-report` |
| ChatGPT with the skill installed | Host-managed skills directory | Managed by the host | Select the installed skill |

For Antigravity or another surface, use its documented skill installation
mechanism and preserve the full folder. This reference does not prescribe an
unverified installation path or promise a slash command in every interface.
`agents/openai.yaml` is optional discovery metadata and may be ignored by other
hosts. Installing in one environment does not install the skill on another
computer, in WSL, or in an SSH/container session.

Installation references:

- [Cursor — Skills](https://cursor.com/docs/skills)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills)
- [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills)
- [GitHub — Copilot CLI skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)

## Executable entry points

| Computer | Bundled entry point | Prerequisite |
|---|---|---|
| Windows | `chat-report.ps1` | Windows PowerShell 5.1 or PowerShell 7, plus Python 3.10+ |
| Linux/macOS | `sh chat-report.sh` | POSIX `sh`, plus Python 3.10+ |
| Windows/Linux/macOS with PowerShell 7 | `pwsh -File chat-report.ps1` | PowerShell 7, plus Python 3.10+ |
| Host with direct Python execution | `python3 scripts/chat_report.py` | Python 3.10+; use the installed interpreter's actual command |

Both launchers use the same standard-library engine. `doctor` checks runtime and
local adapter availability; `sessions` lists bounded candidates; `report`
collects and compiles the selected session; `open` requests local visual display.
Use [commands.md](commands.md) for arguments and copyable commands.

The collection and rendering workflow is offline. It does not download packages,
prices, or parsers, enable telemetry, launch a paid model request, install an
extension, elevate privileges, or change execution policy. If the PowerShell file
is blocked, an already available Python interpreter can run the **same bundled
engine** directly. If Python, the full folder, local data, or a required permission
is missing, state that concrete prerequisite. Do not replace the command suite
with ad hoc code to imply that an unsupported environment worked.

## Bundled source adapters

| `--harness` | Supported source family | Detailed reference |
|---|---|---|
| `cursor` | Local SQLite composer metadata and recognized bubble counters | [Cursor local adapter](cursor-local.md) |
| `codex` | Rollout JSONL with token snapshots and explicit turn events | [Codex and Claude adapters](codex-claude.md) |
| `claude` | Claude Code session JSONL and supported Agent SDK result exports | [Codex and Claude adapters](codex-claude.md) |
| `github-copilot` | Copilot CLI event logs and captured usage/shutdown events | [Copilot and Antigravity adapters](copilot-antigravity.md) |
| `antigravity` | Supported local transcripts and official headless result exports | [Copilot and Antigravity adapters](copilot-antigravity.md) |

These adapters cover known schemas, not every product sharing a brand. Copilot
CLI data does not establish support for every Copilot IDE chat, and Codex local
rollouts do not imply access to ChatGPT's internal session metrics. Native
transcripts, usage exports, and current-session hints differ by host. Follow the
adapter's recorded diagnostic instead of guessing undocumented fields.

Run on the computer and account holding the conversation. A remote agent may
accept an explicitly available supported export via `--source`; it cannot read
the user's desktop through an unrelated filesystem. Preserve exact session
identity and avoid selecting the newest candidate automatically. An unsupported
binary format requires a supported export or a maintained adapter extension,
not an improvised decoder.

A visual report also requires a native HTML/artifact preview or an OS browser on
the relevant desktop. When none is available, deliver the compiled HTML through
the host and state that no preview was displayed. See [HTML delivery](html-report.md).
