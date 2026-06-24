"""Human-readable final outputs."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .scoring import ScoreReport
from .valuation import ValuationResult


def valuation_table(valuations: Iterable[ValuationResult]) -> list[dict[str, object]]:
    return [{"method": v.method, "fair_value_per_share": v.fair_value_per_share, "margin_of_safety": v.margin_of_safety, "confidence": v.confidence, "diagnostics": v.diagnostics} for v in valuations]


def score_table(score: ScoreReport) -> list[dict[str, object]]:
    return [asdict(dimension) for dimension in score.dimensions.values()]


def executive_summary(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult]) -> str:
    available = [v.method for v in valuations if v.fair_value_per_share is not None]
    methods = ", ".join(available) or "nenhum modelo conclusivo"
    return f"{ticker.upper()} recebeu recomendacao **{score.recommendation}**. Score total: {score.total_score:.2f}. Modelos usados: {methods}."


def risk_diagnostics(score: ScoreReport, valuations: Iterable[ValuationResult]) -> list[str]:
    risks: list[str] = []
    if score.dimensions.get("data_confidence") and score.dimensions["data_confidence"].score < 0.50:
        risks.append("Baixa confianca dos dados; revise fontes antes de usar a recomendacao.")
    for valuation in valuations:
        if valuation.diagnostics.get("negative_fcff"):
            risks.append("DCF usa FCFF negativo; a confianca do modelo foi reduzida.")
        if valuation.diagnostics.get("terminal_growth_adjusted") is not None:
            risks.append("Crescimento terminal foi ajustado para ficar abaixo da taxa de desconto.")
    return risks or ["Nenhum risco critico detectado pela camada de validacao."]


def render_markdown_report(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult]) -> str:
    valuations = list(valuations)
    lines = [f"# Fundamental Analysis - {ticker.upper()}", "", "## Resumo executivo", executive_summary(ticker, score, valuations), "", "## Justificativa", recommendation_summary(score), "", "## Valuation por metodo", "| Metodo | Preco justo | Margem de seguranca | Confianca |", "|---|---:|---:|---:|"]
    for row in valuation_table(valuations):
        lines.append(f"| {row['method']} | {_fmt_money(row['fair_value_per_share'])} | {_fmt_pct(row['margin_of_safety'])} | {float(row['confidence'] or 0):.2f} |")
    lines.extend(["", "## Score por dimensao", "| Dimensao | Score | Confianca | Explicacao |", "|---|---:|---:|---|"])
    for row in score_table(score):
        lines.append(f"| {row['name']} | {float(row['score']):.2f} | {float(row['confidence']):.2f} | {str(row['explanation']).replace('|', '/')} |")
    lines.extend(["", "## Diagnostico de riscos"])
    lines.extend(f"- {risk}" for risk in risk_diagnostics(score, valuations))
    lines.extend(["", "## Recomendacao final", f"**{score.recommendation}**"])
    return "\n".join(lines)


def recommendation_summary(score: ScoreReport) -> str:
    best = max(score.dimensions.values(), key=lambda d: d.score)
    worst = min(score.dimensions.values(), key=lambda d: d.score)
    return f"A acao ficou como {score.recommendation}. A melhor dimensao foi {best.name} ({best.score:.2f}) e o principal ponto de atencao foi {worst.name} ({worst.score:.2f})."


def _fmt_money(value: object) -> str:
    try:
        return "-" if value is None else f"${float(value):,.2f}"
    except Exception:
        return "-"


def _fmt_pct(value: object) -> str:
    try:
        return "-" if value is None else f"{float(value) * 100:,.2f}%"
    except Exception:
        return "-"
