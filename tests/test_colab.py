import unittest
from unittest.mock import patch

from fundamental_analysis.colab import prompt_for_ticker, run_colab_analysis
from fundamental_analysis.scoring import ScoreReport


class ColabHelperTests(unittest.TestCase):
    def test_prompt_for_ticker_uses_input_and_remembers_state(self):
        state = {}

        ticker = prompt_for_ticker(state=state, input_func=lambda prompt: " mli ")

        self.assertEqual(ticker, "MLI")
        self.assertEqual(state["ticker"], "MLI")

    def test_prompt_for_ticker_falls_back_on_empty_input(self):
        state = {}

        ticker = prompt_for_ticker(default="AAPL", state=state, input_func=lambda prompt: "")

        self.assertEqual(ticker, "AAPL")
        self.assertEqual(state["ticker"], "AAPL")

    def test_run_colab_analysis_prompts_runs_and_saves(self):
        class DummyResult:
            ticker = "MSFT"
            report = {"html": "<h1>MSFT</h1>"}
            score = ScoreReport(total_score=0.72, recommendation="Comprar", dimensions={})

        with patch("fundamental_analysis.colab.analyze_ticker_live", return_value=DummyResult()) as analyze, patch(
            "fundamental_analysis.colab.save_report_artifacts",
            return_value={"html": "outputs/MSFT_analysis.html"},
        ) as save:
            payload = run_colab_analysis(
                state={},
                show_html=False,
                input_func=lambda prompt: "msft",
            )

        analyze.assert_called_once_with("MSFT")
        save.assert_called_once_with("MSFT", {"html": "<h1>MSFT</h1>"}, "outputs")
        self.assertEqual(payload["ticker"], "MSFT")
        self.assertEqual(payload["artifacts"]["html"], "outputs/MSFT_analysis.html")


if __name__ == "__main__":
    unittest.main()
