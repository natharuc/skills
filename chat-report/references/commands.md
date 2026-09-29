# Command reference

Use the bundled command runner instead of writing one-off collection or report
scripts. It selects the harness adapter, normalizes evidence, calculates metrics,
and compiles the final HTML. Keep the entire skill folder together.

## Contents

- [Runtime and operating systems](#runtime-and-operating-systems)
- [Invocation](#invocation)
- [Commands](#commands)
- [Discover and collect](#discover-and-collect)
- [Generate and display HTML](#generate-and-display-html)
- [Optional rate data](#optional-rate-data)
- [Explicit human work tracking](#explicit-human-work-tracking)
- [Failures and portability](#failures-and-portability)

## Runtime and operating systems

- `chat-report.ps1`: Windows PowerShell 5.1 or PowerShell 7 on Windows, Linux, or
  macOS. A separate Python **3.10 or newer** installation must be available as
  `py -3` on Windows, `python3`, or `python`.
- `chat-report.sh`: POSIX `sh` on Linux and macOS, with Python **3.10 or newer**
  available as `python3` or `python`.
- The shared engine uses the Python standard library. Neither launcher installs
  dependencies, downloads code, changes execution policy, nor requests elevation.
- Resolve the installed skill's absolute path once. Both launchers find bundled
  resources relative to their own location and work from any current directory.
- Run against the computer and user profile holding the conversation. A remote
  agent, container, WSL instance, or SSH host may have different local data. Use
  `--source` for an explicitly available file or directory; do not pretend that a
  remote filesystem is the user's desktop filesystem.

If a Windows execution policy blocks the `.ps1` file, do not change the policy.
Use the same bundled Python engine directly through an available interpreter:

```powershell
py -3 "C:\path to skill\chat-report\scripts\chat_report.py" doctor
```

## Invocation

From the installed skill folder in PowerShell:

```powershell
& .\chat-report.ps1 doctor
& .\chat-report.ps1 sessions --harness cursor --limit 10
& .\chat-report.ps1 report --harness cursor --session "SESSION_ID" --output ".\reports\chat-report.html" --language pt-BR --open
```

From any directory in PowerShell:

```powershell
$ChatReport = "C:\path to skill\chat-report\chat-report.ps1"
& $ChatReport report --harness codex --session "SESSION_ID" --output "C:\Reports\Task report.html" --language en
```

On Linux or macOS:

```sh
sh "/path to skill/chat-report/chat-report.sh" doctor
sh "/path to skill/chat-report/chat-report.sh" report --harness claude --session "SESSION_ID" --output "$PWD/chat-report.html" --language en --open
```

PowerShell 7 also works on Linux and macOS:

```sh
pwsh -File "/path to skill/chat-report/chat-report.ps1" doctor
```

All CLI command names and option names are lowercase. Quote paths and IDs that
contain spaces. The launchers forward arguments without evaluating them and
return the engine's exit status. Use `--help` or `<command> --help` for the current
argument contract. The commands below use `& $ChatReport` after the PowerShell
variable assignment above; the same arguments work with the POSIX launcher.

## Commands

| Command | Purpose |
| --- | --- |
| `doctor` | Inspect runtime, operating system, and local adapter availability. |
| `sessions` | List local session candidates for one harness or all adapters. |
| `collect` | Export normalized evidence for an exact session. |
| `report` | Collect, calculate, and compile an HTML report in one command. |
| `render` | Compile HTML from previously collected evidence. |
| `track` | Record explicitly declared human work intervals. |
| `open` | Open a generated HTML report using the local OS handler. |

Supported harness names are `cursor`, `codex`, `claude`, `github-copilot`, and
`antigravity`. `sessions`, `report`, and `collect` additionally accept `auto`
(the default). Automatic collection must identify the requested session
unambiguously. An adapter can
report unsupported or absent fields. A command existing does not guarantee that
the installed harness records tokens, charges, or execution intervals.

### Discover and collect

```powershell
& $ChatReport doctor
& $ChatReport sessions --harness codex --limit 20
& $ChatReport sessions --harness claude --source "C:\Exports\Claude" --limit 20
& $ChatReport collect --harness cursor --session "SESSION_ID" --output "C:\Reports\evidence.json"
& $ChatReport collect --harness github-copilot --session "SESSION_ID" --source "C:\Exports\Copilot\events.jsonl" --output "C:\Reports\copilot-evidence.json"
```

`sessions --limit` accepts **1 through 1000**, with a default of 100. Discovery is
bounded; it is not a complete machine-wide search. `--source` accepts a concrete
supported session file or a directory with a native layout recognized by that
adapter. A directory containing arbitrary export files is not automatically a
recognized native source. Use a concrete file for saved headless results, for
example `C:\Exports\Antigravity\headless-result.json`.

Choose the conversation's exact session ID from current harness metadata or the
session listing. Do not silently report the newest or the entire account as the
requested conversation. Local inspection is read-only; exported evidence and
reports are separate output files. With no `--output`, `collect` writes its
normalized evidence JSON to standard output.

### Generate and display HTML

```powershell
& $ChatReport report --harness auto --session "SESSION_ID" --output "C:\Reports\chat-report.html" --language pt-BR
& $ChatReport report --harness antigravity --session "SESSION_ID" --source "C:\Exports\Antigravity\headless-result.json" --output "C:\Reports\antigravity-report.html" --language en --open
& $ChatReport report --harness codex --session "SESSION_ID" --cutoff "2026-09-29T16:00:00Z" --output "C:\Reports\chat-report.html"
& $ChatReport render --input "C:\Reports\evidence.json" --output "C:\Reports\chat-report.html" --language en
& $ChatReport render --input "C:\Reports\evidence.json" --output "C:\Reports\chat-report-preview.html" --fragment --language pt-BR
& $ChatReport open --path "C:\Reports\chat-report.html"
```

These are alternative invocations. Existing output files are protected: choose a
new output name or explicitly add `--overwrite` to replace generated outputs.
`--task "Task title"` supplies the report heading.

Every `report` or `render` operation writes three files using the output stem:

| File | Contents |
| --- | --- |
| `chat-report.html` | Complete standalone HTML report. |
| `chat-report.evidence.json` | Normalized source evidence and diagnostics. |
| `chat-report.presentation.json` | Validated, localized report presentation. |

`--fragment` adds a fourth file, `chat-report.fragment.html`, while retaining
the standalone report. For the preview example above, that extra file is
`chat-report-preview.fragment.html`. With no `--output`, `report` and `render`
use `<current directory>/.chat-report/reports/` and generate a name from the
harness, session ID, and report cutoff. Relative output paths also resolve from
the caller's current directory. Keep the evidence file with the report for
auditing; it can contain local source paths omitted from the visual report.

Use a native HTML/artifact preview when the agent supports one. `--open` launches
the local operating system's HTML handler; it is useful when the agent runs on
the user's computer. It does not establish that a cloud or remote browser is
visible to the user. The extra fragment is intended for hosts that accept HTML
fragments rather than complete documents. See [HTML delivery](html-report.md)
for display and persistence requirements.

`--language` accepts `en` or `pt-BR`, with a default of `en`; choose the user's
language explicitly. On `collect` and `report`, `--cutoff` accepts an ISO 8601
timestamp with an explicit timezone and cannot be in the future. If omitted,
the invocation start becomes the fixed cutoff. `render` reuses the cutoff in the
evidence file, so collection, calculation, and rendering retain the same scope.

### Optional rate data

`report` and `render` accept `--rates "C:\Reports\rates.json"`. The file must be
a JSON object with exactly these top-level fields:

| Field | Required value |
| --- | --- |
| `as_of` | Valid `YYYY-MM-DD` date for the supplied rate card. |
| `source` | Nonempty pricing-assumption text or an HTTP(S) source URL without credentials. The runner does not fetch the URL. |
| `currency` | Three-letter uppercase currency code such as `USD`. |
| `models` | Nonempty object keyed by exact observed model identifiers. No aliases or wildcard matching are inferred. |

Each model must provide all five keys: `input_uncached`, `cache_read`,
`cache_write_short`, `cache_write_long`, and `output`. Values are nonnegative
decimal **strings per one million tokens**, or `null` when a category's rate is
unknown. Use decimal points without exponent notation. A known free rate is
`"0"`; it is different from `null`. Unknown fields are rejected.

This example contains **illustrative assumptions, not current provider prices**:

```json
{
  "as_of": "2026-09-29",
  "source": "Illustrative user assumption for this documentation",
  "currency": "USD",
  "models": {
    "example-model": {
      "input_uncached": "1.00",
      "cache_read": "0.10",
      "cache_write_short": "1.25",
      "cache_write_long": null,
      "output": "4.00"
    }
  }
}
```

Replace the example model ID and assumptions with explicit, attributable values:

```powershell
& $ChatReport report --harness claude --session "SESSION_ID" --rates "C:\Reports\rates.json" --output "C:\Reports\priced-report.html"
```

Calculation requires reliable usage allocated to a matching model and token
category. Missing allocations or rates produce partial or unavailable API
reference costs. Do not guess a rate or fetch prices implicitly. Actual charges,
API reference costs, and human labor estimates remain separate; see
[calculation rules](calculation.md).

### Explicit human work tracking

```powershell
& $ChatReport track start --session "SESSION_ID"
& $ChatReport track pause --session "SESSION_ID"
& $ChatReport track resume --session "SESSION_ID"
& $ChatReport track stop --session "SESSION_ID"
& $ChatReport track status --session "SESSION_ID"
```

The default timer directory is `<current directory>/.chat-report/timers/`.
`track`, `report`, and `render` accept `--state-dir` to use an explicit location.
When changing working directories, supply the **same state directory and session
ID** for tracking and report generation so the report can find those intervals:

```powershell
$TimerState = "C:\Reports\tracking"
& $ChatReport track start --session "SESSION_ID" --state-dir $TimerState
& $ChatReport track pause --session "SESSION_ID" --state-dir $TimerState
& $ChatReport report --harness codex --session "SESSION_ID" --state-dir $TimerState --output "C:\Reports\tracked-report.html" --language pt-BR
```

Optionally supply `--hourly-rate` and `--currency` **together** to estimate human
labor from the declared intervals. The hourly rate is a nonnegative decimal
string and the currency is a three-letter uppercase code. This example assumes
BRL 150 per hour; it is not a prescribed rate:

```powershell
& $ChatReport report --harness codex --session "SESSION_ID" --state-dir $TimerState --hourly-rate "150.00" --currency BRL --output "C:\Reports\labor-report.html" --language pt-BR
```

These commands record declared work intervals. They do not observe attention,
keyboard activity, or retrospectively measure work before tracking began. Start,
pause, resume, or stop only when the user requests that action. Generating a
report must not start a work timer. An active interval is counted only through
the report cutoff, and the report identifies it as still open. A supplied hourly
rate cannot produce a labor estimate without recorded human effort.

## Failures and portability

Read the command's diagnostics rather than replacing unknown metrics with zero.
If a source is missing, unsupported, encrypted, locked, or unavailable from the
current host, retain that reason and use an explicit accessible export when the
adapter supports it. Never bypass permissions or modify a harness database.

Launcher exit codes: `2` for an incomplete skill folder, `127` for a missing or
too-old Python interpreter, and `126` for failure to launch a selected interpreter.
After Python starts, the engine's exit code passes through unchanged. The
PowerShell launcher is compatible by design with PowerShell 5.1 and 7; availability
of a local PowerShell runtime determines whether native execution can be tested.
