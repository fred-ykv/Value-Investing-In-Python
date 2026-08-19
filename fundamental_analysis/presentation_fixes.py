"""Small presentation fixes applied after base report rendering."""
from __future__ import annotations

import re


def apply_presentation_fixes_to_markdown(markdown: str) -> str:
    markdown = _fix_indicator_markdown(markdown)
    return _fix_source_markdown_values(markdown)


def apply_presentation_fixes_to_html(html: str) -> str:
    html = _fix_indicator_html(html)
    return _fix_source_html_values(html)


def _fix_indicator_markdown(markdown: str) -> str:
    old_header = "| Grupo | Indicador | Valor | Sinal | Fonte | Confianca | Leitura |"
    if old_header not in markdown or "Fontes dos indicadores:" in markdown:
        return markdown
    lines = markdown.splitlines()
    output: list[str] = []
    sources: dict[str, int] = {}
    in_table = False
    for line in lines:
        if line == old_header:
            in_table = True
            output.append("| Grupo | Indicador | Valor | Sinal | Por que | Confianca | Fonte |")
            continue
        if in_table and line == "|---|---|---:|---|---|---:|---|":
            output.append("|---|---|---:|---|---|---:|---|")
            continue
        if in_table and line.startswith("| "):
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) == 7:
                group, indicator, value, signal, source, confidence, reading = parts
                source_ref = _source_ref(sources, source)
                output.append(f"| {group} | {indicator} | {value} | {signal} | {reading} | {confidence} | [{source_ref}] |")
                continue
        if in_table:
            output.append(_markdown_source_note(sources))
            in_table = False
        output.append(line)
    if in_table:
        output.append(_markdown_source_note(sources))
    return "\n".join(output)


def _fix_source_markdown_values(markdown: str) -> str:
    lines = markdown.splitlines()
    output = []
    in_sources = False
    for line in lines:
        if line.startswith("| Metrica | Valor usado | Fonte legivel |"):
            in_sources = True
            output.append(line)
            continue
        if in_sources and line.startswith("| ") and not line.startswith("|---"):
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) >= 8:
                currency = parts[7]
                if currency and currency != "-" and not parts[1].startswith(f"{currency} "):
                    parts[1] = _prefix_currency(parts[1], currency)
                output.append("| " + " | ".join(parts) + " |")
                continue
        if in_sources and not line.startswith("|"):
            in_sources = False
        output.append(line)
    return "\n".join(output)


def _fix_indicator_html(html: str) -> str:
    if "Fontes dos indicadores:" in html or "Por que</th>" in html:
        return html
    pattern = re.compile(r'(<table class="indicator-table"><thead><tr>)(.*?)(</tr></thead><tbody>)(.*?)(</tbody></table>)', re.DOTALL)

    def replace_table(match: re.Match[str]) -> str:
        body = match.group(4)
        sources: dict[str, int] = {}
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", body, flags=re.DOTALL):
            cells = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) != 7:
                rows.append(f"<tr>{row}</tr>")
                continue
            source_ref = _source_ref(sources, _strip_tags(cells[4]))
            reordered = [cells[0], cells[1], cells[2], cells[3], cells[6], cells[5], f"[{source_ref}]"]
            rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in reordered) + "</tr>")
        header = "".join(f"<th>{item}</th>" for item in ["Grupo", "Indicador", "Valor", "Sinal", "Por que", "Confianca", "Fonte"])
        note = _html_source_note(sources)
        return f'{match.group(1)}{header}{match.group(3)}{"".join(rows)}{match.group(5)}{note}'

    return pattern.sub(replace_table, html, count=1)


def _fix_source_html_values(html: str) -> str:
    section_pattern = re.compile(r"(<h2>Fontes dos dados principais</h2>.*?<tbody>)(.*?)(</tbody></table>)", re.DOTALL)

    def replace_section(match: re.Match[str]) -> str:
        body = match.group(2)
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", body, flags=re.DOTALL):
            cells = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) >= 3:
                currency = _currency_from_text(_strip_tags(cells[2]))
                if currency and not _strip_tags(cells[1]).startswith(f"{currency} "):
                    cells[1] = _prefix_currency(_strip_tags(cells[1]), currency)
                rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
            else:
                rows.append(f"<tr>{row}</tr>")
        return f"{match.group(1)}{''.join(rows)}{match.group(3)}"

    return section_pattern.sub(replace_section, html, count=1)


def _source_ref(sources: dict[str, int], source: str) -> int:
    key = source or "Fonte indisponivel"
    if key not in sources:
        sources[key] = len(sources) + 1
    return sources[key]


def _markdown_source_note(sources: dict[str, int]) -> str:
    if not sources:
        return ""
    notes = " ".join(f"[{ref}] {source}" for source, ref in sources.items())
    return f"\n<small>Fontes dos indicadores: {notes}</small>"


def _html_source_note(sources: dict[str, int]) -> str:
    if not sources:
        return ""
    notes = " ".join(f"<span>[{ref}] {source}</span>" for source, ref in sources.items())
    return f'<p class="indicator-source-notes">Fontes dos indicadores: {notes}</p>'


def _prefix_currency(value: str, currency: str) -> str:
    if value in {"", "-"}:
        return value
    return f"{currency} {value.lstrip('$').strip()}"


def _currency_from_text(text: str) -> str | None:
    match = re.search(r"moeda\s+([A-Z]{3})", text)
    return match.group(1) if match else None


def _strip_tags(value: str) -> str:
    return re.sub(r"<.*?>", "", value).strip()
