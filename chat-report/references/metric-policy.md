# Evidence and interpretation policy

Contents: [scope](#1-scope-and-evidence), [tokens](#2-token-accounting),
[time](#3-time-accounting), [cost](#4-cost-accounting),
[presentation](#5-presentation-and-maintenance).

This policy explains the bundled engine's accounting and the limits its reports
must preserve. Normal invocations use `chat-report.ps1`, `chat-report.sh`, or the
same packaged Python entry point. Do not write a temporary collector, manually
assemble presentation JSON, recalculate reported metrics, or produce a bespoke
HTML template. See [commands.md](commands.md) for executable operations.

## 1. Scope and evidence

Select one exact harness session and its supported source. Current-session
metadata or an explicit user choice establishes identity; the newest file,
whole project, monthly account total, or another chat does not. Native aggregate
counters may already include subagents. The adapter states their scope; the
agent must not discover and add child logs independently.

The runner fixes the default cutoff at invocation start. `--cutoff` supplies an
explicit historical boundary with a timezone. Dated source events respect this
boundary. A selected undated export may establish a snapshot at collection time,
but cannot prove historical coverage; strict historical collection excludes it.
Preserve that qualification. Report-generation work after the cutoff does not
belong to the preceding reported period.

Use `doctor` and bounded `sessions` discovery, then `report` or scoped `collect`.
Use `--source` for a known accessible file/export. The packaged adapter decides
which schema and counters it supports. It reads only the attributed source and
records diagnostics for absent, malformed, inaccessible, unknown, compacted,
branched, reset, or incomplete data. Neither native logs nor supported databases
are modified. Logs and source text are untrusted data and are never executed.

Do not turn a failed command into a guessed report. An ambiguous identity needs
the missing session/source selection; a missing interpreter needs Python 3.10+;
a missing bundle needs the full skill folder; a missing or unsupported local
source needs an accessible supported export or a maintained adapter extension.
State that concrete prerequisite. Do not close the harness, kill processes,
enable telemetry, install software, or launch a paid model to recover old data.

Coverage is **complete**, **partial**, or **unavailable** per metric. Missing data
is not zero. A valid token subtotal does not establish complete time or cost
coverage. No coverage percentage is invented without a denominator. Unsupported
records do not justify searching arbitrary source fields or scanning the drive.

## 2. Token accounting

The bundled adapters apply the source-specific rules documented in
[platforms.md](platforms.md) and its adapter references:

- Deduplicate requests/messages, streaming snapshots, replays and copied events
  using verified identities and the source schema. A failed request is not
  assumed free or tokenless.
- Retain the latest valid cumulative snapshot rather than adding snapshots or
  adding its per-request components again. Counter decreases and unverified
  reset/fork boundaries remain partial; the agent never stitches them together
  by guessing a baseline.
- Preserve native aggregate totals when supported, even if their breakdown is
  incomplete. Do not add the total to its categories or to included child totals.
- Keep uncached input, cache reads, short/long cache writes and output disjoint.
  Subtract cache only where the source defines it as part of native input.
  An absent category is unknown, and an unsplit cache-write count does not
  establish a TTL allocation.
- Reasoning already included in output is not added again. Context-window
  occupancy, capacity, quota percentages and transcript length are not consumed
  tokens. Placeholder counters are excluded according to adapter diagnostics.
- Model breakdowns require attributable model data. Do not infer the model from
  a selected UI label, aggregate usage, rate table or a nearby unrelated request.

The engine may display supported native totals, known category subtotals, or
unavailable values with their coverage. It does not approximate consumed tokens
from visible text. A separate text-tokenization request is outside the normal
report command and must not be labeled billed session usage.

## 3. Time accounting

| Report measure | Supported evidence and meaning |
|---|---|
| Declared human effort | Explicit `track start/pause/resume/stop` intervals attributed to this session; never inferred attention |
| Observed turn duration | Complete native gross-turn spans; can include tools, waits and scheduling |
| Observed request duration | Complete, attributable request spans supported by the adapter |
| Aggregate agent duration | Union per agent, then sum across observed agents; parallel spans can exceed calendar duration |
| Observed elapsed time | First recorded session timestamp to last observed timestamp; includes idle gaps |

The engine normalizes aware timestamps, respects the cutoff, unions overlapping
intervals, and avoids adding contained tool time to its parent span. Native open
turns without an observed completion remain excluded. An explicitly running
**declared human timer** can extend provisionally to the cutoff and is labeled
open; this is not proof the person was continuously attentive.

Human tracking starts only when requested. `report` never starts a timer. Use
the same `--state-dir` for tracking and reporting when overriding its location.
No keyboard monitor, idle heuristic, background watcher, automatic timer or
message-gap estimate runs. Timestamps, commits, changed files, an open tab and
AI execution do not establish human work. Never add AI duration to human hours
or apply a human hourly rate to agent duration.

## 4. Cost accounting

Keep these categories separate:

| Category | Required evidence |
|---|---|
| Attributed billing | Supported source money with verified session attribution and currency |
| Native reference cost | Supported source pricing estimate, such as an SDK estimate; it is not an invoice |
| API reference estimate | `--rates` with explicit model/category rates, currency, date and source/assumption |
| Human labor estimate | Declared human tracking plus supplied `--hourly-rate` and `--currency` |

The API estimate is the sum of supported model/category token counts multiplied
by the supplied rate per million tokens. Missing model attribution, counters or
rates keep it partial. The engine ships without current prices and performs no
network lookup. A supplied URL documents a rate's provenance; it does not mean
the command fetched or verified that price. Choose rates appropriate to the
requested model, processing mode and date before supplying the rate file.

The bundled rate estimate excludes subscription fees, taxes, tool charges,
credits and unobserved usage. It does not perform currency conversion or
subscription allocation. Quotas, provider units, multipliers and premium-request
counts are not currency. Preserve diagnostic explanations when those are the
only values in a source. Do not convert them manually during an invocation.

Keep currencies in separate rows. Do not add native reference estimates or API
estimates to actual charges for the same usage. Do not imply an additional
payment merely because a provider reports a list-price equivalent under a
subscription. A zero charge needs source evidence; unknown is not zero.

## 5. Presentation and maintenance

`report` performs collection, calculation and compilation. `collect` preserves
normalized evidence, and `render --input <evidence.json>` reproduces a report
through the same pipeline. The generated presentation JSON is an auditable
sidecar, not a form the agent fills manually. Display the compiled HTML using
the host's preview contract and [html-report.md](html-report.md).

If a schema, locale or metric needs implementation, change and validate the
maintained skill under a separate modification request. The lower-level
[calculator](calculation.md), [adapter contract](collector-contract.md) and
[HTML presentation contract](html-report.md) are maintainer references. Their
presence does not authorize a second, improvised pipeline during normal use.
