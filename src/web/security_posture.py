"""Security control metadata shared by the dashboard server and diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.web import redaction, security_headers


CSRF_HEADER = "X-CSRF-Token"
DEFAULT_AUTH_ENV = "CANSLIM_DASHBOARD_AUTH"
AUTH_FAILURE_LIMIT = 6
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_LOCKOUT_SECONDS = 30
MAX_JSON_BODY_BYTES = 1_000_000
WRITE_RATE_LIMIT = 180
WRITE_RATE_WINDOW_SECONDS = 60
REQUEST_TIMEOUT_SECONDS = 15
CSRF_EXEMPT_WRITE_PATHS = frozenset({"/api/client-events"})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SENSITIVE_DOWNLOAD_PATHS = frozenset(
    {
        "/api/analyze/export",
        "/api/artifacts/download",
        "/api/review/export",
        "/api/screener/export",
        "/api/session/report",
        "/api/support/bundle",
        "/api/workspace/audit/export",
        "/api/workspace/backups/download",
        "/api/workspace/export",
    }
)


def security_posture(
    *,
    project_root: Path | None = None,
    access_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an operational summary of the dashboard safety controls."""
    controls = [
        _write_protection_control(),
        _download_protection_control(),
        _host_origin_control(),
        _access_control_control(access_context),
        _auth_throttle_control(access_context),
        _request_body_limit_control(access_context),
        _write_rate_limit_control(access_context),
        _request_timeout_control(access_context),
        *_browser_policy_controls(security_headers.security_header_map()),
        _privacy_redaction_control(project_root=project_root),
    ]
    counts = {
        "ready": sum(1 for control in controls if control["level"] == "ready"),
        "warning": sum(1 for control in controls if control["level"] == "warning"),
        "blocked": sum(1 for control in controls if control["level"] == "blocked"),
    }
    level = "blocked" if counts["blocked"] else "warning" if counts["warning"] else "ready"
    return {
        "level": level,
        "summary": f"{counts['ready']}/{len(controls)} controls ready",
        "counts": counts,
        "controls": controls,
    }


def _control(control_id: str, label: str, level: str, detail: str) -> dict[str, str]:
    normalized = level if level in {"ready", "warning", "blocked"} else "warning"
    return {"id": control_id, "label": label, "level": normalized, "detail": detail}


def _write_protection_control() -> dict[str, str]:
    required_methods = {"POST", "PUT", "PATCH", "DELETE"}
    methods_ready = required_methods <= set(WRITE_METHODS)
    header_ready = bool(CSRF_HEADER)
    diagnostics_exempt = CSRF_EXEMPT_WRITE_PATHS == frozenset({"/api/client-events"})
    level = "ready" if methods_ready and header_ready and diagnostics_exempt else "blocked"
    detail = f"{CSRF_HEADER} required for write APIs; diagnostics intake exempted"
    return _control("csrf_write_token", "Write API token", level, detail)


def _download_protection_control() -> dict[str, str]:
    expected = {
        "/api/artifacts/download",
        "/api/review/export",
        "/api/workspace/export",
        "/api/workspace/backups/download",
        "/api/session/report",
        "/api/support/bundle",
    }
    level = "ready" if CSRF_HEADER and expected <= set(SENSITIVE_DOWNLOAD_PATHS) else "blocked"
    detail = f"{len(SENSITIVE_DOWNLOAD_PATHS)} export/download routes require the {CSRF_HEADER} header"
    return _control("download_token", "Download token", level, detail)


def _host_origin_control() -> dict[str, str]:
    return _control(
        "host_origin_guard",
        "Host/origin guard",
        "ready",
        "validated Host header and explicit same-origin Origin required for writes",
    )


def _access_control_control(access_context: Mapping[str, Any] | None = None) -> dict[str, str]:
    context = access_context or {}
    if not context:
        return _control(
            "access_control",
            "Dashboard access control",
            "ready",
            f"local-only binding by default; optional Basic Auth via --auth or {DEFAULT_AUTH_ENV}; --require-auth available for fail-closed deployments",
        )

    allow_remote = bool(context.get("allow_remote"))
    auth_enabled = bool(context.get("auth_enabled"))
    require_auth = bool(context.get("require_auth"))
    auth_env = str(context.get("auth_env") or DEFAULT_AUTH_ENV)
    if not allow_remote:
        detail = "loopback-only dashboard"
        if auth_enabled:
            detail += "; Basic Auth enabled"
        else:
            detail += "; Basic Auth optional for local use"
        return _control("access_control", "Dashboard access control", "ready", detail)
    if not auth_enabled:
        return _control(
            "access_control",
            "Dashboard access control",
            "blocked",
            f"remote binding is enabled without Basic Auth; set --auth or {auth_env}",
        )
    if not require_auth:
        return _control(
            "access_control",
            "Dashboard access control",
            "warning",
            "remote binding is authenticated; add --require-auth for fail-closed startup",
        )
    return _control(
        "access_control",
        "Dashboard access control",
        "ready",
        f"remote binding authenticated and fail-closed via {auth_env}",
    )


def _auth_throttle_control(access_context: Mapping[str, Any] | None = None) -> dict[str, str]:
    context = access_context or {}
    if not context:
        return _control(
            "auth_failure_throttle",
            "Auth failure throttle",
            "ready",
            "Basic Auth failures are rate-limited when authentication is enabled",
        )
    auth_enabled = bool(context.get("auth_enabled"))
    try:
        limit = int(context.get("auth_failure_limit") or AUTH_FAILURE_LIMIT)
        window_seconds = int(context.get("auth_failure_window_seconds") or AUTH_FAILURE_WINDOW_SECONDS)
        lockout_seconds = int(context.get("auth_lockout_seconds") or AUTH_LOCKOUT_SECONDS)
    except (TypeError, ValueError):
        limit = window_seconds = lockout_seconds = 0
    if not auth_enabled:
        return _control(
            "auth_failure_throttle",
            "Auth failure throttle",
            "ready",
            "inactive until Basic Auth is enabled",
        )
    ready = limit > 0 and window_seconds > 0 and lockout_seconds > 0
    return _control(
        "auth_failure_throttle",
        "Auth failure throttle",
        "ready" if ready else "blocked",
        f"{limit} failed attempt(s) per {window_seconds}s lock for {lockout_seconds}s"
        if ready
        else "Basic Auth is enabled but failure throttling is not configured",
    )


def _request_body_limit_control(access_context: Mapping[str, Any] | None = None) -> dict[str, str]:
    context = access_context or {}
    try:
        max_bytes = int(context.get("max_json_body_bytes") or MAX_JSON_BODY_BYTES)
    except (TypeError, ValueError):
        max_bytes = 0
    ready = max_bytes > 0
    return _control(
        "request_body_limit",
        "Request body limit",
        "ready" if ready else "blocked",
        f"JSON write bodies capped at {max_bytes} byte(s)" if ready else "JSON write body limit is not configured",
    )


def _write_rate_limit_control(access_context: Mapping[str, Any] | None = None) -> dict[str, str]:
    context = access_context or {}
    try:
        limit = int(context.get("write_rate_limit") or WRITE_RATE_LIMIT)
        window_seconds = int(context.get("write_rate_window_seconds") or WRITE_RATE_WINDOW_SECONDS)
    except (TypeError, ValueError):
        limit = window_seconds = 0
    ready = limit > 0 and window_seconds > 0
    return _control(
        "write_rate_limit",
        "Write API rate limit",
        "ready" if ready else "blocked",
        f"write APIs capped at {limit} request(s) per {window_seconds}s per client"
        if ready
        else "write API rate limit is not configured",
    )


def _request_timeout_control(access_context: Mapping[str, Any] | None = None) -> dict[str, str]:
    context = access_context or {}
    try:
        timeout_seconds = int(context.get("request_timeout_seconds") or REQUEST_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout_seconds = 0
    ready = timeout_seconds > 0
    return _control(
        "request_timeout",
        "Request timeout",
        "ready" if ready else "blocked",
        f"client sockets time out after {timeout_seconds}s of inactivity"
        if ready
        else "client socket timeout is not configured",
    )


def _browser_policy_controls(headers: Mapping[str, str]) -> list[dict[str, str]]:
    csp = headers.get("Content-Security-Policy", "")
    permissions = headers.get("Permissions-Policy", "")
    isolation_ready = (
        "default-src 'self'" in csp
        and "script-src 'self'" in csp
        and "style-src 'self'" in csp
        and "connect-src 'self'" in csp
        and "object-src 'none'" in csp
        and "base-uri 'none'" in csp
        and "frame-ancestors 'none'" in csp
        and "'unsafe-inline'" not in csp
        and headers.get("Cross-Origin-Opener-Policy") == "same-origin"
        and headers.get("Cross-Origin-Resource-Policy") == "same-origin"
        and headers.get("X-Frame-Options") == "DENY"
    )
    permissions_ready = all(
        directive in permissions
        for directive in (
            "camera=()",
            "microphone=()",
            "geolocation=()",
            "payment=()",
            "clipboard-read=()",
        )
    )
    return [
        _control(
            "browser_isolation_headers",
            "Browser isolation",
            "ready" if isolation_ready else "blocked",
            "strict CSP, frame denial, COOP/CORP, and XFO configured",
        ),
        _control(
            "browser_permission_policy",
            "Browser permissions",
            "ready" if permissions_ready else "blocked",
            "camera, microphone, geolocation, payment, and clipboard APIs disabled",
        ),
    ]


def _privacy_redaction_control(*, project_root: Path | None) -> dict[str, str]:
    sample_path = project_root or redaction.PROJECT_ROOT
    redacted = redaction.redact_local_paths(str(sample_path), project_root=sample_path)
    ready = redacted != str(sample_path)
    return _control(
        "diagnostic_redaction",
        "Diagnostic redaction",
        "ready" if ready else "blocked",
        "support and request diagnostics redact local absolute paths and omit bodies",
    )
