"""Readable Reverse DCF report snippets."""
from __future__ import annotations

from html import escape

from .config import DCF
from .scenarios import ReverseDCFResult


def reverse_dcf_table(reverse_dcf: ReverseDCFResult | None) -> dict[str, object]:
    if reverse_dcf is None:
        return {}
    return {
        "current_price": reverse_dcf.current_price,
        "implied_growth_years": reverse_dcf.implied_growth_years,
        "base_growth_years": reverse_dcf.base_growth_years,
        "discount_rate": reverse_dcf.discount_rate,
        "terminal_growth": reverse_dcf.terminal_growth,
        "confidence": reverse_dcf.confidence,
        "status": reverse_dcf.status,
        "interpretation": reverse_dcf.interpretation,
        "assumptions": reverse_dcf.assumptions,
    }


def reverse_dcf_summary(reverse_dcf: ReverseDCFResult) -> str:
    if reverse_dcf.implied_growth_years is None:
        return reverse_dcf.interpretation
    return (
        f"Para o preco atual de {_fmt_money(reverse_dcf.current_price)} fazer sentido no DCF, "
        f"o modelo precisa embutir crescimento anual de FCFF de aproximadamente {_fmt_pct(reverse_dcf.implied_growth_years)} "
        f"por {DCF.horizon_years} anos, usando taxa de desconto de {_fmt_pct(reverse_dcf.discount_rate)} "
        f"e crescimento terminal de {_fmt_pct(reverse_dcf.terminal_growth)}. {reverse_dcf.interpretation}"
    )


def append_reverse_dcf_to_markdown(markdown: str, reverse_dcf: ReverseDCFResult) -> str:
    reverse = reverse_dcf_table(reverse_dcf)
    section = "\n".join(
        [
            "",
            "## Reverse DCF",
            reverse_dcf_summary(reverse_dcf),
            "",
            "| Preco atual | Crescimento implicito | Crescimento base | Taxa de desconto | Crescimento terminal | Status | Confianca |",
            "|---:|---:|---:|---:|---:|---|---:|",
            f"| {_fmt_money(reverse.get('current_price'))} | {_fmt_pct(reverse.get('implied_growth_years'))} | {_fmt_pct(reverse.get('base_growth_years'))} | {_fmt_pct(reverse.get('discount_rate'))} | {_fmt_pct(reverse.get('terminal_growth'))} | {reverse.get('status', '-')} | {float(reverse.get('confidence') or 0):.2f} |",
        ]
    )
    marker = "\n## Score por dimensao"
    if marker in markdown:
        return markdown.replace(marker, section + marker, 1)
    return markdown + section


def append_reverse_dcf_to_html(html: str, reverse_dcf: ReverseDCFResult) -> str:
    reverse = reverse_dcf_table(reverse_dcf)
    section = (
        '<section class="panel reverse-dcf">'
        "<h2>Reverse DCF</h2>"
        f"<p>{escape(reverse_dcf_summary(reverse_dcf))}</p>"
        '<div class="reverse-grid">'
        f'{_reverse_item("Preco atual", _fmt_money(reverse.get("current_price")))}'
        f'{_reverse_item("Crescimento implicito", _fmt_pct(reverse.get("implied_growth_years")))}'
        f'{_reverse_item("Crescimento base", _fmt_pct(reverse.get("base_growth_years")))}'
        f'{_reverse_item("Taxa de desconto", _fmt_pct(reverse.get("discount_rate")))}'
        f'{_reverse_item("Crescimento terminal", _fmt_pct(reverse.get("terminal_growth")))}'
        f'{_reverse_item("Status", str(reverse.get("status", "-")))}'
        "</div>"
        "</section>"
    )
    style = (
        ".reverse-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 14px; }"
        ".reverse-item { background: #f7f9fb; border: 1px solid #e0e6ed; border-radius: 8px; padding: 12px; }"
        ".reverse-item span { display: block; color: #667385; font-size: 12px; }"
        ".reverse-item strong { display: block; margin-top: 6px; font-size: 20px; }"
    )
    rendered = html.replace("</style>", style + "\n</style>", 1)
    marker = '<section class="panel">\n<h2>Score por dimensao</h2>'
    if marker in rendered:
        return rendered.replace(marker, section + "\n" + marker, 1)
    return rendered.replace("</main>", section + "\n</main>", 1)


def _reverse_item(label: str, value: str) -> str:
    return f'<div class="reverse-item"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>'


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
