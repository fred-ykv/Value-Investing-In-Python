"""Readable WACC and cost-of-equity audit sections."""
from __future__ import annotations

from dataclasses import asdict
from html import escape

from .cost_of_capital import CostOfCapitalResult


def cost_of_capital_payload(result: CostOfCapitalResult) -> dict[str, object]:
    return {**asdict(result), "table": cost_of_capital_table(result), "summary": cost_of_capital_summary(result)}


def cost_of_capital_table(result: CostOfCapitalResult) -> list[dict[str, object]]:
    confidence = result.component_confidences
    rows = [
        _row("Taxa de desconto aplicada", result.discount_rate, "percent", result.sources.get("discount_rate"), confidence.get("discount_rate", result.confidence), _discount_rate_note(result)),
        _row("Custo do patrimonio (Ke)", result.cost_of_equity, "percent", result.sources.get("cost_of_equity"), confidence.get("cost_of_equity", result.confidence), "Taxa exigida pelos acionistas."),
        _row("Taxa livre de risco", result.risk_free_rate, "percent", result.sources.get("risk_free_rate"), confidence.get("risk_free_rate", result.confidence), "Componente base do CAPM."),
        _row("Beta", result.beta, "number", result.sources.get("beta"), confidence.get("beta", result.confidence), "Sensibilidade da acao ao risco de mercado."),
        _row("Premio de risco do mercado", result.equity_risk_premium, "percent", result.sources.get("equity_risk_premium"), confidence.get("equity_risk_premium", result.confidence), "Premio exigido acima da taxa livre de risco."),
    ]
    if result.pre_tax_cost_of_debt is not None:
        rows.extend(
            [
                _row("Custo da divida antes dos impostos", result.pre_tax_cost_of_debt, "percent", result.sources.get("pre_tax_cost_of_debt"), confidence.get("pre_tax_cost_of_debt", result.confidence), "Proxy do custo de financiamento da divida."),
                _row("Aliquota de imposto", result.tax_rate, "percent", result.sources.get("tax_rate"), confidence.get("tax_rate", result.confidence), "Usada para estimar o beneficio fiscal dos juros."),
                _row("Custo da divida apos impostos", result.after_tax_cost_of_debt, "percent", "Calculado pelo modelo", confidence.get("after_tax_cost_of_debt", result.confidence), "Custo da divida x (1 - aliquota de imposto)."),
                _row("Peso do patrimonio", result.equity_weight, "percent", result.sources.get("market_value_equity"), confidence.get("capital_weights", result.confidence), "Valor de mercado do patrimonio / capital total."),
                _row("Peso da divida", result.debt_weight, "percent", result.sources.get("debt_value"), confidence.get("capital_weights", result.confidence), "Divida bruta / capital total."),
            ]
        )
    if result.calculated_wacc is not None and result.method == "explicit_wacc_override":
        rows.append(_row("WACC calculado para comparacao", result.calculated_wacc, "percent", "Calculado pelo modelo", confidence.get("calculated_wacc", result.confidence), "Nao substituiu o WACC informado; serve como controle de consistencia."))
    return rows


def cost_of_capital_summary(result: CostOfCapitalResult) -> str:
    rate = _fmt_percent(result.discount_rate)
    if result.discount_rate_label == "Custo do patrimonio (Ke)":
        return f"Os modelos de banco/financeira usaram Ke de {rate}. Para Lucro Residual e DDM, Ke e a taxa coerente; WACC nao foi aplicado."
    if result.wacc is not None:
        basis = "informado" if result.method == "explicit_wacc_override" else "calculado com pesos de mercado"
        return f"O DCF/FCFF usou WACC de {rate}, {basis}. A memoria abaixo mostra Ke, custo da divida, imposto e pesos utilizados."
    return f"Nao houve dados suficientes para um WACC completo. O DCF usou {result.discount_rate_label} de {rate}; revise estrutura de capital e custo da divida."


def append_cost_of_capital_to_markdown(markdown: str, result: CostOfCapitalResult) -> str:
    section = [
        "",
        "## Taxa de desconto utilizada",
        cost_of_capital_summary(result),
        "",
        "| Componente | Valor | Fonte | Confianca | Como ler |",
        "|---|---:|---|---:|---|",
    ]
    for row in cost_of_capital_table(result):
        section.append(
            f"| {row['component']} | {_format_value(row['value'], row['format'])} | {row['source']} | {float(row['confidence'] or 0):.2f} | {row['note']} |"
        )
    if result.notes:
        section.extend(["", "**Alertas da taxa:**", *[f"- {note}" for note in result.notes]])
    block = "\n".join(section)
    marker = "\n## Cenarios hipoteticos"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    marker = "\n## Score por dimensao"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    return markdown + block


def append_cost_of_capital_to_html(html: str, result: CostOfCapitalResult) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row['component']))}</td>"
        f"<td>{escape(_format_value(row['value'], row['format']))}</td>"
        f"<td>{escape(str(row['source']))}</td>"
        f"<td>{float(row['confidence'] or 0):.2f}</td>"
        f"<td>{escape(str(row['note']))}</td>"
        "</tr>"
        for row in cost_of_capital_table(result)
    )
    alerts = ""
    if result.notes:
        alerts = '<div class="capital-alerts"><strong>Alertas da taxa</strong><ul>' + "".join(f"<li>{escape(note)}</li>" for note in result.notes) + "</ul></div>"
    section = (
        '<section class="panel cost-of-capital">'
        "<h2>Taxa de desconto utilizada</h2>"
        f"<p>{escape(cost_of_capital_summary(result))}</p>"
        "<table><thead><tr><th>Componente</th><th>Valor</th><th>Fonte</th><th>Confianca</th><th>Como ler</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>{alerts}</section>"
    )
    marker = '<section class="panel">\n<h2>Cenarios</h2>'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    marker = '<section class="panel">\n<h2>Score por dimensao</h2>'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    return html.replace("</main>", section + "\n</main>", 1)


def _row(component: str, value: object, format_name: str, source: str | None, confidence: float, note: str) -> dict[str, object]:
    return {
        "component": component,
        "value": value,
        "format": format_name,
        "source": source or "Indisponivel",
        "confidence": confidence,
        "note": note,
    }


def _discount_rate_note(result: CostOfCapitalResult) -> str:
    if result.discount_rate_label == "WACC":
        return "Taxa usada para descontar FCFF e calcular valor da firma."
    return "Taxa usada nos modelos de valor do acionista ou como proxy explicita quando o WACC ficou indisponivel."


def _format_value(value: object, format_name: object) -> str:
    if value is None:
        return "-"
    try:
        numeric = float(value)
    except Exception:
        return str(value)
    if format_name == "percent":
        return _fmt_percent(numeric)
    return f"{numeric:.2f}"


def _fmt_percent(value: object) -> str:
    try:
        return "-" if value is None else f"{float(value) * 100:.2f}%"
    except Exception:
        return "-"
