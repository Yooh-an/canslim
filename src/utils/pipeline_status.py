"""Pipeline status inspection for the CAN SLIM screener."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


def _file_info(path: Path) -> Dict[str, Any]:
    exists = path.exists()
    info: Dict[str, Any] = {"path": str(path), "exists": exists}
    if exists:
        stat = path.stat()
        info.update({"size": stat.st_size, "mtime": stat.st_mtime})
    return info


def _json_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _count_rows_with_any(rows: Iterable[Mapping[str, Any]], fields: Iterable[str]) -> int:
    field_list = list(fields)
    return sum(1 for row in rows if any(row.get(field) is not None for field in field_list))


def _command(mode: str, config: Mapping[str, Any]) -> str:
    config_path = config.get("config_path", "config/base.json")
    profile = config.get("profile_name")
    command = f"python run_screener.py --mode {mode} --config {config_path}"
    if profile and profile != "default":
        command += f" --profile {profile}"
    return command


def collect_pipeline_status(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Collect readiness flags and next-step recommendations for local data files."""
    data_paths = config.get("data_paths", {})
    raw_dir = Path(data_paths.get("raw_data_dir", "data/raw"))
    processed_dir = Path(data_paths.get("processed_data_dir", "data/processed"))
    facts_dir = Path(data_paths.get("company_facts_dir", raw_dir / "company_facts"))
    output_file = Path(data_paths.get("output_file", processed_dir / "results.csv"))
    markdown_file = output_file.with_suffix(".md")

    companies_file = processed_dir / "companies_list.json"
    enriched_file = processed_dir / "companies_list_enriched.json"
    metrics_file = processed_dir / "financial_metrics.parquet"
    market_file = processed_dir / "market_direction.json"
    mapping_file = Path(data_paths.get("cusip_ticker_mapping", processed_dir / "cusip_ticker_mapping.csv"))
    coverage_file = processed_dir / "cusip_ticker_mapping_coverage.csv"
    institutional_dir = Path(config.get("institutional_data", {}).get("raw_13f_dir", raw_dir / "institutional_13f"))
    insider_dir = Path(config.get("insider_data", {}).get("raw_form4_dir", raw_dir / "insider_form4"))

    facts_count = len(list(facts_dir.glob("CIK*.json"))) if facts_dir.exists() else 0
    institutional_current_count = len(list((institutional_dir / "current").glob("*.xml"))) if (institutional_dir / "current").exists() else 0
    institutional_previous_count = len(list((institutional_dir / "previous").glob("*.xml"))) if (institutional_dir / "previous").exists() else 0
    insider_form4_count = len(list(insider_dir.glob("*.xml"))) if insider_dir.exists() else 0

    rows = _json_rows(enriched_file if enriched_file.exists() else companies_file)
    company_count = len(rows)
    leadership_count = _count_rows_with_any(rows, ["rs_rating", "price_vs_52w_high", "avg_dollar_volume_50d"])
    institutional_count = _count_rows_with_any(
        rows,
        [
            "institutional_ownership",
            "institutional_holders",
            "institutional_holders_qoq_change",
            "institutional_value_qoq_change",
            "institutional_accumulation_score",
        ],
    )
    insider_count = _count_rows_with_any(rows, ["insider_buy_count_90d", "net_insider_buy_value_90d"])

    download_ready = facts_count > 0 and companies_file.exists() and companies_file.stat().st_size > 0
    parse_ready = metrics_file.exists() and metrics_file.stat().st_size > 0 and companies_file.exists()
    enrich_ready = enriched_file.exists() and market_file.exists() and leadership_count > 0
    institutional_required = bool(config.get("institutional_criteria", {}).get("require_institutional_sponsorship", False))
    institutional_ready = (not institutional_required) or institutional_count > 0
    screen_ready = output_file.exists() and output_file.stat().st_size > 0

    warnings: List[str] = []
    recommended_commands: List[str] = []
    if not download_ready:
        next_action = "download"
        recommended_commands.append(_command("download", config))
    elif not parse_ready:
        next_action = "parse"
        recommended_commands.append(_command("parse", config))
    elif not enrich_ready:
        next_action = "enrich"
        recommended_commands.append(_command("enrich", config))
    elif not institutional_ready:
        next_action = "institutional_data"
        if not config.get("institutional_data", {}).get("enabled", False):
            warnings.append("institutional_data.enabled=false while institutional sponsorship is required")
        recommended_commands.append(_command("enrich", config))
    elif not screen_ready:
        next_action = "screen"
        recommended_commands.append(_command("screen", config))
    else:
        next_action = "none"

    return {
        "profile_name": config.get("profile_name", "default"),
        "facts_count": facts_count,
        "company_count": company_count,
        "leadership_count": leadership_count,
        "institutional_count": institutional_count,
        "insider_count": insider_count,
        "institutional_current_xml_count": institutional_current_count,
        "institutional_previous_xml_count": institutional_previous_count,
        "insider_form4_xml_count": insider_form4_count,
        "download_ready": download_ready,
        "parse_ready": parse_ready,
        "enrich_ready": enrich_ready,
        "institutional_required": institutional_required,
        "institutional_ready": institutional_ready,
        "screen_ready": screen_ready,
        "next_action": next_action,
        "recommended_commands": recommended_commands,
        "warnings": warnings,
        "files": {
            "raw_dir": str(raw_dir),
            "processed_dir": str(processed_dir),
            "company_facts_dir": str(facts_dir),
            "companies_list": _file_info(companies_file),
            "companies_list_enriched": _file_info(enriched_file),
            "financial_metrics": _file_info(metrics_file),
            "market_direction": _file_info(market_file),
            "results_csv": _file_info(output_file),
            "results_md": _file_info(markdown_file),
            "cusip_ticker_mapping": _file_info(mapping_file),
            "cusip_mapping_coverage": _file_info(coverage_file),
        },
    }


def print_pipeline_status(status: Mapping[str, Any]) -> None:
    """Print a concise human-readable status report."""
    print(f"Pipeline status for profile: {status.get('profile_name')}")
    print(f"- Download data: {'✅' if status.get('download_ready') else '❌'} ({status.get('facts_count')} company facts)")
    print(f"- Parsed data: {'✅' if status.get('parse_ready') else '❌'} ({status.get('company_count')} companies)")
    print(f"- Market/leadership enrichment: {'✅' if status.get('enrich_ready') else '❌'} ({status.get('leadership_count')} companies)")
    print(f"- Institutional data: {'✅' if status.get('institutional_ready') else '❌'} ({status.get('institutional_count')} companies)")
    print(f"- Insider Form 4 data: {'✅' if status.get('insider_count') else '⚪'} ({status.get('insider_count')} companies)")
    print(f"- Screen results: {'✅' if status.get('screen_ready') else '❌'}")
    if status.get("warnings"):
        print("\nWarnings:")
        for warning in status["warnings"]:
            print(f"- {warning}")
    if status.get("next_action") == "none":
        print("\nNext action: none; data and results are present.")
    else:
        print(f"\nNext action: {status.get('next_action')}")
        for command in status.get("recommended_commands", []):
            print(command)


def format_pipeline_status(status: Mapping[str, Any], *, rich_mode: bool = False) -> str:
    """Return a formatted pipeline status string.

    When *rich_mode* is True the output contains Rich markup for pretty
    terminal rendering.  Otherwise plain text is returned.
    """
    if not rich_mode:
        # Plain-text fallback (matches print_pipeline_status output)
        parts: List[str] = []
        parts.append(f"Pipeline status for profile: {status.get('profile_name')}")
        parts.append(f"- Download data: {'✅' if status.get('download_ready') else '❌'} ({status.get('facts_count')} company facts)")
        parts.append(f"- Parsed data: {'✅' if status.get('parse_ready') else '❌'} ({status.get('company_count')} companies)")
        parts.append(f"- Market/leadership enrichment: {'✅' if status.get('enrich_ready') else '❌'} ({status.get('leadership_count')} companies)")
        parts.append(f"- Institutional data: {'✅' if status.get('institutional_ready') else '❌'} ({status.get('institutional_count')} companies)")
        parts.append(f"- Insider Form 4 data: {'✅' if status.get('insider_count') else '⚪'} ({status.get('insider_count')} companies)")
        parts.append(f"- Screen results: {'✅' if status.get('screen_ready') else '❌'}")
        if status.get("warnings"):
            parts.append("\nWarnings:")
            for w in status["warnings"]:
                parts.append(f"- {w}")
        if status.get("next_action") == "none":
            parts.append("\nNext action: none; data and results are present.")
        else:
            parts.append(f"\nNext action: {status.get('next_action')}")
            for cmd in status.get("recommended_commands", []):
                parts.append(cmd)
        return "\n".join(parts)

    # ── Rich-formatted output ──────────────────────────────────────
    lines: List[str] = []
    profile = status.get("profile_name", "default")
    lines.append(f"[bold bright_white]프로필:[/bold bright_white] [bold cyan]{profile}[/bold cyan]")
    lines.append("")

    steps = [
        ("download_ready", "데이터 다운로드", f"{status.get('facts_count', 0)} company facts", "📥"),
        ("parse_ready", "데이터 파싱", f"{status.get('company_count', 0)} companies", "⚙️"),
        ("enrich_ready", "시장/리더십 보강", f"{status.get('leadership_count', 0)} companies", "📈"),
        ("institutional_ready", "기관 데이터", f"{status.get('institutional_count', 0)} companies", "🏦"),
    ]

    # Compute completion for a visual progress bar
    total_steps = len(steps) + 2  # +insider +screen
    done_steps = sum(1 for key, *_ in steps if status.get(key))
    if status.get("insider_count"):
        done_steps += 1
    if status.get("screen_ready"):
        done_steps += 1

    # Progress indicator
    bar_len = 20
    filled = int(bar_len * done_steps / total_steps) if total_steps else 0
    bar = "█" * filled + "░" * (bar_len - filled)
    pct = int(100 * done_steps / total_steps) if total_steps else 0
    pct_color = "bright_green" if pct == 100 else "bright_yellow" if pct >= 50 else "bright_red"
    lines.append(f"  [bold bright_white]진행률[/bold bright_white]  [{pct_color}]{bar}[/{pct_color}]  [{pct_color}]{pct}%[/{pct_color}]  ({done_steps}/{total_steps})")
    lines.append("")

    for key, label, detail, icon in steps:
        ready = status.get(key, False)
        if ready:
            status_icon = "[bright_green]✓[/bright_green]"
            detail_style = "dim"
        else:
            status_icon = "[bright_red]✗[/bright_red]"
            detail_style = "bright_red"
        lines.append(f"  {status_icon}  {icon}  {label:<20} [{detail_style}]{detail}[/{detail_style}]")

    # Insider (optional — uses ⚪ if absent)
    insider_count = status.get("insider_count", 0)
    if insider_count:
        lines.append(f"  [bright_green]✓[/bright_green]  🕵️  {'내부자 Form 4':<20} [dim]{insider_count} companies[/dim]")
    else:
        lines.append(f"  [dim]○[/dim]  🕵️  {'내부자 Form 4':<20} [dim]{insider_count} companies[/dim]")

    # Screen
    screen_ready = status.get("screen_ready", False)
    if screen_ready:
        lines.append(f"  [bright_green]✓[/bright_green]  📊  {'스크리닝 결과':<20} [dim]완료[/dim]")
    else:
        lines.append(f"  [bright_red]✗[/bright_red]  📊  {'스크리닝 결과':<20} [bright_red]미완료[/bright_red]")

    # Raw file counts
    lines.append("")
    lines.append("  [bold underline bright_cyan]원시 파일 현황[/bold underline bright_cyan]")
    lines.append(f"    [dim]•[/dim] 13F XML (current)  : {status.get('institutional_current_xml_count', 0)}")
    lines.append(f"    [dim]•[/dim] 13F XML (previous) : {status.get('institutional_previous_xml_count', 0)}")
    lines.append(f"    [dim]•[/dim] Form 4 XML          : {status.get('insider_form4_xml_count', 0)}")

    # Warnings
    if status.get("warnings"):
        lines.append("")
        lines.append("  [bold bright_yellow]⚠  경고[/bold bright_yellow]")
        for warning in status["warnings"]:
            lines.append(f"    [yellow]• {warning}[/yellow]")

    # Next action
    lines.append("")
    next_action = status.get("next_action", "none")
    if next_action == "none":
        lines.append("  [bold bright_green]🎉 모든 데이터와 결과가 준비되었습니다![/bold bright_green]")
    else:
        lines.append(f"  [bold bright_yellow]▸ 다음 단계:[/bold bright_yellow] [bold bright_white]{next_action}[/bold bright_white]")
        for cmd in status.get("recommended_commands", []):
            lines.append(f"    [dim]$[/dim] [italic cyan]{cmd}[/italic cyan]")

    return "\n".join(lines)
