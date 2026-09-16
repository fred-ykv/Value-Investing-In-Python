from datetime import date
import unittest
from fundamental_analysis.portfolio_simulator import Bar, Event, Signal, simulate, ExecutionRules


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.days = [date(2020, 1, 31), date(2020, 2, 3), date(2020, 2, 4)]
        self.signals = {self.days[0]: [Signal("A", "industrial", .8, self.days[0])]}
        self.bars = {(d, "A"): Bar(100., 100000) for d in self.days}

    def test_next_session_cost_and_accounting(self):
        r = simulate(self.days, self.signals, self.bars)
        self.assertEqual(r["ledger"][0]["date"], "2020-02-03")
        self.assertEqual(r["total_cost"], 5.)
        self.assertEqual(r["equity_curve"][-1]["nav"], 99995.)

    def test_future_signal_and_missing_volume_rejected(self):
        with self.assertRaises(ValueError):
            simulate(self.days, {self.days[0]: [Signal("A", "x", .8, self.days[1])]}, self.bars)
        self.bars[(self.days[1], "A")] = Bar(100., None)
        with self.assertRaises(ValueError):
            simulate(self.days, self.signals, self.bars)

    def test_cancellation_and_cash_acquisition(self):
        for kind, price, nav in [("cancelled_zero", 0., 94995.), ("cash_acquisition", 110., 100495.)]:
            r = simulate(self.days, self.signals, self.bars, {self.days[-1]: [Event("A", kind, price)]})
            self.assertEqual(r["equity_curve"][-1]["nav"], nav)
            self.assertEqual(r["equity_curve"][-1]["holdings"], {})

    def test_liquidity_and_sector_cap(self):
        self.bars[(self.days[1], "A")] = Bar(100., 10)
        with self.assertRaises(ValueError):
            simulate(self.days, self.signals, self.bars)
        signals = {self.days[0]: [Signal(str(i), "same", .8, self.days[0]) for i in range(6)]}
        bars = {(d, str(i)): Bar(100., 100000) for d in self.days for i in range(6)}
        r = simulate(self.days, signals, bars)
        self.assertEqual(len(r["equity_curve"][-1]["holdings"]), 5)

