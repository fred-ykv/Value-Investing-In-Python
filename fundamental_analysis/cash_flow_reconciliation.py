"""Reconcile unlevered FCFF with the levered CFO-minus-capex proxy."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import escape
from typing import Mapping

from .config import CASH_FLOW_RECONCILIATION
from .data_sources import MetricValue, clamp


@dataclass(frozen=True)
class CashFlowReconciliation:
    fcff: float | None
    cfo_after_capex: float | None
    difference: float | None
    relative_gap: float | None
    status: str
    status_label: str
    confidence: float
    currency: str | None
    period_end: date | None
    periods_aligned: bool | None
    currencies_aligned: bool | None
    summary: str
    explanation: str
    sources: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        return asdict(self)


def reconcile_cash_flows(values: Mapping[str, MetricValue]) -> CashFlowReconciliation:
    fcff = values.get("fcff", MetricValue("fcff", None, "missing", 0.0))
    proxy = values.get("free_cash_flow_after_capex", MetricValue("free_cash_flow_after_capex", None, "missing", 0.0))
    sources = tuple(dict.fromkeys(_source_label(item) for item in (fcff, proxy) if item.is_available))
    currency, currencies_aligned = _shared_attribute(fcff, proxy, "currency")
    period_end, periods_aligned = _shared_attribute(fcff, proxy, "period_end")
    explanation = (
        "FCFF mede o caixa operacional antes do financiamento e e descontado pelo WACC. "
        "CFO menos Capex e uma proxy alavancada, pois o CFO normalmente ja reflete juros e outras classificacoes contabeis."
    )
    if not fcff.is_available or not proxy.is_available:
        missing = "FCFF" if not fcff.is_available else "CFO menos Capex"
        return CashFlowReconciliation(
            fcff.value,
            proxy.value,
            None,
            None,
            "indisponivel",
            "Incompleta",
            0.0,
            currency,
            period_end,
            periods_aligned,
            currencies_aligned,
            f"A reconciliacao ficou incompleta porque {missing} nao esta disponivel.",
            explanation,
            sources,
        )

    difference = float(fcff.value) - float(proxy.value)
    denominator = max(abs(float(fcff.value)), abs(float(proxy.value)))
    relative_gap = 0.0 if denominator == 0 else abs(difference) / denominator
    opposite_signs = float(fcff.value) * float(proxy.value) < 0
    if opposite_signs:
        status, label = "sinais_opostos", "Atencao alta"
        summary = (
            f"Os fluxos apresentam sinais opostos e diferenca relativa de {relative_gap:.1%}. "
            "A tese deve explicar juros, impostos, capital de giro e itens nao caixa antes de confiar no DCF."
        )
    elif relative_gap <= CASH_FLOW_RECONCILIATION.close_gap_ratio:
        status, label = "proximos", "Coerente"
        summary = f"FCFF e CFO menos Capex ficaram proximos, com diferenca relativa de {relative_gap:.1%}."
    elif relative_gap <= CASH_FLOW_RECONCILIATION.moderate_gap_ratio:
        status, label = "divergencia_moderada", "Revisar"
        summary = f"Os fluxos divergem {relative_gap:.1%}; a diferenca e material e merece reconciliacao das demonstracoes."
    else:
        status, label = "divergencia_relevante", "Atencao alta"
        summary = f"Os fluxos divergem {relative_gap:.1%}; o DCF fica sensivel a classificacoes e ajustes contabeis."

    confidence = (fcff.confidence + proxy.confidence) / 2.0
    notes: list[str] = []
    if periods_aligned is False:
        confidence -= 0.20
        notes.append("Os fluxos nao pertencem ao mesmo periodo.")
    if currencies_aligned is False:
        confidence -= 0.30
        notes.append("Os fluxos nao usam a mesma moeda.")
    if notes:
        summary += " " + " ".join(notes)
    return CashFlowReconciliation(
        float(fcff.value),
        float(proxy.value),
        difference,
        relative_gap,
        status,
        label,
        clamp(confidence, 0.0, 1.0),
        currency,
        period_end,
        periods_aligned,
        currencies_aligned,
        summary,
        explanation,
        sources,
    )


def append_cash_flow_reconciliation_to_markdown(markdown: str, result: CashFlowReconciliation) -> str:
    lines = [
        "",
        "## Reconciliacao dos fluxos de caixa",
        result.summary,
        "",
        "| Medida | Valor | Papel no modelo |",
        "|---|---:|---|",
        f"| FCFF (nao alavancado) | {_fmt_money(result.fcff, result.currency)} | Fluxo usado no DCF e descontado pelo WACC. |",
        f"| CFO menos Capex | {_fmt_money(result.cfo_after_capex, result.currency)} | Proxy alavancada usada como controle de consistencia. |",
        f"| Diferenca (FCFF - proxy) | {_fmt_money(result.difference, result.currency)} | Diferenca a investigar; nao representa erro automaticamente. |",
        "",
        f"**Leitura:** {result.status_label}. {result.explanation}",
    ]
    if result.sources:
        lines.append(f"**Fontes:** {'; '.join(result.sources)}.")
    block = "\n".join(lines)
    marker = "\n## Taxa de desconto utilizada"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    marker = "\n## Cenarios hipoteticos"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    return markdown + block


def append_cash_flow_reconciliation_to_html(html: str, result: CashFlowReconciliation) -> str:
    source_note = f"<p><small>Fontes: {escape('; '.join(result.sources))}</small></p>" if result.sources else ""
    section = (
        '<section class="panel cash-flow-reconciliation">'
        "<h2>Reconciliacao dos fluxos de caixa</h2>"
        f"<p><strong>{escape(result.status_label)}.</strong> {escape(result.summary)}</p>"
        "<table><thead><tr><th>Medida</th><th>Valor</th><th>Papel no modelo</th></tr></thead><tbody>"
        f"<tr><td>FCFF (nao alavancado)</td><td>{escape(_fmt_money(result.fcff, result.currency))}</td><td>Fluxo usado no DCF e descontado pelo WACC.</td></tr>"
        f"<tr><td>CFO menos Capex</td><td>{escape(_fmt_money(result.cfo_after_capex, result.currency))}</td><td>Proxy alavancada usada como controle de consistencia.</td></tr>"
        f"<tr><td>Diferenca (FCFF - proxy)</td><td>{escape(_fmt_money(result.difference, result.currency))}</td><td>Diferenca a investigar; nao representa erro automaticamente.</td></tr>"
        "</tbody></table>"
        f"<p>{escape(result.explanation)}</p>{source_note}</section>"
    )
    marker = '<section class="panel cost-of-capital">'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    marker = '<section class="panel">\n<h2>Cenarios</h2>'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    return html.replace("</main>", section + "\n</main>", 1)


def _source_label(metric: MetricValue) -> str:
    return metric.source_document or metric.source


def _shared_attribute(left: MetricValue, right: MetricValue, name: str):
    values = [getattr(item, name) for item in (left, right) if item.is_available and getattr(item, name) is not None]
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], None
    return (values[0], True) if values[0] == values[1] else (None, False)


def _fmt_money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "-"
    prefix = "US$" if not currency or currency.upper() == "USD" else currency.upper()
    return f"{prefix} {value:,.2f}"

