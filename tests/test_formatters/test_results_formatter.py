"""Tests for CAN SLIM result formatting and reports."""

from pathlib import Path

import pandas as pd

from src.formatters.results_formatter import ResultsFormatter


def _formatter(tmp_path):
    return ResultsFormatter({"data_paths": {"output_file": str(tmp_path / "results.csv")}})


def test_format_results_includes_canslim_scorecard_and_trade_plan_columns(tmp_path):
    formatter = _formatter(tmp_path)
    df = pd.DataFrame(
        [
            {
                "ticker": "test",
                "name": "Test Corp",
                "canslim_score": 87.4,
                "score_band": "strong",
                "c_score": 90,
                "a_score": 80,
                "n_score": 75,
                "s_score": 70,
                "l_score": 95,
                "i_score": 65,
                "m_score": 100,
                "buy_zone_low": 100,
                "buy_zone_high": 105,
                "stop_loss_price": 92,
                "institutional_accumulation_score": 72,
                "insider_signal": "net_buying",
                "pass_reasons": ["C: current quarterly earnings growth", "L: RS rating leadership"],
                "fail_reasons": [],
            }
        ]
    )

    formatted = formatter.format_results(df)

    assert formatted.loc[0, "ticker"] == "TEST"
    assert "canslim_score" in formatted.columns
    assert "c_score" in formatted.columns
    assert "buy_zone_high" in formatted.columns
    assert "pass_reasons" in formatted.columns
    assert formatted.loc[0, "pass_reasons"] == "C: current quarterly earnings growth; L: RS rating leadership"


def test_create_report_writes_markdown_summary_next_to_csv(tmp_path):
    formatter = _formatter(tmp_path)
    df = pd.DataFrame(
        [
            {
                "ticker": "TEST",
                "name": "Test Corp",
                "canslim_score": 91.2,
                "score_band": "exceptional",
                "c_score": 95,
                "a_score": 90,
                "n_score": 85,
                "s_score": 80,
                "l_score": 99,
                "i_score": 75,
                "m_score": 100,
                "buy_zone_low": 100,
                "buy_zone_high": 105,
                "stop_loss_price": 92,
                "pass_reasons": ["C: current quarterly earnings growth"],
                "fail_reasons": ["I: insufficient institutional sponsorship"],
            }
        ]
    )

    output_path = formatter.create_report(df)
    markdown_path = Path(output_path).with_suffix(".md")

    assert markdown_path.exists()
    content = markdown_path.read_text()
    assert "# CAN SLIM Screening Report" in content
    assert "TEST" in content
    assert "C/A/N/S/L/I/M" in content
    assert "I: insufficient institutional sponsorship" in content
