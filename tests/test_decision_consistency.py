import unittest
from types import SimpleNamespace

from fundamental_analysis.decision_consistency import audit_decision_consistency, append_decision_consistency_to_markdown


def scenario(key, margin):
    return SimpleNamespace(key=key, margin_of_safety=margin)


class DecisionConsistencyTests(unittest.TestCase):
    def test_buy_with_all_negative_scenarios_is_explicitly_conflicting(self):
        audit = audit_decision_consistency("Comprar", [scenario("base", -0.20), scenario("optimistic", -0.05)], ["Risco critico: DCF usou fallback"])
        self.assertEqual(audit.overall_status, "conflitante")
        self.assertEqual(audit.scenario_status, "conflitante")
        self.assertEqual(audit.critical_risk_count, 1)
        self.assertEqual(len(audit.warnings), 2)

    def test_buy_with_positive_base_is_coherent_without_critical_risk(self):
        audit = audit_decision_consistency("Comprar", [scenario("base", 0.10), scenario("optimistic", 0.20)], ["Liquidez adequada"])
        self.assertEqual(audit.overall_status, "coerente")
        self.assertFalse(audit.warnings)

    def test_missing_scenarios_are_inconclusive(self):
        audit = audit_decision_consistency("Observar", [], [])
        self.assertEqual(audit.overall_status, "inconclusivo")
        self.assertEqual(audit.available_scenario_count, 0)

    def test_markdown_explains_conflict(self):
        audit = audit_decision_consistency("Comprar", [scenario("base", -0.10)], [])
        output = append_decision_consistency_to_markdown("## Notas explicativas", audit)
        self.assertIn("Coerencia da decisao", output)
        self.assertIn("depende de premissas diferentes", output)


if __name__ == "__main__":
    unittest.main()

