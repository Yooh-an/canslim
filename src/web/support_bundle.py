"""Support bundle export for dashboard diagnostics."""

from __future__ import annotations

import datetime as dt
import json
import platform
from pathlib import Path
from typing import Any, Callable

from src.web import data_provider, job_runner, redaction, request_trace, runtime_info, workspace_audit
from src.web.disclosure import research_disclosure


SCHEMA_VERSION = 2


def export_support_bundle(profile: str | None = None, *, access_context: dict[str, Any] | None = None) -> dict[str, str]:
    """Return a downloadable JSON support bundle for troubleshooting."""
    bundle = build_support_bundle(profile, access_context=access_context)
    body = json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return {
        "profile": str(bundle["profile"]),
        "filename": f"canslim-support-{bundle['profile']}.json",
        "content_type": "application/json; charset=utf-8",
        "body": body,
    }


def build_support_bundle(profile: str | None = None, *, access_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build non-portfolio operational context for support/debugging."""
    profile_name = data_provider.normalize_profile(profile)
    sections = {
        "diagnostics": _safe_section(
            lambda: data_provider.get_operational_diagnostics(profile_name, access_context=access_context)
        ),
        "readiness": _safe_section(lambda: data_provider.get_release_readiness(profile_name, access_context=access_context)),
        "artifacts": _safe_section(lambda: data_provider.get_artifacts(profile_name)),
        "provenance": _safe_section(lambda: data_provider.get_data_provenance(profile_name)),
        "current_job": _safe_section(job_runner.current_job),
        "job_history": _safe_section(lambda: job_runner.job_history(limit=10)),
        "request_trace": _safe_section(lambda: request_trace.recent_request_trace(limit=25)),
        "client_events": _safe_section(lambda: request_trace.recent_client_events(limit=25)),
        "workspace_audit": _safe_section(lambda: workspace_audit.get_workspace_audit(limit=20)),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now(),
        "profile": profile_name,
        "research_disclosure": research_disclosure(),
        "privacy": {
            "redaction_level": "operational_metadata_only",
            "path_policy": "absolute local paths are replaced with project-relative or redacted labels",
            "excluded": [
                "review queue item bodies",
                "session journal note text",
                "workspace snapshot payloads",
                "raw store file contents",
                "HTTP query strings and request bodies",
                "browser localStorage/sessionStorage contents",
            ],
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "project": data_provider.PROJECT_ROOT.name,
        },
        "runtime": runtime_info.runtime_metadata(),
        "sections": _section_index(sections),
        **sections,
    }


def _safe_section(factory: Callable[[], Any]) -> dict[str, Any]:
    try:
        payload = factory()
    except Exception as exc:  # pragma: no cover - defensive bundle resilience
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "data": _redact_paths(payload)}


def _section_index(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failed = [name for name, section in sections.items() if not section.get("ok")]
    return {
        "total": len(sections),
        "ok_count": len(sections) - len(failed),
        "failed_count": len(failed),
        "failed": failed,
    }


def _redact_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _redact_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_paths(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_paths(item) for item in value]
    if isinstance(value, str):
        return _redact_path_text(value)
    return value


def _redact_path_text(value: str) -> str:
    return redaction.redact_local_paths(value, project_root=data_provider.PROJECT_ROOT, home_root=Path.home())


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()
