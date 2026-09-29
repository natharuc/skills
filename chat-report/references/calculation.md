# Optional offline calculation

Contents: [input contract](#input-contract),
[output and interpretation](#output-and-interpretation),
[runnable example](#runnable-example).

`scripts/calculate.py` accepts a normalized JSON file, uses only the Python 3
standard library, and prints JSON to stdout. It does not collect logs, look up
prices, access the network, change files, or infer time from messages. Errors
are written as JSON to stderr with exit code 2. Run it with `python` (or
`python3`, depending on the installation):

```sh
python scripts/calculate.py normalized.json
```

## Input contract

- `scope`: a nonempty `label`, a required `cutoff`, and an optional `start`.
  Timestamps use `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` or an offset of `±HH:MM`; a
  timezone is required. The adapter must select only requests within the scope
  up to the cutoff; the script does not receive request timestamps or verify
  that selection.
- `coverage`: `complete` or `partial`, applying to the dataset for the scope.
  Use `complete` only with evidence that the relevant sources provide complete
  coverage.
- `coverage_by_metric`: an optional object with optional keys `tokens`, `agent`,
  and `human`, each set to `complete` or `partial`. Each key overrides global
  coverage only for its metric; omitted keys inherit `coverage`. Token coverage
  also governs costs. For example, partial token coverage and complete human
  observation: `"coverage": "partial", "coverage_by_metric": {"human": "complete"}`.
- `requests`: an optional list. Each object contains an `id` with nonempty
  strings for `provider`, `session`, and `request`, and `tokens` with **all** five
  categories: `input_uncached`, `cache_read`, `cache_write_short`,
  `cache_write_long`, and `output`. Each count is an integer ≥ 0 or `null`.
  Categories must be **disjoint**; normalize the provider's inclusive counters
  before calling the script. Cache reads and writes must not remain included in
  `input_uncached`. Do not add reasoning tokens again if they are already included
  in output. The script does not accept a separate reasoning category.
- Zero means confirmed absence in that category. Use `null` when the value is
  unavailable; do not assume zero for a field missing from the log.
- `pricing` is optional per request; omit the object when prices are unavailable.
  When present, it requires `currency` (three uppercase letters), `source`
  (a nonempty reference), `as_of` (`YYYY-MM-DD`, the date of the applicable price
  schedule), and `per_million` with the same five categories. Rates are
  nonnegative decimal strings without an exponent, or `null`; for example,
  `"2.50"`. Record prices applicable to the selected model, tier, context window,
  operation, and date. A URL in `source` is metadata only: the script does not
  visit it or verify the price schedule.
- `agent_intervals`: an optional list of objects containing `start`/`end` and
  `agent_id` (a nonempty, stable string identifying the observed agent). Each
  interval represents observed execution with a known end. Overlapping and
  duplicate intervals for the same agent are merged before effort is summed;
  different IDs preserve parallel work by separate agents.
- `human_intervals`: an optional list containing `start`/`end` and `basis`, which
  must be `measured` or `declared`. Include only explicitly measured or declared
  human time. Message timestamps, tool execution, and silence do not measure
  human attention. Declared intervals remain declarations, not measurements.
- Intervals must satisfy `start ≤ end ≤ cutoff`; when `scope.start` is present,
  no interval may begin before it. There is no automatic clipping. Missing or
  `null` end timestamps are rejected: report open activities outside the
  calculation. Include a zero duration only when observed or explicitly declared.
- Unknown fields, omitted categories, incorrect types, and duplicate JSON keys
  are rejected. Omitted and empty lists produce unavailable metrics (`null`),
  not evidence of zero usage or duration.

## Output and interpretation

`known_subtotal` sums only known values; `total` is populated only when there is
evidence, no component is missing, and the metric's effective coverage is
`complete`. With effective coverage of `partial`, `total` remains `null` even
when the subtotal can be calculated. The output repeats global coverage and
effective coverage in `coverage_by_metric`. Each calculated result has a
`coverage` of `complete`, `partial`, or `unavailable`;
`known_values`/`missing_values` count components, not tokens. For calendar time,
components are the merged intervals; they do not represent individual activities.
Never present a subtotal as the complete total for the scope.

Requests with the same `provider/session/request` tuple and identical contents
are counted once. The same ID with different contents causes an error, including
conflicting prices or metadata. Reconcile the source before calculating; do not
silently choose one version.

Costs are an **API reference estimate**, calculated with `Decimal` for each
request/category as `tokens × rate / 1,000,000` and preserved as decimal strings
without rounding to cents. They are not billed cost, an invoice, a subscription
price, or observed financial savings. There is no total across currencies: see
`currency_buckets` and the rows in `reference_api_cost.requests`. A category with
confirmed zero tokens has zero cost even if its rate is unknown, provided the
currency is identified; unknown token counts remain unavailable. Requests
without `pricing` appear in `unassigned_currency_requests` and prevent complete
bucket totals because their currency is also unknown. Different rates per
request are preserved. The calculator supports only these five categories: if a
single request has modalities or tiers with different rates within one category,
calculate them separately outside the script with supporting evidence, without
inventing an average rate or a number of requests.

`time.agent.calendar_seconds` is the duration of the **union** of intervals:
parallel execution does not double-count calendar time. `aggregate_agent_seconds`
sums the durations of the union of intervals **per agent** and can be higher when
distinct agents work in parallel. Repeated or overlapping intervals for the same
`agent_id` do not increase this effort. `time.human.calendar_seconds` also uses
the union, exclusively of the human intervals supplied.
`elapsed_scope_seconds` is simply `cutoff − scope.start`, or `null` without a
start; it does not measure execution, agent effort, human attention, or manual
time saved. Durations are decimal strings in seconds with microsecond precision.

## Runnable example

Save this as `normalized.json` and run the command above from the skill directory.
The prices below are **fictional**, provided only to check the arithmetic.

```json
{
  "scope": {
    "label": "Local demonstration",
    "start": "2026-09-29T10:00:00Z",
    "cutoff": "2026-09-29T10:10:00Z"
  },
  "coverage": "complete",
  "requests": [{
    "id": {"provider": "demo", "session": "s1", "request": "r1"},
    "tokens": {
      "input_uncached": 1000,
      "cache_read": 2000,
      "cache_write_short": 100,
      "cache_write_long": 0,
      "output": 500
    },
    "pricing": {
      "currency": "USD",
      "source": "Fictional price schedule for demonstration",
      "as_of": "2026-09-29",
      "per_million": {
        "input_uncached": "2",
        "cache_read": "0.2",
        "cache_write_short": "2.5",
        "cache_write_long": "4",
        "output": "8"
      }
    }
  }],
  "agent_intervals": [
    {"agent_id": "a1", "start": "2026-09-29T10:00:00Z", "end": "2026-09-29T10:04:00Z"},
    {"agent_id": "a2", "start": "2026-09-29T10:02:00Z", "end": "2026-09-29T10:06:00Z"}
  ],
  "human_intervals": [
    {"start": "2026-09-29T10:07:00Z", "end": "2026-09-29T10:08:00Z", "basis": "declared"}
  ]
}
```

Results: 3,600 tokens; API reference estimate of `"0.00665"` USD; agent calendar
time of `"360"` s; aggregate effort of `"480"` s; declared human time of `"60"` s;
elapsed scope of `"600"` s. Removing the human intervals makes human time `null`;
changing `coverage` to `partial` preserves subtotals but makes totals `null`.
