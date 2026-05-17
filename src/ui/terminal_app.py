"""Interactive terminal menu for common CAN SLIM workflows.

Uses the Rich library for polished, visually appealing terminal output
including colored panels, tables, progress spinners, and styled prompts.
"""

from __future__ import annotations

import io
import logging
from contextlib import redirect_stdout
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align
from rich.rule import Rule
from rich import box

from src.utils.config_loader import load_config_file
from src.utils.logger import setup_logger
from src.screeners.ticker_analysis import analyze_ticker, format_ticker_analysis
from src.utils.pipeline_status import collect_pipeline_status, format_pipeline_status


PROFILE_CHOICES = {
    "1": "canslim_pure",
    "2": "canslim_watchlist",
    "3": "canslim_hybrid",
}

MENU_CHOICES = {
    "1": "screen",
    "screen": "screen",
    "screener": "screen",
    "스크리너": "screen",
    "2": "analyze",
    "ticker": "analyze",
    "analyze": "analyze",
    "분석": "analyze",
    "3": "status",
    "status": "status",
    "상태": "status",
    "4": "update",
    "update": "update",
    "업데이트": "update",
    "0": "exit",
    "q": "exit",
    "quit": "exit",
    "exit": "exit",
    "종료": "exit",
}

# ── Visual constants ───────────────────────────────────────────────────
BANNER_ART = r"""
   ██████╗ █████╗ ███╗   ██╗    ███████╗██╗     ██╗███╗   ███╗
  ██╔════╝██╔══██╗████╗  ██║    ██╔════╝██║     ██║████╗ ████║
  ██║     ███████║██╔██╗ ██║    ███████╗██║     ██║██╔████╔██║
  ██║     ██╔══██║██║╚██╗██║    ╚════██║██║     ██║██║╚██╔╝██║
  ╚██████╗██║  ██║██║ ╚████║    ███████║███████╗██║██║ ╚═╝ ██║
   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝    ╚══════╝╚══════╝╚═╝╚═╝     ╚═╝"""

SUBTITLE = "Growth Stock Screener & Analyzer"

THEME = {
    "accent": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "muted": "dim white",
    "highlight": "bold bright_white",
}


def normalize_menu_choice(choice: str) -> str:
    """Normalize a menu input to an action key."""
    return MENU_CHOICES.get(str(choice or "").strip().lower(), "unknown")


class TerminalApp:
    """Interactive terminal application with injectable actions for tests.

    When *input_func* / *print_func* are injected (unit-tests) the app
    falls back to plain-text output so assertions can match strings.
    """

    def __init__(
        self,
        *,
        config_path: str = "config/base.json",
        default_profile: str = "canslim_pure",
        input_func: Callable[[str], str] = input,
        print_func: Callable[..., None] = print,
        screen_action: Optional[Callable[[str], str]] = None,
        analyze_action: Optional[Callable[[str, str], str]] = None,
        status_action: Optional[Callable[[str], str]] = None,
        update_action: Optional[Callable[[str], str]] = None,
    ):
        self.config_path = config_path
        self.default_profile = default_profile
        self.input = input_func
        self.print = print_func
        self.screen_action = screen_action or self._screen_action
        self.analyze_action = analyze_action or self._analyze_action
        self.status_action = status_action or self._status_action
        self.update_action = update_action or self._update_action

        # Detect whether we're in "rich mode" (real terminal) or "plain
        # mode" (test harness).  When callers inject their own print,
        # we stay plain so test assertions keep working.
        self._rich_mode = print_func is print and input_func is input
        if self._rich_mode:
            self.console = Console()
        else:
            self.console = None

    # ── Rich helpers ───────────────────────────────────────────────────

    def _rprint(self, *args, **kwargs) -> None:
        """Print via Rich console if available, else fall back to plain."""
        if self.console:
            self.console.print(*args, **kwargs)
        else:
            # Strip Rich markup for plain output
            text = " ".join(str(a) for a in args)
            self.print(text)

    def _print_banner(self) -> None:
        if not self._rich_mode:
            self.print("\n=== CAN SLIM Terminal ===")
            return

        banner_text = Text(BANNER_ART, style="bold cyan")
        subtitle = Text(f"\n  {SUBTITLE}", style="italic bright_white")
        combined = Text.assemble(banner_text, subtitle)

        panel = Panel(
            Align.center(combined),
            border_style="bright_cyan",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
        self.console.print()
        self.console.print(panel)

    def _print_menu(self) -> None:
        if not self._rich_mode:
            self.print(
                "\n1. 스크리너 실행\n"
                "2. Ticker 분석\n"
                "3. 현재 상태 확인\n"
                "4. 필요한 단계 자동 업데이트\n"
                "0. 종료"
            )
            return

        menu_items = [
            ("1", "📊", "스크리너 실행", "CAN SLIM 기준으로 종목 선별", "cyan"),
            ("2", "🔍", "Ticker 분석", "개별 종목 상세 분석", "green"),
            ("3", "📋", "현재 상태 확인", "파이프라인 데이터 현황", "yellow"),
            ("4", "🔄", "자동 업데이트", "필요한 단계 자동 실행", "magenta"),
            ("0", "🚪", "종료", "프로그램 종료", "red"),
        ]

        table = Table(
            show_header=False,
            box=box.SIMPLE_HEAVY,
            border_style="bright_cyan",
            padding=(0, 2),
            expand=True,
        )
        table.add_column("Key", style="bold bright_white", width=5, justify="center")
        table.add_column("Icon", width=4, justify="center")
        table.add_column("Action", style="bold", min_width=20)
        table.add_column("Description", style="dim")

        for key, icon, action, desc, color in menu_items:
            table.add_row(
                f"[{color}]{key}[/{color}]",
                icon,
                f"[{color}]{action}[/{color}]",
                desc,
            )

        panel = Panel(
            table,
            title="[bold bright_white]   메뉴 선택   [/bold bright_white]",
            title_align="center",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 1),
        )
        self.console.print()
        self.console.print(panel)

    def _prompt_profile(self, *, default: str) -> str:
        if not self._rich_mode:
            self.print("\n프로필 선택:")
            self.print("1. canslim_pure - 엄격한 CAN SLIM")
            self.print("2. canslim_watchlist - 넓은 후보군")
            self.print("3. canslim_hybrid - 하이브리드")
            choice = self.input(f"프로필 [기본: {default}]: ").strip()
            if not choice:
                return default
            return PROFILE_CHOICES.get(choice, choice)

        profiles = [
            ("1", "canslim_pure", "엄격한 CAN SLIM", "🎯", "bright_red"),
            ("2", "canslim_watchlist", "넓은 후보군 (Watchlist)", "📋", "bright_yellow"),
            ("3", "canslim_hybrid", "하이브리드 전략", "⚡", "bright_green"),
        ]

        table = Table(
            show_header=False,
            box=box.SIMPLE,
            border_style="dim",
            padding=(0, 1),
        )
        table.add_column("Key", style="bold bright_white", width=5, justify="center")
        table.add_column("Icon", width=4, justify="center")
        table.add_column("Profile", min_width=22)
        table.add_column("Description", style="dim")

        for key, name, desc, icon, color in profiles:
            marker = " ◀ default" if name == default else ""
            table.add_row(
                f"[{color}]{key}[/{color}]",
                icon,
                f"[{color}]{name}[/{color}][dim]{marker}[/dim]",
                desc,
            )

        panel = Panel(
            table,
            title="[bold bright_white]  프로필 선택  [/bold bright_white]",
            title_align="center",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(0, 1),
        )
        self.console.print(panel)

        choice = self.input(f"  프로필 [기본: {default}]: ").strip()
        if not choice:
            return default
        selected = PROFILE_CHOICES.get(choice, choice)
        self.console.print(f"  [dim]→ 선택된 프로필:[/dim] [bold cyan]{selected}[/bold cyan]")
        return selected

    def _print_result(self, text: str, *, title: str = "결과", style: str = "green") -> None:
        """Print an action result inside a styled panel."""
        if not self._rich_mode:
            self.print(text)
            return

        panel = Panel(
            text,
            title=f"[bold bright_white]  {title}  [/bold bright_white]",
            title_align="left",
            border_style=style,
            box=box.ROUNDED,
            padding=(1, 2),
        )
        self.console.print(panel)

    def _print_error(self, text: str) -> None:
        if not self._rich_mode:
            self.print(text)
            return
        self.console.print(f"  [bold red]✗[/bold red] {text}")

    def _print_success(self, text: str) -> None:
        if not self._rich_mode:
            self.print(text)
            return
        self.console.print(f"  [bold green]✓[/bold green] {text}")

    # ── Main loop ──────────────────────────────────────────────────────

    def run(self) -> None:
        """Run the interactive menu until the user exits."""
        self._print_banner()
        while True:
            self._print_menu()

            if self._rich_mode:
                choice_raw = self.input("  선택 ▸ ")
            else:
                choice_raw = self.input("선택: ")

            action = normalize_menu_choice(choice_raw)

            if action == "exit":
                if self._rich_mode:
                    self.console.print()
                    self.console.print(
                        Rule("[bold bright_cyan]  프로그램을 종료합니다  [/bold bright_cyan]", style="bright_cyan")
                    )
                    self.console.print()
                else:
                    self.print("종료합니다.")
                return

            if action == "screen":
                profile = self._prompt_profile(default="canslim_watchlist")
                if self._rich_mode:
                    with self.console.status("[bold cyan]스크리닝 실행 중...[/bold cyan]", spinner="dots"):
                        result = self.screen_action(profile)
                    self._print_result(result, title="스크리닝 결과", style="cyan")
                else:
                    self.print(self.screen_action(profile))

            elif action == "analyze":
                if self._rich_mode:
                    self.console.print()
                    ticker = self.input("  🔍 Ticker 입력 ▸ ").strip().upper()
                else:
                    ticker = self.input("Ticker 입력: ").strip().upper()

                if not ticker:
                    self._print_error("Ticker가 비어 있습니다.")
                    continue

                profile = self._prompt_profile(default=self.default_profile)

                if self._rich_mode:
                    with self.console.status(
                        f"[bold cyan]{ticker} 분석 중...[/bold cyan]", spinner="dots"
                    ):
                        result = self.analyze_action(ticker, profile)
                    self._print_result(result, title=f"{ticker} 분석 결과", style="green")
                else:
                    self.print(self.analyze_action(ticker, profile))

            elif action == "status":
                profile = self._prompt_profile(default=self.default_profile)
                if self._rich_mode:
                    with self.console.status("[bold cyan]상태 확인 중...[/bold cyan]", spinner="dots"):
                        result = self.status_action(profile)
                    self._print_result(result, title="파이프라인 상태", style="yellow")
                else:
                    self.print(self.status_action(profile))

            elif action == "update":
                profile = self._prompt_profile(default="canslim_watchlist")
                if self._rich_mode:
                    with self.console.status(
                        "[bold cyan]업데이트 실행 중...[/bold cyan]", spinner="dots"
                    ):
                        result = self.update_action(profile)
                    self._print_success(result)
                else:
                    self.print(self.update_action(profile))
            else:
                self._print_error("알 수 없는 선택입니다. 다시 선택해주세요.")

    # ── Default actions (real implementations) ─────────────────────────

    def _load_config(self, profile: str):
        config = load_config_file(self.config_path, profile=profile)
        config["config_path"] = self.config_path
        return config

    def _screen_action(self, profile: str) -> str:
        from src import growth_stock_screener as gss

        self._ensure_logger(gss)
        config = self._load_config(profile)
        gss.ensure_directories(config)
        gss.screen_stocks(config)
        output = config.get("data_paths", {}).get("output_file", "data/processed/results.csv")
        return f"스크리닝 완료: {output}"

    def _analyze_action(self, ticker: str, profile: str) -> str:
        config = self._load_config(profile)
        result = analyze_ticker(ticker, config)
        if self._rich_mode:
            return format_ticker_analysis(result, rich_mode=True)
        return format_ticker_analysis(result)

    def _status_action(self, profile: str) -> str:
        config = self._load_config(profile)
        status = collect_pipeline_status(config)
        if self._rich_mode:
            return format_pipeline_status(status, rich_mode=True)
        return self._capture_status_text(status)

    def _update_action(self, profile: str) -> str:
        from src import growth_stock_screener as gss

        self._ensure_logger(gss)
        config = self._load_config(profile)
        gss.ensure_directories(config)
        gss.update_pipeline(config)
        return "업데이트 실행 완료"

    def _capture_status_text(self, status) -> str:
        from src.utils.pipeline_status import print_pipeline_status
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            print_pipeline_status(status)
        return buffer.getvalue().rstrip()

    @staticmethod
    def _ensure_logger(gss_module) -> None:
        if not hasattr(gss_module, "logger"):
            gss_module.logger = setup_logger("growth_stock_screener", log_level=logging.INFO)


def main() -> None:
    TerminalApp().run()
