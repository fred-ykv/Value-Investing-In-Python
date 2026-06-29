"""Google Colab helpers for interactive analysis runs."""
from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from .main import AnalysisResult, analyze_ticker_live
from .reports import save_report_artifacts


def prompt_for_ticker(
    *,
    default: str = "MLI",
    state: MutableMapping[str, Any] | None = None,
    input_func: Callable[[str], str] = input,
) -> str:
    """Ask for a ticker and remember it in a notebook-friendly state dict."""
    try:
        symbol = input_func("Digite o ticker: ").strip().upper()
        if not symbol:
            raise ValueError("Ticker vazio")
    except Exception:
        symbol = default.strip().upper()

    if state is not None:
        state["ticker"] = symbol
    return symbol


def run_colab_analysis(
    *,
    default_ticker: str = "MLI",
    output_dir: str = "outputs",
    state: MutableMapping[str, Any] | None = None,
    show_html: bool = True,
    download: bool = False,
    input_func: Callable[[str], str] = input,
) -> dict[str, Any]:
    """Prompt for a ticker, run live analysis, show HTML, and save artifacts."""
    symbol = prompt_for_ticker(default=default_ticker, state=state, input_func=input_func)
    result = analyze_ticker_live(symbol)
    artifacts = save_report_artifacts(result.ticker, result.report, output_dir)

    if show_html:
        display_html(result.report["html"])
    if download:
        download_artifacts(artifacts)

    print(f"Ticker selecionado: {result.ticker}")
    print(f"Recomendacao final: {result.score.recommendation} | Score: {result.score.total_score:.2f}")
    return {"ticker": symbol, "result": result, "artifacts": artifacts}


def display_html(html: object) -> None:
    try:
        from IPython.display import HTML, display  # type: ignore

        display(HTML(str(html)))
    except Exception:
        print(str(html))


def download_artifacts(artifacts: dict[str, str]) -> None:
    try:
        from google.colab import files  # type: ignore
    except Exception:
        print("Download automatico disponivel apenas no Google Colab.")
        return
    for path in artifacts.values():
        files.download(path)


__all__ = ["prompt_for_ticker", "run_colab_analysis"]
