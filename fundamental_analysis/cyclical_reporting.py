"""Readable audit trail for cyclical normalization."""

from __future__ import annotations

from dataclasses import asdict
from html import escape
from typing import Mapping

from .cyclical_normalization import CyclicalNormalizationResult
from .data_sources import MetricValue


def cyclical_normalization_payload(
    result: CyclicalNormalizationResult,
    values: Mapping[str, MetricValue],
) -> dict[str, object]:
    return {
        "is_cyclical": result.is_cyclical,
        "applied": result.applied,
        "status": result.status,
        "status_label": _status_label(result),
        "confidence": result.confidence,
        "sample_years": result.sample_years,
        "cycle_position": result.cycle_position,
        "cycle_position_label": _cycle_position_label(result.cycle_position),
        "transition_years": result.transition_years,
        "summary": cyclical_normalization_summary(result),
        "comparison_table": cyclical_comparison_table(result, values),
        "history": [asdict(period) for period in result.periods],
        "warnings": list(result.warnings),
    }


def cyclical_comparison_table(
    result: CyclicalNormalizationResult,
    values: Mapping[str, MetricValue],
) -> list[dict[str, object]]:
    current_reinvestment = _difference(values.get("nopat"), values.get("fcff"))
    return [
        _row("Margem operacional (EBIT)", result.current_operating_margin, result.normalized_operating_margin, "percent", "Media robusta das margens anuais do ciclo."),
        _row("Margem liquida", result.current_net_margin, result.normalized_net_margin, "percent", "Media robusta do lucro liquido sobre a receita."),
        _row("Margem de FCFF", result.current_fcff_margin, result.normalized_fcff_margin, "percent", "FCFF anual dividido pela receita de cada periodo."),
        _row("EBIT", _number(values.get("ebit")), _number(result.normalized_ebit), "money", "Receita corrente multiplicada pela margem operacional normalizada."),
        _row("Lucro liquido", _number(values.get("net_income")), _number(result.normalized_net_income), "money", "Receita corrente multiplicada pela margem liquida normalizada."),
        _row("Reinvestimento", current_reinvestment, _number(result.normalized_reinvestment), "money", "NOPAT menos FCFF; normalizado como proporcao da receita."),
        _row("FCFF", _number(values.get("fcff")), _number(result.normalized_fcff), "money", "NOPAT normalizado menos reinvestimento normalizado."),
        _row("ROIC", _number(values.get("roic_proxy")), _number(result.normalized_roic), "percent", "NOPAT normalizado dividido pelo capital investido corrente."),
    ]


def cyclical_normalization_summary(result: CyclicalNormalizationResult) -> str:
    if not result.is_cyclical:
        return "A empresa nao foi classificada como ciclica; os valores correntes foram preservados."
    if result.applied:
        return (
            f"A normalizacao foi aplicada com {result.sample_years} anos e confianca "
            f"de {result.confidence:.0%}. O DCF converge gradualmente do FCFF atual "
            f"para o FCFF de meio de ciclo em {result.transition_years} anos; Graham "
            "e EVA usam lucro e rentabilidade normalizados."
        )
    return (
        f"A empresa foi identificada como ciclica, mas a normalizacao nao foi aplicada "
        f"(historico: {result.sample_years} anos; confianca: {result.confidence:.0%}). "
        "Os valores correntes foram preservados para evitar falsa precisao."
    )


def append_cyclical_normalization_to_markdown(
    markdown: str,
    result: CyclicalNormalizationResult,
    values: Mapping[str, MetricValue],
) -> str:
    if not result.is_cyclical:
        return markdown
    lines = [
        "",
        "## Normalizacao do ciclo",
        cyclical_normalization_summary(result),
        "",
        f"**Status:** {_status_label(result)} | **Posicao no ciclo:** {_cycle_position_label(result.cycle_position)}",
        "",
        "| Medida | Atual | Normalizado | Como foi normalizado |",
        "|---|---:|---:|---|",
    ]
    for row in cyclical_comparison_table(result, values):
        lines.append(
            f"| {row['metric']} | {_format(row['current'], row['format'])} | "
            f"{_format(row['normalized'], row['format'])} | {row['explanation']} |"
        )
    lines.extend(
        [
            "",
            "### Historico usado",
            "| Periodo | Margem EBIT | Margem liquida | Margem FCFF | Reinvestimento/receita | Confianca |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for period in result.periods:
        lines.append(
            f"| {period.period_end} | {_percent(period.operating_margin)} | "
            f"{_percent(period.net_margin)} | {_percent(period.fcff_margin)} | "
            f"{_percent(period.reinvestment_margin)} | {period.confidence:.2f} |"
        )
    if result.warnings:
        lines.extend(["", "**Pontos de atencao:**", *[f"- {item}" for item in result.warnings]])
    block = "\n".join(lines)
    marker = "\n## Taxa de desconto utilizada"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    return markdown + block


def append_cyclical_normalization_to_html(
    html: str,
    result: CyclicalNormalizationResult,
    values: Mapping[str, MetricValue],
) -> str:
    if not result.is_cyclical:
        return html
    comparison_rows = "".join(
        "<tr>"
        f"<td>{escape(str(row['metric']))}</td>"
        f"<td>{escape(_format(row['current'], row['format']))}</td>"
        f"<td><strong>{escape(_format(row['normalized'], row['format']))}</strong></td>"
        f"<td>{escape(str(row['explanation']))}</td>"
        "</tr>"
        for row in cyclical_comparison_table(result, values)
    )
    history_rows = "".join(
        "<tr>"
        f"<td>{period.period_end}</td>"
        f"<td>{escape(_percent(period.operating_margin))}</td>"
        f"<td>{escape(_percent(period.net_margin))}</td>"
        f"<td>{escape(_percent(period.fcff_margin))}</td>"
        f"<td>{escape(_percent(period.reinvestment_margin))}</td>"
        f"<td>{period.confidence:.2f}</td>"
        "</tr>"
        for period in result.periods
    )
    warning_html = ""
    if result.warnings:
        warning_html = "<div><strong>Pontos de atencao</strong><ul>" + "".join(
            f"<li>{escape(item)}</li>" for item in result.warnings
        ) + "</ul></div>"
    section = (
        '<section class="panel cyclical-normalization">'
        "<h2>Normalizacao do ciclo</h2>"
        f"<p>{escape(cyclical_normalization_summary(result))}</p>"
        f"<p><strong>Status:</strong> {escape(_status_label(result))} &nbsp; "
        f"<strong>Posicao no ciclo:</strong> {escape(_cycle_position_label(result.cycle_position))}</p>"
        "<table><thead><tr><th>Medida</th><th>Atual</th><th>Normalizado</th><th>Como foi normalizado</th></tr></thead>"
        f"<tbody>{comparison_rows}</tbody></table>"
        "<h3>Historico usado</h3>"
        "<table><thead><tr><th>Periodo</th><th>Margem EBIT</th><th>Margem liquida</th><th>Margem FCFF</th><th>Reinvestimento/receita</th><th>Confianca</th></tr></thead>"
        f"<tbody>{history_rows}</tbody></table>{warning_html}</section>"
    )
    marker = '<section class="panel cost-of-capital">'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    return html.replace("</main>", section + "\n</main>", 1)


def _row(metric: str, current: float | None, normalized: float | None, format_name: str, explanation: str) -> dict[str, object]:
    return {"metric": metric, "current": current, "normalized": normalized, "format": format_name, "explanation": explanation}


def _number(metric: MetricValue | None) -> float | None:
    return float(metric.value) if metric is not None and metric.is_available else None


def _difference(left: MetricValue | None, right: MetricValue | None) -> float | None:
    left_value, right_value = _number(left), _number(right)
    return left_value - right_value if left_value is not None and right_value is not None else None


def _status_label(result: CyclicalNormalizationResult) -> str:
    if result.applied:
        return "Aplicada"
    labels = {
        "insufficient_history": "Nao aplicada: historico insuficiente",
        "low_confidence": "Nao aplicada: baixa confianca",
        "invalid_current_revenue": "Nao aplicada: receita corrente invalida",
    }
    return labels.get(result.status, "Nao aplicavel")


def _cycle_position_label(value: str) -> str:
    return {
        "acima_do_meio_do_ciclo": "Acima do meio do ciclo",
        "abaixo_do_meio_do_ciclo": "Abaixo do meio do ciclo",
        "proximo_do_meio_do_ciclo": "Proximo do meio do ciclo",
    }.get(value, "Indeterminada")


def _format(value: object, format_name: object) -> str:
    if value is None:
        return "-"
    numeric = float(value)
    if format_name == "percent":
        return _percent(numeric)
    return f"US$ {numeric:,.2f}"


def _percent(value: object) -> str:
    return "-" if value is None else f"{float(value) * 100:.2f}%"


__all__ = [
    "append_cyclical_normalization_to_html",
    "append_cyclical_normalization_to_markdown",
    "cyclical_comparison_table",
    "cyclical_normalization_payload",
]
