from datetime import date
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

from fundamental_analysis.portfolio_runner import input_hashes, run_portfolio, validate_calendar
from fundamental_analysis.portfolio_simulator import Bar, ExecutionRules, Signal


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
            with self.assertRaisesRegex(ValueError, "atestado completo"):
                run_portfolio([], {}, {}, start=date(2020,1,1), end=date(2020,2,1))
            engine.assert_not_called()

    def test_bound_inputs_reach_simulator_and_return_attestation(self):
        sessions = (date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3))
        signals = {date(2020, 1, 31): (Signal("AAA", "industrial", 0.8, date(2020, 1, 31)),)}
        bars = {(day, "AAA"): Bar(10.0, 100000) for day in sessions}
        rules = ExecutionRules()
        hashes = input_hashes(sessions, signals, bars, None, rules)
        preflight = ModuleType("fundamental_analysis.benchmark_preflight")
        preflight.build_preflight = Mock(return_value={
            "status": "ready", "blocking_reasons": [], "portfolio_input_hashes": hashes,
            "calendar_sessions_sha256": "calendar-hash", "experiment_id": "exp", "manifest_version": "1.1",
        })
        engine_result = {"ledger": [], "equity_curve": []}
        with patch.dict(sys.modules, {preflight.__name__: preflight}), \
                patch("fundamental_analysis.portfolio_runner.validate_calendar", return_value={"sessions_sha256": "calendar-hash"}), \
                patch("fundamental_analysis.portfolio_runner.simulate", return_value=engine_result) as engine:
            result = run_portfolio(sessions, signals, bars, start=sessions[0], end=sessions[-1], rules=rules)
        engine.assert_called_once()
        self.assertEqual(result["input_attestation"]["portfolio_input_hashes"], hashes)
        self.assertEqual(result["input_attestation"]["preflight_experiment_id"], "exp")

    def test_tampering_after_attestation_is_rejected(self):
        sessions = (date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3))
        signals = {}
        bars = {}
        rules = ExecutionRules()
        hashes = input_hashes(sessions, signals, bars, None, rules)
        preflight = ModuleType("fundamental_analysis.benchmark_preflight")
        preflight.build_preflight = Mock(return_value={
            "status": "ready", "blocking_reasons": [], "portfolio_input_hashes": hashes,
            "calendar_sessions_sha256": "calendar-hash",
        })
        changed = ExecutionRules(cost_bps=25.0)
        with patch.dict(sys.modules, {preflight.__name__: preflight}), \
                patch("fundamental_analysis.portfolio_runner.validate_calendar", return_value={"sessions_sha256": "calendar-hash"}), \
                patch("fundamental_analysis.portfolio_runner.simulate") as engine:
            with self.assertRaisesRegex(ValueError, "rules"):
                run_portfolio(sessions, signals, bars, start=sessions[0], end=sessions[-1], rules=changed)
        engine.assert_not_called()

    def test_calendar_hash_must_match_preflight(self):
        sessions = (date(2020, 1, 30), date(2020, 1, 31), date(2020, 2, 3))
        rules = ExecutionRules()
        hashes = input_hashes(sessions, {}, {}, None, rules)
        preflight = ModuleType("fundamental_analysis.benchmark_preflight")
        preflight.build_preflight = Mock(return_value={
            "status": "ready", "blocking_reasons": [], "portfolio_input_hashes": hashes,
            "calendar_sessions_sha256": "approved",
        })
        with patch.dict(sys.modules, {preflight.__name__: preflight}), \
                patch("fundamental_analysis.portfolio_runner.validate_calendar", return_value={"sessions_sha256": "changed"}), \
                patch("fundamental_analysis.portfolio_runner.simulate") as engine:
            with self.assertRaisesRegex(ValueError, "Calendario diverge"):
                run_portfolio(sessions, {}, {}, start=sessions[0], end=sessions[-1], rules=rules)
        engine.assert_not_called()

