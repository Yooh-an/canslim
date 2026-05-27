"""Tests for the interactive terminal menu."""

import logging
from types import SimpleNamespace

from src.ui.terminal_app import TerminalApp, normalize_menu_choice, normalize_profile_choice


class IO:
    def __init__(self, inputs):
        self.inputs = list(inputs)
        self.outputs = []

    def input(self, prompt=""):
        self.outputs.append(prompt)
        return self.inputs.pop(0)

    def print(self, *args, **kwargs):
        self.outputs.append(" ".join(str(arg) for arg in args))


def test_normalize_menu_choice_accepts_number_and_alias():
    assert normalize_menu_choice("1") == "screen"
    assert normalize_menu_choice("ticker") == "analyze"
    assert normalize_menu_choice("dashboard") == "web"
    assert normalize_menu_choice("q") == "exit"


def test_normalize_profile_choice_rejects_unknown_choice():
    profiles = {"canslim_pure", "canslim_watchlist", "canslim_score_rank"}

    assert (
        normalize_profile_choice(
            "",
            default="canslim_watchlist",
            available_profiles=profiles,
        )
        == "canslim_watchlist"
    )
    assert (
        normalize_profile_choice(
            "2",
            default="canslim_watchlist",
            available_profiles=profiles,
        )
        == "canslim_watchlist"
    )
    assert (
        normalize_profile_choice(
            "canslim_score_rank",
            default="canslim_watchlist",
            available_profiles=profiles,
        )
        == "canslim_score_rank"
    )
    assert (
        normalize_profile_choice(
            "4",
            default="canslim_watchlist",
            available_profiles=profiles,
        )
        is None
    )


def test_terminal_app_can_exit_from_menu():
    io = IO(["0"])
    app = TerminalApp(input_func=io.input, print_func=io.print)

    app.run()

    joined = "\n".join(io.outputs)
    assert "CAN SLIM Terminal" in joined
    assert "종료" in joined


def test_terminal_app_runs_ticker_analysis_with_selected_profile():
    io = IO(["2", "STRL", "", "0"])
    calls = []

    def analyze_action(ticker, profile):
        calls.append((ticker, profile))
        return f"analysis for {ticker} using {profile}"

    app = TerminalApp(input_func=io.input, print_func=io.print, analyze_action=analyze_action)

    app.run()

    assert calls == [("STRL", "canslim_pure")]
    assert "analysis for STRL using canslim_pure" in "\n".join(io.outputs)


def test_terminal_app_runs_screen_with_watchlist_profile():
    io = IO(["1", "2", "0"])
    calls = []

    def screen_action(profile):
        calls.append(profile)
        return "screen done"

    app = TerminalApp(input_func=io.input, print_func=io.print, screen_action=screen_action)

    app.run()

    assert calls == ["canslim_watchlist"]
    assert "screen done" in "\n".join(io.outputs)


def test_terminal_app_reprompts_for_invalid_profile_choice():
    io = IO(["4", "4", "2", "0"])
    calls = []

    def update_action(profile):
        calls.append(profile)
        return "update done"

    app = TerminalApp(
        input_func=io.input,
        print_func=io.print,
        update_action=update_action,
    )

    app.run()

    assert calls == ["canslim_watchlist"]
    joined = "\n".join(io.outputs)
    assert "알 수 없는 프로필" in joined
    assert "update done" in joined


def test_terminal_app_runs_web_dashboard_action():
    io = IO(["5", "0"])
    calls = []

    def web_action():
        calls.append("web")
        return "dashboard started"

    app = TerminalApp(input_func=io.input, print_func=io.print, web_action=web_action)

    app.run()

    assert calls == ["web"]
    joined = "\n".join(io.outputs)
    assert "웹 대시보드" in joined
    assert "dashboard started" in joined


def test_ensure_logger_initializes_growth_screener_logger():
    module = SimpleNamespace()

    TerminalApp._ensure_logger(module)

    assert module.logger.name == "growth_stock_screener"
    assert module.logger.level == logging.INFO
