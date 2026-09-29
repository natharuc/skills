#!/usr/bin/env python3
"""Validate and render an offline chat-report presentation; never calculate usage."""

import argparse
import html
import json
from pathlib import Path
import re
import string
import sys
from urllib.parse import urlsplit


LOCALES = {
    "en": {
        "statuses": {"measured": "Measured", "declared": "Declared",
                     "calculated": "Calculated", "estimated": "Estimated",
                     "unavailable": "Unavailable"},
        "coverage": {"complete": "Complete coverage", "partial": "Partial coverage",
                     "unavailable": "Coverage unavailable"},
        "kpi_labels": {"human_time": "Human effort", "agent_time": "Agent execution",
                       "tokens": "Tokens consumed", "cost": "Cost"},
        "report_title": "Chat report",
        "kicker": "Chat report · Time, usage and cost",
        "missing_scope": "Scope not provided.",
        "period_labels": {"start": "Start", "cutoff": "Cutoff", "timezone": "Time zone"},
        "not_provided": "Not provided",
        "kpis": "Key metrics",
        "missing_evidence": "No evidence provided for this metric.",
        "missing_source": "Source not provided.",
        "metric": "Metric", "result": "Result", "basis_sources": "Basis and sources",
        "metrics_title": "Metrics and evidence",
        "metrics_subtitle": "Each result includes its qualification and coverage.",
        "timeline_title": "Timeline",
        "timeline_subtitle": "Events with identified sources.",
        "deliverables_title": "Recorded deliverables",
        "deliverables_subtitle": "Confirmed outcomes within the scope.",
        "sources_title": "Sources and limitations",
        "sources_subtitle": "Traceability to interpret the results.",
        "no_sources": "No sources were provided for this presentation.",
        "limits_title": "Interpretation limits",
        "no_limits": "Additional limitations not provided.",
        "footer": "Values preserved according to the listed sources and qualifications.",
    },
    "pt-BR": {
        "statuses": {"measured": "Medido", "declared": "Informado",
                     "calculated": "Calculado", "estimated": "Estimado",
                     "unavailable": "Indisponível"},
        "coverage": {"complete": "Cobertura completa", "partial": "Cobertura parcial",
                     "unavailable": "Cobertura indisponível"},
        "kpi_labels": {"human_time": "Dedicação humana", "agent_time": "Execução do agente",
                       "tokens": "Tokens consumidos", "cost": "Custo"},
        "report_title": "Relatório do chat",
        "kicker": "Relatório do chat · Tempo, consumo e custo",
        "missing_scope": "Escopo não informado.",
        "period_labels": {"start": "Início", "cutoff": "Corte", "timezone": "Fuso horário"},
        "not_provided": "Não informado",
        "kpis": "Indicadores principais",
        "missing_evidence": "Sem evidência fornecida para esta métrica.",
        "missing_source": "Fonte não informada.",
        "metric": "Métrica", "result": "Resultado", "basis_sources": "Base e fontes",
        "metrics_title": "Métricas e evidências",
        "metrics_subtitle": "A qualificação e a cobertura acompanham cada resultado.",
        "timeline_title": "Linha do tempo",
        "timeline_subtitle": "Eventos com fonte identificada.",
        "deliverables_title": "Entregas registradas",
        "deliverables_subtitle": "Resultados confirmados no escopo.",
        "sources_title": "Fontes e limites",
        "sources_subtitle": "Rastreabilidade para interpretar os resultados.",
        "no_sources": "Nenhuma fonte foi fornecida para esta apresentação.",
        "limits_title": "Limites de interpretação",
        "no_limits": "Limitações adicionais não informadas.",
        "footer": "Valores preservados conforme as fontes e qualificações indicadas.",
    },
}
STATUSES = frozenset(LOCALES["en"]["statuses"])
COVERAGE = frozenset(LOCALES["en"]["coverage"])


class InvalidReport(ValueError):
    pass


def obj(value, allowed, location):
    if not isinstance(value, dict):
        raise InvalidReport(f"{location}: expected a JSON object")
    unknown = set(value) - set(allowed)
    if unknown:
        raise InvalidReport(f"{location}: unknown fields: {', '.join(sorted(unknown))}")
    return value


def text(value, location, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidReport(f"{location}: expected nonempty text" + (" or null" if nullable else ""))
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise InvalidReport(f"{location}: control character not allowed")
    return value


def array(value, location):
    if not isinstance(value, list):
        raise InvalidReport(f"{location}: expected a list")
    return value


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReport(f"JSON: duplicate key: {key}")
        result[key] = value
    return result


def no_constant(value):
    raise InvalidReport(f"JSON: constant not allowed: {value}")


def source_refs(value, location, source_ids, required=False):
    refs = array(value, location)
    if required and not refs:
        raise InvalidReport(f"{location}: at least one source is required")
    for index, ref in enumerate(refs):
        text(ref, f"{location}[{index}]")
        if ref not in source_ids:
            raise InvalidReport(f"{location}: undefined source: {ref}")
    if len(set(refs)) != len(refs):
        raise InvalidReport(f"{location}: duplicate sources")
    return refs


def validate_metrics(value, location, source_ids):
    metrics = []
    ids = set()
    for index, item in enumerate(array(value, location)):
        loc = f"{location}[{index}]"
        item = obj(item, {"id", "label", "value", "status", "coverage", "source_ids", "note"}, loc)
        metric_id = text(item.get("id"), loc + ".id")
        if metric_id in ids:
            raise InvalidReport(f"{loc}: duplicate metric id")
        ids.add(metric_id)
        val = text(item.get("value"), loc + ".value", nullable=True)
        status = item.get("status", "unavailable")
        coverage = item.get("coverage", "unavailable")
        if not isinstance(status, str) or status not in STATUSES:
            raise InvalidReport(f"{loc}.status: unknown qualification")
        if not isinstance(coverage, str) or coverage not in COVERAGE:
            raise InvalidReport(f"{loc}.coverage: unknown coverage")
        if val is None and (status != "unavailable" or coverage != "unavailable"):
            raise InvalidReport(f"{loc}: a null value requires unavailable status and coverage")
        if val is not None and (status == "unavailable" or coverage == "unavailable"):
            raise InvalidReport(f"{loc}: a known value requires explicit status and coverage")
        metrics.append({
            "id": metric_id,
            "label": text(item.get("label"), loc + ".label"),
            "value": val, "status": status, "coverage": coverage,
            "source_ids": source_refs(item.get("source_ids", []), loc + ".source_ids", source_ids, val is not None),
            "note": text(item.get("note"), loc + ".note", nullable=True),
        })
    return metrics


def validate(data):
    data = obj(data, {"version", "language", "task", "scope", "period", "summary", "metrics", "breakdowns", "timeline", "deliverables", "sources", "limitations"}, "report")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise InvalidReport("report.version: expected integer 1")
    language = data.get("language", "en")
    if not isinstance(language, str) or language not in LOCALES:
        raise InvalidReport("report.language: expected en or pt-BR")
    report = {
        "language": language,
        "task": text(data.get("task"), "report.task"),
        "scope": text(data.get("scope"), "report.scope", nullable=True),
        "summary": text(data.get("summary"), "report.summary", nullable=True),
    }
    period = obj(data.get("period", {}), {"start", "cutoff", "timezone"}, "report.period")
    report["period"] = {key: text(period.get(key), f"report.period.{key}", nullable=True) for key in ("start", "cutoff", "timezone")}
    sources = []
    source_ids = set()
    for index, item in enumerate(array(data.get("sources", []), "report.sources")):
        loc = f"report.sources[{index}]"
        item = obj(item, {"id", "label", "detail", "url"}, loc)
        source_id = text(item.get("id"), loc + ".id")
        if source_id in source_ids:
            raise InvalidReport(f"{loc}: duplicate source id")
        source_ids.add(source_id)
        url = text(item.get("url"), loc + ".url", nullable=True)
        if url is not None:
            try:
                parsed = urlsplit(url)
                valid_url = (parsed.scheme in ("http", "https") and parsed.hostname
                             and parsed.username is None and parsed.password is None
                             and not any(char.isspace() for char in url))
            except ValueError:
                valid_url = False
            if not valid_url:
                raise InvalidReport(f"{loc}.url: use an http/https URL without credentials")
        sources.append({"id": source_id, "label": text(item.get("label"), loc + ".label"),
                        "detail": text(item.get("detail"), loc + ".detail", nullable=True), "url": url})
    report["sources"] = sources
    report["metrics"] = validate_metrics(data.get("metrics", []), "report.metrics", source_ids)
    report["breakdowns"] = []
    for index, item in enumerate(array(data.get("breakdowns", []), "report.breakdowns")):
        loc = f"report.breakdowns[{index}]"
        item = obj(item, {"title", "metrics"}, loc)
        metrics = validate_metrics(item.get("metrics", []), loc + ".metrics", source_ids)
        if not metrics:
            raise InvalidReport(f"{loc}.metrics: provide at least one metric")
        report["breakdowns"].append({"title": text(item.get("title"), loc + ".title"), "metrics": metrics})
    for section, keys in (("timeline", {"time", "title", "detail", "source_ids"}),
                          ("deliverables", {"label", "detail", "source_ids"})):
        report[section] = []
        for index, item in enumerate(array(data.get(section, []), f"report.{section}")):
            loc = f"report.{section}[{index}]"
            item = obj(item, keys, loc)
            clean = {key: text(item.get(key), f"{loc}.{key}", nullable=(key == "detail"))
                     for key in keys - {"source_ids"}}
            clean["source_ids"] = source_refs(item.get("source_ids", []), loc + ".source_ids", source_ids, True)
            report[section].append(clean)
    report["limitations"] = [text(item, f"report.limitations[{index}]") for index, item in
                             enumerate(array(data.get("limitations", []), "report.limitations"))]
    return report


def esc(value):
    return html.escape(value, quote=True)


def badges(metric, locale):
    return (f'<div class="cr-badges"><span class="cr-badge cr-{metric["status"]}">{esc(locale["statuses"][metric["status"]])}</span>'
            f'<span class="cr-coverage">{esc(locale["coverage"][metric["coverage"]])}</span></div>')


def missing_metric(metric_id, label, locale):
    return {"id": metric_id, "label": label, "value": None, "status": "unavailable",
            "coverage": "unavailable", "source_ids": [], "note": locale["missing_evidence"]}


def render_body(report):
    locale = LOCALES[report["language"]]
    unavailable = locale["statuses"]["unavailable"]
    source_lookup = {item["id"]: (index, item["label"]) for index, item in enumerate(report["sources"], 1)}

    def refs(ids):
        if not ids:
            return esc(locale["missing_source"])
        return "; ".join(f'[{source_lookup[item][0]}] {esc(source_lookup[item][1])}' for item in ids)

    def metric_table(title, metrics, subtitle=None):
        out = [f'<section class="cr-section"><div class="cr-section-head"><h2>{esc(title)}</h2>']
        if subtitle:
            out.append(f'<p class="cr-subtitle">{esc(subtitle)}</p>')
        out.append('</div><div class="cr-table-wrap"><table><thead><tr>'
                   + ''.join(f'<th scope="col">{esc(locale[key])}</th>' for key in ("metric", "result", "basis_sources"))
                   + '</tr></thead><tbody>')
        for metric in metrics:
            out.append(f'<tr><td class="cr-metric-label">{esc(metric["label"])}</td><td><div class="cr-result">{esc(metric["value"] or unavailable)}</div>{badges(metric, locale)}</td><td><p class="cr-source-text">{refs(metric["source_ids"])}</p>')
            if metric["note"]:
                out.append(f'<p class="cr-note">{esc(metric["note"])}</p>')
            out.append('</td></tr>')
        out.append('</tbody></table></div></section>')
        return "".join(out)

    metric_lookup = {metric["id"]: metric for metric in report["metrics"]}
    kpis = [metric_lookup.get(key, missing_metric(key, label, locale)) for key, label in locale["kpi_labels"].items()]
    # Missing primary metrics remain explicit in the audit table too.
    all_metrics = report["metrics"] + [metric for metric in kpis if metric["id"] not in metric_lookup]
    out = [f'<main class="chat-report" lang="{esc(report["language"])}" aria-label="{esc(locale["report_title"])}">',
           f'<header class="cr-hero"><p class="cr-kicker">{esc(locale["kicker"])}</p>',
           f'<h1>{esc(report["task"])}</h1>',
           f'<p class="cr-scope">{esc(report["scope"] or locale["missing_scope"])}</p><dl class="cr-period">']
    for key, label in locale["period_labels"].items():
        out.append(f'<div><dt>{esc(label)}</dt><dd>{esc(report["period"][key] or locale["not_provided"])}</dd></div>')
    out.append('</dl></header>')
    if report["summary"]:
        out.append(f'<p class="cr-summary">{esc(report["summary"])}</p>')
    out.append(f'<section class="cr-kpis" aria-label="{esc(locale["kpis"])}">')
    for metric in kpis:
        missing = ' cr-missing' if metric["value"] is None else ''
        out.append(f'<article class="cr-kpi"><h2 class="cr-kpi-label">{esc(metric["label"])}</h2><p class="cr-kpi-value{missing}">{esc(metric["value"] or unavailable)}</p>{badges(metric, locale)}')
        if metric["note"]:
            out.append(f'<p class="cr-kpi-note">{esc(metric["note"])}</p>')
        out.append('</article>')
    out.append('</section>')
    out.append(metric_table(locale["metrics_title"], all_metrics, locale["metrics_subtitle"]))
    for group in report["breakdowns"]:
        out.append(metric_table(group["title"], group["metrics"]))
    if report["timeline"] or report["deliverables"]:
        out.append('<div class="cr-grid">' if report["timeline"] and report["deliverables"] else '<div>')
        if report["timeline"]:
            out.append(f'<section class="cr-section"><div class="cr-section-head"><h2>{esc(locale["timeline_title"])}</h2><p class="cr-subtitle">{esc(locale["timeline_subtitle"])}</p></div><div class="cr-content"><ol class="cr-timeline">')
            for event in report["timeline"]:
                out.append(f'<li><p class="cr-time">{esc(event["time"])}</p><p class="cr-item-title">{esc(event["title"])}</p>')
                if event["detail"]:
                    out.append(f'<p class="cr-item-detail">{esc(event["detail"])}</p>')
                out.append(f'<p class="cr-note">{refs(event["source_ids"])}</p></li>')
            out.append('</ol></div></section>')
        if report["deliverables"]:
            out.append(f'<section class="cr-section"><div class="cr-section-head"><h2>{esc(locale["deliverables_title"])}</h2><p class="cr-subtitle">{esc(locale["deliverables_subtitle"])}</p></div><div class="cr-content"><ul class="cr-deliverables">')
            for item in report["deliverables"]:
                out.append(f'<li><p class="cr-item-title">{esc(item["label"])}</p>')
                if item["detail"]:
                    out.append(f'<p class="cr-item-detail">{esc(item["detail"])}</p>')
                out.append(f'<p class="cr-note">{refs(item["source_ids"])}</p></li>')
            out.append('</ul></div></section>')
        out.append('</div>')
    out.append(f'<section class="cr-section"><div class="cr-section-head"><h2>{esc(locale["sources_title"])}</h2><p class="cr-subtitle">{esc(locale["sources_subtitle"])}</p></div><div class="cr-content">')
    if report["sources"]:
        out.append('<ol class="cr-source-list">')
        for source in report["sources"]:
            label = esc(source["label"])
            if source["url"]:
                label = f'<a href="{esc(source["url"])}" rel="noreferrer noopener">{label}</a>'
            out.append(f'<li><strong>{label}</strong>')
            if source["detail"]:
                out.append(f'<p class="cr-item-detail">{esc(source["detail"])}</p>')
            out.append('</li>')
        out.append('</ol>')
    else:
        out.append(f'<p class="cr-empty">{esc(locale["no_sources"])}</p>')
    out.append(f'</div><div class="cr-limits"><h3>{esc(locale["limits_title"])}</h3><ul>')
    for limitation in report["limitations"] or [locale["no_limits"]]:
        out.append(f'<li>{esc(limitation)}</li>')
    out.append(f'</ul></div></section><footer class="cr-footer"><strong>CHAT REPORT</strong><span>{esc(locale["footer"])}</span></footer></main>')
    return "\n".join(out)


def render(report, fragment=False):
    template_path = Path(__file__).resolve().parent.parent / "assets" / "report-template.html"
    template = template_path.read_text(encoding="utf-8")
    body = render_body(report)
    if fragment:
        match = re.search(r'<style id="chat-report-styles">(.*?)</style>', template, re.DOTALL)
        if match is None:
            raise InvalidReport("Template is missing the expected style block")
        return '<style>\n' + match.group(1) + '\n</style>\n' + body + '\n'
    return string.Template(template).substitute(
        document_language=esc(report["language"]),
        document_title=esc(LOCALES[report["language"]]["report_title"] + " — " + report["task"]),
        report_body=body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Presentation JSON (not calculation data)")
    parser.add_argument("--output", required=True, type=Path, help="Destination HTML file")
    parser.add_argument("--fragment", action="store_true", help="Scoped CSS and static markup only, without doctype/head/body")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing file")
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise InvalidReport("Input and output must be different files")
        data = json.loads(args.input.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys, parse_constant=no_constant)
        rendered = render(validate(data), fragment=args.fragment)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w" if args.overwrite else "x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except (InvalidReport, OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "format": "fragment" if args.fragment else "standalone"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
