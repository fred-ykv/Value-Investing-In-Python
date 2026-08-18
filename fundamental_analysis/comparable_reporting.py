"""Readable report helpers for market comparables."""
from __future__ import annotations

from html import escape

from .comparables import ComparableReport


BASIS_LABELS = {
    "approved_peer_medians": "medianas de pares aprovados",
    "sector_benchmark": "benchmark setorial de referencia",
    "unavailable": "comparacao indisponivel",
}


def comparable_diagnostics_table(comparables: ComparableReport) -> dict[str, object]:
    return {
        "basis": comparables.basis,
        "basis_label": comparable_basis_label(comparables),
        "benchmark_key": comparables.benchmark_key,
        "diagnostics": list(comparables.diagnostics),
    }


def append_comparable_diagnostics_to_markdown(markdown: str, comparables: ComparableReport) -> str:
    block = comparable_markdown_block(comparables)
    if not block:
        return markdown
    marker = "\n## Score por dimensao"
    if marker in markdown:
        return markdown.replace(marker, block + "\n" + marker, 1)
    return markdown + block


def append_comparable_diagnostics_to_html(html: str, comparables: ComparableReport) -> str:
    block = comparable_html_block(comparables)
    if not block:
        return html
    marker = "<section class=\"panel\">\n<h2>Riscos principais</h2>"
    if marker in html:
        return html.replace(marker, block + marker, 1)
    if "</main>" in html:
        return html.replace("</main>", block + "</main>", 1)
    return html + block


def comparable_markdown_block(comparables: ComparableReport) -> str:
    lines = [
        "",
        "**Base dos comparaveis:** " + comparable_basis_label(comparables) + ".",
    ]
    if comparables.benchmark_key:
        lines.append(f"**Categoria de referencia:** `{comparables.benchmark_key}`.")
    for diagnostic in comparables.diagnostics:
        lines.append(f"- {diagnostic}")
    return "\n".join(lines) + "\n"


def comparable_html_block(comparables: ComparableReport) -> str:
    diagnostics = "".join(f"<li>{escape(item)}</li>" for item in comparables.diagnostics)
    benchmark = ""
    if comparables.benchmark_key:
        benchmark = f"<p><strong>Categoria de referencia:</strong> {escape(comparables.benchmark_key)}</p>"
    return (
        "<section class=\"panel\"><h2>Leitura dos comparaveis</h2>"
        f"<p><strong>Base dos comparaveis:</strong> {escape(comparable_basis_label(comparables))}.</p>"
        f"{benchmark}"
        f"<ul>{diagnostics}</ul>"
        "</section>"
    )


def comparable_basis_label(comparables: ComparableReport) -> str:
    return BASIS_LABELS.get(comparables.basis, comparables.basis.replace("_", " "))
