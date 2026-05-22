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
