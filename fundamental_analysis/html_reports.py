"""Static HTML report rendering."""
from __future__ import annotations

from html import escape
from typing import Iterable

from .comparables import ComparableReport
from .data_sources import MetricValue
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
    recommendation_summary,
    risk_diagnostics,
    scenario_assumption_text,
    scenario_table,
    score_scale_note,
    score_table,
    valuation_table,
)
from .scenarios import ScenarioResult
from .scoring import ScoreReport
from .valuation import ValuationResult


def render_html_report(ticker: str, score: ScoreReport, valuations: Iterable[ValuationResult], metrics: dict[str, MetricValue] | None = None, scenarios: Iterable[ScenarioResult] | None = None, comparables: ComparableReport | None = None, peer_selection: PeerSelectionReport | None = None) -> str:
    valuations = list(valuations)
    scenarios = list(scenarios or [])
    risks = risk_diagnostics(score, valuations, metrics)
    valuation_rows = valuation_table(valuations)
    indicator_rows = key_indicator_table(metrics)
    scenario_rows = scenario_table(scenarios)
    comparable_rows = comparable_table(comparables) if comparables else []
    price = current_price_summary(metrics)
    cards = [
        ("Recomendacao", score.recommendation, "Decisao final do modelo"),
        ("Score total", f"{score.total_score:.2f}", "Composicao multifatorial"),
        ("Preco atual", _fmt_money(price["value"]), f"Fonte: {price['source']}"),
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
        _html_table(
            ["Grupo", "Indicador", "Valor", "Fonte", "Confianca", "Leitura"],
            [[row["group"], row["indicator"], _fmt_indicator(row), row["source"], f"{float(row['confidence'] or 0):.2f}", row["explanation"]] for row in indicator_rows],
        ),
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
                _html_table(
                    ["Cenario", "Preco justo", "Margem", "Confianca", "Premissas"],
                    [[row["scenario"], _fmt_money(row["fair_value_per_share"]), _fmt_pct(row["margin_of_safety"]), f"{float(row['confidence'] or 0):.2f}", scenario_assumption_text(row["assumptions"])] for row in scenario_rows],
                ),
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
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; color: #526071; background: #f2f5f8; }
th, td { padding: 10px 8px; border-bottom: 1px solid #e3e8ef; vertical-align: top; }
td:not(:first-child), th:not(:first-child) { text-align: right; }
ul { margin: 0; padding-left: 20px; }
li { margin: 8px 0; }
@media (max-width: 720px) {
  h1 { font-size: 32px; }
  .dimension { grid-template-columns: 1fr; gap: 6px; }
  td:not(:first-child), th:not(:first-child) { text-align: left; }
}
"""


def _metric_card(title: str, value: str, subtitle: str, recommendation: str = "") -> str:
    klass = {"Comprar": "buy", "Observar": "watch", "Evitar": "avoid"}.get(recommendation, "")
    return (
        f'<article class="card {klass}">'
        f"<span>{escape(title)}</span>"
        f"<strong>{escape(value)}</strong>"
        f"<span>{escape(subtitle)}</span>"
        "</article>"
    )


def _dimension_bar(row: dict[str, object]) -> str:
    score = max(0.0, min(1.0, float(row.get("score") or 0.0)))
    return (
        '<div class="dimension">'
        f"<div><strong>{escape(str(row.get('name', '-')))}</strong><br><small>{escape(str(row.get('explanation', '-')))}</small></div>"
        f'<div class="bar"><i style="width: {score * 100:.0f}%"></i></div>'
        f"<strong>{score:.2f}</strong>"
        "</div>"
    )


def _html_table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "<p>Sem dados disponiveis.</p>"
    header_html = "".join(f"<th>{escape(str(header))}</th>" for header in headers)
    row_html = []
    for row in rows:
        row_html.append("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in row) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(row_html)}</tbody></table>"


def _fmt_indicator(row: dict[str, object]) -> str:
    kind = row.get("format")
    value = row.get("value")
    if kind == "percent":
        return _fmt_pct(value)
    if kind == "money":
        return _fmt_money(value)
    return _fmt_number(value)
