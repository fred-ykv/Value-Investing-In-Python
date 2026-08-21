"""Small presentation fixes applied after base report rendering."""
from __future__ import annotations

from html import escape
import re


METRIC_LABELS = {
    "price": "Preco Atual",
    "revenue": "Receita",
    "ebit": "EBIT",
    "net_income": "Lucro Liquido",
    "fcff": "Fluxo de Caixa Livre para a Firma",
    "free_cash_flow_after_capex": "Fluxo de Caixa Livre apos CAPEX",
    "total_assets": "Ativos Totais",
    "total_debt": "Divida Total",
    "cash": "Caixa",
    "shares": "Numero de Acoes",
    "market_cap": "Valor de Mercado",
    "equity": "Patrimonio Liquido",
    "current_assets": "Ativos Circulantes",
    "current_liabilities": "Passivos Circulantes",
    "total_liabilities": "Passivos Totais",
}

MONEY_METRICS = {
    "price",
    "revenue",
    "ebit",
    "net_income",
    "fcff",
    "free_cash_flow_after_capex",
    "total_assets",
    "total_debt",
    "cash",
    "market_cap",
    "equity",
    "current_assets",
    "current_liabilities",
    "total_liabilities",
}

CURRENCY_SYMBOLS = {"USD": "US$", "BRL": "R$", "EUR": "EUR", "GBP": "GBP"}


def apply_presentation_fixes_to_markdown(markdown: str) -> str:
    markdown = _fix_indicator_markdown(markdown)
    markdown = _fix_source_markdown_values(markdown)
    return _translate_remaining_english(markdown)


def apply_presentation_fixes_to_html(html: str) -> str:
    html = _fix_indicator_html(html)
    html = _fix_source_html_values(html)
    return _translate_remaining_english(html)


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
            output.append(_markdown_source_note("Fontes dos indicadores", sources))
            in_table = False
        output.append(line)
    if in_table:
        output.append(_markdown_source_note("Fontes dos indicadores", sources))
    return "\n".join(output)


def _fix_source_markdown_values(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    sources: dict[str, int] = {}
    in_sources = False
    source_header_seen = False
    for line in lines:
        if line.startswith("| Metrica | Valor usado | Fonte legivel |"):
            in_sources = True
            source_header_seen = True
            output.append("| Metrica | Valor usado | Base | Periodo | Moeda | Confianca | Fonte |")
            continue
        if in_sources and line.startswith("|---"):
            output.append("|---|---:|---|---|---|---:|---|")
            continue
        if in_sources and line.startswith("| "):
            parts = [part.strip() for part in line.strip("|").split("|")]
            if len(parts) >= 9:
                metric, value, readable_source, _technical_source, basis, _fallback, period, currency, confidence = parts[:9]
                source_ref = _source_ref(sources, readable_source)
                value = _format_metric_value(metric, value, currency)
                output.append(
                    f"| {_metric_label(metric)} | {value} | {_friendly_basis(basis)} | {period or '-'} | {currency or '-'} | {confidence} | [{source_ref}] |"
                )
                continue
        if in_sources and not line.startswith("|"):
            output.append(_markdown_source_note("Fontes dos dados principais", sources))
            in_sources = False
        output.append(line)
    if in_sources and source_header_seen:
        output.append(_markdown_source_note("Fontes dos dados principais", sources))
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
        note = _html_source_note("Fontes dos indicadores", sources)
        return f'{match.group(1)}{header}{match.group(3)}{"".join(rows)}{match.group(5)}{note}'

    return pattern.sub(replace_table, html, count=1)


def _fix_source_html_values(html: str) -> str:
    section_pattern = re.compile(r"(<h2>Fontes dos dados principais</h2>.*?<table>)(.*?<thead><tr>.*?</tr></thead>)?(<tbody>)(.*?)(</tbody></table>)", re.DOTALL)

    def replace_section(match: re.Match[str]) -> str:
        body = match.group(4)
        sources: dict[str, int] = {}
        rows = []
        for row in re.findall(r"<tr>(.*?)</tr>", body, flags=re.DOTALL):
            cells = re.findall(r"<td>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) >= 5:
                metric_raw = _strip_tags(cells[0])
                value_raw = _strip_tags(cells[1])
                source_raw = _strip_tags(cells[2])
                basis_raw = _strip_tags(cells[3])
                if len(cells) >= 6:
                    currency_raw = _strip_tags(cells[4])
                    confidence_raw = _strip_tags(cells[5])
                else:
                    currency_raw = ""
                    confidence_raw = _strip_tags(cells[4])
                currency = None if currency_raw in {"", "-"} else currency_raw
                currency = currency or _currency_from_text(source_raw)
                source_ref = _source_ref(sources, source_raw)
                rendered = [
                    escape(_metric_label(metric_raw)),
                    escape(_format_metric_value(metric_raw, value_raw, currency)),
                    escape(_friendly_basis(basis_raw)),
                    escape(confidence_raw),
                    escape(f"[{source_ref}]"),
                ]
                rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in rendered) + "</tr>")
            else:
                rows.append(f"<tr>{row}</tr>")
        header = "<thead><tr>" + "".join(f"<th>{item}</th>" for item in ["Metrica", "Valor usado", "Base", "Confianca", "Fonte"]) + "</tr></thead>"
        note = _html_source_note("Fontes dos dados principais", sources)
        return f"{match.group(1)}{header}{match.group(3)}{''.join(rows)}{match.group(5)}{note}"

    return section_pattern.sub(replace_section, html, count=1)


def _source_ref(sources: dict[str, int], source: str) -> int:
    key = source or "Fonte indisponivel"
    if key not in sources:
        sources[key] = len(sources) + 1
    return sources[key]


def _markdown_source_note(title: str, sources: dict[str, int]) -> str:
    if not sources:
        return ""
    notes = " ".join(f"[{ref}] {source}" for source, ref in sources.items())
    return f"\n<small>{title}: {notes}</small>"


def _html_source_note(title: str, sources: dict[str, int]) -> str:
    if not sources:
        return ""
    notes = " ".join(f"<span>[{ref}] {escape(source)}</span>" for source, ref in sources.items())
    return f'<p class="indicator-source-notes" style="color:#667385;font-size:12px;line-height:1.45;margin:10px 0 0;">{escape(title)}: {notes}</p>'


def _metric_label(metric: str) -> str:
    clean = _strip_tags(metric).strip()
    return METRIC_LABELS.get(clean, clean.replace("_", " ").title())


def _format_metric_value(metric: str, value: str, currency: str | None) -> str:
    clean_metric = _strip_tags(metric).strip()
    clean_value = _strip_tags(value).strip()
    if clean_value in {"", "-"}:
        return "-"
    numeric = _parse_number(clean_value)
    if numeric is None:
        return clean_value
    if clean_metric == "shares":
        return f"{numeric:,.0f} acoes"
    if clean_metric in MONEY_METRICS or currency:
        symbol = CURRENCY_SYMBOLS.get(str(currency or "").upper(), str(currency or "").upper())
        prefix = f"{symbol} " if symbol else ""
        return f"{prefix}{numeric:,.2f}"
    return f"{numeric:,.4f}"


def _friendly_basis(value: str) -> str:
    normalized = _strip_tags(value).strip().lower()
    labels = {
        "reported": "Informado pela fonte",
        "raw": "Valor bruto",
        "derived": "Calculado pelo modelo",
        "fallback": "Premissa fallback",
        "manual": "Entrada manual",
        "missing": "Indisponivel",
    }
    return labels.get(normalized, value or "-")


def _currency_from_text(text: str) -> str | None:
    match = re.search(r"moeda\s+([A-Z]{3})", text)
    return match.group(1) if match else None


def _parse_number(value: str) -> float | None:
    try:
        cleaned = value.replace("US$", "").replace("R$", "").replace("USD", "").replace("BRL", "")
        cleaned = cleaned.replace("acoes", "").replace("%", "").strip()
        return float(cleaned.replace(",", ""))
    except Exception:
        return None


def _strip_tags(value: str) -> str:
    return re.sub(r"<.*?>", "", value).strip()


def _translate_remaining_english(text: str) -> str:
    replacements = {
        "Blends intrinsic margin of safety with peer-relative multiples; peer signal is capped by sample confidence.": "Combina margem de seguranca dos modelos intrinsecos com multiplos relativos de pares; o peso dos comparaveis e limitado pela confianca da amostra.",
        "Balance sheet leverage.": "Avalia a alavancagem do balanco, principalmente divida sobre patrimonio e divida liquida sobre EBIT.",
        "Average confidence of sources and derived metrics.": "Mede a confianca media das fontes e das metricas derivadas; nao e probabilidade de acerto.",
        "Revenue/FCFF growth profile.": "Avalia o perfil de crescimento de receita e de fluxo de caixa livre para a firma.",
        "Profitability, accruals, and Piotroski-style quality.": "Avalia rentabilidade, qualidade do lucro, accruals e sinais inspirados no Piotroski F-Score.",
        "Short-term liquidity.": "Avalia a folga de liquidez de curto prazo.",
    }
    for english, portuguese in replacements.items():
        text = text.replace(english, portuguese)
    return text
