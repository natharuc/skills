# Compiled HTML report

Contents: [visual delivery](#visual-delivery), [command execution](#command-execution),
[maintainer presentation contract](#presentation-contract),
[fictional example](#fictional-example), [guarantees and limitations](#guarantees-and-limitations).

Normal use follows the bundled command pipeline in [SKILL.md](../SKILL.md) and
[commands.md](commands.md). The runner selects the maintained adapter, normalizes
evidence, calculates metrics, creates presentation data, and compiles the HTML.
The agent must not create a temporary collector, hand-build presentation JSON,
write replacement rendering functions, or design a fresh HTML template for each
invocation. Install and retain the full skill folder; `SKILL.md` alone is not
an executable distribution.

## Visual delivery

The default result is a **fully populated**, responsive and auditable HTML file.
Display that file using the host's native HTML preview, artifact or browser
surface. A code editor or download link does not replace an available visual
preview. Preserve the full document and generated evidence/presentation sidecars
at the host's required durable destination. Use the runner's session/cutoff-specific
default filename or supply `--output`; do not overwrite an unrelated report.

When a native surface requires a fragment, invoke the runner with `--fragment`.
It also preserves the complete document. The fragment contains `<style>` and
`<main>`, without `doctype`, `html`, `head`, `body` or JavaScript; its CSS is scoped
to `.chat-report`. Follow the surface's actual display contract rather than
inserting a complete document into a fragment-only API. If styles are stripped,
use a full-file preview when available.

On the user's local desktop, `--open` or `open --path <report.html>` requests the
OS browser handler. A successful launch request does not prove that the user saw
rendered content, especially in a remote/container environment. Inspect an
available preview before claiming display. If the host has no visual surface,
deliver the compiled HTML and state that no preview was displayed. Do not publish
the report online, install an extension, or enable remote browser access as a
side effect.

The maintained layout contains four main metrics, an evidence table, model/agent
breakdowns when supported, sources and limitations. The renderer contract also
supports attributed events and deliverables for maintained integrations; the
normal runner does not invent these to fill space. The document remains readable
offline, without JavaScript, and in print.

The skill instructions are English. The bundled report locales are **`en` and
`pt-BR`**: choose `--language` from the user's request/conversation, as specified
in `SKILL.md`. Built-in headings, diagnostics, badges, fallback text, number
formatting and HTML language follow that selection through the command pipeline.
For another requested language, disclose the current locale limit. Do not claim
to support it, create a one-off localized template, or modify a renderer copy
while generating a report. Additional locales require a maintained skill change.

## Command execution

The entire workflow uses the existing Python 3.10+ standard-library engine with
PowerShell or POSIX shell launchers. For example, from the installed skill folder:

```powershell
& .\chat-report.ps1 report --harness codex --session "SESSION_ID" --language en --open
& .\chat-report.ps1 render --input "evidence.json" --output "report.html" --language pt-BR
& .\chat-report.ps1 render --input "evidence.json" --output "report-fragment.html" --fragment --language pt-BR
```

```sh
sh "/path/to/chat-report/chat-report.sh" report --harness claude --session "SESSION_ID" --language en --open
```

Use `doctor` for runtime/source diagnostics. A missing interpreter requires
Python 3.10+; missing assets/scripts require the full bundle; a remote computer
without the local source needs an accessible supported export. State the concrete
prerequisite rather than installing packages, changing execution policy or
substituting loose functions. The normal workflow requires no network service.

`collect` saves normalized evidence. `render --input` consumes that evidence and
reuses the deterministic calculation/presentation pipeline; it does **not** ask
the agent to prepare presentation JSON. `report` does both in one invocation.
Existing outputs are preserved unless `--overwrite` is explicit. Read the JSON
command result and diagnostics and surface failures rather than sending an
unpopulated template as a successful report.

### Lower-level renderer for maintainers

The rest of this file documents the renderer's internal presentation contract
for maintaining the skill, adding a supported integration and running fixtures.
It is not an alternative workflow for routine `/chat-report` calls. The runner
creates this data and calls the lower-level renderer. Maintainer examples:

```sh
python3 scripts/render_report.py presentation.json --output renderer-fixture.html
python3 scripts/render_report.py presentation.json --output renderer-fragment-fixture.html --fragment
```

This lower-level renderer validates presentation structure; it does not collect
logs, calculate token/duration totals, consume `calculate.py` output directly,
translate supplied free text, or verify evidence authenticity. It creates parent
directories, rejects identical input/output paths, and preserves an existing
output unless `--overwrite` is set. It prints JSON with `output` and `format` on
success; a validation error produces an `error` object on stderr and exit code 2.

## Presentation contract

**Maintainer reference:** the command pipeline generates this object. Do not ask
the reporting agent to fill it by hand. Supplied text must already match the
selected locale; the low-level renderer does not translate it or reformat values.

Unknown fields, duplicate JSON keys, `NaN`, incorrect types, empty strings,
duplicate IDs, and references to undefined sources are rejected. Optional
objects/lists must be omitted rather than set to `null`; `null` is allowed only
for the text fields described as optional. Text is literal, not HTML or Markdown.

| Root field | Type and rule |
|---|---|
| `version` | Required: integer `1`. |
| `language` | Optional: `en` or `pt-BR`; defaults to `en`. Select the user's requested report language. |
| `task` | Required: nonempty text, a brief task title. |
| `scope` | Optional text or `null`, the attributed scope. |
| `period` | Optional object with `start`, `cutoff`, and `timezone`; each field is display text or `null`. No date parsing or time zone inference occurs. |
| `summary` | Optional text or `null`, an evidence-based summary. |
| `metrics` | Optional list of metrics in the format below. |
| `breakdowns` | Optional list of objects `{ "title": text, "metrics": [metric, ...] }`; each group requires at least one metric. Use for identified models or agents. |
| `timeline` | Optional list of events `{ "time": text, "title": text, "detail": text or null, "source_ids": [id, ...] }`. `time`, `title`, and at least one source are required. Supplied order is preserved. |
| `deliverables` | Optional list of objects `{ "label": text, "detail": text or null, "source_ids": [id, ...] }`; the label and at least one source are required. Confirmed outcomes only. |
| `sources` | Optional list of sources in the format below. |
| `limitations` | Optional list of nonempty strings describing gaps, attribution, coverage, assumptions, and precision. |

Each **metric** accepts exactly:

| Field | Type and rule |
|---|---|
| `id` | Required text, unique within its own list. |
| `label` | Required text: the precise name of the measure. |
| `value` | A formatted string or `null`; omission is equivalent to `null`. JSON numbers are rejected. |
| `status` | `measured`, `declared`, `calculated`, `estimated`, or `unavailable`; defaults to `unavailable`. |
| `coverage` | `complete`, `partial`, or `unavailable`; defaults to `unavailable`. |
| `source_ids` | List of existing source IDs; at least one source if `value` is not `null`. Duplicate IDs are rejected. |
| `note` | Optional text or `null`: method, qualification, assumption, or gap. |

English status labels are **Measured**, **Declared**, **Calculated**,
**Estimated**, and **Unavailable**; the renderer localizes these labels for
`pt-BR`. A known value requires a status other than `unavailable`, `complete` or
`partial` coverage, and a source. A `null` value requires `unavailable` status
and coverage. Include zero as formatted text only when supported by evidence.
The validator checks structural consistency, not authenticity.

In the root `metrics` list, four IDs select the main cards:

| ID | Use |
|---|---|
| `human_time` | Human effort; do not substitute AI duration or gaps between messages. |
| `agent_time` | Agent execution, or raw duration explicitly identified in `label`. |
| `tokens` | Observed usage; for partial coverage use, for example, `"Subtotal: 3,600"`, in addition to the visible partial-coverage badge. |
| `cost` | One specific cost category. Preserve the currency and precise category in `label`, such as "API reference estimate" or "Attributed billing". Never add these two categories together. |

The supplied label, value, and qualification are also preserved in the card.
Missing main IDs generate **Unavailable** cards and table rows with no numbers,
localized to the selected language. Other metrics appear in the table in their
supplied order. Show additional costs as separate rows with their own IDs. Do
not create a total across currencies. If the cost is unknown, the card says it
is unavailable.

Each **source** accepts required `id` and `label`, optional text or `null` for
`detail`, and optional text or `null` for `url`. IDs link evidence internally and
are not printed; the UI uses local numbering. URLs allow only `http` or `https`,
without credentials, and become conventional links without automatic fetching.
Prefer sanitized labels such as "Session usage export", without transcripts,
access tokens, sensitive paths, credentials, or unnecessary internal identifiers.
The renderer **does not automatically redact** text: prepare safe data first.

## Fictional example

This maintainer fixture is **FICTIONAL**, only to exercise the layout. Do not reuse its numbers,
dates, price, or deliverables in a real report.

```json
{
  "version": 1,
  "language": "en",
  "task": "FICTIONAL — Report demonstration",
  "scope": "Fictional session and linked agents",
  "period": {
    "start": "29 Sep 2026 · 10:00",
    "cutoff": "29 Sep 2026 · 10:10",
    "timezone": "UTC"
  },
  "summary": "Fictional demonstration of one deliverable and its known usage.",
  "metrics": [
    {
      "id": "human_time", "label": "Human effort", "value": null,
      "note": "No timer or human effort declaration is available."
    },
    {
      "id": "agent_time", "label": "Agent execution", "value": "6 min",
      "status": "calculated", "coverage": "complete", "source_ids": ["demo"],
      "note": "Union of observed intervals."
    },
    {
      "id": "tokens", "label": "Tokens consumed", "value": "Subtotal: 3,600",
      "status": "measured", "coverage": "partial", "source_ids": ["demo"],
      "note": "One agent has no telemetry."
    },
    {
      "id": "cost", "label": "API reference estimate", "value": "US$ 0.00665",
      "status": "estimated", "coverage": "partial", "source_ids": ["demo"],
      "note": "Reference subtotal; fictional rate."
    }
  ],
  "timeline": [{
    "time": "10:06 UTC", "title": "Validation completed",
    "detail": "Fictional event documented for demonstration.", "source_ids": ["demo"]
  }],
  "deliverables": [{
    "label": "Demonstration report", "source_ids": ["demo"]
  }],
  "sources": [{
    "id": "demo", "label": "Fictional data",
    "detail": "Documentation example; does not represent a real session."
  }],
  "limitations": ["All data in this example is fictional."]
}
```

Minimum valid input: `{"version": 1, "task": "Task name"}`. It produces an
English report with no invented numbers, no sources, and unavailable metrics.
Set `"language": "pt-BR"` and supply Portuguese text for a Portuguese report.
Do not add events or deliverables merely to fill empty space.

## Guarantees and limitations

- The final HTML contains prerendered values. It needs no scripts to populate the
  display; there is no CDN, external font, library, or network dependency.
- `html.escape(..., quote=True)` protects all supplied text and attributes. CSS
  classes come only from validated enums. Strings containing tags appear as text.
- Source links are accessed only through user action; the renderer does not query
  services, environment variables, logs, prices, or telemetry.
- The template contains only structure and styles, without sample metrics or
  events. Do not deliver the placeholder template as if it were the final report.
- The contract preserves supplied text. The maintained presentation pipeline must distinguish subtotals,
  totals, actual billing, reference costs, estimates, declarations and missing
  data. Any supported event/deliverable extension requires attributed evidence
  and appropriate precision.
- Printing uses dedicated CSS. Inspect the final report in the available host,
  especially on narrow screens or with long text. The fragment uses scoped
  styles, but its appearance can also depend on the host's rules.
