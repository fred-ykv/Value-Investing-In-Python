from datetime import date
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from fundamental_analysis.portfolio_runner import run_portfolio, validate_calendar


class RunnerTests(unittest.TestCase):
    def test_preflight_blocks_before_simulation(self):
        module = ModuleType("fundamental_analysis.benchmark_preflight")
        module.build_preflight = Mock(return_value={"status": "blocked", "blocking_reasons": ["volume ausente"]})
        with patch.dict(sys.modules, {module.__name__: module}), patch("fundamental_analysis.portfolio_runner.simulate") as engine:
            with self.assertRaisesRegex(ValueError, "volume ausente"):
                run_portfolio([], {}, {}, start=date(2020,1,1), end=date(2020,2,1))
            engine.assert_not_called()

    def test_ready_flag_does_not_authorize_unbound_inputs(self):
        module = ModuleType("fundamental_analysis.benchmark_preflight")
        module.build_preflight = Mock(return_value={"status": "ready", "blocking_reasons": []})
        with patch.dict(sys.modules, {module.__name__: module}), patch("fundamental_analysis.portfolio_runner.validate_calendar", return_value={}), patch("fundamental_analysis.portfolio_runner.simulate") as engine:
            with self.assertRaisesRegex(ValueError, "hashes"):
                run_portfolio([], {}, {}, start=date(2020,1,1), end=date(2020,2,1))
            engine.assert_not_called()

