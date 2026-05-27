"""Session report export helpers for the local web dashboard."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Mapping

from src.web import data_provider, job_runner, review_store, session_journal, workspace_snapshot, workspace_store
from src.web.disclosure import research_disclosure


SCHEMA_VERSION = 1


def export_session_report(
    profile: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
    format: str | None = None,
    session_date: str | None = None,
) -> dict[str, str]:
    """Return a downloadable daily operating report for the active workspace."""
    report = build_session_report(profile, risk=risk, session_date=session_date)
    report_format = _normalize_report_format(format)
    extension = "json" if report_format == "json" else "md"
    if report_format == "json":
        body = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        content_type = "application/json; charset=utf-8"
    else:
        body = _report_to_markdown(report)
        content_type = "text/markdown; charset=utf-8"
    return {
        "profile": str(report["profile"]),
        "filename": f"canslim-session-{report['profile']}.{extension}",
        "content_type": content_type,
        "body": body,
    }


def build_session_report(
    profile: str | None = None,
    *,
    risk: Mapping[str, Any] | None = None,
    session_date: str | None = None,
) -> dict[str, Any]:
    """Build a shareable snapshot of the current research session."""
    preferences = workspace_store.get_preferences()
    profile_name = data_provider.normalize_profile(profile or str(preferences.get("profile") or ""))
    snapshot = workspace_snapshot.build_workspace_snapshot(profile_name, risk=risk)
    risk_settings = _mapping(_mapping(snapshot.get("preferences")).get("risk"))
    review_export = json.loads(review_store.export_review_queue(profile_name, "json", risk=risk_settings)["body"])
    overview = data_provider.get_overview(profile_name)
    artifacts = data_provider.get_artifacts(profile_name)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "profile": profile_name,
        "research_disclosure": research_disclosure(),
        "preferences": snapshot.get("preferences", {}),
        "journal": session_journal.get_session_journal(profile_name, session_date=session_date),
        "data_health": overview.get("data_health", {}),
        "strategy": overview.get("profile_summary", {}),
        "market_direction": overview.get("market_direction", {}),
        "action_center": overview.get("action_center", {}),
        "candidate_stats": overview.get("candidate_stats", {}),
        "top_candidates": list(overview.get("top_candidates") or [])[:10],
        "review": snapshot.get("review", {}),
        "review_export": review_export,
        "review_summary": snapshot.get("review_summary", {}),
        "artifacts": artifacts,
        "jobs": job_runner.job_history(limit=6),
        "provenance": snapshot.get("provenance", {}),
    }


def _report_to_markdown(report: Mapping[str, Any]) -> str:
    disclosure = _mapping(report.get("research_disclosure"))
    health = _mapping(report.get("data_health"))
    strategy = _mapping(report.get("strategy"))
    market = _mapping(report.get("market_direction"))
    action_center = _mapping(report.get("action_center"))
    journal = _mapping(report.get("journal"))
    review = _mapping(report.get("review"))
    review_export = _mapping(report.get("review_export"))
    summary = _mapping(report.get("review_summary"))
    artifacts = _mapping(report.get("artifacts"))
    jobs = _mapping(report.get("jobs"))
    provenance = _mapping(report.get("provenance"))

    lines = [
        "# CANSLIM SEPA Session Report",
        "",
        f"- Generated: {_inline(report.get('generated_at'))}",
        f"- Profile: {_inline(report.get('profile'))}",
        f"- Disclosure: {_inline(disclosure.get('title'))}",
        f"- Disclosure detail: {_inline(disclosure.get('text'))}",
    ]
    for point in _list(disclosure.get("points")):
        lines.append(f"  - {_inline(point)}")

    lines.extend(
        [
            "",
            "## Data Freshness",
            "",
            f"- Level: {_inline(health.get('level'))}",
            f"- Readiness: {_number(health.get('readiness_pct'))}%",
            f"- Next action: {_inline(health.get('next_action'))}",
            f"- Results age: {_age_hours(health.get('result_age_hours'))}",
            f"- Market freshness: {_market_freshness(health)}",
            f"- Expected market as-of: {_inline(health.get('market_expected_as_of'))}",
            f"- Candidates: {_number(health.get('candidate_count'))}",
        ]
    )
    findings = _list(health.get("source_findings"))[:5]
    if findings:
        lines.extend(["", "Source findings:"])
        for finding in findings:
            finding_map = _mapping(finding)
            lines.append(
                f"- {_inline(finding_map.get('level'))}: {_inline(finding_map.get('label'))} - "
                f"{_inline(finding_map.get('detail'))}"
            )

    lines.extend(
        [
            "",
            "## Strategy Lens",
            "",
            f"- Name: {_inline(strategy.get('label') or strategy.get('profile'))}",
            f"- Result file: {_inline(strategy.get('result_file'))}",
        ]
    )
    rules = _list(strategy.get("rules"))[:8]
    if rules:
        lines.extend(["", "| Rule | Value |", "| --- | --- |"])
        for rule in rules:
            rule_map = _mapping(rule)
            lines.append(f"| {_cell(rule_map.get('label') or rule_map.get('key'))} | {_cell(rule_map.get('value'))} |")

    lines.extend(
        [
            "",
            "## Market And Actions",
            "",
            f"- Market status: {_inline(market.get('market_direction_status') or action_center.get('market_status'))}",
            f"- Recommended exposure: {_percent_fraction(action_center.get('recommended_exposure'))}",
            f"- Posture: {_inline(action_center.get('posture'))}",
            f"- High-quality candidates: {_number(action_center.get('high_quality_count'))}",
        ]
    )
    tasks = _list(action_center.get("tasks"))
    if tasks:
        lines.extend(["", "Action tasks:"])
        for task in tasks:
            task_map = _mapping(task)
            lines.append(f"- {_inline(task_map.get('label'))}: {_inline(task_map.get('detail'))}")
    focus = _list(action_center.get("focus_candidates"))[:6]
    if focus:
        lines.extend(
            [
                "",
                "| Focus | Action | Score | Setup | Pivot |",
                "| --- | --- | ---: | --- | ---: |",
            ]
        )
        for candidate in focus:
            row = _mapping(candidate)
            lines.append(
                "| "
                f"{_cell(row.get('ticker'))} | "
                f"{_cell(row.get('action'))} | "
                f"{_cell(_number(row.get('canslim_score')))} | "
                f"{_cell(row.get('setup_status'))} | "
                f"{_cell(_pct(row.get('pivot_distance_pct')))} |"
            )

    journal_fields = [
        ("Market thesis", journal.get("market_thesis")),
        ("Watchlist focus", journal.get("watchlist_focus")),
        ("Risk notes", journal.get("risk_notes")),
        ("Post-session review", journal.get("post_session_review")),
    ]
    lines.extend(
        [
            "",
            "## Session Journal",
            "",
            f"- Date: {_inline(journal.get('date'))}",
            f"- Updated: {_inline(journal.get('updated_at'))}",
        ]
    )
    if any(value for _, value in journal_fields):
        for label, value in journal_fields:
            if value:
                lines.extend(["", f"### {label}", "", _markdown_block(value)])
    else:
        lines.append("- No journal notes.")

    lines.extend(
        [
            "",
            "## Review And Risk",
            "",
            f"- Active items: {_number(summary.get('active_items'))}",
            f"- Ready items: {_number(_mapping(summary.get('status_counts')).get('ready'))}",
            f"- Unsized active items: {_number(summary.get('unsized_items'))}",
            f"- Total planned risk: {_money(summary.get('total_risk_amount'))}",
            f"- Total planned capital: {_money(summary.get('total_planned_capital'))}",
            f"- Queue risk: {_pct(summary.get('risk_budget_pct'))}",
            f"- Planned capital: {_pct(summary.get('planned_capital_pct'))}",
            f"- Open stop risk: {_pct(_mapping(summary.get('open_position_risk')).get('stop_risk_pct'))}",
        ]
    )
    warnings = _list(summary.get("warnings"))[:8]
    if warnings:
        lines.extend(["", "Risk warnings:"])
        for warning in warnings:
            warning_map = _mapping(warning)
            lines.append(f"- {_inline(warning_map.get('label') or warning_map.get('message') or warning)}")
    risk_actions = _list(summary.get("risk_actions"))[:8]
    if risk_actions:
        lines.extend(["", "Risk actions:"])
        for action in risk_actions:
            action_map = _mapping(action)
            tickers = ", ".join(str(ticker) for ticker in _list(action_map.get("tickers"))[:4])
            suffix = f" ({_inline(tickers)})" if tickers else ""
            lines.append(
                f"- {_inline(action_map.get('label') or 'Review risk')}: "
                f"{_inline(action_map.get('detail') or action_map.get('action') or '')}{suffix}"
            )
    breakdown = _list(summary.get("status_breakdown"))
    if breakdown:
        lines.extend(
            [
                "",
                "| Status | Count | Risk | Capital |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for row_value in breakdown:
            row = _mapping(row_value)
            lines.append(
                "| "
                f"{_cell(row.get('status'))} | "
                f"{_cell(_number(row.get('count')))} | "
                f"{_cell(_money(row.get('risk_amount')))} | "
                f"{_cell(_money(row.get('planned_capital')))} |"
            )

    items = (_list(review_export.get("items")) or _list(review.get("items")))[:12]
    lines.extend(["", "## Review Queue", ""])
    if items:
        lines.extend(
            [
                "| Ticker | Status | Priority | Tags | Score | Shares | Risk | Capital |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for item in items:
            row = _mapping(item)
            tags = ", ".join(str(tag) for tag in _list(row.get("review_tags")))
            lines.append(
                "| "
                f"{_cell(row.get('ticker'))} | "
                f"{_cell(row.get('decision_status'))} | "
                f"{_cell(row.get('review_priority'))} | "
                f"{_cell(tags)} | "
                f"{_cell(_number(row.get('canslim_score')))} | "
                f"{_cell(_number(row.get('planned_shares')))} | "
                f"{_cell(_money(row.get('risk_amount')))} | "
                f"{_cell(_money(row.get('planned_capital')))} |"
            )
    else:
        lines.append("No review items.")

    artifact_rows = _list(artifacts.get("artifacts"))
    lines.extend(["", "## Generated Outputs", ""])
    if artifact_rows:
        lines.extend(["| Output | State | Detail |", "| --- | --- | --- |"])
        for artifact in artifact_rows:
            row = _mapping(artifact)
            state = "ready" if row.get("exists") else "missing"
            detail_parts = [
                row.get("path") or row.get("filename"),
                _age_hours(row.get("age_hours")) if row.get("age_hours") is not None else "",
                f"{_number(row.get('rows'))} rows" if row.get("rows") is not None else "",
            ]
            lines.append(
                "| "
                f"{_cell(row.get('label') or row.get('id'))} | "
                f"{_cell(state)} | "
                f"{_cell(' / '.join(part for part in detail_parts if part))} |"
            )
    else:
        lines.append("No artifact metadata.")

    job_rows = _list(jobs.get("jobs"))
    lines.extend(["", "## Recent Jobs", ""])
    if job_rows:
        lines.extend(["| Mode | Status | Finished | Return |", "| --- | --- | --- | ---: |"])
        for job in job_rows:
            row = _mapping(job)
            lines.append(
                "| "
                f"{_cell(row.get('mode'))} | "
                f"{_cell(row.get('status'))} | "
                f"{_cell(row.get('finished_at') or row.get('started_at'))} | "
                f"{_cell(row.get('returncode'))} |"
            )
    else:
        lines.append("No job history.")

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Source count: {_number(provenance.get('source_count'))}",
            f"- Missing required: {_inline(', '.join(str(item) for item in _list(provenance.get('missing_required'))) or 'none')}",
            f"- Stale sources: {_inline(', '.join(str(item) for item in _list(provenance.get('stale_sources'))) or 'none')}",
        ]
    )
    sources = _list(provenance.get("sources"))[:8]
    if sources:
        lines.extend(["", "| Source | State | Path |", "| --- | --- | --- |"])
        for source in sources:
            row = _mapping(source)
            state = "missing" if not row.get("exists") else "stale" if row.get("stale") else "ready"
            lines.append(f"| {_cell(row.get('label') or row.get('id'))} | {_cell(state)} | {_cell(row.get('path'))} |")

    return "\n".join(lines).rstrip() + "\n"


def _normalize_report_format(value: str | None) -> str:
    normalized = str(value or "md").strip().lower()
    if normalized in {"md", "markdown"}:
        return "md"
    if normalized == "json":
        return "json"
    raise ValueError("format must be one of: json, md")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _inline(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("\r", " ").replace("\n", " ").strip() or "-"


def _cell(value: Any) -> str:
    return _inline(value).replace("|", "\\|")


def _markdown_block(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return text if text else "-"


def _number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if not number.is_integer():
        return f"{number:.2f}".rstrip("0").rstrip(".")
    return str(int(number))


def _money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"${number:,.2f}"


def _pct(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.1f}%"


def _percent_fraction(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return _pct(number * 100)


def _age_hours(value: Any) -> str:
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return "-"
    if hours < 1:
        return "<1h"
    return f"{hours:.0f}h"


def _age_days(value: Any) -> str:
    try:
        days = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{days:.0f}d"


def _market_freshness(health: Mapping[str, Any]) -> str:
    lag = health.get("market_session_lag")
    days = health.get("market_age_days")
    lag_label = "-"
    try:
        lag_number = float(lag)
    except (TypeError, ValueError):
        pass
    else:
        lag_count = int(lag_number)
        lag_label = f"{lag_count} completed session" if lag_count == 1 else f"{lag_count} completed sessions"
    day_label = _age_days(days)
    return f"{lag_label} ({day_label} calendar)"
