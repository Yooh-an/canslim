"""Tests for the interactive terminal menu."""

from src.ui.terminal_app import TerminalApp, normalize_menu_choice


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
    assert normalize_menu_choice("q") == "exit"


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
