"""Visual polish layer for static HTML reports."""
from __future__ import annotations

import re


def apply_visual_polish_to_html(html: str, recommendation: str) -> str:
    """Add presentation-only structure and styles to the final HTML report."""
    polished = _add_body_class(html, recommendation)
    polished = _insert_visual_guide(polished)
    polished = _decorate_valuation_margins(polished)
    return _inject_visual_style(polished)


def _add_body_class(html: str, recommendation: str) -> str:
    class_name = {
        "Comprar": "recommend-buy",
        "Observar": "recommend-watch",
        "Evitar": "recommend-avoid",
    }.get(recommendation, "recommend-neutral")
    if '<body class="visual-polish' in html:
        return html
    if "<body>" in html:
        return html.replace("<body>", f'<body class="visual-polish {class_name}">', 1)
    return html


def _insert_visual_guide(html: str) -> str:
    if "Legenda visual" in html:
        return html
    guide = "\n".join(
        [
            '<section class="panel visual-guide" aria-label="Legenda visual">',
            "<h2>Legenda visual</h2>",
            '<div class="legend-grid">',
            '<div><span class="legend-dot positive"></span><strong>Favoravel</strong><small>Ajuda a tese ou indica menor risco relativo.</small></div>',
            '<div><span class="legend-dot neutral"></span><strong>Neutro</strong><small>Exige contexto; sozinho nao confirma nem invalida a tese.</small></div>',
            '<div><span class="legend-dot negative"></span><strong>Atencao</strong><small>Pode pressionar valuation, qualidade, divida ou liquidez.</small></div>',
            '<div><span class="legend-dot missing"></span><strong>Dado fraco</strong><small>Fonte incompleta ou confianca baixa; revisar antes de decidir.</small></div>',
            "</div>",
            "</section>",
        ]
    )
    marker = "</header>"
    if marker in html:
        return html.replace(marker, f"{marker}\n{guide}", 1)
    if '<main class="page">' in html:
        return html.replace('<main class="page">', f'<main class="page">\n{guide}', 1)
    return f"{guide}\n{html}"


def _inject_visual_style(html: str) -> str:
    if "visual-polish-css" in html:
        return html
    style = f'<style id="visual-polish-css">\n{VISUAL_POLISH_CSS}\n</style>'
    if "</head>" in html:
        return html.replace("</head>", f"{style}\n</head>", 1)
    return f"{style}\n{html}"


def _decorate_valuation_margins(html: str) -> str:
    if "margin-pill" in html:
        return html
    pattern = re.compile(r"(<h2>Valuation por metodo</h2>\s*<table>.*?</table>)", re.DOTALL)
    return pattern.sub(lambda match: _decorate_margin_table(match.group(1)), html, count=1)


def _decorate_margin_table(table_html: str) -> str:
    row_pattern = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)

    def decorate_row(match: re.Match[str]) -> str:
        row = match.group(1)
        cells = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
        if len(cells) < 3:
            return match.group(0)
        cells[2] = _margin_badge(cells[2])
        return "<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"

    return row_pattern.sub(decorate_row, table_html)


def _margin_badge(value_html: str) -> str:
    band_class, band_label = _margin_band(value_html)
    return (
        '<span class="margin-readout">'
        f"<strong>{value_html}</strong>"
        f'<span class="margin-pill {band_class}">{band_label}</span>'
        "</span>"
    )


def _margin_band(value_html: str) -> tuple[str, str]:
    text = re.sub(r"<.*?>", "", value_html).strip()
    try:
        margin = float(text.replace("%", "").replace(",", "")) / 100.0
    except Exception:
        return "neutral", "Sem leitura"
    if margin >= 0.15:
        return "positive", "Margem positiva"
    if margin >= 0.0:
        return "neutral", "Margem estreita"
    return "negative", "Margem negativa"


VISUAL_POLISH_CSS = """
.visual-polish {
  background: #f3f5f7;
  color: #17202a;
}
.visual-polish .page {
  max-width: 1220px;
  padding: 28px 18px 56px;
}
.visual-polish header {
  background: #ffffff;
  border: 1px solid #d8e0e8;
  border-left: 7px solid #687789;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(24, 32, 42, 0.06);
  margin-bottom: 16px;
  padding: 24px;
}
.visual-polish.recommend-buy header { border-left-color: #1f7a4d; }
.visual-polish.recommend-watch header { border-left-color: #a66a00; }
.visual-polish.recommend-avoid header { border-left-color: #b23b3b; }
.visual-polish header > p:first-child {
  color: #667385;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .08em;
  margin: 0 0 6px;
  text-transform: uppercase;
}
.visual-polish h1 {
  color: #111820;
  font-size: 40px;
  line-height: 1.05;
}
.visual-polish h2 {
  color: #17202a;
  font-size: 19px;
  line-height: 1.25;
}
.visual-polish h3 {
  color: #263442;
  font-size: 15px;
}
.visual-polish .cards {
  gap: 12px;
}
.visual-polish .card,
.visual-polish .panel {
  border-color: #d9e1ea;
  box-shadow: 0 6px 18px rgba(24, 32, 42, 0.05);
}
.visual-polish .card {
  min-height: 112px;
  padding: 16px;
}
.visual-polish .card span:first-child {
  color: #5b6878;
  font-weight: 700;
}
.visual-polish .card strong {
  color: #111820;
  font-size: 27px;
  line-height: 1.1;
}
.visual-polish .card.buy,
.visual-polish .card.watch,
.visual-polish .card.avoid {
  border-top: 4px solid #687789;
}
.visual-polish .card.buy { border-top-color: #1f7a4d; }
.visual-polish .card.watch { border-top-color: #a66a00; }
.visual-polish .card.avoid { border-top-color: #b23b3b; }
.visual-polish .visual-guide {
  background: #ffffff;
  margin-top: 0;
}
.visual-polish .visual-guide h2 {
  margin-bottom: 10px;
}
.visual-polish .legend-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
}
.visual-polish .legend-grid div {
  align-items: flex-start;
  background: #f8fafc;
  border: 1px solid #e0e6ed;
  border-radius: 8px;
  display: grid;
  gap: 3px 8px;
  grid-template-columns: 14px 1fr;
  padding: 10px 12px;
}
.visual-polish .legend-grid strong {
  color: #17202a;
  font-size: 13px;
}
.visual-polish .legend-grid small {
  color: #667385;
  font-size: 12px;
  grid-column: 2;
  line-height: 1.35;
}
.visual-polish .legend-dot {
  border-radius: 999px;
  display: inline-block;
  height: 10px;
  margin-top: 3px;
  width: 10px;
}
.visual-polish .legend-dot.positive { background: #1f7a4d; }
.visual-polish .legend-dot.neutral { background: #b58100; }
.visual-polish .legend-dot.negative { background: #b23b3b; }
.visual-polish .legend-dot.missing { background: #7b8794; }
.visual-polish .didactic-summary {
  border-top: 4px solid #2f6f9f;
}
.visual-polish .bridge {
  border-left: 4px solid #2f6f9f;
}
.visual-polish .muted {
  background: #f9fbfd;
  color: #475569;
}
.visual-polish table {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  border-spacing: 0;
  border-collapse: separate;
  overflow: hidden;
}
.visual-polish th {
  background: #eef3f7;
  color: #445367;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .03em;
  text-transform: uppercase;
}
.visual-polish td {
  color: #263442;
}
.visual-polish tbody tr:nth-child(even) td {
  background: #fbfcfe;
}
.visual-polish .indicator-table td:nth-child(7) {
  color: #5b6878;
  min-width: 220px;
}
.visual-polish .signal,
.visual-polish .peer-badge {
  min-height: 24px;
}
.visual-polish .bar {
  height: 12px;
}
.visual-polish .bar i {
  background: #2f6f9f;
}
.visual-polish .score-positive .bar i {
  background: #1f7a4d;
}
.visual-polish .score-neutral .bar i {
  background: #b58100;
}
.visual-polish .score-negative .bar i {
  background: #b23b3b;
}
.visual-polish .dimension > strong {
  font-size: 15px;
}
.visual-polish .score-readout {
  min-width: 86px;
}
.visual-polish .score-readout strong {
  color: #17202a;
  font-size: 16px;
}
.visual-polish .score-pill {
  letter-spacing: .02em;
  min-width: 72px;
  text-align: center;
}
.visual-polish .margin-readout {
  align-items: flex-end;
  display: inline-grid;
  gap: 4px;
  justify-items: end;
}
.visual-polish .margin-pill {
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  min-width: 104px;
  padding: 3px 7px;
  text-align: center;
  text-transform: uppercase;
}
.visual-polish .margin-pill.positive {
  color: #176b43;
  background: #e7f4ec;
  border: 1px solid #b9dfc8;
}
.visual-polish .margin-pill.neutral {
  color: #6b5600;
  background: #fff7d6;
  border: 1px solid #ead47a;
}
.visual-polish .margin-pill.negative {
  color: #9c2f2f;
  background: #fdeaea;
  border: 1px solid #efb6b6;
}
.visual-polish .reverse-item,
.visual-polish .peer-summary div {
  background: #f8fafc;
}
@media (max-width: 720px) {
  .visual-polish .page { padding: 18px 10px 36px; }
  .visual-polish header { padding: 18px; }
  .visual-polish h1 { font-size: 31px; }
  .visual-polish .card { min-height: 0; }
}
"""
