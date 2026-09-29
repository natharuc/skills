# Compiled HTML report

Contents: [visual delivery](#visual-delivery), [execution](#execution),
[presentation contract](#presentation-contract),
[fictional example](#fictional-example), [guarantees and limitations](#guarantees-and-limitations).

## Visual delivery

The default result is a **fully populated** HTML document that is polished,
responsive, and auditable. Produce the final file and open it in the native
HTML preview, artifact, or browser surface provided by the host. Showing source
code or a download link does not replace a preview when one is available.
Save the complete document to the destination authorized by the host, even when
the preview uses a fragment. Suggested name: `chat-report-<session>-<cutoff>.html`.

Use `--fragment` only for hosts that accept CSS and static HTML in a native visual
surface. It contains `<style>` and `<main>`, without `doctype`, `html`, `head`,
`body`, or JavaScript. CSS is scoped to `.chat-report`. Do not inject the complete
document into an API that accepts only fragments. If the surface strips styles,
prefer a preview of the complete file. If no visual capability exists, deliver
the HTML and state the limitation without claiming that a preview was shown.

The layout contains four key metrics, an evidence table, optional breakdowns by
model or agent, supported events, deliverables, and limitations. Do not invent
charts, progress bars, timelines, or distributions without supporting data.
The HTML remains readable without JavaScript, offline, and in print.

The skill instructions are written in English; the **report follows the user's
language or explicit language request**. Set `language` to `en` or `pt-BR` in the
presentation JSON, and write all supplied labels, notes, and other text in that
same language. The renderer defaults to English if `language` is omitted. It
localizes built-in headings, fallback labels, status and coverage badges, and
HTML `lang` attributes. It does not translate supplied text or reformat values.
For other languages, generate an equivalent localized HTML document or adapt a
copy of the renderer/template, preserving every evidence and safety rule. Do
not pass an unsupported language to this renderer or silently force English.

## Execution

The renderer uses only the Python 3 standard library. From the skill directory:

```sh
python3 scripts/render_report.py presentation.json --output chat-report.html
python3 scripts/render_report.py presentation.json --output chat-report-fragment.html --fragment
```

`--overwrite` explicitly permits replacing an existing file. Without it, the
file is preserved and execution fails. The renderer creates required parent
directories, rejects an output path equal to the input path, and prints a JSON
object to stdout with `output` and `format` (`standalone` or `fragment`). Errors
produce an `error` object on stderr and exit code 2; success returns 0.

The script validates **presentation data**. It does not consume `calculate.py`
output directly or recalculate tokens, durations, currencies, or costs. Prepare
the JSON after checking evidence and calculations. The same JSON generates both
output forms. CLI help and validation errors are written in English.

## Presentation contract

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

This JSON is **FICTIONAL**, only to exercise the layout. Do not reuse its numbers,
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
- The contract preserves supplied text. The agent must distinguish subtotals,
  totals, actual billing, reference costs, estimates, declarations, and missing
  data; confirm events and deliverables; and avoid unsupported precision.
- Printing uses dedicated CSS. Inspect the final report in the available host,
  especially on narrow screens or with long text. The fragment uses scoped
  styles, but its appearance can also depend on the host's rules.
