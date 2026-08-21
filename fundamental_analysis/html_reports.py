"""Static HTML report rendering."""
from __future__ import annotations

from html import escape
from typing import Iterable

from .comparables import ComparableReport
from .data_sources import MetricValue
from .peer_reporting import peer_median_detail_table, peer_selection_visual_table
from .peer_selection import PeerSelectionReport
from .reports import (
    _fmt_money,
    _fmt_number,
    _fmt_pct,
    comparable_table,
    current_price_summary,
    decision_bridge,
    explanatory_notes,
    key_indicator_table,
    metric_lineage_table,
    recommendation_summary,
    risk_diagnostics,
    scenario_assumption_text,
    scenario_table,
    score_scale_note,
    score_table,
    valuation_table,
)
from .reverse_dcf_reporting import reverse_dcf_summary, reverse_dcf_table
from .scenarios import ReverseDCFResult, ScenarioResult
from .scoring import ScoreReport
from .valuation import ValuationResult


def render_html_report(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None, scenarios: Iterable[ScenarioResult] | None = None, comparables: ComparableReport | None = None, peer_selection: PeerSelectionReport | None = None, reverse_dcf: ReverseDCFResult | None = None) -> str:
    valuations = list(valuations)
    scenarios = list(scenarios or [])
    risks = risk_diagnostics(score, valuations, metrics)
    valuation_rows = valuation_table(valuations)
    indicator_rows = key_indicator_table(metrics)
    scenario_rows = scenario_table(scenarios)
    comparable_rows = comparable_table(comparables) if comparables else []
    peer_rows = peer_selection_visual_table(peer_selection) if peer_selection else []
    peer_median_rows = peer_median_detail_table(peer_selection) if peer_selection else []
    reverse = reverse_dcf_table(reverse_dcf) if reverse_dcf else {}
    price = current_price_summary(metrics)
    cards = [
        ("Recomendacao", score.recommendation, "Decisao final do modelo"),
        ("Score total", f"{score.total_score:.2f}", "Composicao multifatorial"),
        ("Preco atual", _fmt_money(price["value"]), f"Fonte: {price.get('source_detail', price['source'])}"),
        ("Valuation", f"{score.dimensions.get('valuation').score:.2f}" if score.dimensions.get("valuation") else "-", "Preco vs valor justo"),
        ("Confianca", f"{score.dimensions.get('data_confidence').score:.2f}" if score.dimensions.get("data_confidence") else "-", "Qualidade dos dados"),
    ]
    body = [
        "<!doctype html>",
        '<html lang="pt-BR">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Analise fundamentalista - {escape(ticker.upper())}</title>",
        "<style>",
        _html_style(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        f"<header><p>Analise fundamentalista</p><h1>{escape(ticker.upper())}</h1><p>{escape(recommendation_summary(score, valuations))}</p></header>",
        '<section class="cards">',
        *[_metric_card(title, value, subtitle, score.recommendation if title == "Recomendacao" else "") for title, value, subtitle in cards],
        "</section>",
        '<section class="panel bridge">',
        "<h2>Ponte para decisao</h2>",
        "<ul>",
        *[f"<li>{escape(item)}</li>" for item in decision_bridge(score, valuations)],
        "</ul>",
        "</section>",
        '<section class="panel">',
        "<h2>Indicadores principais</h2>",
        _indicator_table(indicator_rows),
        "</section>",
        '<section class="panel">',
        "<h2>Fontes dos dados principais</h2>",
        _source_table(metric_lineage_table(metrics or {})),
        "</section>",
        '<section class="panel">',
        "<h2>Score por dimensao</h2>",
        f"<p>{escape(score_scale_note())}</p>",
        '<div class="score-grid">',
        *[_dimension_bar(row) for row in score_table(score)],
        "</div>",
        "</section>",
        '<section class="panel">',
        "<h2>Valuation por metodo</h2>",
        _html_table(
            ["Metodo", "Preco justo", "Margem", "Fonte", "Confianca"],
            [[row["display_method"], _fmt_money(row["fair_value_per_share"]), _fmt_pct(row["margin_of_safety"]), row["source"], f"{float(row['confidence'] or 0):.2f}"] for row in valuation_rows],
        ),
        "</section>",
    ]
    if scenario_rows:
        body.extend(
            [
                '<section class="panel">',
                "<h2>Cenarios</h2>",
                "<p>Os cenarios abaixo testam como o valor justo muda quando crescimento, custo de capital, crescimento terminal e FCFF sao alterados.</p>",
                _html_table(
                    ["Cenario", "Leitura", "Preco justo", "Margem", "Confianca", "Premissas"],
                    [[row["scenario"], scenario_readthrough(row), _fmt_money(row["fair_value_per_share"]), _fmt_pct(row["margin_of_safety"]), f"{float(row['confidence'] or 0):.2f}", scenario_assumption_text(row["assumptions"])] for row in scenario_rows],
                ),
                "</section>",
            ]
        )
    if reverse:
        body.extend(
            [
                '<section class="panel reverse-dcf">',
                "<h2>Reverse DCF</h2>",
                f"<p>{escape(reverse_dcf_summary(reverse_dcf))}</p>" if reverse_dcf else "",
                '<div class="reverse-grid">',
                _reverse_item("Preco atual", _fmt_money(reverse.get("current_price"))),
                _reverse_item("Crescimento implicito", _fmt_pct(reverse.get("implied_growth_years"))),
                _reverse_item("Crescimento base", _fmt_pct(reverse.get("base_growth_years"))),
                _reverse_item("Taxa de desconto", _fmt_pct(reverse.get("discount_rate"))),
                _reverse_item("Crescimento terminal", _fmt_pct(reverse.get("terminal_growth"))),
                _reverse_item("Status", str(reverse.get("status", "-"))),
                "</div>",
                "</section>",
            ]
        )
    if peer_selection and (peer_selection.approved or peer_selection.rejected):
        snapshot = peer_selection_snapshot(peer_selection, peer_median_rows)
        body.extend(
            [
                '<section class="panel peer-selection">',
                "<h2>Selecao de pares</h2>",
                f"<p>{escape(str(peer_selection.summary))}</p>",
                '<div class="peer-summary">',
                _peer_summary_item("Aprovados", snapshot["approved_count"]),
                _peer_summary_item("Rejeitados", snapshot["rejected_count"]),
                _peer_summary_item("Multiplos com mediana", snapshot["median_metric_count"]),
                _peer_summary_item("Confianca", f"{float(snapshot['confidence'] or 0):.2f}"),
                "</div>",
                _peer_selection_table(peer_rows),
                "<h3>Multiplos usados na mediana</h3>",
                _peer_median_table(peer_median_rows),
                "</section>",
            ]
        )
    if comparables:
        body.extend(
            [
                '<section class="panel">',
                "<h2>Comparaveis</h2>",
                f"<p>{escape(comparables.summary if comparables else '')}</p>",
                _html_table(
                    ["Multiplo", "Empresa", "Mediana pares", "N pares", "Premio/desconto", "Score", "Leitura"],
                    [
                        [
                            row["metric"],
                            _fmt_number(row["company_value"]),
                            _fmt_number(row["peer_median"]),
                            int(row["peer_count"] or 0),
                            _fmt_pct(row["premium_discount"]),
                            f"{float(row['score'] or 0):.2f}",
                            row["interpretation"],
                        ]
                        for row in comparable_rows
                    ],
                ),
                "</section>",
            ]
        )
    body.extend(
        [
            '<section class="panel">',
            "<h2>Riscos principais</h2>",
            "<ul>",
            *[f"<li>{escape(risk)}</li>" for risk in risks],
            "</ul>",
            "</section>",
            '<section class="panel muted">',
            "<h2>Notas explicativas</h2>",
            "<ul>",
            *[f"<li>{escape(note)}</li>" for note in explanatory_notes(score, valuations, metrics)],
            "</ul>",
            "</section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(body)


def scenario_readthrough(row: dict[str, object]) -> str:
    try:
        margin = float(row.get("margin_of_safety"))
    except Exception:
        return "Sem leitura conclusiva."
    if margin >= 0.15:
        return "Sustenta a tese com folga."
    if margin >= 0.0:
        return "Sustenta a tese, mas com pouca folga."
    if margin >= -0.15:
        return "Fragiliza a tese."
    return "Pressiona fortemente a tese."


def peer_selection_snapshot(peer_selection: PeerSelectionReport, median_rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "approved_count": len(peer_selection.approved),
        "rejected_count": len(peer_selection.rejected),
        "median_metric_count": len([row for row in median_rows if row.get("included_in_median")]),
        "confidence": peer_selection.confidence,
    }


def _html_style() -> str:
    return """
:root { color-scheme: light; font-family: Inter, Segoe UI, Arial, sans-serif; color: #18202a; background: #f5f7fa; }
body { margin: 0; }
.page { max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }
header { margin-bottom: 24px; }
header p { max-width: 900px; line-height: 1.55; color: #526071; }
h1 { margin: 4px 0 10px; font-size: 42px; letter-spacing: 0; }
h2 { margin: 0 0 16px; font-size: 20px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-bottom: 16px; }
.card, .panel { background: #ffffff; border: 1px solid #dfe5ec; border-radius: 8px; box-shadow: 0 1px 2px rgba(20, 32, 45, 0.05); }
.card { padding: 16px; }
.card span { display: block; color: #667385; font-size: 13px; }
.card strong { display: block; margin: 8px 0 4px; font-size: 28px; }
.card.buy strong { color: #176b43; }
.card.watch strong { color: #875500; }
.card.avoid strong { color: #a33232; }
.panel { padding: 18px; margin-top: 16px; overflow-x: auto; }
.muted { background: #fbfcfe; }
.score-grid { display: grid; gap: 12px; }
.dimension { display: grid; grid-template-columns: minmax(140px, 180px) 1fr minmax(44px, auto); gap: 12px; align-items: center; }
.bar { height: 10px; background: #e8edf3; border-radius: 999px; overflow: hidden; }
.bar i { display: block; height: 100%; background: #2f6f9f; }
.dimension small { color: #667385; }
.score-readout { display: grid; gap: 4px; justify-items: end; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; color: #526071; background: #f2f5f8; }
th, td { padding: 10px 8px; border-bottom: 1px solid #e3e8ef; vertical-align: top; }
td:not(:first-child), th:not(:first-child) { text-align: right; }
.indicator-table td:nth-child(1), .indicator-table th:nth-child(1), .indicator-table td:nth-child(2), .indicator-table th:nth-child(2), .indicator-table td:nth-child(4), .indicator-table th:nth-child(4), .indicator-table td:nth-child(5), .indicator-table th:nth-child(5), .indicator-table td:nth-child(7), .indicator-table th:nth-child(7) { text-align: left; }
.signal, .peer-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 84px; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 700; }
.signal.positive, .peer-badge.approved { color: #176b43; background: #e7f4ec; border: 1px solid #b9dfc8; }
.signal.neutral, .peer-badge.weak { color: #6b5600; background: #fff7d6; border: 1px solid #ead47a; }
.signal.negative, .peer-badge.rejected { color: #9c2f2f; background: #fdeaea; border: 1px solid #efb6b6; }
.signal.missing { color: #667385; background: #eef2f6; border: 1px solid #d6dde6; }
.reverse-grid, .peer-summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-top: 14px; }
.reverse-item, .peer-summary div { background: #f7f9fb; border: 1px solid #e0e6ed; border-radius: 8px; padding: 12px; }
.reverse-item span, .peer-summary span { display: block; color: #667385; font-size: 12px; }
.reverse-item strong, .peer-summary strong { display: block; margin-top: 6px; font-size: 18px; }
.peer-selection h3 { margin: 18px 0 10px; font-size: 16px; }
ul { margin: 0; padding-left: 20px; }
li { margin: 8px 0; }
@media (max-width: 720px) { h1 { font-size: 32px; } .dimension { grid-template-columns: 1fr; gap: 6px; } td:not(:first-child), th:not(:first-child) { text-align: left; } }
"""


def _metric_card(title: str, value: str, subtitle: str, recommendation: str = "") -> str:
    klass = {"Comprar": "buy", "Observar": "watch", "Evitar": "avoid"}.get(recommendation, "")
    return f'<article class="card {klass}"><span>{escape(title)}</span><strong>{escape(value)}</strong><span>{escape(subtitle)}</span></article>'


def _dimension_bar(row: dict[str, object]) -> str:
    score = max(0.0, min(1.0, float(row.get("score") or 0.0)))
    band_class, band_label = _score_band(score)
    return (
        f'<div class="dimension score-{band_class}">'
        f"<div><strong>{escape(str(row.get('name', '-')))}</strong><br><small>{escape(str(row.get('explanation', '-')))}</small></div>"
        f'<div class="bar"><i style="width: {score * 100:.0f}%"></i></div>'
        f'<div class="score-readout"><strong>{score:.2f}</strong><span class="score-pill {band_class}">{escape(band_label)}</span></div>'
        "</div>"
    )


def _score_band(score: float) -> tuple[str, str]:
    if score >= 0.75:
        return "positive", "Forte"
    if score >= 0.50:
        return "neutral", "Intermediario"
    return "negative", "Fraco"


def _reverse_item(label: str, value: str) -> str:
    return f'<div class="reverse-item"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


def _peer_summary_item(label: str, value: object) -> str:
    return f"<div><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def _peer_selection_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem pares avaliados.</p>"
    rendered = []
    for row in rows:
        rendered.append([
            row.get("ticker", "-"),
            _peer_badge(str(row.get("decision", "-"))),
            f"{float(row.get('score') or 0):.2f}",
            f"{float(row.get('evidence_weight') or 0):.2f}",
            f"{float(row.get('data_confidence') or 0):.2f}",
            row.get("why", "-"),
            row.get("multiples", "-"),
        ])
    return _html_table(["Ticker", "Decisao", "Score", "Evidencia", "Confianca", "Por que", "Multiplos"], rendered)


def _peer_median_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem multiplos suficientes dos pares aprovados.</p>"
    rendered = []
    for row in rows:
        median = _fmt_number(row.get("median")) if row.get("included_in_median") else "nao usada"
        rendered.append([row.get("display_metric", "-"), median, int(row.get("peer_count") or 0), row.get("used_peers", "-")])
    return _html_table(["Multiplo", "Mediana usada", "N pares", "Pares usados"], rendered)


def _peer_badge(decision: str) -> str:
    klass = "approved" if decision == "Aprovado" else "weak" if decision == "Referencia fraca" else "rejected"
    return f'<span class="peer-badge {klass}">{escape(decision)}</span>'


def _html_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "<p>Sem dados disponiveis.</p>"
    header_html = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    row_html = []
    for row in rows:
        cells = []
        for value in row:
            text = str(value)
            cells.append(f"<td>{text if text.startswith('<span class=') else escape(text)}</td>")
        row_html.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html)}</tbody></table>"


def _indicator_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem dados disponiveis.</p>"
    headers = ["Grupo", "Indicador", "Valor", "Sinal", "Fonte", "Confianca", "Leitura"]
    row_html = []
    for row in rows:
        signal = str(row.get("signal") or "neutral")
        label = str(row.get("signal_label") or "Neutro")
        cells = [
            escape(str(row.get("group", "-"))),
            escape(str(row.get("indicator", "-"))),
            escape(_fmt_indicator(row)),
            f'<span class="signal {escape(signal)}">{escape(label)}</span>',
            escape(str(row.get("source", "-"))),
            escape(f"{float(row.get('confidence') or 0):.2f}"),
            escape(str(row.get("explanation", "-"))),
        ]
        row_html.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    return f'<table class="indicator-table"><thead><tr>{"".join(f"<th>{header}</th>" for header in headers)}</tr></thead><tbody>{"".join(row_html)}</tbody></table>'


def _source_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "<p>Sem fontes disponiveis.</p>"
    preferred = {"price", "revenue", "ebit", "net_income", "fcff", "free_cash_flow_after_capex", "total_assets", "total_debt", "cash", "shares"}
    selected = [row for row in rows if row.get("metric") in preferred] or rows[:10]
    return _html_table(
        ["Metrica", "Valor", "Fonte", "Base", "Confianca"],
        [[row.get("metric", "-"), _fmt_number(row.get("value")), row.get("source_detail") or row.get("source", "-"), row.get("basis", "-"), f"{float(row.get('confidence') or 0):.2f}"] for row in selected[:12]],
    )


def _fmt_indicator(row: dict[str, object]) -> str:
    kind = row.get("format")
    value = row.get("value")
    if kind == "percent":
        return _fmt_pct(value)
    if kind == "money":
        return _fmt_money(value)
    return _fmt_number(value)
