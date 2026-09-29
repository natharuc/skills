"""Deterministic conversion of local evidence into renderer presentation data.

No model calls, network access, pricing lookup, or human-time inference occurs.
Supplied rate cards express a currency amount per one million tokens.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re
from urllib.parse import urlsplit


CATEGORIES = ("input_uncached", "cache_read", "cache_write_short", "cache_write_long", "output")
COVERAGES = {"complete", "partial", "unavailable"}
TEXT = {
    "en": {
        "task": "Conversation usage report", "scope": "Selected {harness} session",
        "source": "Local session metadata", "source_detail": "Read-only collection for the selected session; private source paths are omitted.",
        "summary": "Compiled from local session evidence. Every value retains its source and coverage; unavailable metrics remain explicit.",
        "human": "Human effort", "human_missing": "No human timer or effort declaration was supplied.",
        "human_note": "Explicitly declared timer or effort; never inferred from messages or agent activity.",
        "human_open": "The declared timer remains open; its running interval is counted only through the report cutoff.",
        "human_source": "Declared human effort", "human_source_detail": "User-controlled timer or explicit human effort declaration.",
        "gross_turn": "Observed turn duration", "request": "Observed request duration", "none": "Agent duration",
        "duration_note": "Union of explicit {basis} intervals; overlapping intervals are counted once. This does not measure human effort.",
        "gross_basis": "gross turn", "request_basis": "request", "time_missing": "No complete, attributable timing intervals were observed.",
        "gross_limit": "Gross turn duration can include tool execution and waits; it is not CPU time or continuous model inference.",
        "request_limit": "Request duration reflects the recorded request boundaries; it is not human work time.",
        "aggregate": "Aggregate agent duration", "aggregate_note": "Union within each agent, then sum across agents; parallel agents add independently.",
        "agent_title": "Observed agents", "agent_label": "Agent {number} duration",
        "elapsed": "Observed elapsed time", "elapsed_note": "First recorded session timestamp to last observation, including idle gaps.",
        "elapsed_missing": "A valid first timestamp and last observation are required.",
        "tokens": "Tokens consumed", "token_note": "Native session total retained; cached categories are not added again.",
        "token_sum_note": "Sum of known disjoint categories. Missing categories are not assumed to be zero.",
        "token_missing": "The selected source does not provide a reliable token count.",
        "token_partial": "Token coverage is partial; the displayed amount may be a subtotal of the session.",
        "input_uncached": "Uncached input tokens", "cache_read": "Cache-read tokens",
        "cache_write_short": "Short cache-write tokens", "cache_write_long": "Long cache-write tokens", "output": "Output tokens",
        "category_note": "Observed disjoint token category; no inference from text length.",
        "subtotal": "Subtotal: {value}", "cost": "Cost", "cost_missing": "No attributed billing or calculable API reference was provided.",
        "attributed": "Attributed billing", "reference": "Native reference cost", "api": "API reference estimate",
        "billing_note": "Source-recorded {kind}; kept separate from API and human labor estimates.",
        "billing_multi": "Costs use multiple currencies. Review the separate currency rows; no cross-currency total is calculated.",
        "rates_source": "Supplied API rate card", "rates_detail": "Rates per one million tokens, dated {as_of}; {basis}.",
        "rates_url": "source URL supplied by the user", "rates_assumption": "user-supplied pricing assumption",
        "api_note": "Known model/category tokens × supplied rate ÷ 1,000,000; excludes subscriptions, credits, taxes, tools, and unobserved usage.",
        "api_partial": "The API reference has partial coverage because token categories, models, or matching rates are missing.",
        "api_no_models": "API pricing requires a reliable model allocation; no model was guessed from aggregate usage.",
        "model": "Model: {model}", "model_cost": "API reference — {category}",
        "labor": "Human labor estimate", "labor_note": "Declared human effort × supplied hourly rate; separate from provider charges.",
        "labor_source": "Supplied hourly rate", "labor_detail": "User-supplied labor assumption: {amount} per hour.",
        "diagnostic": "Collection diagnostic {code}: the adapter reported a limitation; inspect the diagnostic JSON for details.",
        "limit_missing": "Metrics without reliable local evidence are unavailable; missing evidence is not zero consumption.",
        "time_partial": "Only explicitly observed timing intervals are included; coverage is partial.",
        "invalid_model_coverage": "Model allocations do not account for all observed session usage; API costs are a partial reference.",
        "money_precision": "Currency amounts display up to eight decimal places, rounded only after calculation; smaller positive amounts are shown with a less-than sign.",
        "reported_run": "Antigravity reports {seconds} seconds of run elapsed duration. This cumulative snapshot has no dated execution interval and does not measure human work or pure model inference time.",
    },
    "pt-BR": {
        "task": "Relatório de consumo da conversa", "scope": "Sessão selecionada de {harness}",
        "source": "Metadados locais da sessão", "source_detail": "Coleta em modo somente leitura da sessão selecionada; caminhos privados foram omitidos.",
        "summary": "Compilado a partir de evidências locais da sessão. Cada valor mantém sua fonte e cobertura; métricas indisponíveis ficam explícitas.",
        "human": "Dedicação humana", "human_missing": "Nenhum cronômetro humano ou declaração de dedicação foi fornecido.",
        "human_note": "Cronômetro ou dedicação explicitamente declarados; nunca inferidos das mensagens ou da atividade do agente.",
        "human_open": "O cronômetro declarado continua aberto; o intervalo em andamento é contado somente até o corte do relatório.",
        "human_source": "Dedicação humana declarada", "human_source_detail": "Cronômetro controlado pelo usuário ou declaração explícita de dedicação humana.",
        "gross_turn": "Duração observada dos turnos", "request": "Duração observada das requisições", "none": "Duração do agente",
        "duration_note": "União dos intervalos explícitos de {basis}; sobreposições são contadas uma vez. Não mede dedicação humana.",
        "gross_basis": "turnos completos", "request_basis": "requisições", "time_missing": "Nenhum intervalo completo de tempo atribuível foi observado.",
        "gross_limit": "A duração completa dos turnos pode incluir ferramentas e esperas; não representa tempo de CPU ou inferência contínua do modelo.",
        "request_limit": "A duração das requisições reflete os limites registrados; não representa trabalho humano.",
        "aggregate": "Duração agregada dos agentes", "aggregate_note": "União dos intervalos de cada agente, seguida da soma entre agentes; agentes paralelos contam separadamente.",
        "agent_title": "Agentes observados", "agent_label": "Duração do agente {number}",
        "elapsed": "Tempo decorrido observado", "elapsed_note": "Do primeiro registro da sessão à última observação, incluindo períodos ociosos.",
        "elapsed_missing": "São necessários um primeiro registro e uma última observação válidos.",
        "tokens": "Tokens consumidos", "token_note": "Total nativo da sessão preservado; categorias de cache não são somadas novamente.",
        "token_sum_note": "Soma das categorias disjuntas conhecidas. Categorias ausentes não são consideradas zero.",
        "token_missing": "A fonte selecionada não fornece uma contagem confiável de tokens.",
        "token_partial": "A cobertura de tokens é parcial; o valor exibido pode ser um subtotal da sessão.",
        "input_uncached": "Tokens de entrada sem cache", "cache_read": "Tokens de leitura de cache",
        "cache_write_short": "Tokens de gravação curta em cache", "cache_write_long": "Tokens de gravação longa em cache", "output": "Tokens de saída",
        "category_note": "Categoria disjunta de tokens observados; sem inferência pelo tamanho do texto.",
        "subtotal": "Subtotal: {value}", "cost": "Custo", "cost_missing": "Nenhuma cobrança atribuída ou referência calculável de API foi fornecida.",
        "attributed": "Cobrança atribuída", "reference": "Custo de referência nativo", "api": "Estimativa de referência de API",
        "billing_note": "{kind} registrado na fonte; mantido separado das estimativas de API e trabalho humano.",
        "billing_multi": "Os custos usam moedas diferentes. Consulte as linhas por moeda; nenhum total entre moedas é calculado.",
        "rates_source": "Tabela de preços de API fornecida", "rates_detail": "Preços por um milhão de tokens, datados de {as_of}; {basis}.",
        "rates_url": "URL da fonte fornecida pelo usuário", "rates_assumption": "premissa de preço fornecida pelo usuário",
        "api_note": "Tokens conhecidos por modelo/categoria × preço fornecido ÷ 1.000.000; exclui assinaturas, créditos, impostos, ferramentas e consumo não observado.",
        "api_partial": "A referência de API tem cobertura parcial porque faltam categorias, modelos ou preços correspondentes.",
        "api_no_models": "O cálculo de API exige uma distribuição confiável por modelo; nenhum modelo foi presumido a partir do consumo agregado.",
        "model": "Modelo: {model}", "model_cost": "Referência de API — {category}",
        "labor": "Estimativa de trabalho humano", "labor_note": "Dedicação humana declarada × preço por hora fornecido; separada das cobranças do provedor.",
        "labor_source": "Preço por hora fornecido", "labor_detail": "Premissa de trabalho fornecida pelo usuário: {amount} por hora.",
        "diagnostic": "Diagnóstico da coleta {code}: o adaptador identificou uma limitação; consulte os detalhes no JSON de diagnóstico.",
        "limit_missing": "Métricas sem evidência local confiável ficam indisponíveis; ausência de evidência não significa consumo zero.",
        "time_partial": "Somente intervalos de tempo explicitamente observados estão incluídos; a cobertura é parcial.",
        "invalid_model_coverage": "A distribuição por modelo não contempla todo o consumo observado; os custos de API são uma referência parcial.",
        "money_precision": "Valores monetários são exibidos com até oito casas decimais, arredondados somente após o cálculo; valores positivos menores usam o sinal de menor que.",
        "reported_run": "O Antigravity informa {seconds} segundos de duração decorrida da execução. Esse retrato acumulado não tem um intervalo de execução datado e não mede trabalho humano nem tempo exclusivo de inferência do modelo.",
    },
}

# Fixed translations avoid leaking raw diagnostic messages or private paths.
# Unknown adapter codes still remain visible with a localized explanation.
DIAGNOSTICS = {}


def _diagnostic_group(codes, en, pt):
    for code in codes.split():
        DIAGNOSTICS[code] = {"en": en, "pt-BR": pt}


_diagnostic_group("source_unavailable source_missing", "The expected local source was not found. Select an existing session file or export from this computer.", "A fonte local esperada não foi encontrada. Selecione um arquivo ou exportação de sessão existente neste computador.")
_diagnostic_group("source_unreadable source_incomplete record_limit byte_limit oversized_record", "A source could not be read completely within the safety limits; retained evidence may be partial.", "A leitura da fonte não foi concluída dentro dos limites de segurança; as evidências preservadas podem ser parciais.")
_diagnostic_group("unsupported_schema unsupported_format unsupported_bubble_index unsupported_bubble_version undocumented_schema", "The local format is undocumented or unsupported by this adapter. Only recognized records are reported; use a supported structured export for additional evidence.", "O formato local não é documentado ou não é suportado pelo adaptador. Somente registros reconhecidos entram no relatório; use uma exportação estruturada suportada para obter mais evidências.")
_diagnostic_group("malformed_record invalid_counters invalid_usage unsupported_usage", "Malformed, inconsistent, or unsupported counters were excluded from accounting.", "Contadores inválidos, inconsistentes ou não suportados foram excluídos da contagem.")
_diagnostic_group("session_not_found", "The selected session identity was not found in the supported source records.", "O identificador da sessão selecionada não foi encontrado nos registros suportados da fonte.")
_diagnostic_group("usage_unavailable missing_usage usage_not_persisted usage_result_missing", "No supported usage counters cover some or all selected records. Missing telemetry is not zero consumption.", "Parte ou todos os registros selecionados não têm contadores de consumo suportados. Ausência de telemetria não significa consumo zero.")
_diagnostic_group("default_zero_usage", "All-zero Cursor bubble counters are unverified defaults, so they were not treated as zero consumption.", "Contadores zerados das mensagens do Cursor podem ser valores padrão não confirmados; não foram tratados como consumo zero.")
_diagnostic_group("native_bubble_usage", "Populated Cursor bubble counters were counted once per stored bubble; they are a partial observation rather than verified billed requests.", "Contadores preenchidos do Cursor foram contados uma vez por mensagem armazenada; são uma observação parcial, sem verificação por requisição faturada.")
_diagnostic_group("cache_split_unknown input_cache_semantics native_total_semantics", "The source does not establish a reliable disjoint input/cache allocation. Native totals are retained where supported, and uncertain categories stay unavailable.", "A fonte não estabelece uma divisão confiável entre entrada e cache sem sobreposição. Totais nativos são preservados quando suportados, e categorias incertas ficam indisponíveis.")
_diagnostic_group("billing_unavailable currency_charge_unavailable billing_units_not_money", "No verified session charge in currency is available. Quotas, credits, request multipliers, and provider units are not converted into money.", "Não há cobrança monetária verificada para a sessão. Cotas, créditos, multiplicadores de requisições e unidades do provedor não são convertidos em dinheiro.")
_diagnostic_group("time_not_execution time_requires_timestamps", "Calendar timestamps or an undated duration cannot establish active agent intervals or human effort.", "Datas de mensagens ou uma duração sem início e fim datados não estabelecem intervalos ativos do agente nem dedicação humana.")
_diagnostic_group("gross_turn_time", "Recorded turn boundaries include tools and possible waits; they do not measure continuous model inference or human attention.", "Os limites registrados dos turnos incluem ferramentas e possíveis esperas; não medem inferência contínua do modelo nem atenção humana.")
_diagnostic_group("open_turn unfinished_turns", "Unfinished turns without an observed end were excluded from measured durations.", "Turnos sem um encerramento observado foram excluídos das durações medidas.")
_diagnostic_group("undated_event_skipped untimed_at_cutoff timestamps_missing", "Records without usable timestamps cannot establish intervals or pass a historical cutoff and were excluded where required.", "Registros sem datas utilizáveis não estabelecem intervalos nem permitem aplicar um corte histórico; foram excluídos quando necessário.")
_diagnostic_group("cutoff_unverifiable", "An undated export cannot be attributed to the requested historical cutoff; use a structured export with explicit timestamps.", "Uma exportação sem datas não pode ser atribuída ao corte histórico solicitado; use uma exportação estruturada com datas explícitas.")
_diagnostic_group("snapshot_as_exported", "Usage is the snapshot as exported. The report cutoff is the collection time and does not establish when those tokens were consumed.", "O consumo corresponde ao retrato da exportação. O corte do relatório indica a coleta e não estabelece quando esses tokens foram consumidos.")
_diagnostic_group("history_boundary compacted_history inherited_history_unsupported", "Compaction, rollback, or inherited history prevents complete attribution; missing history is not reconstructed.", "Compactação, reversão ou histórico herdado impedem uma atribuição completa; o histórico ausente não é reconstruído.")
_diagnostic_group("cumulative_reset summary_counter_reset", "Cumulative counters decreased. Only the latest supported segment or snapshot is retained; reset segments are not guessed or added.", "Os contadores acumulados diminuíram. Somente o segmento ou retrato mais recente suportado foi preservado; trechos anteriores não são presumidos nem somados.")
_diagnostic_group("shutdown_snapshot cumulative_result_snapshot native_model_snapshot", "The latest supported cumulative result is retained. Earlier snapshots and request-level counters are not added again.", "O resultado acumulado suportado mais recente foi preservado. Retratos anteriores e contadores por requisição não são somados novamente.")
_diagnostic_group("usage_after_snapshot", "Activity continues after the latest usage summary and is excluded until a newer attributable summary is available.", "Há atividade posterior ao último resumo de consumo, excluída até existir um resumo atribuível mais recente.")
_diagnostic_group("captured_usage_partial result_main_loop", "Usage covers only the observed, deduplicated records; complete session or subagent coverage is not assumed.", "O consumo cobre somente os registros observados após remoção de duplicatas; não se presume cobertura completa da sessão ou dos subagentes.")
_diagnostic_group("message_output_only assistant_output_unverified", "Message-level counters do not establish all token categories. Unsupported input or output totals remain unavailable.", "Contadores por mensagem não estabelecem todas as categorias de tokens. Totais de entrada ou saída sem suporte permanecem indisponíveis.")
_diagnostic_group("sdk_cost_estimate", "The SDK cost is a client-side pricing reference, not an authoritative charge, and can include restored or subagent spend.", "O custo informado pelo SDK é uma referência de preço calculada no cliente, sem comprovação de cobrança, e pode incluir consumo restaurado ou de subagentes.")
_diagnostic_group("child_records_excluded child_spans_excluded", "Child records or intervals were excluded where their parent accounting may already include them.", "Registros ou intervalos de agentes filhos foram excluídos quando a contabilização do agente principal pode já incluí-los.")
_diagnostic_group("context_capacity_snapshot context_window_not_usage", "Context-window capacity snapshots were excluded; they do not measure consumed tokens.", "Retratos de capacidade da janela de contexto foram excluídos; eles não medem tokens consumidos.")
_diagnostic_group("missing_usage_identity conflicting_usage_identity usage_identity_missing unattributed_record bubble_identity_mismatch result_without_id", "Records without consistent session, request, or message identities cannot be safely attributed or deduplicated and were limited or excluded.", "Registros sem identificação consistente de sessão, requisição ou mensagem não podem ser atribuídos ou deduplicados com segurança e foram limitados ou excluídos.")
_diagnostic_group("step_usage_not_added", "Per-step usage was excluded because the cumulative result can already include it.", "O consumo por etapa foi excluído porque o resultado acumulado pode já incluí-lo.")
_diagnostic_group("zero_error_result zero_error_cost usage_snapshot_correction", "Conflicting or error snapshots were handled conservatively; a default error value is not evidence of zero usage or cost.", "Retratos conflitantes ou com erro foram tratados de forma conservadora; um valor padrão de erro não prova consumo ou custo zero.")
_diagnostic_group("unknown_events", "Unrecognized source records were skipped, so their metric coverage remains unknown.", "Registros não reconhecidos da fonte foram ignorados; sua cobertura de métricas permanece desconhecida.")
_diagnostic_group("invalid_reported_run_duration", "An invalid or out-of-range reported run duration was excluded; no execution interval was inferred.", "Uma duração informada inválida ou fora do intervalo permitido foi excluída; nenhum intervalo de execução foi inferido.")

REPORTED_RUN_PATTERN = re.compile(
    r"Antigravity reports ((?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?)"
    r" seconds as reported run elapsed duration; no dated execution interval\. "
    r"This cumulative snapshot is not human work or pure model inference time\."
)


def _decimal(value, field):
    if not isinstance(value, str) or len(value) > 48 or not re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value):
        raise ValueError(f"{field}: expected a nonnegative finite decimal string")
    return Decimal(value)


def _currency(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError(f"{field}: expected a three-letter uppercase currency code")
    return value


def _object(value, keys, field, required=()):
    if not isinstance(value, dict) or set(value) - set(keys) or set(required) - set(value):
        raise ValueError(f"{field}: unexpected or missing fields")
    return value


def _time(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO strings with a timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamps must be ISO strings with a timezone") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def _seconds(delta):
    return Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)


def _number(value, field):
    if value is None:
        return None
    if isinstance(value, str) and len(value) <= 30 and re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
        value = int(value)
    if type(value) is not int or value < 0 or value >= 10 ** 30:
        raise ValueError(f"{field}: expected a nonnegative integer or null")
    return value


def _tokens(value):
    _object(value, CATEGORIES + ("total",), "tokens")
    return {key: _number(value.get(key), f"tokens.{key}") for key in CATEGORIES + ("total",)}


def _coverage(value, known=False):
    if value not in COVERAGES:
        raise ValueError("unknown coverage")
    return "partial" if known and value == "unavailable" else value


def _numeric(value, language):
    result = format(value, "f") if isinstance(value, Decimal) else str(value)
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    whole, _, frac = result.partition(".")
    whole = f"{int(whole):,}"
    if language == "pt-BR":
        return whole.replace(",", ".") + ("," + frac if frac else "")
    return whole + ("." + frac if frac else "")


def _duration(seconds, language):
    hours, remain = divmod(seconds, Decimal(3600))
    minutes, seconds = divmod(remain, Decimal(60))
    items = []
    if hours:
        items.append(f"{int(hours)} h")
    if minutes:
        items.append(f"{int(minutes)} min")
    if seconds or not items:
        items.append(f"{_numeric(seconds, language)} s")
    return " ".join(items)


def _money(value, currency, language):
    unit = Decimal("0.00000001")
    if 0 < value < unit:
        return f"< {currency} {_numeric(unit, language)}"
    with localcontext() as ctx:
        ctx.prec = 110
        value = value.quantize(unit, rounding=ROUND_HALF_UP)
    return f"{currency} {_numeric(value, language)}"


def _union(intervals):
    if not intervals:
        return Decimal(0)
    ordered = sorted(intervals)
    start, end = ordered[0]
    seconds = Decimal(0)
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            seconds += _seconds(end - start)
            start, end = next_start, next_end
    return seconds + _seconds(end - start)


def _rate_card(rates):
    _object(rates, {"as_of", "source", "currency", "models"}, "rates", {"as_of", "source", "currency", "models"})
    if not isinstance(rates["as_of"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rates["as_of"]):
        raise ValueError("rates.as_of: expected YYYY-MM-DD")
    date.fromisoformat(rates["as_of"])
    _currency(rates["currency"], "rates.currency")
    source = rates["source"]
    if not isinstance(source, str) or not source.strip() or len(source) > 2000:
        raise ValueError("rates.source: expected a URL or user assumption")
    url = None
    if "://" in source:
        parsed = urlsplit(source)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or any(char.isspace() for char in source)):
            raise ValueError("rates.source: URL must use http/https without credentials")
        url = source
    if not isinstance(rates["models"], dict) or not rates["models"]:
        raise ValueError("rates.models: expected at least one model")
    models = {}
    for model, prices in rates["models"].items():
        if not isinstance(model, str) or not model.strip() or len(model) > 160:
            raise ValueError("rates.models: invalid model name")
        _object(prices, CATEGORIES, "model rates", CATEGORIES)
        models[model] = {key: None if prices[key] is None else _decimal(prices[key], f"rates.{model}.{key}") for key in CATEGORIES}
    return {**rates, "models": models, "url": url}


def build_presentation(collection, language="en", task=None, rates=None, human=None,
                       hourly_rate=None, labor_currency=None):
    """Return presentation JSON accepted by ``render_report.validate``.

    Unknown usage and costs stay null. Native billing, API reference pricing, and
    human labor remain separate. Source file paths and diagnostic free text are
    deliberately excluded from the visual artifact.
    """
    if language not in TEXT:
        raise ValueError("language: expected en or pt-BR")
    if not isinstance(collection, dict) or collection.get("schema_version") != 1:
        raise ValueError("collection: expected schema_version 1")
    t = TEXT[language]
    harness = collection.get("harness", "unknown")
    if harness not in {"cursor", "codex", "claude", "github-copilot", "copilot", "antigravity", "unknown"}:
        harness = "unknown"
    if task is not None and (not isinstance(task, str) or not task.strip()):
        raise ValueError("task: expected nonempty text")
    sources = [{"id": "session", "label": t["source"], "detail": t["source_detail"]}]
    limitations = []
    breakdowns = []

    def metric(metric_id, label, value=None, status="calculated", coverage="partial", note=None, refs=None):
        return {"id": metric_id, "label": label, "value": value,
                "status": status if value is not None else "unavailable",
                "coverage": coverage if value is not None else "unavailable",
                "source_ids": (refs if refs is not None else ["session"]) if value is not None else [], "note": note}

    def amount(value, coverage, currency=None):
        formatted = _money(value, currency, language) if currency else _numeric(value, language)
        return t["subtotal"].format(value=formatted) if coverage == "partial" else formatted

    human_seconds = None
    human_coverage = "unavailable"
    if human is not None:
        _object(human, {"seconds", "basis", "coverage", "open"}, "human", {"seconds", "basis", "coverage"})
        if human["basis"] != "declared" or type(human.get("open", False)) is not bool:
            raise ValueError("human: expected declared basis and boolean open")
        human_seconds = _decimal(human["seconds"], "human.seconds")
        human_coverage = _coverage(human["coverage"], known=True)
        sources.append({"id": "human", "label": t["human_source"], "detail": t["human_source_detail"]})
        if human.get("open"):
            limitations.append(t["human_open"])
    human_metric = metric("human_time", t["human"], None if human_seconds is None else _duration(human_seconds, language),
                          "declared", human_coverage, t["human_note"] if human is not None else t["human_missing"], ["human"])

    started = _time(collection.get("started_at"))
    observed = _time(collection.get("observed_until"))
    cutoff = _time(collection.get("cutoff")) or observed
    if observed is not None and cutoff is not None:
        observed = min(observed, cutoff)
    basis = collection.get("time_basis", "none")
    if basis not in {"gross_turn", "request", "none"}:
        raise ValueError("time_basis: expected gross_turn, request, or none")
    by_agent = {}
    intervals = collection.get("intervals", [])
    if not isinstance(intervals, list):
        raise ValueError("intervals: expected a list")
    for interval in intervals:
        _object(interval, {"start", "end", "agent_id"}, "interval", {"start", "end", "agent_id"})
        start, end = _time(interval["start"]), _time(interval["end"])
        if start is None or end is None or start > end:
            raise ValueError("interval: expected ordered start/end timestamps")
        agent_id = interval["agent_id"]
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("interval.agent_id: expected a nonempty string")
        if cutoff is not None:
            if start > cutoff:
                continue
            end = min(end, cutoff)
        by_agent.setdefault(agent_id, []).append((start, end))
    if intervals and basis == "none":
        raise ValueError("intervals require an explicit time_basis")
    time_cov = _coverage(collection.get("time_coverage", "partial"), known=bool(by_agent))
    duration = _union([item for spans in by_agent.values() for item in spans]) if by_agent else None
    time_note = t["duration_note"].format(basis=t["gross_basis" if basis == "gross_turn" else "request_basis"]) if by_agent else t["time_missing"]
    agent_metric = metric("agent_time", t[basis], None if duration is None else _duration(duration, language), coverage=time_cov, note=time_note)
    aggregate = sum((_union(spans) for spans in by_agent.values()), Decimal(0)) if by_agent else None
    aggregate_metric = metric("aggregate_agent", t["aggregate"], None if aggregate is None else _duration(aggregate, language), coverage=time_cov, note=t["aggregate_note"])
    if by_agent:
        limitations.append(t["gross_limit" if basis == "gross_turn" else "request_limit"])
        if time_cov == "partial":
            limitations.append(t["time_partial"])
        if len(by_agent) > 1:
            breakdowns.append({"title": t["agent_title"], "metrics": [
                metric(f"agent_{index}", t["agent_label"].format(number=index), _duration(_union(spans), language), coverage=time_cov, note=time_note)
                for index, spans in enumerate(by_agent.values(), 1)]})
    elapsed = _seconds(observed - started) if started is not None and observed is not None and observed >= started else None
    elapsed_metric = metric("elapsed", t["elapsed"], None if elapsed is None else _duration(elapsed, language), note=t["elapsed_note"] if elapsed is not None else t["elapsed_missing"])

    tokens = _tokens(collection.get("tokens", {}))
    token_cov = _coverage(collection.get("token_coverage", "unavailable"), known=any(value is not None for value in tokens.values()))

    def token_metrics(values, coverage):
        known = [values[key] for key in CATEGORIES if values[key] is not None]
        total, total_cov, status = values["total"], coverage, "measured"
        note = t["token_note"]
        if total is None:
            total = sum(known) if known else None
            total_cov = "partial" if len(known) < len(CATEGORIES) or coverage != "complete" else "complete"
            note, status = t["token_sum_note"], "calculated"
        result = [metric("tokens", t["tokens"], None if total is None else amount(total, total_cov), status, total_cov,
                         note if total is not None else t["token_missing"])]
        result.extend(metric(key, t[key], None if values[key] is None else amount(values[key], coverage),
                             "measured", coverage, t["category_note"]) for key in CATEGORIES)
        return result

    token_rows = token_metrics(tokens, token_cov)
    if token_rows[0]["coverage"] == "partial":
        limitations.append(t["token_partial"])

    cost_rows = []
    billing = collection.get("billing", [])
    if not isinstance(billing, list):
        raise ValueError("billing: expected a list")
    bill_groups = {}
    for bill in billing:
        _object(bill, {"currency", "amount", "kind", "coverage"}, "billing", {"currency", "amount", "kind", "coverage"})
        if bill["kind"] not in {"attributed", "reference"}:
            raise ValueError("billing.kind: expected attributed or reference")
        currency = _currency(bill["currency"], "billing.currency")
        number = _decimal(bill["amount"], "billing.amount")
        coverage = _coverage(bill["coverage"], known=True)
        bill_groups.setdefault((bill["kind"], currency), []).append((number, coverage))
    with localcontext() as ctx:
        ctx.prec = 100
        for (kind, currency), bills in sorted(bill_groups.items()):
            number = sum((item[0] for item in bills), Decimal(0))
            coverage = "complete" if all(item[1] == "complete" for item in bills) else "partial"
            cost_rows.append(metric(f"billing_{kind}_{currency}", f"{t[kind]} ({currency})", amount(number, coverage, currency),
                                    "measured" if kind == "attributed" else "estimated", coverage, t["billing_note"].format(kind=t[kind])))

    card = _rate_card(rates) if rates is not None else None
    if card:
        sources.append({"id": "rates", "label": t["rates_source"],
                        "detail": t["rates_detail"].format(as_of=card["as_of"], basis=t["rates_url" if card["url"] else "rates_assumption"]), "url": card["url"]})
    model_usage = collection.get("model_usage", [])
    if not isinstance(model_usage, list):
        raise ValueError("model_usage: expected a list")
    models_seen, model_records = set(), []
    api_values, api_complete = [], bool(model_usage)
    for usage in model_usage:
        _object(usage, {"model", "tokens", "coverage"}, "model_usage", {"model", "tokens", "coverage"})
        model = usage["model"]
        if not isinstance(model, str) or not model.strip() or len(model) > 160 or model in models_seen:
            raise ValueError("model_usage: model names must be nonempty and unique")
        models_seen.add(model)
        values = _tokens(usage["tokens"])
        coverage = _coverage(usage["coverage"], known=any(value is not None for value in values.values()))
        model_records.append(values)
        rows = token_metrics(values, coverage)
        if card:
            prices = card["models"].get(model, {})
            partials, model_complete = [], coverage == "complete"
            for category in CATEGORIES:
                count, price = values[category], prices.get(category)
                with localcontext() as ctx:
                    ctx.prec = 100
                    part = (Decimal(count) * price / Decimal(1000000)) if count is not None and price is not None else None
                if part is None:
                    model_complete = False
                else:
                    partials.append(part)
                rows.append(metric(f"api_{category}", t["model_cost"].format(category=t[category]),
                                   None if part is None else amount(part, coverage, card["currency"]), "estimated", coverage, t["api_note"], ["session", "rates"]))
            with localcontext() as ctx:
                ctx.prec = 100
                model_cost = sum(partials, Decimal(0)) if partials else None
            if model_cost is not None:
                api_values.append(model_cost)
            else:
                model_complete = False
            api_complete = api_complete and model_complete
            model_cov = "complete" if model_complete else "partial"
            rows.append(metric("api_reference", t["api"], None if model_cost is None else amount(model_cost, model_cov, card["currency"]), "estimated", model_cov, t["api_note"], ["session", "rates"]))
        breakdowns.append({"title": t["model"].format(model=model), "metrics": rows})

    if card:
        # Complete model records alone cannot prove allocation of the whole session.
        allocated = bool(model_records) and token_cov == "complete"
        for category in CATEGORIES + ("total",):
            if tokens[category] is not None:
                parts = [record[category] for record in model_records]
                if any(part is None for part in parts) or sum(parts) != tokens[category]:
                    allocated = False
        if not allocated:
            api_complete = False
            if model_records:
                limitations.append(t["invalid_model_coverage"])
        coverage = "complete" if api_complete else "partial"
        with localcontext() as ctx:
            ctx.prec = 100
            total_api = sum(api_values, Decimal(0)) if api_values else None
        cost_rows.append(metric("api_reference", f"{t['api']} ({card['currency']})", None if total_api is None else amount(total_api, coverage, card["currency"]),
                                "estimated", coverage, t["api_note"], ["session", "rates"]))
        if not model_usage:
            limitations.append(t["api_no_models"])
        elif not api_complete:
            limitations.append(t["api_partial"])

    # Pick one cost class for the KPI. Never combine currencies or cost classes.
    candidates = [row for row in cost_rows if row["id"].startswith("billing_attributed_")]
    if not candidates:
        candidates = [row for row in cost_rows if row["id"].startswith("billing_reference_")]
    if not candidates:
        candidates = [row for row in cost_rows if row["id"] == "api_reference" and row["value"] is not None]
    if len(candidates) == 1:
        cost_metric = {**candidates[0], "id": "cost"}
        cost_rows = [row for row in cost_rows if row is not candidates[0]]
    else:
        note = t["billing_multi"] if len(candidates) > 1 else t["cost_missing"]
        cost_metric = metric("cost", t["cost"], note=note)
        if len(candidates) > 1:
            limitations.append(note)

    if hourly_rate is not None or labor_currency is not None:
        if hourly_rate is None or labor_currency is None:
            raise ValueError("hourly_rate and labor_currency must be supplied together")
        hourly = _decimal(hourly_rate, "hourly_rate")
        currency = _currency(labor_currency, "labor_currency")
        sources.append({"id": "labor", "label": t["labor_source"], "detail": t["labor_detail"].format(amount=_money(hourly, currency, language))})
        with localcontext() as ctx:
            ctx.prec = 100
            labor = human_seconds * hourly / Decimal(3600) if human_seconds is not None else None
        cost_rows.append(metric("human_labor", f"{t['labor']} ({currency})", None if labor is None else amount(labor, human_coverage, currency),
                                "estimated", human_coverage, t["labor_note"], ["human", "labor"]))

    diagnostics = collection.get("diagnostics", [])
    if not isinstance(diagnostics, list):
        raise ValueError("diagnostics: expected a list")
    for item in diagnostics:
        code = item.get("code") if isinstance(item, dict) else None
        code = code if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) else "unknown"
        note = f"{code}: {DIAGNOSTICS[code][language]}" if code in DIAGNOSTICS else t["diagnostic"].format(code=code)
        if code == "reported_run_duration" and harness == "antigravity":
            message = item.get("message")
            match = REPORTED_RUN_PATTERN.fullmatch(message) if isinstance(message, str) and len(message) < 300 else None
            if match and len(match.group(1)) <= 48:
                seconds = Decimal(match.group(1))
                if seconds.is_finite() and 0 <= seconds <= 2 ** 53 - 1:
                    displayed = format(seconds, "g") if 0 < seconds < Decimal("0.00000001") else _numeric(seconds, language)
                    if language == "pt-BR" and "e" in displayed.lower():
                        displayed = displayed.replace(".", ",")
                    note = f"{code}: " + t["reported_run"].format(seconds=displayed)
        if note not in limitations:
            limitations.append(note)
    metrics = [human_metric, agent_metric, token_rows[0], cost_metric, elapsed_metric, aggregate_metric] + token_rows[1:] + cost_rows
    if any(row["value"] is not None for row in [cost_metric] + cost_rows):
        limitations.append(t["money_precision"])
    if any(row["value"] is None for row in metrics[:4]):
        limitations.append(t["limit_missing"])
    return {"version": 1, "language": language, "task": task or t["task"], "scope": t["scope"].format(harness=harness),
            "period": {"start": started.isoformat().replace("+00:00", "Z") if started else None,
                       "cutoff": cutoff.isoformat().replace("+00:00", "Z") if cutoff else None, "timezone": "UTC"},
            "summary": t["summary"], "metrics": metrics, "breakdowns": breakdowns,
            "sources": sources, "limitations": limitations}
