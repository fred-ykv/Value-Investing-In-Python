"""Audit whether the recommendation, scenarios and risks tell the same story."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
from typing import Iterable, Mapping


@dataclass(frozen=True)
class DecisionConsistencyAudit:
    recommendation: str
    scenario_status: str
    scenario_summary: str
    base_margin: float | None
    positive_scenario_count: int
    available_scenario_count: int
    critical_risk_count: int
    overall_status: str
    explanation: str
    warnings: tuple[str, ...] = ()

    def payload(self) -> dict[str, object]:
        return asdict(self)


def audit_decision_consistency(
    recommendation: str,
    scenarios: Iterable[object] | None,
    risks: Iterable[str] | None,
) -> DecisionConsistencyAudit:
    available = [
        item for item in (scenarios or ())
        if _number(getattr(item, "margin_of_safety", None)) is not None
    ]
    margins = [_number(getattr(item, "margin_of_safety", None)) for item in available]
    margins = [value for value in margins if value is not None]
    by_key = {str(getattr(item, "key", "")): _number(getattr(item, "margin_of_safety", None)) for item in available}
    base_margin = by_key.get("base")
    positive_count = sum(value >= 0 for value in margins)
    critical_risks = [str(risk) for risk in (risks or ()) if _is_critical(risk)]

    if not available:
        scenario_status = "inconclusivo"
        scenario_summary = "Nenhum cenario produziu margem de seguranca utilizavel."
    elif base_margin is not None and base_margin < 0 and positive_count == 0:
        scenario_status = "conflitante"
        scenario_summary = "O cenario base e todos os cenarios disponiveis ficaram abaixo do preco atual."
    elif base_margin is not None and base_margin < 0:
        scenario_status = "atencao"
        scenario_summary = "O cenario base ficou abaixo do preco atual, embora exista algum cenario favoravel."
    else:
        scenario_status = "favoravel"
        scenario_summary = "O cenario base sustenta a recomendacao pelo criterio de margem de seguranca."

    warnings: list[str] = []
    if recommendation.lower() == "comprar" and scenario_status in {"conflitante", "atencao"}:
        warnings.append("A recomendacao Comprar depende de premissas diferentes das usadas no cenario base; valide o preco e o crescimento antes de investir.")
    if recommendation.lower() == "comprar" and critical_risks:
        warnings.append("A recomendacao Comprar convive com alerta(s) critico(s); a qualidade dos dados ou das premissas precisa ser revisada.")
    if recommendation.lower() == "evitar" and scenario_status == "favoravel":
        warnings.append("A recomendacao Evitar nao acompanha o cenario base favoravel; confira as travas e os demais pilares.")
    overall = "conflitante" if warnings else "coerente" if scenario_status == "favoravel" else "requer_revisao"
    if not available:
        overall = "inconclusivo"
    explanation = (
        f"Recomendacao {recommendation}; cenarios: {scenario_summary} "
        f"Riscos criticos identificados: {len(critical_risks)}. "
        "Esta auditoria explica a decisao e nao altera automaticamente a recomendacao."
    )
    return DecisionConsistencyAudit(
        recommendation,
        scenario_status,
        scenario_summary,
        base_margin,
        positive_count,
        len(available),
        len(critical_risks),
        overall,
        explanation,
        tuple(warnings),
    )


def append_decision_consistency_to_markdown(markdown: str, audit: DecisionConsistencyAudit) -> str:
    lines = [
        "## Coerencia da decisao",
        audit.explanation,
        "",
        f"- Status geral: **{audit.overall_status}**.",
        f"- Leitura dos cenarios: **{audit.scenario_status}**; {audit.scenario_summary}",
        f"- Margem do cenario base: **{_percent(audit.base_margin)}**.",
        f"- Cenarios favoraveis: **{audit.positive_scenario_count}/{audit.available_scenario_count}**.",
        f"- Riscos criticos: **{audit.critical_risk_count}**.",
    ]
    if audit.warnings:
        lines.extend(["", "**Pontos que exigem revisao:**", *[f"- {warning}" for warning in audit.warnings]])
    block = "\n".join(lines)
    marker = "\n## Notas explicativas"
    return markdown.replace(marker, f"\n{block}{marker}", 1) if marker in markdown else f"{markdown}\n\n{block}"


def append_decision_consistency_to_html(html: str, audit: DecisionConsistencyAudit) -> str:
    warnings = "".join(f"<li>{escape(item)}</li>" for item in audit.warnings)
    warning_block = f"<h3>Pontos que exigem revisao</h3><ul>{warnings}</ul>" if warnings else ""
    section = (
        '<section class="panel decision-consistency">'
        "<h2>Coerencia da decisao</h2>"
        f"<p>{escape(audit.explanation)}</p>"
        f"<p><strong>Status:</strong> {escape(audit.overall_status)} &nbsp; "
        f"<strong>Cenario base:</strong> {escape(_percent(audit.base_margin))} &nbsp; "
        f"<strong>Riscos criticos:</strong> {audit.critical_risk_count}</p>"
        f"{warning_block}</section>"
    )
    marker = '<section class="panel risks">'
    return html.replace(marker, section + "\n" + marker, 1) if marker in html else html.replace("</main>", section + "\n</main>", 1)


def _number(value: object) -> float | None:
    try:
        result = float(value) if value is not None else None
        return result if result is not None and result == result else None
    except (TypeError, ValueError):
        return None


def _is_critical(risk: object) -> bool:
    text = str(risk).lower()
    return any(term in text for term in ("critico", "bloqueado", "fallback", "inconclusivo"))


def _percent(value: float | None) -> str:
    return "indisponivel" if value is None else f"{value:.2%}"


__all__ = ["DecisionConsistencyAudit", "audit_decision_consistency", "append_decision_consistency_to_markdown", "append_decision_consistency_to_html"]

