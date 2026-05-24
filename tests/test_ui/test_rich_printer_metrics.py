"""Tests for metric coverage rendering."""

from io import StringIO

from rich.console import Console

from src.ui import rich_printer


def test_print_metrics_stats_hides_insider_section_when_disabled():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=120)
    try:
        rich_printer.print_metrics_stats(
            {"quarterly_eps_growth": 1, "insider_buy_count_90d": 1, "net_insider_buy_value_90d": 1},
            10,
            include_insider=False,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "내부자" not in rendered
    assert "insider_buy_count_90d" not in rendered
    assert "quarterly_eps_growth" in rendered


def test_print_metrics_stats_shows_short_interest_coverage_when_enabled():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=120)
    try:
        rich_printer.print_metrics_stats(
            {"short_interest": 3, "short_percent_float": 2, "short_days_to_cover": 1},
            10,
            include_short_interest=True,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "공매도" in rendered
    assert "short_interest" in rendered
    assert "short_percent_float" in rendered


def test_print_metrics_stats_can_hide_short_interest_section():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=120)
    try:
        rich_printer.print_metrics_stats(
            {"short_interest": 3, "quarterly_eps_growth": 1},
            10,
            include_short_interest=False,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "공매도" not in rendered
    assert "short_interest" not in rendered
    assert "quarterly_eps_growth" in rendered


def test_print_results_table_adds_short_columns_when_any_result_has_short_data():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=160)
    try:
        rich_printer.print_results_table(
            [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "canslim_score": 91.2,
                    "score_band": "A",
                    "quarterly_eps_growth": 0.5,
                    "annual_eps_cagr": 0.3,
                    "revenue_growth": 0.4,
                    "rs_rating": 95,
                    "price_vs_52w_high": 0.98,
                    "market_cap": 1_000_000_000,
                    "short_percent_shares_outstanding": 0.12,
                    "short_days_to_cover": 4.5,
                },
                {
                    "ticker": "BBB",
                    "name": "Beta",
                    "canslim_score": 82.0,
                    "score_band": "B",
                    "quarterly_eps_growth": 0.4,
                    "annual_eps_cagr": 0.25,
                    "revenue_growth": 0.2,
                    "rs_rating": 88,
                    "price_vs_52w_high": 0.91,
                    "market_cap": 2_000_000_000,
                }
            ],
            2,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "Short%" in rendered
    assert "DTC" in rendered
    assert "12.0%SO" in rendered
    assert "4.5" in rendered
    assert "미수집" in rendered


def test_print_results_table_renders_zero_short_interest_as_zero():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=160)
    try:
        rich_printer.print_results_table(
            [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "canslim_score": 91.2,
                    "score_band": "A",
                    "quarterly_eps_growth": 0.5,
                    "annual_eps_cagr": 0.3,
                    "revenue_growth": 0.4,
                    "rs_rating": 95,
                    "price_vs_52w_high": 0.98,
                    "market_cap": 1_000_000_000,
                    "short_interest": 0,
                }
            ],
            1,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "Short%" in rendered
    assert "0.0%" in rendered
    assert "0" in rendered


def test_print_results_table_hides_short_columns_when_no_result_has_short_data():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=160)
    try:
        rich_printer.print_results_table(
            [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "canslim_score": 91.2,
                    "score_band": "A",
                    "quarterly_eps_growth": 0.5,
                    "annual_eps_cagr": 0.3,
                    "revenue_growth": 0.4,
                    "rs_rating": 95,
                    "price_vs_52w_high": 0.98,
                    "market_cap": 1_000_000_000,
                }
            ],
            1,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "Short%" not in rendered
    assert "DTC" not in rendered


def test_print_results_table_adds_short_columns_when_hidden_result_has_short_data():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=160)
    try:
        rich_printer.print_results_table(
            [
                {
                    "ticker": "AAA",
                    "name": "Alpha",
                    "canslim_score": 91.2,
                    "score_band": "A",
                    "quarterly_eps_growth": 0.5,
                    "annual_eps_cagr": 0.3,
                    "revenue_growth": 0.4,
                    "rs_rating": 95,
                    "price_vs_52w_high": 0.98,
                    "market_cap": 1_000_000_000,
                },
                {
                    "ticker": "BBB",
                    "name": "Beta",
                    "canslim_score": 80.0,
                    "score_band": "B",
                    "quarterly_eps_growth": 0.4,
                    "annual_eps_cagr": 0.2,
                    "revenue_growth": 0.3,
                    "rs_rating": 88,
                    "price_vs_52w_high": 0.9,
                    "market_cap": 900_000_000,
                    "short_interest": 0,
                },
            ],
            2,
            max_display=1,
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "Short%" in rendered
    assert "DTC" in rendered
    assert "미수집" in rendered
    assert "BBB" not in rendered


def test_print_screening_criteria_hides_disabled_volume_trend_threshold():
    buffer = StringIO()
    original_console = rich_printer._console
    rich_printer._console = Console(file=buffer, force_terminal=False, width=120)
    try:
        rich_printer.print_screening_criteria(
            {},
            {},
            {},
            {},
            {
                "require_supply_demand": True,
                "up_down_volume_ratio_min": 0.9,
                "volume_trend_50_200_min": None,
            },
            {},
        )
    finally:
        rich_printer._console = original_console

    rendered = buffer.getvalue()
    assert "상승/하락 거래량 비율" in rendered
    assert "50/200 거래량 추세" not in rendered
