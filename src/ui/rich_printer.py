"""Rich-powered printer for the CAN SLIM screener output.

Provides a drop-in replacement for plain ``print()`` calls in the
screening pipeline, rendering beautiful tables, panels and progress
bars when a terminal is available.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


_console: Optional[Console] = None


def _get_console() -> Console:
    global _console
    if _console is None:
        _console = Console()
    return _console


def _as_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        number = float(value)
        if math.isfinite(number):
            return number
    except (TypeError, ValueError):
        return None
    return None


def _has_real_value(value: Any) -> bool:
    if _as_float(value) is not None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"", "n/a", "na", "none", "null", "nan"}
    return value is not None


def _format_share_count(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "[dim]미수집[/dim]"
    if abs(number) >= 1_000_000:
        return f"[bright_white]{number / 1_000_000:.1f}M[/bright_white]"
    if abs(number) >= 1_000:
        return f"[bright_white]{number / 1_000:.0f}K[/bright_white]"
    return f"[bright_white]{number:.0f}[/bright_white]"


def _fmt_short_pct(company: Mapping[str, Any]) -> str:
    value = _as_float(company.get("short_percent_float"))
    suffix = "F"
    if value is None:
        value = _as_float(company.get("short_percent_shares_outstanding"))
        suffix = "SO"
    if value is None:
        short_interest = _as_float(company.get("short_interest"))
        if short_interest == 0:
            return "[bright_white]0.0%[/bright_white]"
        if short_interest is not None:
            return "[dim]분모 없음[/dim]"
        return _format_share_count(company.get("short_interest"))
    color = "bright_red" if value >= 0.20 else "bright_yellow" if value >= 0.10 else "bright_white"
    return f"[{color}]{value * 100:.1f}%{suffix}[/{color}]"


def _fmt_days_to_cover(value: Any, short_interest: Any = None) -> str:
    number = _as_float(value)
    if number is None:
        if _as_float(short_interest) == 0:
            return "[bright_white]0[/bright_white]"
        return "[dim]미수집[/dim]"
    color = "bright_red" if number >= 10 else "bright_yellow" if number >= 5 else "bright_white"
    return f"[{color}]{number:.1f}[/{color}]"


# ── Screening criteria ─────────────────────────────────────────────────


def print_screening_header(
    total_companies: int,
    profile_name: Optional[str],
) -> None:
    """Print a styled header for the screening run."""
    console = _get_console()
    lines = [
        f"[bold bright_white]{total_companies:,}[/bold bright_white] 종목 로드 완료",
    ]
    if profile_name:
        lines.append(f"활성 프로필: [bold cyan]{profile_name}[/bold cyan]")
    console.print()
    panel = Panel(
        "\n".join(lines),
        title="[bold bright_white]  📊 스크리닝 시작  [/bold bright_white]",
        title_align="left",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    )
    console.print(panel)


def print_screening_criteria(
    criteria: Mapping[str, Any],
    leadership: Mapping[str, Any],
    market_direction_criteria: Mapping[str, Any],
    market_direction: Mapping[str, Any],
    supply_demand: Mapping[str, Any],
    institutional: Mapping[str, Any],
) -> None:
    """Print the screening criteria as a styled table."""
    console = _get_console()

    table = Table(
        show_header=True,
        header_style="bold bright_cyan",
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("기준", style="bright_white", min_width=30)
    table.add_column("조건", justify="right", style="bold")

    def _add(label: str, value: str, color: str = "bright_yellow") -> None:
        table.add_row(label, f"[{color}]{value}[/{color}]")

    def _format_pct(val: Optional[float], default: float) -> str:
        v = val if val is not None else default
        if v is None or v < -5.0:
            return "제한 없음"
        return f"≥ {v * 100:.1f}%"

    def _format_de(val: Optional[float]) -> str:
        if val is None or val >= 900:
            return "제한 없음"
        return f"≤ {val}"

    def _format_mktcap(val: Optional[float]) -> str:
        if val is None or val <= 0:
            return "제한 없음"
        return f"${val / 1_000_000:.1f}M"

    def _format_rs(val: Optional[float]) -> str:
        if val is None or val <= 0:
            return "제한 없음"
        return f"≥ {val:.0f}"

    def _format_volume(val: Optional[float]) -> str:
        if val is None or val <= 0:
            return "제한 없음"
        return f"≥ ${val / 1_000_000:.1f}M"

    _add("분기 EPS 성장률", _format_pct(criteria.get('quarterly_eps_growth'), 0.20))
    _add("연간 EPS CAGR", _format_pct(criteria.get('annual_eps_cagr'), 0.20))
    _add("매출 성장률", _format_pct(criteria.get('revenue_growth'), 0.15))
    _add("영업이익률", _format_pct(criteria.get('profit_margin'), 0.10))
    _add("ROE", _format_pct(criteria.get('roe'), 0.15))
    _add("부채비율 (D/E)", _format_de(criteria.get('debt_to_equity')))
    _add("최소 시가총액", _format_mktcap(criteria.get('min_market_cap')))
    if criteria.get("outperform_sp500", True):
        _add("S&P 500 아웃퍼폼", "필수", "bright_green")
    else:
        _add("S&P 500 아웃퍼폼", "제한 없음", "dim white")
    _add("RS Rating", _format_rs(leadership.get('rs_rating_min')))
    _add("52주 고가 대비", _format_pct(leadership.get('price_vs_52w_high_min'), 0.85))
    _add("50일 평균 거래대금", _format_volume(leadership.get('avg_dollar_volume_min')))

    if market_direction_criteria.get("required", False):
        status = market_direction.get("market_direction_status", "missing")
        allowed = market_direction_criteria.get("allowed_statuses", [])
        _add("시장 방향", f"{status} ∈ {allowed}")

    if supply_demand.get("require_supply_demand", False):
        _add("상승/하락 거래량 비율", f"≥ {supply_demand.get('up_down_volume_ratio_min', 1.1):.2f}")
        volume_trend_min = supply_demand.get("volume_trend_50_200_min", 1.0)
        if volume_trend_min is not None:
            _add("50/200 거래량 추세", f"≥ {volume_trend_min:.2f}")
        if supply_demand.get("require_volume_dry_up", False):
            _add("거래량 드라이업", f"≤ {supply_demand.get('volume_dry_up_ratio_max', 0.8):.2f}")

    if institutional.get("require_institutional_sponsorship", False):
        lo = institutional.get("institutional_ownership_min", 0.2) * 100
        hi = institutional.get("institutional_ownership_max", 0.95) * 100
        _add("기관 보유 비율", f"{lo:.1f}% ~ {hi:.1f}%")

    panel = Panel(
        table,
        title="[bold bright_white]  🎯 스크리닝 기준  [/bold bright_white]",
        title_align="left",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    console.print(panel)


# ── Metrics data coverage ──────────────────────────────────────────────


def print_metrics_stats(
    metrics_counts: Dict[str, int],
    total: int,
    *,
    signal_counts: Dict[str, int] | None = None,
    include_insider: bool = True,
    include_short_interest: bool = True,
) -> None:
    """Print data availability as a compact bar chart table.

    For boolean setup/signal metrics, coverage means the field was computed;
    ``signal_counts`` optionally shows how many rows have the bullish signal.
    """
    console = _get_console()

    # Group metrics into categories for readability
    groups: Dict[str, List[str]] = {
        "📈 펀더멘탈": [
            "quarterly_eps_growth", "annual_eps_cagr", "revenue_growth",
            "profit_margin", "roe", "debt_to_equity",
        ],
        "🏷️ 시장/가격": [
            "market_cap", "rs_rating", "price_vs_52w_high",
            "avg_dollar_volume_50d",
        ],
        "📊 수급/거래량": [
            "up_down_volume_ratio_50d", "volume_trend_50_200",
            "volume_dry_up_ratio_10_50",
        ],
        "🏦 기관": [
            "institutional_ownership", "institutional_holders",
            "institutional_holders_qoq_change", "institutional_value_qoq_change",
            "institutional_accumulation_score",
            "new_holder_count", "increased_holder_count",
            "decreased_holder_count", "exited_holder_count",
        ],
        "🕵️ 내부자": [
            "insider_buy_count_90d", "net_insider_buy_value_90d",
        ],
        "📉 공매도": [
            "short_interest", "short_percent_float",
            "short_percent_shares_outstanding", "short_days_to_cover",
        ],
        "🎯 스코어/패턴": [
            "canslim_score", "breakout_volume_ratio",
            "new_52w_high", "recent_new_52w_high", "near_pivot", "valid_breakout",
        ],
    }
    if not include_insider:
        groups.pop("🕵️ 내부자", None)
    if not include_short_interest:
        groups.pop("📉 공매도", None)

    table = Table(
        show_header=True,
        header_style="bold bright_cyan",
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("지표", min_width=32, style="bright_white")
    table.add_column("커버리지", justify="right", width=16)
    table.add_column("바", width=22)
    table.add_column("%", justify="right", width=7)

    for group_name, keys in groups.items():
        # Section header row
        table.add_row(f"[bold underline]{group_name}[/bold underline]", "", "", "")
        for key in keys:
            count = metrics_counts.get(key, 0)
            pct = count / total * 100 if total else 0
            bar_len = 15
            filled = int(bar_len * pct / 100)
            if pct >= 50:
                bar_color = "bright_green"
            elif pct >= 20:
                bar_color = "bright_yellow"
            else:
                bar_color = "bright_red"
            bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * (bar_len - filled)}[/dim]"
            extra = ""
            if signal_counts and key in signal_counts:
                extra = f" [dim](True {signal_counts.get(key, 0):,})[/dim]"
            table.add_row(
                f"  {key}",
                f"[dim]{count:,}[/dim] / [dim]{total:,}[/dim]{extra}",
                bar,
                f"[{bar_color}]{pct:.1f}%[/{bar_color}]",
            )

    panel = Panel(
        table,
        title="[bold bright_white]  📋 데이터 커버리지  [/bold bright_white]",
        title_align="left",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    console.print(panel)


# ── Category pass rates ────────────────────────────────────────────────


def print_criteria_breakdown(
    criteria_counts: Dict[str, int],
    total: int,
) -> None:
    """Print per-category pass rates as a styled table."""
    console = _get_console()

    table = Table(
        show_header=True,
        header_style="bold bright_cyan",
        box=box.SIMPLE_HEAVY,
        border_style="dim",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("카테고리", min_width=20, style="bright_white")
    table.add_column("통과", justify="right", width=14)
    table.add_column("바", width=22)
    table.add_column("%", justify="right", width=7)

    # Friendly names for criteria keys
    friendly: Dict[str, str] = {
        "eps": "📈 분기 EPS",
        "eps_cagr": "📈 연간 EPS CAGR",
        "eps_consecutive_growth": "📈 연간 EPS 연속 성장",
        "revenue": "💰 매출 성장",
        "margin": "💹 영업이익률",
        "roe": "🎯 ROE",
        "debt": "🏦 부채비율",
        "mktcap": "💎 시가총액",
        "sp500": "🇺🇸 S&P 500 아웃퍼폼",
        "rs": "⚡ RS Rating",
        "near_high": "📊 52주 고가 근접",
        "liquidity": "💧 유동성",
        "rs_line": "📉 RS 라인 신고가",
        "industry": "🏭 산업군",
        "market_direction": "🧭 시장 방향",
        "supply_demand": "📦 수급",
        "institutional": "🏛️ 기관",
        "new_high": "🎯 N 셋업",
        "base": "🏗️ 베이스 패턴",
        "breakout": "🚀 돌파",
    }

    for key, count in criteria_counts.items():
        pct = count / total * 100 if total else 0
        bar_len = 15
        filled = int(bar_len * pct / 100)
        if pct >= 50:
            bar_color = "bright_green"
        elif pct >= 20:
            bar_color = "bright_yellow"
        elif pct >= 5:
            bar_color = "yellow"
        else:
            bar_color = "bright_red"
        bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * (bar_len - filled)}[/dim]"
        label = friendly.get(key, key)
        table.add_row(
            label,
            f"[dim]{count:,}[/dim] / [dim]{total:,}[/dim]",
            bar,
            f"[{bar_color}]{pct:.1f}%[/{bar_color}]",
        )

    panel = Panel(
        table,
        title="[bold bright_white]  🔍 카테고리별 통과 현황  [/bold bright_white]",
        title_align="left",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )
    console.print(panel)


# ── Top results table ──────────────────────────────────────────────────

def _band_color(band: str) -> str:
    b = str(band).lower()
    if b in ("exceptional", "a+", "a"):
        return "bold bright_green"
    if b in ("excellent", "b+", "b"):
        return "green"
    if b in ("good", "c+", "c"):
        return "bright_yellow"
    if b in ("fair", "d"):
        return "yellow"
    return "bright_red"


def print_results_table(
    companies: Sequence[Mapping[str, Any]],
    total_passed: int,
    *,
    max_display: int = 10,
) -> None:
    """Print top screening results in a beautiful Rich table."""
    console = _get_console()

    if not companies:
        console.print(
            Panel(
                "[bold bright_yellow]스크리닝 기준을 통과한 종목이 없습니다.[/bold bright_yellow]\n"
                "[dim]프로필 기준을 완화하거나 데이터를 업데이트해 주세요.[/dim]",
                title="[bold bright_white]  📭 결과 없음  [/bold bright_white]",
                title_align="left",
                border_style="yellow",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        return

    all_companies = list(companies)
    visible_companies = all_companies[:max_display]
    show_short_columns = any(
        _has_real_value(company.get(field))
        for company in all_companies
        for field in [
            "short_percent_float",
            "short_percent_shares_outstanding",
            "short_interest",
            "short_days_to_cover",
        ]
    )

    table = Table(
        show_header=True,
        header_style="bold bright_cyan",
        box=box.HEAVY_HEAD,
        border_style="bright_cyan",
        padding=(0, 1),
        expand=False,
        title=f"[bold bright_white]총 {total_passed:,}개 종목 통과[/bold bright_white]",
        title_style="bold",
        caption=f"[dim]상위 {min(max_display, total_passed)}개 표시[/dim]" if total_passed > max_display else None,
    )
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Ticker", style="bold bright_white", width=7)
    table.add_column("종목명", min_width=15, max_width=28, no_wrap=False)
    table.add_column("Score", justify="center", width=6)
    table.add_column("Band", justify="center", width=12)
    table.add_column("Q EPS", justify="right", width=8)
    table.add_column("A EPS", justify="right", width=8)
    table.add_column("매출", justify="right", width=8)
    table.add_column("RS", justify="center", width=4)
    table.add_column("52W", justify="right", width=7)
    if show_short_columns:
        table.add_column("Short%", justify="right", width=8)
        table.add_column("DTC", justify="right", width=5)
    table.add_column("시총", justify="right", width=10)

    for i, company in enumerate(visible_companies, 1):
        ticker = company.get("ticker", "N/A")
        name = company.get("name", "Unknown")
        if len(name) > 24:
            name = name[:21] + "..."

        score = company.get("canslim_score", 0)
        band = company.get("score_band", "N/A")
        bc = _band_color(band)

        q_eps = company.get("quarterly_eps_growth", 0)
        a_eps = company.get("annual_eps_cagr", 0)
        rev = company.get("revenue_growth", 0)
        rs = company.get("rs_rating", 0)
        near_high = company.get("price_vs_52w_high", 0)
        mktcap = company.get("market_cap", 0)

        def _fmtpct(v: Any) -> str:
            try:
                v = float(v)
                color = "bright_green" if v > 0 else "bright_red"
                return f"[{color}]{v * 100:.1f}%[/{color}]"
            except (TypeError, ValueError):
                return "[dim]N/A[/dim]"

        def _fmtcap(v: Any) -> str:
            try:
                v = float(v)
                if v >= 1e9:
                    return f"${v / 1e9:.1f}B"
                return f"${v / 1e6:.1f}M"
            except (TypeError, ValueError):
                return "[dim]N/A[/dim]"

        row = [
            str(i),
            f"[bold bright_cyan]{ticker}[/bold bright_cyan]",
            name,
            f"[{bc}]{score:.1f}[/{bc}]",
            f"[{bc}]{band}[/{bc}]",
            _fmtpct(q_eps),
            _fmtpct(a_eps),
            _fmtpct(rev),
            f"[bright_white]{rs:.0f}[/bright_white]" if rs else "[dim]N/A[/dim]",
            _fmtpct(near_high),
        ]
        if show_short_columns:
            row.extend([_fmt_short_pct(company), _fmt_days_to_cover(company.get("short_days_to_cover"), company.get("short_interest"))])
        row.append(_fmtcap(mktcap))
        table.add_row(*row)

    console.print()
    console.print(table)

    if total_passed > max_display:
        console.print(
            f"  [dim]… 외 {total_passed - max_display}개 종목은 결과 파일을 참조하세요.[/dim]"
        )


def print_data_quality_warning(warnings: Sequence[str]) -> None:
    """Print non-blocking warnings for partial enrichment/data coverage."""
    if not warnings:
        return
    console = _get_console()
    lines = [f"  [yellow]•[/yellow] {warning}" for warning in warnings]
    panel = Panel(
        "\n".join(lines),
        title="[bold bright_yellow]  ⚠️  데이터 품질 경고  [/bold bright_yellow]",
        title_align="left",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def print_missing_enrich_warning(
    reasons: Sequence[str],
    enrich_cmd: str,
) -> None:
    """Print a styled warning when enrichment data is missing."""
    console = _get_console()
    lines = ["[bold bright_yellow]시장/리더십 데이터가 누락되어 스크리닝 결과가 0건이 됩니다.[/bold bright_yellow]", ""]
    for reason in reasons:
        lines.append(f"  [yellow]•[/yellow] {reason}")
    lines.extend([
        "",
        "[bold bright_white]다음 명령어를 먼저 실행하세요:[/bold bright_white]",
        f"  [italic cyan]{enrich_cmd}[/italic cyan]",
    ])
    panel = Panel(
        "\n".join(lines),
        title="[bold bright_yellow]  ⚠️  데이터 누락  [/bold bright_yellow]",
        title_align="left",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)


def print_saved_result(output_file: str) -> None:
    """Print a success message for saved results."""
    console = _get_console()
    console.print(
        f"  [bold green]✓[/bold green] 결과 저장 완료: [bold bright_white]{output_file}[/bold bright_white]"
    )
