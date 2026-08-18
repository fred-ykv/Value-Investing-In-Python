"""Readable DCF sensitivity report snippets."""
from __future__ import annotations

from html import escape
from typing import Iterable

from .valuation import ValuationResult


def dcf_sensitivity_table(valuations: Iterable[ValuationResult]) -> list[dict[str, object]]:
    dcf = find_dcf_valuation(valuations)
    matrix = dcf.diagnostics.get("sensitivity") if dcf else None
    if not isinstance(matrix, dict):
        return []
    rows: list[dict[str, object]] = []
    for wacc, values in matrix.items():
        if isinstance(values, dict):
            rows.append({"wacc": wacc, "values": values})
    return rows


def append_dcf_sensitivity_to_markdown(markdown: str, valuations: Iterable[ValuationResult]) -> str:
    rows = dcf_sensitivity_table(valuations)
    if not rows:
        return markdown
    columns = sorted({column for row in rows for column in dict(row["values"]).keys()})
    section = [
        "",
        "## Matriz de sensibilidade DCF",
        dcf_sensitivity_summary(valuations),
        "",
        "| WACC \\ g terminal | " + " | ".join(columns) + " |",
        "|---:|" + "|".join("---:" for _ in columns) + "|",
    ]
    for row in rows:
        values = dict(row["values"])
        section.append("| " + str(row["wacc"]) + " | " + " | ".join(_fmt_money(values.get(column)) for column in columns) + " |")
    block = "\n".join(section)
    marker = "\n## Cenarios hipoteticos"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    marker = "\n## Score por dimensao"
    if marker in markdown:
        return markdown.replace(marker, block + marker, 1)
    return markdown + block


def append_dcf_sensitivity_to_html(html: str, valuations: Iterable[ValuationResult]) -> str:
    rows = dcf_sensitivity_table(valuations)
    if not rows:
        return html
    columns = sorted({column for row in rows for column in dict(row["values"]).keys()})
    header = "<tr><th>WACC \\ g terminal</th>" + "".join(f"<th>{escape(column)}</th>" for column in columns) + "</tr>"
    body = []
    for row in rows:
        values = dict(row["values"])
        body.append("<tr><td>" + escape(str(row["wacc"])) + "</td>" + "".join(f"<td>{escape(_fmt_money(values.get(column)))}</td>" for column in columns) + "</tr>")
    section = (
        '<section class="panel dcf-sensitivity">'
        "<h2>Matriz de sensibilidade DCF</h2>"
        f"<p>{escape(dcf_sensitivity_summary(valuations))}</p>"
        f"<table><thead>{header}</thead><tbody>{''.join(body)}</tbody></table>"
        "</section>"
    )
    marker = '<section class="panel">\n<h2>Cenarios</h2>'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    marker = '<section class="panel">\n<h2>Score por dimensao</h2>'
    if marker in html:
        return html.replace(marker, section + "\n" + marker, 1)
    return html.replace("</main>", section + "\n</main>", 1)


def dcf_sensitivity_summary(valuations: Iterable[ValuationResult]) -> str:
    dcf = find_dcf_valuation(valuations)
    if dcf is None:
        return "Sem DCF conclusivo para montar a matriz de sensibilidade."
    matrix = dcf.diagnostics.get("sensitivity")
    values = [
        float(value)
        for row in matrix.values()
        for value in row.values()
        if isinstance(matrix, dict) and isinstance(row, dict) and value is not None
    ] if isinstance(matrix, dict) else []
    if not values:
        return "A matriz existe, mas nao ha valores suficientes para leitura."
    low, high = min(values), max(values)
    terminal_share = dcf.diagnostics.get("terminal_value_share")
    terminal_note = ""
    if isinstance(terminal_share, (int, float)):
        if terminal_share >= 0.75:
            terminal_note = " O valor terminal concentra grande parte do DCF, entao pequenas mudancas em WACC e crescimento terminal podem alterar bastante o preco justo."
        else:
            terminal_note = " O valor terminal nao domina sozinho o DCF, mas ainda deve ser acompanhado com cuidado."
    return f"A matriz mostra preco justo por acao entre {_fmt_money(low)} e {_fmt_money(high)} conforme WACC e crescimento terminal mudam.{terminal_note}"


def find_dcf_valuation(valuations: Iterable[ValuationResult]) -> ValuationResult | None:
    for valuation in valuations:
        if valuation.method == "dcf_fcff" and isinstance(valuation.diagnostics.get("sensitivity"), dict):
            return valuation
    return None


def _fmt_money(value: object) -> str:
    try:
        return "-" if value is None else f"${float(value):,.2f}"
    except Exception:
        return "-"
