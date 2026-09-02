"""Executive recommendation narrative for beginner-friendly reports."""
from __future__ import annotations

from html import escape
from typing import Iterable

from .config import SCORE
from .reports import recommendation_gate_note, valuation_readthrough
from .scoring import ScoreReport
from .valuation import ValuationResult


DIMENSION_LABELS = {
    "valuation": "Valuation",
    "growth": "Crescimento",
    "quality": "Qualidade",
    "debt": "Divida",
    "liquidity": "Liquidez",
    "data_confidence": "Confianca dos dados",
}


def executive_decision_summary(score: ScoreReport, valuations: Iterable[ValuationResult] | None = None) -> dict[str, object]:
    supports, pressures = decision_drivers(score)
    gate = recommendation_gate_note(score)
    score_label, score_reading = total_score_band(score.total_score)
    return {
        "recommendation": score.recommendation,
        "score": score.total_score,
        "score_label": score_label,
        "score_reading": score_reading,
        "headline": _headline(score.recommendation),
        "supports": supports,
        "pressures": pressures,
        "gate": gate or "Nenhuma trava automatica especifica foi acionada; a recomendacao veio da combinacao dos pilares.",
        "gate_triggered": bool(gate),
        "valuation_readthrough": valuation_readthrough(list(valuations or [])),
    }


def apply_executive_layer_to_markdown(markdown: str, score: ScoreReport, valuations: list[ValuationResult]) -> str:
    if "## Conclusao executiva" in markdown:
        return markdown
    block = _executive_markdown(executive_decision_summary(score, valuations))
    marker = "\n## Ponte para decisao"
    if marker in markdown:
        return markdown.replace(marker, f"\n{block}{marker}", 1)
    return f"{markdown}\n\n{block}"


def apply_executive_layer_to_html(html: str, score: ScoreReport, valuations: list[ValuationResult]) -> str:
    if "executive-decision" in html:
        return html
    block = _executive_html(executive_decision_summary(score, valuations))
    marker = '<section class="panel bridge">'
    if marker in html:
        return html.replace(marker, f"{block}\n{marker}", 1)
    return f"{block}\n{html}"


def decision_drivers(score: ScoreReport) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    dimensions = list(score.dimensions.values())
    if not dimensions:
        empty = [{"name": "Sem dimensoes", "label": "Sem dimensoes", "score": None, "reading": "Sem leitura", "explanation": "Nao ha pilares suficientes para explicar a decisao."}]
        return empty, empty
    contributions = {
        item.name: item for item in score.dimension_contributions
    }
    supports = sorted(
        dimensions,
        key=lambda dimension: (
            contributions[dimension.name].weighted_contribution
            if dimension.name in contributions
            else dimension.score
        ),
        reverse=True,
    )
    pressures = sorted(
        dimensions,
        key=lambda dimension: (
            contributions[dimension.name].normalized_weight
            * (1.0 - dimension.score)
            if dimension.name in contributions
            else 1.0 - dimension.score
        ),
        reverse=True,
    )
    return (
        [_driver_row(item, contributions.get(item.name)) for item in supports[:3]],
        [_driver_row(item, contributions.get(item.name)) for item in pressures[:3]],
    )


def total_score_band(value: float) -> tuple[str, str]:
    if value >= SCORE.buy_threshold:
        return "Forte", "Score total acima da faixa minima de Compra; ainda precisa respeitar as travas de valuation e risco."
    if value >= SCORE.watch_threshold:
        return "Intermediario", "Score suficiente para acompanhar, mas ainda com assimetria ou confianca incompleta."
    return "Fraco", "Score abaixo da faixa minima de observacao; exige melhora material antes de reconsiderar."


def dimension_reading(value: float) -> str:
    if value >= 0.75:
        return "Forte"
    if value >= 0.50:
        return "Intermediario"
    return "Fraco"


def _executive_markdown(summary: dict[str, object]) -> str:
    supports = summary.get("supports") if isinstance(summary.get("supports"), list) else []
    pressures = summary.get("pressures") if isinstance(summary.get("pressures"), list) else []
    lines = [
        "## Conclusao executiva",
        str(summary["headline"]),
        "",
        f"- Recomendacao: **{summary['recommendation']}**.",
        f"- Score total: **{float(summary['score']):.2f}** ({summary['score_label']}). {summary['score_reading']}",
        f"- Leitura de valuation: {summary['valuation_readthrough']}",
        f"- Trava/condicao decisiva: {summary['gate']}",
        "",
        "### O que ajudou",
        *_driver_markdown_lines(supports),
        "",
        "### O que pesou contra",
        *_driver_markdown_lines(pressures),
        "",
    ]
    return "\n".join(lines)


def _executive_html(summary: dict[str, object]) -> str:
    supports = summary.get("supports") if isinstance(summary.get("supports"), list) else []
    pressures = summary.get("pressures") if isinstance(summary.get("pressures"), list) else []
    gate_class = "negative" if summary.get("gate_triggered") else "neutral"
    return "\n".join(
        [
            f'<style id="executive-reporting-css">{EXECUTIVE_CSS}</style>',
            '<section class="panel executive-decision">',
            "<h2>Conclusao executiva</h2>",
            f"<p>{escape(str(summary.get('headline', '-')))}</p>",
            '<div class="executive-grid">',
            _executive_card("Recomendacao", str(summary.get("recommendation", "-")), "Decisao final combinando score, valuation, riscos e confianca.", _recommendation_class(str(summary.get("recommendation", "")))),
            _executive_card("Score total", f"{float(summary.get('score') or 0):.2f} - {summary.get('score_label', '-')}", str(summary.get("score_reading", "-")), _score_class(float(summary.get("score") or 0.0))),
            _executive_card("Trava/condicao", str(summary.get("gate", "-")), "Explica se alguma regra impediu uma recomendacao mais forte.", gate_class),
            _executive_card("Valuation", str(summary.get("valuation_readthrough", "-")), "Mostra se os modelos sustentam ou pressionam a tese.", "neutral"),
            "</div>",
            '<div class="executive-columns">',
            _executive_driver_list("O que ajudou", supports),
            _executive_driver_list("O que pesou contra", pressures),
            "</div>",
            "</section>",
        ]
    )


def _driver_row(dimension: object, contribution: object | None = None) -> dict[str, object]:
    score_value = float(getattr(dimension, "score", 0.0))
    name = str(getattr(dimension, "name", "-"))
    return {
        "name": name,
        "label": DIMENSION_LABELS.get(name, name),
        "score": score_value,
        "weighted_contribution": float(
            getattr(contribution, "weighted_contribution", score_value)
        ),
        "weighted_shortfall": float(
            getattr(contribution, "normalized_weight", 1.0)
        ) * (1.0 - score_value),
        "reading": dimension_reading(score_value),
        "explanation": getattr(dimension, "explanation", "-"),
    }


def _driver_markdown_lines(items: list[object]) -> list[str]:
    lines = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append(f"- **{item['label']}**: {float(item['score'] or 0):.2f} ({item['reading']}). {str(item['explanation']).replace('|', '/')}")
    return lines or ["- Sem dados suficientes."]


def _executive_card(title: str, value: str, note: str, klass: str) -> str:
    return (
        f'<article class="executive-card {klass}">'
        f"<span>{escape(title)}</span>"
        f"<strong>{escape(value)}</strong>"
        f"<small>{escape(note)}</small>"
        "</article>"
    )


def _executive_driver_list(title: str, items: list[object]) -> str:
    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        score_value = float(item.get("score") or 0.0)
        rows.append(f"<li><strong>{escape(str(item.get('label', '-')))}</strong>: {score_value:.2f} ({escape(str(item.get('reading', '-')))}). {escape(str(item.get('explanation', '-')))}</li>")
    if not rows:
        rows.append("<li>Sem dados suficientes.</li>")
    return f'<div class="executive-list"><h3>{escape(title)}</h3><ul>{"".join(rows)}</ul></div>'


def _headline(recommendation: str) -> str:
    if recommendation == "Comprar":
        return "A leitura combinada ficou favoravel, desde que valuation, qualidade e confianca dos dados continuem sustentando a tese."
    if recommendation == "Observar":
        return "A tese tem pontos positivos, mas ainda nao oferece assimetria suficiente para Compra com a seguranca exigida."
    if recommendation == "Evitar":
        return "A relacao entre preco, fundamentos e riscos ficou fraca para uma decisao de entrada."
    return "A recomendacao resume a combinacao entre score total, valuation, qualidade, riscos e confianca dos dados."


def _recommendation_class(recommendation: str) -> str:
    return {"Comprar": "positive", "Observar": "neutral", "Evitar": "negative"}.get(recommendation, "neutral")


def _score_class(score: float) -> str:
    if score >= SCORE.buy_threshold:
        return "positive"
    if score >= SCORE.watch_threshold:
        return "neutral"
    return "negative"


EXECUTIVE_CSS = """
.executive-decision { border-left: 5px solid #2f6f9f; }
.executive-decision > p { color: #334155; line-height: 1.5; margin: 0 0 14px; max-width: 920px; }
.executive-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin: 12px 0 14px; }
.executive-card { background: #f8fafc; border: 1px solid #e0e6ed; border-left: 5px solid #7b8794; border-radius: 8px; display: grid; gap: 6px; padding: 12px; }
.executive-card.positive { border-left-color: #1f7a4d; }
.executive-card.neutral { border-left-color: #b58100; }
.executive-card.negative { border-left-color: #b23b3b; }
.executive-card span { color: #64748b; font-size: 11px; font-weight: 800; text-transform: uppercase; }
.executive-card strong { color: #111820; font-size: 17px; line-height: 1.2; }
.executive-card small { color: #667385; font-size: 12px; line-height: 1.35; }
.executive-columns { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.executive-list { background: #fbfcfe; border: 1px solid #e5ebf2; border-radius: 8px; padding: 12px; }
.executive-list h3 { margin: 0 0 8px; }
"""
