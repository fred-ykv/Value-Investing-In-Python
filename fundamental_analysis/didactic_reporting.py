"""Beginner-friendly report presentation layer."""
from __future__ import annotations

from html import escape
import re

from .data_sources import MetricValue
from .executive_reporting import apply_executive_layer_to_html, apply_executive_layer_to_markdown
from .scoring import ScoreReport
from .valuation import ValuationResult


DISPLAY_LABELS = {
    "total_assets": "Ativos Totais",
    "total_liabilities": "Passivos Totais",
    "current_assets": "Ativos Circulantes",
    "current_liabilities": "Passivos Circulantes",
    "net_income": "Lucro Liquido",
    "revenue": "Receita",
    "ebit": "EBIT",
    "cfo": "Fluxo de Caixa Operacional",
    "capex": "CAPEX",
    "fcff": "Fluxo de Caixa Livre para a Firma",
    "free_cash_flow_after_capex": "Fluxo de Caixa Livre apos CAPEX",
    "market_cap": "Valor de Mercado",
    "shares": "Numero de Acoes",
    "price": "Preco Atual",
    "cash": "Caixa",
    "cash_burn": "Queima de Caixa",
    "cash_runway_years": "Runway de Caixa",
    "total_debt": "Divida Total",
    "equity": "Patrimonio Liquido",
    "depreciation_amortization": "Depreciacao e Amortizacao",
    "change_in_nwc": "Variacao do Capital de Giro",
    "book_value_per_share": "Valor Patrimonial por Acao",
    "cfo_to_net_income": "Caixa Operacional / Lucro Liquido",
    "earnings_quality": "Qualidade do Lucro",
    "fcff_yield": "FCFF Yield",
    "interest_expense": "Despesa com Juros",
    "net_debt_to_ebit": "Divida Liquida / EBIT",
    "ncav_per_share": "NCAV por Acao",
    "piotroski_proxy": "Piotroski aproximado",
    "tax_provision": "Imposto sobre Lucro",
    "tax_rate": "Aliquota de Imposto",
    "roa": "ROA",
    "roe": "ROE",
    "price_to_earnings": "P/L",
    "price_to_book": "P/VP",
    "price_to_sales": "P/Receita",
    "ev_to_sales": "EV/Receita",
    "ev_to_ebitda": "EV/EBITDA",
    "ev_to_ebit": "EV/EBIT",
    "current_ratio": "Liquidez Corrente",
    "debt_to_equity": "Divida/Patrimonio",
    "operating_margin": "Margem Operacional",
    "net_margin": "Margem Liquida",
    "roic_proxy": "ROIC aproximado",
    "revenue_growth": "Crescimento da Receita",
    "data_confidence": "Confianca dos Dados",
    "valuation": "Valuation",
    "growth": "Crescimento",
    "quality": "Qualidade",
    "debt": "Divida",
    "liquidity": "Liquidez",
    "dcf_fcff": "Fluxo de Caixa Descontado (DCF/FCFF)",
    "growth_tech": "Modelo Growth/Tech",
    "residual_income": "Lucro Residual",
}

DIMENSION_EXPLANATIONS = {
    "valuation": "mede se o preco parece caro ou barato contra valor justo e pares.",
    "growth": "mede a velocidade de crescimento da empresa.",
    "quality": "mede margens, retorno sobre capital e qualidade do lucro.",
    "debt": "mede se a divida parece confortavel ou perigosa.",
    "liquidity": "mede a folga de caixa e capital de giro.",
    "data_confidence": "mede se os dados usados parecem completos e confiaveis.",
}


def apply_didactic_layer_to_markdown(markdown: str, score: ScoreReport, metrics: dict[str, MetricValue], valuations: list[ValuationResult]) -> str:
    translated = humanize_report_text(markdown)
    translated = apply_executive_layer_to_markdown(translated, score, valuations)
    block = _didactic_markdown(score, metrics, valuations)
    marker = "\n## Tese da recomendacao"
    if marker in translated:
        translated = translated.replace(marker, f"\n{block}{marker}", 1)
    else:
        translated = f"{translated}\n\n{block}"
    return humanize_report_text(translated)


def apply_didactic_layer_to_html(html: str, score: ScoreReport, metrics: dict[str, MetricValue], valuations: list[ValuationResult]) -> str:
    translated = humanize_report_text(html)
    translated = apply_executive_layer_to_html(translated, score, valuations)
    block = _didactic_html(score, metrics, valuations)
    marker = "</header>"
    if marker in translated:
        translated = translated.replace(marker, f"{marker}\n{block}", 1)
    else:
        translated = f"{block}\n{translated}"
    return humanize_report_text(translated)


def didactic_summary_table(score: ScoreReport, metrics: dict[str, MetricValue], valuations: list[ValuationResult]) -> list[dict[str, object]]:
    return [
        {"item": "Recomendacao", "value": score.recommendation, "reading": _recommendation_reading(score.recommendation)},
        {"item": "Score Total", "value": round(score.total_score * 100), "reading": "Quanto mais perto de 100, melhor."},
        {"item": "Preco Atual", "value": _money(_metric_number(metrics.get("price"))), "reading": "Preco usado como base para valuation e margem de seguranca."},
        {"item": "Margem de Seguranca Media", "value": _pct(_average_margin(valuations)), "reading": "Folga estimada entre valor justo e preco atual."},
        {"item": "Confianca dos Dados", "value": _score_pct(_dimension_score(score, "data_confidence")), "reading": "Qualidade e disponibilidade das fontes usadas."},
    ]


def humanize_report_text(text: str) -> str:
    output = _normalize_usd(text)
    for raw, label in sorted(DISPLAY_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        output = re.sub(rf"\b{re.escape(raw)}\b", label, output)
    return output


def _didactic_markdown(score: ScoreReport, metrics: dict[str, MetricValue], valuations: list[ValuationResult]) -> str:
    rows = didactic_summary_table(score, metrics, valuations)
    strongest, weakest = _dimension_extremes(score)
    lines = [
        "## Leitura rapida para iniciantes",
        "",
        "Esta secao traduz o resultado para uma primeira leitura. Ela nao substitui a auditoria das fontes nem a revisao das premissas.",
        "",
        "| Item | Resultado | Como ler |",
        "| --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['item']} | {row['value']} | {row['reading']} |")
    lines.extend(
        [
            "",
            "### O que olhar primeiro",
            "",
            f"- Ponto mais forte: **{strongest[0]}** com leitura de **{strongest[1]}**.",
            f"- Principal ponto de atencao: **{weakest[0]}** com leitura de **{weakest[1]}**.",
            f"- Score: **{round(score.total_score * 100)}/100**. Quanto mais perto de 100, melhor; abaixo de 50 exige cautela.",
            f"- Preco atual usado: **{_money(_metric_number(metrics.get('price')))}**.",
            f"- Margem de seguranca media: **{_pct(_average_margin(valuations))}**.",
            "",
            "### Guia rapido dos pilares",
            "",
        ]
    )
    for name, explanation in DIMENSION_EXPLANATIONS.items():
        value = _dimension_score(score, name)
        lines.append(f"- **{DISPLAY_LABELS.get(name, name)}**: {_score_pct(value)}; {explanation}")
    return "\n".join(lines)


def _didactic_html(score: ScoreReport, metrics: dict[str, MetricValue], valuations: list[ValuationResult]) -> str:
    rows = didactic_summary_table(score, metrics, valuations)
    strongest, weakest = _dimension_extremes(score)
    cards = "\n".join(
        [
            (
                '<article class="card">'
                f"<span>{escape(str(row['item']))}</span>"
                f"<strong>{escape(str(row['value']))}</strong>"
                f"<span>{escape(str(row['reading']))}</span>"
                "</article>"
            )
            for row in rows
        ]
    )
    pillars = "\n".join(
        f"<li><strong>{escape(DISPLAY_LABELS.get(name, name))}:</strong> {escape(_score_pct(_dimension_score(score, name)))}; {escape(text)}</li>"
        for name, text in DIMENSION_EXPLANATIONS.items()
    )
    return "\n".join(
        [
            '<section class="panel didactic-summary">',
            "<h2>Leitura rapida para iniciantes</h2>",
            "<p>Esta secao traduz o resultado para uma primeira leitura. Ela nao substitui a auditoria das fontes nem a revisao das premissas.</p>",
            '<div class="cards">',
            cards,
            "</div>",
            "<h3>O que olhar primeiro</h3>",
            "<ul>",
            f"<li>Ponto mais forte: <strong>{escape(strongest[0])}</strong> com leitura de <strong>{escape(strongest[1])}</strong>.</li>",
            f"<li>Principal ponto de atencao: <strong>{escape(weakest[0])}</strong> com leitura de <strong>{escape(weakest[1])}</strong>.</li>",
            f"<li>Score: <strong>{round(score.total_score * 100)}/100</strong>. Quanto mais perto de 100, melhor; abaixo de 50 exige cautela.</li>",
            f"<li>Preco atual usado: <strong>{escape(_money(_metric_number(metrics.get('price'))))}</strong>.</li>",
            f"<li>Margem de seguranca media: <strong>{escape(_pct(_average_margin(valuations)))}</strong>.</li>",
            "</ul>",
            "<h3>Guia rapido dos pilares</h3>",
            "<ul>",
            pillars,
            "</ul>",
            "</section>",
        ]
    )


def _dimension_extremes(score: ScoreReport) -> tuple[tuple[str, str], tuple[str, str]]:
    if not score.dimensions:
        return ("Sem dimensoes", "-"), ("Sem dimensoes", "-")
    strongest = max(score.dimensions.values(), key=lambda item: item.score)
    weakest = min(score.dimensions.values(), key=lambda item: item.score)
    return (
        (DISPLAY_LABELS.get(strongest.name, strongest.name), _score_pct(strongest.score)),
        (DISPLAY_LABELS.get(weakest.name, weakest.name), _score_pct(weakest.score)),
    )


def _dimension_score(score: ScoreReport, name: str) -> float | None:
    dimension = score.dimensions.get(name)
    return None if dimension is None else dimension.score


def _recommendation_reading(recommendation: str) -> str:
    readings = {
        "Comprar": "A leitura combinada esta favoravel, respeitando riscos e premissas.",
        "Observar": "A tese tem pontos positivos, mas ainda precisa de preco melhor, dados melhores ou menor risco.",
        "Evitar": "A relacao entre preco, fundamentos e risco nao esta atraente.",
    }
    return readings.get(recommendation, "Leitura final do modelo.")


def _average_margin(valuations: list[ValuationResult]) -> float | None:
    margins = [float(item.margin_of_safety) for item in valuations if item.margin_of_safety is not None]
    return sum(margins) / len(margins) if margins else None


def _metric_number(metric: MetricValue | None) -> float | None:
    if metric is None or metric.value is None:
        return None
    try:
        return float(metric.value)
    except Exception:
        return None


def _money(value: float | None) -> str:
    return "-" if value is None else f"US$ {value:,.2f}"


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:,.2f}%"


def _score_pct(value: float | None) -> str:
    return "-" if value is None else f"{round(value * 100)}/100"


def _normalize_usd(text: str) -> str:
    return re.sub(r"(?<!US)\$(?=\d)", "US$ ", text)
