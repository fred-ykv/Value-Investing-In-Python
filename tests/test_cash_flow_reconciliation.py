from datetime import date
import unittest

from fundamental_analysis.cash_flow_reconciliation import (
    append_cash_flow_reconciliation_to_html,
    append_cash_flow_reconciliation_to_markdown,
    reconcile_cash_flows,
)
from fundamental_analysis.data_sources import metric_value


class CashFlowReconciliationTests(unittest.TestCase):
    def values(self, fcff=786_800_723.182, proxy=-188_000_000.0):
        kwargs = {
            "source_document": "Yahoo Finance cash flow statement",
            "period_end": date(2025, 12, 31),
            "currency": "USD",
        }
        return {
            "fcff": metric_value("fcff", fcff, "derived", confidence=0.79, **kwargs),
            "free_cash_flow_after_capex": metric_value("free_cash_flow_after_capex", proxy, "derived", confidence=0.80, **kwargs),
        }

    def test_opposite_signs_are_highlighted_without_calling_either_measure_wrong(self):
        result = reconcile_cash_flows(self.values())

        self.assertEqual(result.status, "sinais_opostos")
        self.assertEqual(result.status_label, "Atencao alta")
        self.assertGreater(result.relative_gap, 1.0)
        self.assertAlmostEqual(result.difference, 974_800_723.182)
        self.assertIn("nao representa erro", append_cash_flow_reconciliation_to_markdown("", result))

    def test_close_flows_are_marked_coherent(self):
        result = reconcile_cash_flows(self.values(fcff=100.0, proxy=90.0))

        self.assertEqual(result.status, "proximos")
        self.assertAlmostEqual(result.relative_gap, 0.10)

    def test_html_and_markdown_show_currency_and_explanation(self):
        result = reconcile_cash_flows(self.values())
        markdown = append_cash_flow_reconciliation_to_markdown("\n## Taxa de desconto utilizada", result)
        html = append_cash_flow_reconciliation_to_html('<main><section class="panel cost-of-capital"></section></main>', result)

        self.assertIn("Reconciliacao dos fluxos de caixa", markdown)
        self.assertIn("US$ 786,800,723.18", markdown)
        self.assertIn("FCFF mede o caixa operacional antes do financiamento", markdown)
        self.assertIn("cash-flow-reconciliation", html)
        self.assertIn("US$ 786,800,723.18", html)


if __name__ == "__main__":
    unittest.main()

