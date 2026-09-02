"""Readable peer-selection reporting helpers."""
from __future__ import annotations

from html import escape

from .config import PEER_ENRICHMENT, PEER_SELECTION
from .peer_selection import MULTIPLE_FIELDS, PeerSelectionReport
from .reports import _fmt_number


PEER_STATUS_LABELS = {
    "strong": "Aprovado forte",
    "acceptable": "Aprovado",
    "weak_reference": "Referencia fraca",
    "rejected_low_similarity": "Rejeitado por baixa similaridade",
    "rejected_low_evidence": "Rejeitado por falta de evidencias",
    "rejected_veto": "Rejeitado por incompatibilidade",
}

PEER_MULTIPLE_LABELS = {
    "price_to_earnings": "P/L",
    "price_to_book": "P/VP",
    "ev_to_sales": "EV/Receita",
    "ev_to_ebitda": "EV/EBITDA",
    "ev_to_ebit": "EV/EBIT",
    "price_to_sales": "P/Receita",
}


def peer_selection_visual_table(peer_selection: PeerSelectionReport) -> list[dict[str, object]]:
    rows = []
    for result in [*peer_selection.approved, *peer_selection.rejected]:
        rows.append(
            {
                "ticker": result.ticker,
                "decision": peer_decision_text(result.status),
                "status": peer_status_label(result.status),
                "score": result.score,
                "evidence_weight": result.evidence_weight,
                "data_confidence": result.data_confidence,
                "why": peer_main_reason(result),
                "multiples": peer_multiple_summary(result.metrics),
            }
        )
    return rows


def peer_median_detail_table(peer_selection: PeerSelectionReport) -> list[dict[str, object]]:
    rows = []
    for field_name in MULTIPLE_FIELDS:
        median_value = peer_selection.peer_medians.get(field_name)
        count = peer_selection.peer_median_counts.get(field_name, 0)
        used = []
        inputs = []
        for result in peer_selection.median_candidates:
            if (
                result.metrics.get(field_name) is not None
                and result.data_confidence
                >= PEER_ENRICHMENT.minimum_confidence_for_relative_valuation
            ):
                source = result.metric_sources.get(field_name, "fonte nao informada")
                used.append(f"{result.ticker} {_fmt_number(result.metrics.get(field_name))} ({source})")
                inputs.append(
                    {
                        "ticker": result.ticker,
                        "value": result.metrics.get(field_name),
                        "source": source,
                        "lineage": result.metric_lineage.get(field_name, {}),
                        "equivalence_status": result.status,
                        "equivalence_score": result.score,
                        "data_confidence": result.data_confidence,
                    }
                )
        if median_value is not None or count:
            rows.append(
                {
                    "metric": field_name,
                    "display_metric": PEER_MULTIPLE_LABELS.get(field_name, field_name),
                    "median": median_value,
                    "peer_count": count,
                    "used_peers": "; ".join(used) if used else "-",
                    "included_in_median": median_value is not None,
                    "median_inputs": inputs,
                }
            )
    return rows


def peer_equivalence_policy() -> dict[str, object]:
    return {
        "strong_threshold": PEER_SELECTION.strong_threshold,
        "acceptable_threshold": PEER_SELECTION.acceptable_threshold,
        "weak_reference_threshold": PEER_SELECTION.weak_threshold,
        "minimum_evidence_weight": PEER_SELECTION.min_evidence_weight,
        "minimum_approved_peers": PEER_SELECTION.min_approved_peers,
        "minimum_data_confidence_for_median": PEER_ENRICHMENT.minimum_confidence_for_relative_valuation,
        "weights": {
            "sector": PEER_SELECTION.sector_weight,
            "industry": PEER_SELECTION.industry_weight,
            "sic": PEER_SELECTION.sic_weight,
            "business_model": PEER_SELECTION.business_model_weight,
            "size": PEER_SELECTION.size_weight,
            "growth": PEER_SELECTION.growth_weight,
            "margin": PEER_SELECTION.margin_weight,
            "leverage": PEER_SELECTION.leverage_weight,
        },
    }


def append_peer_selection_to_markdown(markdown: str, peer_selection: PeerSelectionReport) -> str:
    if not peer_selection or not (peer_selection.approved or peer_selection.rejected):
        return markdown
    block = _peer_selection_markdown(peer_selection)
    marker = "\n## Comparaveis de mercado"
    if marker in markdown:
        return markdown.replace(marker, f"\n{block}{marker}", 1)
    return f"{markdown}\n\n{block}"


def append_peer_selection_to_html(html: str, peer_selection: PeerSelectionReport) -> str:
    if not peer_selection or not (peer_selection.approved or peer_selection.rejected):
        return html
    block = _peer_selection_html(peer_selection)
    marker = '<section class="panel">\n<h2>Comparaveis</h2>'
    if marker in html:
        return html.replace(marker, f"{block}\n{marker}", 1)
    closing = "</main>"
    if closing in html:
        return html.replace(closing, f"{block}\n{closing}", 1)
    return f"{html}\n{block}"


def peer_status_label(status: str) -> str:
    return PEER_STATUS_LABELS.get(status, status.replace("_", " "))


def peer_decision_text(status: str) -> str:
    if status in {"strong", "acceptable"}:
        return "Aprovado"
    if status == "weak_reference":
        return "Referencia fraca"
    return "Rejeitado"


def peer_main_reason(result: object) -> str:
    vetoes = getattr(result, "vetoes", []) or []
    reasons = getattr(result, "reasons", []) or []
    if vetoes:
        return "; ".join(str(item) for item in vetoes)
    if reasons:
        return "; ".join(str(item) for item in reasons[:3])
    return "Sem evidencias suficientes para explicar a decisao."


def peer_multiple_summary(metrics: dict[str, float]) -> str:
    if not metrics:
        return "Nenhum multiplo disponivel"
    parts = []
    for field_name in MULTIPLE_FIELDS:
        if metrics.get(field_name) is not None:
            parts.append(f"{PEER_MULTIPLE_LABELS.get(field_name, field_name)} {_fmt_number(metrics.get(field_name))}")
    return "; ".join(parts) if parts else "Nenhum multiplo disponivel"


def _peer_selection_markdown(peer_selection: PeerSelectionReport) -> str:
    visual_rows = peer_selection_visual_table(peer_selection)
    median_rows = peer_median_detail_table(peer_selection)
    approved = len(peer_selection.approved)
    rejected = len(peer_selection.rejected)
    median_count = len([row for row in median_rows if row["included_in_median"]])
    lines = [
        "## Selecao visual de pares",
        "",
        f"Resumo: **{approved} aprovados**, **{rejected} rejeitados**, **{median_count} multiplos com mediana utilizavel**. Confianca da selecao: **{peer_selection.confidence:.2f}**.",
        "",
        peer_selection.summary,
        "",
        (
            f"Regua: forte >= {PEER_SELECTION.strong_threshold:.2f}; "
            f"aceitavel >= {PEER_SELECTION.acceptable_threshold:.2f}; "
            f"referencia fraca >= {PEER_SELECTION.weak_threshold:.2f}; "
            f"evidencia minima {PEER_SELECTION.min_evidence_weight:.2f}."
        ),
        "",
        "| Ticker | Decisao | Score | Evidencia | Confianca dados | Por que | Multiplos encontrados |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in visual_rows:
        lines.append(
            f"| {row['ticker']} | {row['decision']} | {_fmt_number(row['score'])} | {_fmt_number(row['evidence_weight'])} | {_fmt_number(row['data_confidence'])} | {row['why']} | {row['multiples']} |"
        )
    lines.extend(
        [
            "",
            "### Multiplos que entraram na mediana",
            "",
            "| Multiplo | Mediana usada | N pares | Pares usados |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    if median_rows:
        for row in median_rows:
            median = _fmt_number(row["median"]) if row["included_in_median"] else "nao usada"
            lines.append(f"| {row['display_metric']} | {median} | {row['peer_count']} | {row['used_peers']} |")
    else:
        lines.append("| - | nao usada | 0 | Sem multiplos suficientes dos pares aprovados |")
    return "\n".join(lines)


def _peer_selection_html(peer_selection: PeerSelectionReport) -> str:
    visual_rows = peer_selection_visual_table(peer_selection)
    median_rows = peer_median_detail_table(peer_selection)
    approved = len(peer_selection.approved)
    rejected = len(peer_selection.rejected)
    median_count = len([row for row in median_rows if row["included_in_median"]])
    return "\n".join(
        [
            '<section class="panel peer-selection">',
            "<h2>Selecao de pares</h2>",
            f"<p>{escape(str(peer_selection.summary))}</p>",
            (
                '<p class="muted">Regua de equivalencia: '
                f"forte &gt;= {PEER_SELECTION.strong_threshold:.2f}; "
                f"aceitavel &gt;= {PEER_SELECTION.acceptable_threshold:.2f}; "
                f"referencia fraca &gt;= {PEER_SELECTION.weak_threshold:.2f}; "
                f"evidencia minima {PEER_SELECTION.min_evidence_weight:.2f}.</p>"
            ),
            '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0 16px;">',
            _peer_summary_card("Aprovados", approved),
            _peer_summary_card("Rejeitados", rejected),
            _peer_summary_card("Multiplos com mediana", median_count),
            _peer_summary_card("Confianca", f"{peer_selection.confidence:.2f}"),
            "</div>",
            _peer_selection_table_html(visual_rows),
            "<h3>Multiplos usados na mediana</h3>",
            _peer_median_table_html(median_rows),
            "</section>",
        ]
    )


def _peer_summary_card(label: str, value: object) -> str:
    return (
        '<div style="background:#f7f9fb;border:1px solid #e0e6ed;border-radius:8px;padding:10px 12px;">'
        f'<span style="display:block;color:#667385;font-size:12px;">{escape(str(label))}</span>'
        f'<strong style="display:block;margin-top:4px;font-size:18px;">{escape(str(value))}</strong>'
        "</div>"
    )


def _peer_selection_table_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem pares avaliados.</p>"
    rendered = []
    for row in rows:
        rendered.append(
            [
                escape(str(row.get("ticker", "-"))),
                _peer_badge(str(row.get("decision", "-"))),
                escape(_fmt_number(row.get("score"))),
                escape(_fmt_number(row.get("evidence_weight"))),
                escape(_fmt_number(row.get("data_confidence"))),
                escape(str(row.get("why", "-"))),
                escape(str(row.get("multiples", "-"))),
            ]
        )
    return _html_table(["Ticker", "Decisao", "Score", "Evidencia", "Confianca", "Por que", "Multiplos"], rendered)


def _peer_median_table_html(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem multiplos suficientes dos pares aprovados.</p>"
    rendered = []
    for row in rows:
        median = _fmt_number(row.get("median")) if row.get("included_in_median") else "nao usada"
        rendered.append(
            [
                escape(str(row.get("display_metric", "-"))),
                escape(median),
                escape(str(int(row.get("peer_count") or 0))),
                escape(str(row.get("used_peers", "-"))),
            ]
        )
    return _html_table(["Multiplo", "Mediana usada", "N pares", "Pares usados"], rendered)


def _peer_badge(decision: str) -> str:
    if decision == "Aprovado":
        klass = "approved"
        style = "color:#176b43;background:#e7f4ec;border:1px solid #b9dfc8;"
    elif decision == "Referencia fraca":
        klass = "weak"
        style = "color:#6b5600;background:#fff7d6;border:1px solid #ead47a;"
    else:
        klass = "rejected"
        style = "color:#9c2f2f;background:#fdeaea;border:1px solid #efb6b6;"
    return (
        f'<span class="peer-badge {klass}" '
        f'style="display:inline-flex;align-items:center;justify-content:center;min-width:86px;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700;{style}">'
        f"{escape(decision)}</span>"
    )


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "<tr>" + "".join(f"<th>{escape(header)}</th>" for header in headers) + "</tr>"
    body = []
    for row in rows:
        body.append("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>")
    return f"<table>{head}{''.join(body)}</table>"
