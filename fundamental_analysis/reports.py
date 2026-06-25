"""Human-readable final outputs."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .comparables import ComparableReport
from .config import GROWTH_TECH, SCORE
from .data_sources import MetricValue
from .peer_selection import PeerSelectionReport
from .scenarios import ScenarioResult
from .scoring import ScoreReport
from .valuation import ValuationResult


def valuation_table(valuations: Iterable[ValuationResult]) -> list[dict[str, object]]:
    return [{"method": v.method, "fair_value_per_share": v.fair_value_per_share, "margin_of_safety": v.margin_of_safety, "confidence": v.confidence, "source": v.source, "diagnostics": v.diagnostics} for v in valuations]


def scenario_table(scenarios: Iterable[ScenarioResult]) -> list[dict[str, object]]:
    return [
        {
            "scenario": scenario.label,
            "fair_value_per_share": scenario.fair_value_per_share,
            "margin_of_safety": scenario.margin_of_safety,
            "confidence": scenario.confidence,
            "assumptions": scenario.assumptions,
            "description": scenario.description,
        }
        for scenario in scenarios
    ]


def comparable_table(comparables: ComparableReport) -> list[dict[str, object]]:
    return [
        {
            "metric": metric.name,
            "company_value": metric.company_value,
            "peer_median": metric.peer_median,
            "premium_discount": metric.premium_discount,
            "score": metric.score,
            "source": metric.source,
            "interpretation": metric.interpretation,
        }
        for metric in comparables.metrics
    ]


def peer_selection_table(peer_selection: PeerSelectionReport) -> list[dict[str, object]]:
    rows = []
    for result in peer_selection.approved + peer_selection.rejected:
        rows.append(
            {
                "ticker": result.ticker,
                "status": result.status,
                "score": result.score,
                "reasons": "; ".join(result.reasons),
                "vetoes": "; ".join(result.vetoes),
            }
        )
    return rows


def score_table(score: ScoreReport) -> list[dict[str, object]]:
    return [asdict(dimension) for dimension in score.dimensions.values()]


def metric_lineage_table(metrics: dict[str, MetricValue]) -> list[dict[str, object]]:
    rows = []
    for name in sorted(metrics):
        metric = metrics[name]
        rows.append({"metric": name, "value": metric.value, "source": metric.source, "confidence": metric.confidence, "note": metric.note})
    return rows


def executive_summary(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult]) -> str:
    available = [v.method for v in valuations if v.fair_value_per_share is not None]
    methods = ", ".join(available) or "nenhum modelo conclusivo"
    return f"{ticker.upper()} recebeu recomendacao **{score.recommendation}**. Score total: {score.total_score:.2f}. Modelos usados: {methods}."


def risk_diagnostics(score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None) -> list[str]:
    risks: list[str] = []
    if score.dimensions.get("data_confidence") and score.dimensions["data_confidence"].score < 0.50:
        risks.append("Baixa confianca dos dados; revise fontes antes de usar a recomendacao.")
    for valuation in valuations:
        if valuation.diagnostics.get("negative_fcff"):
            risks.append("DCF usa FCFF negativo; a confianca do modelo foi reduzida.")
        if valuation.diagnostics.get("terminal_growth_adjusted") is not None:
            risks.append("Crescimento terminal foi ajustado para ficar abaixo da taxa de desconto.")
    if metrics:
        runway = metric_number(metrics.get("cash_runway_years"))
        burn = metric_number(metrics.get("cash_burn"))
        if burn is not None and runway is not None and runway < GROWTH_TECH.min_cash_runway_years:
            risks.append(f"Runway de caixa estimado em {runway:.1f} anos, abaixo do minimo de {GROWTH_TECH.min_cash_runway_years:.1f} anos para growth/tech.")
    return risks or ["Nenhum risco critico detectado pela camada de validacao."]


def render_markdown_report(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None, scenarios: Iterable[ScenarioResult] | None = None, comparables: ComparableReport | None = None, peer_selection: PeerSelectionReport | None = None) -> str:
    valuations = list(valuations)
    scenarios = list(scenarios or [])
    lines = [
        f"# Fundamental Analysis - {ticker.upper()}",
        "",
        "## Resumo executivo",
        executive_summary(ticker, score, valuations),
        "",
        "## Tese da recomendacao",
        recommendation_summary(score, valuations),
        "",
        "## Valuation por metodo",
        "| Metodo | Preco justo | Margem de seguranca | Fonte | Confianca |",
        "|---|---:|---:|---|---:|",
    ]
    for row in valuation_table(valuations):
        lines.append(f"| {row['method']} | {_fmt_money(row['fair_value_per_share'])} | {_fmt_pct(row['margin_of_safety'])} | {row['source']} | {float(row['confidence'] or 0):.2f} |")
    if scenarios:
        lines.extend(["", "## Cenarios hipoteticos", "| Cenario | Preco justo medio | Margem de seguranca | Confianca | Premissas-chave |", "|---|---:|---:|---:|---|"])
        for row in scenario_table(scenarios):
            assumptions = row["assumptions"]
            lines.append(
                f"| {row['scenario']} | {_fmt_money(row['fair_value_per_share'])} | {_fmt_pct(row['margin_of_safety'])} | "
                f"{float(row['confidence'] or 0):.2f} | {scenario_assumption_text(assumptions)} |"
            )
    if peer_selection and (peer_selection.approved or peer_selection.rejected):
        lines.extend(["", "## Selecao assistida de pares", peer_selection.summary, "", "| Ticker | Status | Score | Motivos | Vetos |", "|---|---|---:|---|---|"])
        for row in peer_selection_table(peer_selection):
            lines.append(
                f"| {row['ticker']} | {row['status']} | {float(row['score'] or 0):.2f} | "
                f"{str(row['reasons']).replace('|', '/')} | {str(row['vetoes']).replace('|', '/')} |"
            )
    if comparables:
        lines.extend(["", "## Comparaveis de mercado", comparables.summary, "", "| Multiplo | Empresa | Mediana pares | Premio/desconto | Score | Fonte | Leitura |", "|---|---:|---:|---:|---:|---|---|"])
        for row in comparable_table(comparables):
            lines.append(
                f"| {row['metric']} | {_fmt_number(row['company_value'])} | {_fmt_number(row['peer_median'])} | "
                f"{_fmt_pct(row['premium_discount'])} | {float(row['score'] or 0):.2f} | {row['source']} | {str(row['interpretation']).replace('|', '/')} |"
            )
    lines.extend(["", "## Score por dimensao", "| Dimensao | Score | Confianca | Explicacao |", "|---|---:|---:|---|"])
    for row in score_table(score):
        lines.append(f"| {row['name']} | {float(row['score']):.2f} | {float(row['confidence']):.2f} | {str(row['explanation']).replace('|', '/')} |")
    if metrics:
        lines.extend(["", "## Fontes e confianca das metricas", "| Metrica | Valor usado | Fonte | Confianca | Observacao |", "|---|---:|---|---:|---|"])
        for row in metric_lineage_table(metrics):
            lines.append(f"| {row['metric']} | {_fmt_number(row['value'])} | {row['source']} | {float(row['confidence'] or 0):.2f} | {str(row['note']).replace('|', '/')} |")
    lines.extend(["", "## Diagnostico de riscos"])
    lines.extend(f"- {risk}" for risk in risk_diagnostics(score, valuations, metrics))
    lines.extend(["", "## Notas explicativas"])
    lines.extend(f"- {note}" for note in explanatory_notes(score, valuations, metrics))
    lines.extend(["", "## Recomendacao final", f"**{score.recommendation}**"])
    return "\n".join(lines)


def recommendation_summary(score: ScoreReport, valuations: Iterable[ValuationResult] | None = None) -> str:
    best = max(score.dimensions.values(), key=lambda d: d.score)
    worst = min(score.dimensions.values(), key=lambda d: d.score)
    lines = [
        f"A acao ficou como **{score.recommendation}** com score total de **{score.total_score:.2f}**.",
        f"O principal suporte da tese foi **{best.name}** ({best.score:.2f}); o maior ponto de atencao foi **{worst.name}** ({worst.score:.2f}).",
    ]
    gate = recommendation_gate_note(score)
    if gate:
        lines.append(gate)
    valuation_read = valuation_readthrough(list(valuations or []))
    if valuation_read:
        lines.append(valuation_read)
    return " ".join(lines)


def recommendation_gate_note(score: ScoreReport) -> str:
    valuation = score.dimensions.get("valuation")
    quality = score.dimensions.get("quality")
    valuation_score = valuation.score if valuation else 0.0
    quality_score = quality.score if quality else 0.0
    if score.total_score >= SCORE.buy_threshold and score.recommendation == "Observar" and valuation_score < SCORE.min_valuation_score_for_buy:
        return f"A recomendacao nao subiu para Comprar porque o score de valuation ({valuation_score:.2f}) ficou abaixo do minimo exigido ({SCORE.min_valuation_score_for_buy:.2f})."
    if score.recommendation == "Evitar" and valuation_score < SCORE.avoid_if_valuation_below and quality_score < SCORE.avoid_if_quality_below:
        return f"A recomendacao foi mantida em Evitar porque valuation ({valuation_score:.2f}) e qualidade ({quality_score:.2f}) ficaram simultaneamente abaixo dos limites de seguranca."
    return ""


def valuation_readthrough(valuations: Iterable[ValuationResult]) -> str:
    available = [v for v in valuations if v.margin_of_safety is not None]
    if not available:
        return "Os modelos de valuation nao produziram margem de seguranca conclusiva; a leitura deve priorizar qualidade dos dados e fundamentos."
    margins = [float(v.margin_of_safety or 0.0) for v in available]
    average_margin = sum(margins) / len(margins)
    best = max(available, key=lambda v: float(v.margin_of_safety or -999.0))
    worst = min(available, key=lambda v: float(v.margin_of_safety or 999.0))
    return (
        f"A margem de seguranca media dos modelos foi {_fmt_pct(average_margin)}; "
        f"o metodo mais favoravel foi {best.method} ({_fmt_pct(best.margin_of_safety)}) "
        f"e o mais conservador foi {worst.method} ({_fmt_pct(worst.margin_of_safety)})."
    )


def explanatory_notes(score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None) -> list[str]:
    notes = [
        "Comprar exige score total elevado e valuation minimamente aceitavel; qualidade sozinha nao deve compensar preco excessivo.",
        "Observar indica assimetria incompleta: a empresa pode ter bons fundamentos, mas ainda exige preco melhor, dados melhores ou reducao de riscos.",
        "Evitar indica baixa atratividade relativa, risco fundamental elevado ou combinacao fraca de valuation e qualidade.",
        "Margem de seguranca negativa significa que o preco justo estimado ficou abaixo do preco atual; quanto mais negativa, menor a atratividade pelo modelo.",
        "Confianca mede qualidade e disponibilidade das fontes usadas; nao e probabilidade de acerto nem recomendacao de investimento.",
    ]
    gate = recommendation_gate_note(score)
    if gate:
        notes.insert(0, gate)
    if any(v.diagnostics.get("negative_fcff") for v in valuations):
        notes.append("FCFF negativo reduz a confianca do DCF porque empresas nessa fase dependem mais de premissas de reversao, runway e margem futura.")
    if metrics:
        runway = metric_number(metrics.get("cash_runway_years"))
        burn = metric_number(metrics.get("cash_burn"))
        if burn is not None and runway is not None:
            notes.append(f"Cash runway compara caixa disponivel com queima anual estimada; neste caso, o runway estimado foi de {runway:.1f} anos.")
            if runway < GROWTH_TECH.min_cash_runway_years:
                notes.append(f"Runway abaixo de {GROWTH_TECH.min_cash_runway_years:.1f} anos reduz a leitura de liquidez para growth/tech, mesmo quando o current ratio parece forte.")
    if score.dimensions.get("data_confidence") and score.dimensions["data_confidence"].score < 0.60:
        notes.append("A confianca dos dados ficou abaixo de 0.60; revise demonstrativos e fontes antes de usar o resultado em decisao real.")
    return notes


def scenario_assumption_text(assumptions: object) -> str:
    if not isinstance(assumptions, dict):
        return "-"
    return (
        f"crescimento {_fmt_pct(assumptions.get('growth_years'))}; "
        f"desconto {_fmt_pct(assumptions.get('discount_rate'))}; "
        f"g terminal {_fmt_pct(assumptions.get('terminal_growth'))}; "
        f"ajuste FCFF {_fmt_pct(assumptions.get('fcff_adjustment'))}"
    )


def metric_number(metric: MetricValue | None) -> float | None:
    if metric is None or metric.value is None:
        return None
    try:
        return float(metric.value)
    except Exception:
        return None


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


def _fmt_number(value: object) -> str:
    try:
        return "-" if value is None else f"{float(value):,.4f}"
    except Exception:
        return "-"
