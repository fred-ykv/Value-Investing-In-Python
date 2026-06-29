"""Human-readable final outputs."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
from typing import Iterable

from .comparables import ComparableReport
from .config import GROWTH_TECH, SCORE
from .data_sources import MetricValue
from .peer_selection import PeerSelectionReport
from .scenarios import ScenarioResult
from .scoring import ScoreReport
from .valuation import ValuationResult


VALUATION_METHOD_LABELS = {
    "dcf_fcff": (
        "Fluxo de Caixa Descontado (DCF/FCFF)",
        "Estima o valor da empresa descontando o fluxo de caixa livre para a firma.",
    ),
    "graham": (
        "Valor Intrinseco de Graham",
        "Modelo conservador que combina lucro por acao e valor patrimonial por acao.",
    ),
    "eva": (
        "Valor Economico Agregado (EVA)",
        "Avalia se o retorno sobre o capital supera o custo de capital.",
    ),
    "residual_income": (
        "Lucro Residual para Bancos",
        "Modelo usado em financeiras, comparando ROE, custo de capital e valor patrimonial.",
    ),
    "ddm": (
        "Modelo de Dividendos (DDM)",
        "Estima valor a partir de dividendos esperados e custo de capital.",
    ),
    "growth_tech": (
        "Modelo Growth/Tech",
        "Valoriza empresas de crescimento por receita, margem futura e caixa liquido.",
    ),
}


def valuation_table(valuations: Iterable[ValuationResult]) -> list[dict[str, object]]:
    rows = []
    for valuation in valuations:
        label, description = valuation_method_label(valuation.method)
        rows.append(
            {
                "method": valuation.method,
                "display_method": label,
                "method_description": description,
                "fair_value_per_share": valuation.fair_value_per_share,
                "margin_of_safety": valuation.margin_of_safety,
                "confidence": valuation.confidence,
                "source": valuation.source,
                "diagnostics": valuation.diagnostics,
            }
        )
    return rows


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
            "peer_count": metric.peer_count,
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
                "evidence_weight": result.evidence_weight,
                "data_confidence": result.data_confidence,
                "metric_sources": "; ".join(f"{key}:{value}" for key, value in sorted(result.metric_sources.items())),
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


def current_price_summary(metrics: dict[str, MetricValue] | None = None) -> dict[str, object]:
    metric = (metrics or {}).get("price")
    return {
        "indicator": "Preco atual da acao",
        "value": metric.value if metric else None,
        "source": metric.source if metric else "missing",
        "confidence": metric.confidence if metric else 0.0,
    }


def key_indicator_table(metrics: dict[str, MetricValue] | None = None) -> list[dict[str, object]]:
    metrics = metrics or {}
    price = metric_number(metrics.get("price"))
    shares = metric_number(metrics.get("shares"))
    market_cap = metric_number(metrics.get("market_cap"))
    revenue = metric_number(metrics.get("revenue"))
    ebit = metric_number(metrics.get("ebit"))
    net_income = metric_number(metrics.get("net_income"))
    equity = metric_number(metrics.get("equity"))
    assets = metric_number(metrics.get("total_assets"))
    liabilities = metric_number(metrics.get("total_liabilities"))
    cash = metric_number(metrics.get("cash"))
    debt = metric_number(metrics.get("total_debt"))
    current_assets = metric_number(metrics.get("current_assets"))
    current_liabilities = metric_number(metrics.get("current_liabilities"))
    depreciation = metric_number(metrics.get("depreciation_amortization"))
    bvps = metric_number(metrics.get("book_value_per_share"))
    ebitda = None if ebit is None else ebit + (depreciation or 0.0)
    market_cap = market_cap if market_cap is not None else _safe_mul(price, shares)
    enterprise_value = None if market_cap is None else market_cap + (debt or 0.0) - (cash or 0.0)
    net_debt = None if debt is None and cash is None else (debt or 0.0) - (cash or 0.0)
    working_capital = None if current_assets is None or current_liabilities is None else current_assets - current_liabilities
    ncav = None if current_assets is None or liabilities is None else current_assets - liabilities
    eps = _safe_div(net_income, shares)
    revenue_per_share = _safe_div(revenue, shares)
    dividend_per_share = metric_number(metrics.get("dividend_per_share"))
    gross_margin = metric_number(metrics.get("gross_margin"))
    rows = [
        _indicator_row("Valuation", "D.Y", _safe_div(dividend_per_share, price), metrics, ("dividend_per_share", "price"), "Dividend yield: dividendos anuais por acao divididos pelo preco atual.", "percent"),
        _indicator_row("Valuation", "P/L", _safe_div(price, eps), metrics, ("price", "net_income", "shares"), "Preco dividido pelo lucro por acao.", "number"),
        _indicator_row("Valuation", "PEG Ratio", _safe_div(_safe_div(price, eps), _percent_points(metrics.get("revenue_growth"))), metrics, ("price", "net_income", "shares", "revenue_growth"), "P/L dividido pelo crescimento esperado; menor tende a indicar preco mais razoavel para o crescimento.", "number"),
        _indicator_row("Valuation", "P/VP", _safe_div(price, bvps), metrics, ("price", "book_value_per_share"), "Preco dividido pelo valor patrimonial por acao.", "number"),
        _indicator_row("Valuation", "EV/EBITDA", _safe_div(enterprise_value, ebitda), metrics, ("market_cap", "total_debt", "cash", "ebit", "depreciation_amortization"), "Valor da firma dividido pelo EBITDA.", "number"),
        _indicator_row("Valuation", "EV/EBIT", _safe_div(enterprise_value, ebit), metrics, ("market_cap", "total_debt", "cash", "ebit"), "Valor da firma dividido pelo EBIT.", "number"),
        _indicator_row("Valuation", "P/EBITDA", _safe_div(market_cap, ebitda), metrics, ("market_cap", "ebit", "depreciation_amortization"), "Valor de mercado dividido pelo EBITDA.", "number"),
        _indicator_row("Valuation", "P/EBIT", _safe_div(market_cap, ebit), metrics, ("market_cap", "ebit"), "Valor de mercado dividido pelo EBIT.", "number"),
        _indicator_row("Valuation", "VPA", bvps, metrics, ("book_value_per_share",), "Valor patrimonial por acao.", "money"),
        _indicator_row("Valuation", "P/Ativo", _safe_div(market_cap, assets), metrics, ("market_cap", "total_assets"), "Valor de mercado dividido pelos ativos totais.", "number"),
        _indicator_row("Valuation", "LPA", eps, metrics, ("net_income", "shares"), "Lucro por acao.", "money"),
        _indicator_row("Valuation", "P/SR", _safe_div(price, revenue_per_share), metrics, ("price", "revenue", "shares"), "Preco dividido pela receita por acao.", "number"),
        _indicator_row("Valuation", "P/Cap. Giro", _safe_div(market_cap, working_capital), metrics, ("market_cap", "current_assets", "current_liabilities"), "Valor de mercado dividido pelo capital de giro.", "number"),
        _indicator_row("Valuation", "P/Ativo Circ. Liq.", _safe_div(market_cap, ncav), metrics, ("market_cap", "current_assets", "total_liabilities"), "Valor de mercado dividido pelo ativo circulante liquido.", "number"),
        _indicator_row("Endividamento", "Div. liquida/PL", _safe_div(net_debt, equity), metrics, ("total_debt", "cash", "equity"), "Divida liquida dividida pelo patrimonio liquido.", "number"),
        _indicator_row("Endividamento", "Div. liquida/EBITDA", _safe_div(net_debt, ebitda), metrics, ("total_debt", "cash", "ebit", "depreciation_amortization"), "Divida liquida dividida pelo EBITDA.", "number"),
        _indicator_row("Endividamento", "Div. liquida/EBIT", _safe_div(net_debt, ebit), metrics, ("total_debt", "cash", "ebit"), "Divida liquida dividida pelo EBIT.", "number"),
        _indicator_row("Endividamento", "PL/Ativos", _safe_div(equity, assets), metrics, ("equity", "total_assets"), "Patrimonio liquido dividido pelos ativos.", "percent"),
        _indicator_row("Endividamento", "Passivos/Ativos", _safe_div(liabilities, assets), metrics, ("total_liabilities", "total_assets"), "Passivos totais divididos pelos ativos.", "percent"),
        _indicator_row("Endividamento", "Liq. corrente", metric_number(metrics.get("current_ratio")), metrics, ("current_ratio",), "Ativos circulantes divididos por passivos circulantes.", "number"),
        _indicator_row("Eficiencia", "M. Bruta", gross_margin, metrics, ("gross_margin",), "Margem bruta informada ou calculada quando disponivel.", "percent"),
        _indicator_row("Eficiencia", "M. EBITDA", _safe_div(ebitda, revenue), metrics, ("ebit", "depreciation_amortization", "revenue"), "EBITDA dividido pela receita.", "percent"),
        _indicator_row("Eficiencia", "M. EBIT", metric_number(metrics.get("operating_margin")), metrics, ("operating_margin",), "EBIT dividido pela receita.", "percent"),
        _indicator_row("Eficiencia", "M. Liquida", metric_number(metrics.get("net_margin")), metrics, ("net_margin",), "Lucro liquido dividido pela receita.", "percent"),
        _indicator_row("Rentabilidade", "ROE", metric_number(metrics.get("roe")), metrics, ("roe",), "Lucro liquido dividido pelo patrimonio liquido.", "percent"),
        _indicator_row("Rentabilidade", "ROA", metric_number(metrics.get("roa")), metrics, ("roa",), "Lucro liquido dividido pelos ativos.", "percent"),
        _indicator_row("Rentabilidade", "ROIC", metric_number(metrics.get("roic_proxy")), metrics, ("roic_proxy",), "Proxy de ROIC: EBIT dividido por capital investido simplificado.", "percent"),
        _indicator_row("Rentabilidade", "Giro ativos", _safe_div(revenue, assets), metrics, ("revenue", "total_assets"), "Receita dividida pelos ativos.", "number"),
        _indicator_row("Crescimento", "CAGR Receitas 5 anos", metric_number(metrics.get("revenue_cagr_5y")), metrics, ("revenue_cagr_5y",), "Crescimento anual composto da receita em 5 anos, quando informado.", "percent"),
        _indicator_row("Crescimento", "CAGR Lucros 5 anos", metric_number(metrics.get("earnings_cagr_5y")), metrics, ("earnings_cagr_5y",), "Crescimento anual composto do lucro em 5 anos, quando informado.", "percent"),
    ]
    return rows


def executive_summary(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult]) -> str:
    available = [v.method for v in valuations if v.fair_value_per_share is not None]
    methods = ", ".join(valuation_method_label(method)[0] for method in available) or "nenhum modelo conclusivo"
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
        "## Ponte para decisao",
        *[f"- {item}" for item in decision_bridge(score, valuations)],
        "",
        "## Preco atual e Indicadores principais",
        f"Preco atual da acao: **{_fmt_money(current_price_summary(metrics)['value'])}**.",
        "",
        "| Grupo | Indicador | Valor | Fonte | Confianca | Leitura |",
        "|---|---|---:|---|---:|---|",
    ]
    for row in key_indicator_table(metrics):
        lines.append(f"| {row['group']} | {row['indicator']} | {_fmt_indicator(row)} | {row['source']} | {float(row['confidence'] or 0):.2f} | {str(row['explanation']).replace('|', '/')} |")
    lines.extend(
        [
            "",
            "## Valuation por metodo",
            "| Metodo | Preco justo | Margem de seguranca | Fonte | Confianca |",
            "|---|---:|---:|---|---:|",
        ]
    )
    for row in valuation_table(valuations):
        lines.append(f"| {row['display_method']} | {_fmt_money(row['fair_value_per_share'])} | {_fmt_pct(row['margin_of_safety'])} | {row['source']} | {float(row['confidence'] or 0):.2f} |")
    if scenarios:
        lines.extend(["", "## Cenarios hipoteticos", "| Cenario | Preco justo medio | Margem de seguranca | Confianca | Premissas-chave |", "|---|---:|---:|---:|---|"])
        for row in scenario_table(scenarios):
            assumptions = row["assumptions"]
            lines.append(
                f"| {row['scenario']} | {_fmt_money(row['fair_value_per_share'])} | {_fmt_pct(row['margin_of_safety'])} | "
                f"{float(row['confidence'] or 0):.2f} | {scenario_assumption_text(assumptions)} |"
            )
    if peer_selection and (peer_selection.approved or peer_selection.rejected):
        lines.extend(["", "## Selecao assistida de pares", peer_selection.summary, "", "| Ticker | Status | Score | Confianca dados | Fontes | Motivos | Vetos |", "|---|---|---:|---:|---|---|---|"])
        for row in peer_selection_table(peer_selection):
            lines.append(
                f"| {row['ticker']} | {row['status']} | {float(row['score'] or 0):.2f} | {float(row['data_confidence'] or 0):.2f} | "
                f"{str(row['metric_sources']).replace('|', '/')} | "
                f"{str(row['reasons']).replace('|', '/')} | {str(row['vetoes']).replace('|', '/')} |"
            )
    if comparables:
        lines.extend(["", "## Comparaveis de mercado", comparables.summary, "", "| Multiplo | Empresa | Mediana pares | N pares | Premio/desconto | Score | Fonte | Leitura |", "|---|---:|---:|---:|---:|---:|---|---|"])
        for row in comparable_table(comparables):
            lines.append(
                f"| {row['metric']} | {_fmt_number(row['company_value'])} | {_fmt_number(row['peer_median'])} | {int(row['peer_count'] or 0)} | "
                f"{_fmt_pct(row['premium_discount'])} | {float(row['score'] or 0):.2f} | {row['source']} | {str(row['interpretation']).replace('|', '/')} |"
            )
    lines.extend(["", "## Score por dimensao", score_scale_note(), "", "| Dimensao | Score | Confianca | Explicacao |", "|---|---:|---:|---|"])
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


def save_report_artifacts(ticker: str, report: dict[str, object], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    prefix = _safe_filename(ticker)
    artifacts = {
        "markdown": output_path / f"{prefix}_analysis.md",
        "html": output_path / f"{prefix}_analysis.html",
        "tables_json": output_path / f"{prefix}_tables.json",
    }
    artifacts["markdown"].write_text(str(report.get("markdown", "")), encoding="utf-8")
    artifacts["html"].write_text(str(report.get("html", "")), encoding="utf-8")
    table_payload = {
        key: report.get(key)
        for key in (
            "executive_summary",
            "recommendation",
            "valuation_table",
            "scenario_table",
            "peer_selection_table",
            "comparable_table",
            "score_table",
            "metric_lineage_table",
            "risk_diagnostics",
            "key_indicator_table",
        )
    }
    artifacts["tables_json"].write_text(json.dumps(table_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {name: str(path) for name, path in artifacts.items()}


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


def decision_bridge(score: ScoreReport, valuations: Iterable[ValuationResult] | None = None) -> list[str]:
    dimensions = list(score.dimensions.values())
    if not dimensions:
        return ["Nao ha dimensoes suficientes para explicar a recomendacao."]
    strongest = max(dimensions, key=lambda dimension: dimension.score)
    weakest = min(dimensions, key=lambda dimension: dimension.score)
    bridge = [
        f"Principal motor positivo: {strongest.name} com score {strongest.score:.2f}; este fator sustentou a recomendacao.",
        f"Principal gargalo: {weakest.name} com score {weakest.score:.2f}; este e o primeiro ponto a validar antes de aumentar exposicao.",
    ]
    gate = recommendation_gate_note(score)
    if gate:
        bridge.append(f"Para virar Comprar, a analise precisa primeiro resolver a trava indicada: {gate}")
    elif score.recommendation == "Comprar":
        bridge.append("A recomendacao de Comprar depende de manutencao simultanea de valuation aceitavel, qualidade operacional e confianca dos dados; perda relevante em qualquer um desses pilares deve rebaixar a leitura para Observar.")
    elif score.recommendation == "Observar":
        bridge.append(f"Para virar Comprar, o score total precisa superar {SCORE.buy_threshold:.2f} com valuation acima de {SCORE.min_valuation_score_for_buy:.2f}; enquanto isso nao ocorrer, a leitura correta e aguardar preco melhor, premissas melhores ou dados mais fortes.")
    else:
        bridge.append("Antes de reconsiderar a tese, o caso precisa sair da zona de risco combinando melhora de valuation, qualidade dos fundamentos e confianca das fontes.")

    valuation_list = [valuation for valuation in list(valuations or []) if valuation.margin_of_safety is not None]
    if valuation_list:
        average_margin = sum(float(valuation.margin_of_safety or 0.0) for valuation in valuation_list) / len(valuation_list)
        if average_margin < 0:
            bridge.append(f"A margem de seguranca media ficou negativa ({_fmt_pct(average_margin)}), sinalizando que o preco atual ainda exige desconto ou premissas mais favoraveis.")
        else:
            bridge.append(f"A margem de seguranca media ficou positiva ({_fmt_pct(average_margin)}), mas deve ser confirmada contra qualidade, crescimento e riscos setoriais.")
    else:
        bridge.append("Como nao houve margem de seguranca conclusiva, a decisao deve dar peso maior a qualidade dos dados, liquidez e consistencia dos fundamentos.")
    return bridge


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
        f"o metodo mais favoravel foi {valuation_method_label(best.method)[0]} ({_fmt_pct(best.margin_of_safety)}) "
        f"e o mais conservador foi {valuation_method_label(worst.method)[0]} ({_fmt_pct(worst.margin_of_safety)})."
    )


def explanatory_notes(score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None) -> list[str]:
    notes = [
        score_scale_note(),
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


def score_scale_note() -> str:
    return "Escala do score: quanto mais perto de 1, melhor a leitura daquela dimensao; quanto mais perto de 0, pior ou mais arriscada."


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


def valuation_method_label(method: str) -> tuple[str, str]:
    return VALUATION_METHOD_LABELS.get(method, (method.replace("_", " ").title(), "Metodo de valuation calculado pelo modelo."))


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


def _fmt_indicator(row: dict[str, object]) -> str:
    kind = row.get("format")
    value = row.get("value")
    if kind == "percent":
        return _fmt_pct(value)
    if kind == "money":
        return _fmt_money(value)
    return _fmt_number(value)


def _safe_filename(ticker: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", ticker.strip().upper())
    return safe.strip("._-") or "ANALYSIS"


def _safe_div(num: float | None, den: float | None) -> float | None:
    return None if num is None or den in (None, 0) else num / den


def _safe_mul(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else left * right


def _percent_points(metric: MetricValue | None) -> float | None:
    value = metric_number(metric)
    return None if value is None else value * 100.0


def _indicator_row(group: str, indicator: str, value: float | None, metrics: dict[str, MetricValue], dependencies: tuple[str, ...], explanation: str, fmt: str) -> dict[str, object]:
    used = [metrics[name] for name in dependencies if name in metrics and metrics[name].is_available]
    source = ", ".join(sorted({metric.source for metric in used})) if used else "missing"
    confidence = sum(metric.confidence for metric in used) / len(used) if used else 0.0
    return {
        "group": group,
        "indicator": indicator,
        "value": value,
        "source": source,
        "confidence": confidence if value is not None else 0.0,
        "explanation": explanation,
        "format": fmt,
    }
