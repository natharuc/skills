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


STATUSES = {
    "measured": "Medido", "declared": "Informado",
    "calculated": "Calculado", "estimated": "Estimado",
    "unavailable": "Indisponível",
}
COVERAGE = {
    "complete": "Cobertura completa", "partial": "Cobertura parcial",
    "unavailable": "Cobertura indisponível",
}
KPI_LABELS = {
    "human_time": "Dedicação humana", "agent_time": "Execução do agente",
    "tokens": "Tokens consumidos", "cost": "Custo",
}


class InvalidReport(ValueError):
    pass


def obj(value, allowed, location):
    if not isinstance(value, dict):
        raise InvalidReport(f"{location}: esperado objeto JSON")
    unknown = set(value) - set(allowed)
    if unknown:
        raise InvalidReport(f"{location}: campos desconhecidos: {', '.join(sorted(unknown))}")
    return value


def text(value, location, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidReport(f"{location}: esperado texto não vazio" + (" ou null" if nullable else ""))
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise InvalidReport(f"{location}: caractere de controle não permitido")
    return value


def array(value, location):
    if not isinstance(value, list):
        raise InvalidReport(f"{location}: esperada lista")
    return value


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidReport(f"JSON: chave repetida: {key}")
        result[key] = value
    return result


def no_constant(value):
    raise InvalidReport(f"JSON: constante não permitida: {value}")


def source_refs(value, location, source_ids, required=False):
    refs = array(value, location)
    if required and not refs:
        raise InvalidReport(f"{location}: ao menos uma fonte é obrigatória")
    for index, ref in enumerate(refs):
        text(ref, f"{location}[{index}]")
        if ref not in source_ids:
            raise InvalidReport(f"{location}: fonte não definida: {ref}")
    if len(set(refs)) != len(refs):
        raise InvalidReport(f"{location}: fontes repetidas")
    return refs


def validate_metrics(value, location, source_ids):
    metrics = []
    ids = set()
    for index, item in enumerate(array(value, location)):
        loc = f"{location}[{index}]"
        item = obj(item, {"id", "label", "value", "status", "coverage", "source_ids", "note"}, loc)
        metric_id = text(item.get("id"), loc + ".id")
        if metric_id in ids:
            raise InvalidReport(f"{loc}: id de métrica repetido")
        ids.add(metric_id)
        val = text(item.get("value"), loc + ".value", nullable=True)
        status = item.get("status", "unavailable")
        coverage = item.get("coverage", "unavailable")
        if not isinstance(status, str) or status not in STATUSES:
            raise InvalidReport(f"{loc}.status: qualificação desconhecida")
        if not isinstance(coverage, str) or coverage not in COVERAGE:
            raise InvalidReport(f"{loc}.coverage: cobertura desconhecida")
        if val is None and (status != "unavailable" or coverage != "unavailable"):
            raise InvalidReport(f"{loc}: valor null exige status e coverage unavailable")
        if val is not None and (status == "unavailable" or coverage == "unavailable"):
            raise InvalidReport(f"{loc}: valor conhecido exige status e cobertura explícitos")
        metrics.append({
            "id": metric_id,
            "label": text(item.get("label"), loc + ".label"),
            "value": val, "status": status, "coverage": coverage,
            "source_ids": source_refs(item.get("source_ids", []), loc + ".source_ids", source_ids, val is not None),
            "note": text(item.get("note"), loc + ".note", nullable=True),
        })
    return metrics


def validate(data):
    data = obj(data, {"version", "task", "scope", "period", "summary", "metrics", "breakdowns", "timeline", "deliverables", "sources", "limitations"}, "report")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise InvalidReport("report.version: esperado inteiro 1")
    report = {
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
            raise InvalidReport(f"{loc}: id de fonte repetido")
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
                raise InvalidReport(f"{loc}.url: use URL http/https sem credenciais")
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
            raise InvalidReport(f"{loc}.metrics: forneça ao menos uma métrica")
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


def badges(metric):
    return (f'<div class="cr-badges"><span class="cr-badge cr-{metric["status"]}">{STATUSES[metric["status"]]}</span>'
            f'<span class="cr-coverage">{COVERAGE[metric["coverage"]]}</span></div>')


def missing_metric(metric_id, label):
    return {"id": metric_id, "label": label, "value": None, "status": "unavailable",
            "coverage": "unavailable", "source_ids": [], "note": "Sem evidência fornecida para esta métrica."}


def render_body(report):
    source_lookup = {item["id"]: (index, item["label"]) for index, item in enumerate(report["sources"], 1)}

    def refs(ids):
        if not ids:
            return "Fonte não informada."
        return "; ".join(f'[{source_lookup[item][0]}] {esc(source_lookup[item][1])}' for item in ids)

    def metric_table(title, metrics, subtitle=None):
        out = [f'<section class="cr-section"><div class="cr-section-head"><h2>{esc(title)}</h2>']
        if subtitle:
            out.append(f'<p class="cr-subtitle">{esc(subtitle)}</p>')
        out.append('</div><div class="cr-table-wrap"><table><thead><tr><th scope="col">Métrica</th><th scope="col">Resultado</th><th scope="col">Base e fontes</th></tr></thead><tbody>')
        for metric in metrics:
            out.append(f'<tr><td class="cr-metric-label">{esc(metric["label"])}</td><td><div class="cr-result">{esc(metric["value"] or "Indisponível")}</div>{badges(metric)}</td><td><p class="cr-source-text">{refs(metric["source_ids"])}</p>')
            if metric["note"]:
                out.append(f'<p class="cr-note">{esc(metric["note"])}</p>')
            out.append('</td></tr>')
        out.append('</tbody></table></div></section>')
        return "".join(out)

    metric_lookup = {metric["id"]: metric for metric in report["metrics"]}
    kpis = [metric_lookup.get(key, missing_metric(key, label)) for key, label in KPI_LABELS.items()]
    # Missing primary metrics remain explicit in the audit table too.
    all_metrics = report["metrics"] + [metric for metric in kpis if metric["id"] not in metric_lookup]
    out = ['<main class="chat-report" aria-label="Relatório do chat">',
           '<header class="cr-hero"><p class="cr-kicker">Relatório do chat · Tempo, consumo e custo</p>',
           f'<h1>{esc(report["task"])}</h1>',
           f'<p class="cr-scope">{esc(report["scope"] or "Escopo não informado.")}</p><dl class="cr-period">']
    for key, label, fallback in (("start", "Início", "Não informado"), ("cutoff", "Corte", "Não informado"), ("timezone", "Fuso horário", "Não informado")):
        out.append(f'<div><dt>{label}</dt><dd>{esc(report["period"][key] or fallback)}</dd></div>')
    out.append('</dl></header>')
    if report["summary"]:
        out.append(f'<p class="cr-summary">{esc(report["summary"])}</p>')
    out.append('<section class="cr-kpis" aria-label="Indicadores principais">')
    for metric in kpis:
        missing = ' cr-missing' if metric["value"] is None else ''
        out.append(f'<article class="cr-kpi"><h2 class="cr-kpi-label">{esc(metric["label"])}</h2><p class="cr-kpi-value{missing}">{esc(metric["value"] or "Indisponível")}</p>{badges(metric)}')
        if metric["note"]:
            out.append(f'<p class="cr-kpi-note">{esc(metric["note"])}</p>')
        out.append('</article>')
    out.append('</section>')
    out.append(metric_table("Métricas e evidências", all_metrics, "A qualificação e a cobertura acompanham cada resultado."))
    for group in report["breakdowns"]:
        out.append(metric_table(group["title"], group["metrics"]))
    if report["timeline"] or report["deliverables"]:
        out.append('<div class="cr-grid">' if report["timeline"] and report["deliverables"] else '<div>')
        if report["timeline"]:
            out.append('<section class="cr-section"><div class="cr-section-head"><h2>Linha do tempo</h2><p class="cr-subtitle">Eventos com fonte identificada.</p></div><div class="cr-content"><ol class="cr-timeline">')
            for event in report["timeline"]:
                out.append(f'<li><p class="cr-time">{esc(event["time"])}</p><p class="cr-item-title">{esc(event["title"])}</p>')
                if event["detail"]:
                    out.append(f'<p class="cr-item-detail">{esc(event["detail"])}</p>')
                out.append(f'<p class="cr-note">{refs(event["source_ids"])}</p></li>')
            out.append('</ol></div></section>')
        if report["deliverables"]:
            out.append('<section class="cr-section"><div class="cr-section-head"><h2>Entregas registradas</h2><p class="cr-subtitle">Resultados confirmados no escopo.</p></div><div class="cr-content"><ul class="cr-deliverables">')
            for item in report["deliverables"]:
                out.append(f'<li><p class="cr-item-title">{esc(item["label"])}</p>')
                if item["detail"]:
                    out.append(f'<p class="cr-item-detail">{esc(item["detail"])}</p>')
                out.append(f'<p class="cr-note">{refs(item["source_ids"])}</p></li>')
            out.append('</ul></div></section>')
        out.append('</div>')
    out.append('<section class="cr-section"><div class="cr-section-head"><h2>Fontes e limites</h2><p class="cr-subtitle">Rastreabilidade para interpretar os resultados.</p></div><div class="cr-content">')
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
        out.append('<p class="cr-empty">Nenhuma fonte foi fornecida para esta apresentação.</p>')
    out.append('</div><div class="cr-limits"><h3>Limites de interpretação</h3><ul>')
    for limitation in report["limitations"] or ["Limitações adicionais não informadas."]:
        out.append(f'<li>{esc(limitation)}</li>')
    out.append('</ul></div></section><footer class="cr-footer"><strong>CHAT REPORT</strong><span>Valores preservados conforme as fontes e qualificações indicadas.</span></footer></main>')
    return "\n".join(out)


def render(report, fragment=False):
    template_path = Path(__file__).resolve().parent.parent / "assets" / "report-template.html"
    template = template_path.read_text(encoding="utf-8")
    body = render_body(report)
    if fragment:
        match = re.search(r'<style id="chat-report-styles">(.*?)</style>', template, re.DOTALL)
        if match is None:
            raise InvalidReport("Template sem bloco de estilos esperado")
        return '<style>\n' + match.group(1) + '\n</style>\n' + body + '\n'
    return string.Template(template).substitute(document_title=esc("Relatório do chat — " + report["task"]), report_body=body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON de apresentação (não dados de cálculo)")
    parser.add_argument("--output", required=True, type=Path, help="Arquivo HTML de destino")
    parser.add_argument("--fragment", action="store_true", help="Somente CSS isolado e marcação estática, sem doctype/head/body")
    parser.add_argument("--overwrite", action="store_true", help="Autorizar substituição de arquivo existente")
    args = parser.parse_args()
    try:
        if args.input.resolve() == args.output.resolve():
            raise InvalidReport("Entrada e saída devem ser arquivos diferentes")
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
