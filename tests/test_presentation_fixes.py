import unittest

from fundamental_analysis.presentation_fixes import apply_presentation_fixes_to_html, apply_presentation_fixes_to_markdown


class PresentationFixesTests(unittest.TestCase):
    def test_markdown_indicator_sources_are_numbered_and_discreet(self):
        markdown = "\n".join(
            [
                "| Grupo | Indicador | Valor | Sinal | Fonte | Confianca | Leitura |",
                "|---|---|---:|---|---|---:|---|",
                "| Valuation | P/L | 16.0000 | Neutro | Yahoo Finance, moeda USD | 0.85 | Preco dividido pelo lucro. |",
                "",
            ]
        )

        fixed = apply_presentation_fixes_to_markdown(markdown)

        self.assertIn("| Grupo | Indicador | Valor | Sinal | Por que | Confianca | Fonte |", fixed)
        self.assertIn("| Valuation | P/L | 16.0000 | Neutro | Preco dividido pelo lucro. | 0.85 | [1] |", fixed)
        self.assertIn("Fontes dos indicadores: [1] Yahoo Finance, moeda USD", fixed)

    def test_markdown_source_values_show_friendly_metric_currency_and_numbered_sources(self):
        markdown = "\n".join(
            [
                "| Metrica | Valor usado | Fonte legivel | Fonte tecnica | Base | Fallback | Periodo | Moeda | Confianca | Formula | Observacao |",
                "|---|---:|---|---|---|---|---|---|---:|---|---|",
                "| cash | 35,934,000,000.0000 | Yahoo Finance, moeda USD | yfinance | reported | nao | - | USD | 0.85 | - | - |",
            ]
        )

        fixed = apply_presentation_fixes_to_markdown(markdown)

        self.assertIn("| Metrica | Valor usado | Base | Periodo | Moeda | Confianca | Fonte |", fixed)
        self.assertIn("| Caixa | US$ 35,934,000,000.00 | Informado pela fonte | - | USD | 0.85 | [1] |", fixed)
        self.assertIn("Fontes dos dados principais: [1] Yahoo Finance, moeda USD", fixed)

    def test_html_indicator_sources_are_numbered_and_discreet(self):
        html = (
            '<table class="indicator-table"><thead><tr>'
            "<th>Grupo</th><th>Indicador</th><th>Valor</th><th>Sinal</th><th>Fonte</th><th>Confianca</th><th>Leitura</th>"
            "</tr></thead><tbody>"
            "<tr><td>Valuation</td><td>P/L</td><td>16.0000</td><td><span>Neutro</span></td><td>Yahoo Finance, moeda USD</td><td>0.85</td><td>Preco dividido pelo lucro.</td></tr>"
            "</tbody></table>"
        )

        fixed = apply_presentation_fixes_to_html(html)

        self.assertIn("<th>Por que</th>", fixed)
        self.assertIn("<td>Preco dividido pelo lucro.</td><td>0.85</td><td>[1]</td>", fixed)
        self.assertIn("Fontes dos indicadores:", fixed)

    def test_html_source_values_show_friendly_metric_currency_and_numbered_sources(self):
        html = (
            "<h2>Fontes dos dados principais</h2><table><tbody>"
            "<tr><td>cash</td><td>35,934,000,000.0000</td><td>Yahoo Finance, moeda USD</td><td>reported</td><td>0.85</td></tr>"
            "</tbody></table>"
        )

        fixed = apply_presentation_fixes_to_html(html)

        self.assertIn("<th>Metrica</th><th>Valor usado</th><th>Base</th><th>Confianca</th><th>Fonte</th>", fixed)
        self.assertIn("<td>Caixa</td><td>US$ 35,934,000,000.00</td><td>Informado pela fonte</td><td>0.85</td><td>[1]</td>", fixed)
        self.assertIn("Fontes dos dados principais:", fixed)

    def test_remaining_english_score_explanations_are_translated(self):
        html = "Balance sheet leverage. Average confidence of sources and derived metrics."

        fixed = apply_presentation_fixes_to_html(html)

        self.assertIn("Avalia a alavancagem do balanco", fixed)
        self.assertIn("Mede a confianca media das fontes", fixed)


if __name__ == "__main__":
    unittest.main()
