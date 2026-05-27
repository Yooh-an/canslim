"""Local HTTP server for the CAN SLIM browser UI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import mimetypes
import os
import secrets
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.web import (
    data_provider,
    job_runner,
    request_trace,
    redaction,
    review_store,
    runtime_info,
    security_headers,
    security_posture,
    session_journal,
    session_report,
    support_bundle,
    workspace_audit,
    workspace_snapshot,
    workspace_store,
)


STATIC_ROOT = data_provider.PROJECT_ROOT / "web"
mimetypes.add_type("application/manifest+json", ".webmanifest")
AUTH_REALM = "CANSLIM SEPA"
DEFAULT_AUTH_ENV = security_posture.DEFAULT_AUTH_ENV
CSRF_HEADER = security_posture.CSRF_HEADER
CSRF_EXEMPT_WRITE_PATHS = security_posture.CSRF_EXEMPT_WRITE_PATHS
WRITE_METHODS = security_posture.WRITE_METHODS
SENSITIVE_DOWNLOAD_PATHS = security_posture.SENSITIVE_DOWNLOAD_PATHS
AUTH_FAILURE_LIMIT = security_posture.AUTH_FAILURE_LIMIT
AUTH_FAILURE_WINDOW_SECONDS = security_posture.AUTH_FAILURE_WINDOW_SECONDS
AUTH_LOCKOUT_SECONDS = security_posture.AUTH_LOCKOUT_SECONDS
MAX_JSON_BODY_BYTES = security_posture.MAX_JSON_BODY_BYTES
WRITE_RATE_LIMIT = security_posture.WRITE_RATE_LIMIT
WRITE_RATE_WINDOW_SECONDS = security_posture.WRITE_RATE_WINDOW_SECONDS
REQUEST_TIMEOUT_SECONDS = security_posture.REQUEST_TIMEOUT_SECONDS
DOWNLOAD_AUDIT_ACTIONS = {
    "/api/analyze/export": "stock_dossier_export",
    "/api/artifacts/download": "artifact_download",
    "/api/review/export": "review_queue_export",
    "/api/screener/export": "screener_export",
    "/api/session/report": "session_report_export",
    "/api/support/bundle": "support_bundle_export",
    "/api/workspace/audit/export": "workspace_audit_export",
    "/api/workspace/backups/download": "workspace_backup_download",
    "/api/workspace/export": "workspace_snapshot_export",
}


class UnsupportedMediaType(ValueError):
    """Raised when a request body uses a media type the API does not accept."""


class PayloadTooLarge(ValueError):
    """Raised when a request body exceeds the dashboard API limit."""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Serve static assets and JSON API routes."""

    server_version = "CANSLIMDashboard/1.0"

    def setup(self) -> None:
        self.request.settimeout(_request_timeout_seconds(self.server))
        super().setup()

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request(head_only=True):
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed.path, parse_qs(parsed.query), head_only=True)
            return
        self._serve_static(parsed.path, head_only=True)

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request(require_same_origin=True):
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND)
            return
        if not self._csrf_token_allowed(parsed.path):
            self._send_error_json("CSRF token is invalid or missing", status=HTTPStatus.FORBIDDEN)
            return
        if self._reject_rate_limited_write_request():
            return
        self._handle_api_write("POST", parsed.path, parse_qs(parsed.query))

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request(require_same_origin=True):
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND)
            return
        if not self._csrf_token_allowed(parsed.path):
            self._send_error_json("CSRF token is invalid or missing", status=HTTPStatus.FORBIDDEN)
            return
        if self._reject_rate_limited_write_request():
            return
        self._handle_api_write("DELETE", parsed.path, parse_qs(parsed.query))

    def do_PUT(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request(require_same_origin=True):
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND)
            return
        if not self._csrf_token_allowed(parsed.path):
            self._send_error_json("CSRF token is invalid or missing", status=HTTPStatus.FORBIDDEN)
            return
        if self._reject_rate_limited_write_request():
            return
        self._handle_api_write("PUT", parsed.path, parse_qs(parsed.query))

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib callback name
        self._begin_request()
        if self._reject_untrusted_request(require_same_origin=True):
            return
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND)
            return
        if not self._csrf_token_allowed(parsed.path):
            self._send_error_json("CSRF token is invalid or missing", status=HTTPStatus.FORBIDDEN)
            return
        if self._reject_rate_limited_write_request():
            return
        self._handle_api_write("PATCH", parsed.path, parse_qs(parsed.query))

    def log_message(self, format: str, *args: object) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(format, *args)

    def version_string(self) -> str:
        return self.server_version

    def _begin_request(self) -> None:
        self._dashboard_request_started_at = time.perf_counter()
        self._request_id()

    def end_headers(self) -> None:
        for key, value in security_headers.security_header_map().items():
            self.send_header(key, value)
        self.send_header("X-Request-ID", self._request_id())
        super().end_headers()

    def _request_id(self) -> str:
        request_id = getattr(self, "_dashboard_request_id", "")
        if not request_id:
            request_id = secrets.token_hex(6)
            self._dashboard_request_id = request_id
        return request_id

    def _send_response(self, status: HTTPStatus | int) -> None:
        self._record_request_trace(status)
        self.send_response(status)

    def _record_request_trace(self, status: HTTPStatus | int) -> None:
        if getattr(self, "_dashboard_request_recorded", False):
            return
        self._dashboard_request_recorded = True
        parsed = urlparse(getattr(self, "path", ""))
        if not parsed.path.startswith("/api/"):
            return
        started_at = getattr(self, "_dashboard_request_started_at", time.perf_counter())
        request_trace.record_request(
            request_id=self._request_id(),
            method=getattr(self, "command", ""),
            path=parsed.path,
            status=int(status),
            duration_ms=(time.perf_counter() - started_at) * 1000,
            error_code=str(getattr(self, "_dashboard_error_code", "") or ""),
            error=str(getattr(self, "_dashboard_error", "") or ""),
        )

    def _reject_untrusted_request(self, *, require_same_origin: bool = False, head_only: bool = False) -> bool:
        auth_credentials = getattr(self.server, "auth_credentials", None)
        auth_key = _auth_failure_key(getattr(self, "client_address", None))
        retry_after = _auth_retry_after(self.server, auth_key) if auth_credentials is not None else 0
        if retry_after:
            self._send_error_json(
                "Authentication is temporarily locked",
                status=HTTPStatus.TOO_MANY_REQUESTS,
                head_only=head_only,
                extra_headers={"Retry-After": str(retry_after)},
            )
            return True
        if not _basic_auth_allowed(self.headers.get("Authorization"), auth_credentials):
            retry_after = _record_auth_failure(self.server, auth_key) if auth_credentials is not None else 0
            status = HTTPStatus.TOO_MANY_REQUESTS if retry_after else HTTPStatus.UNAUTHORIZED
            headers = {"WWW-Authenticate": f'Basic realm="{AUTH_REALM}", charset="UTF-8"'}
            if retry_after:
                headers["Retry-After"] = str(retry_after)
            self._send_error_json(
                "Authentication is temporarily locked" if retry_after else "Authentication is required",
                status=status,
                head_only=head_only,
                extra_headers=headers,
            )
            return True
        _clear_auth_failures(self.server, auth_key)
        allow_remote = bool(getattr(self.server, "allow_remote", False))
        if not _host_header_allowed(self.headers.get("Host"), allow_remote=allow_remote):
            self._send_error_json("Host header is not allowed", status=HTTPStatus.FORBIDDEN, head_only=head_only)
            return True
        if require_same_origin and not _origin_header_allowed(
            self.headers.get("Origin"),
            self.headers.get("Host"),
            allow_remote=allow_remote,
        ):
            self._send_error_json("Origin is not allowed", status=HTTPStatus.FORBIDDEN, head_only=head_only)
            return True
        return False

    def _reject_rate_limited_write_request(self) -> bool:
        retry_after = _record_write_rate_request(self.server, _write_rate_key(getattr(self, "client_address", None)))
        if not retry_after:
            return False
        self._send_error_json(
            "Write API is rate limited",
            status=HTTPStatus.TOO_MANY_REQUESTS,
            extra_headers={"Retry-After": str(retry_after)},
        )
        return True

    def _handle_api(self, path: str, query: dict[str, list[str]], *, head_only: bool = False) -> None:
        try:
            if path in SENSITIVE_DOWNLOAD_PATHS and not self._download_token_allowed():
                self._send_error_json("Download token is invalid or missing", status=HTTPStatus.FORBIDDEN, head_only=head_only)
                return
            profile = _first(query, "profile")
            if path == "/api/overview":
                payload = data_provider.get_overview(profile)
            elif path == "/api/screener":
                payload = data_provider.get_candidates(
                    profile,
                    limit=_int(_first(query, "limit"), 80),
                    query=_first(query, "q") or "",
                    min_score=_float(_first(query, "min_score")),
                    setup=_first(query, "setup") or "",
                    sort_by=_first(query, "sort_by") or "",
                    sort_dir=_first(query, "sort_dir") or "",
                )
            elif path == "/api/compare":
                payload = data_provider.get_candidate_comparison(
                    profile,
                    tickers=_first(query, "tickers") or _first(query, "ticker") or "",
                )
            elif path == "/api/screener/export":
                export = data_provider.export_candidates(
                    profile,
                    limit=_int(_first(query, "limit"), 300),
                    query=_first(query, "q") or "",
                    min_score=_float(_first(query, "min_score")),
                    setup=_first(query, "setup") or "",
                    sort_by=_first(query, "sort_by") or "",
                    sort_dir=_first(query, "sort_dir") or "",
                )
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=str(export.get("profile") or profile or ""),
                    audit_detail={"row_count": export.get("row_count")},
                    head_only=head_only,
                )
                return
            elif path == "/api/analyze":
                payload = data_provider.get_stock_analysis(_first(query, "ticker") or "", profile)
            elif path == "/api/analyze/export":
                export = data_provider.export_stock_dossier(_first(query, "ticker") or "", profile)
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=str(export.get("payload", {}).get("profile") or profile or ""),
                    audit_detail={"ticker": _first(query, "ticker") or ""},
                    head_only=head_only,
                )
                return
            elif path == "/api/profiles":
                payload = {"profiles": data_provider.available_profiles()}
            elif path == "/api/provenance":
                payload = data_provider.get_data_provenance(profile)
            elif path == "/api/artifacts":
                payload = data_provider.get_artifacts(profile)
            elif path == "/api/artifacts/download":
                artifact = data_provider.get_artifact_file(_first(query, "id") or "", profile)
                self._send_audited_file_download(
                    artifact["path"],
                    route=path,
                    content_type=artifact["content_type"],
                    filename=artifact["filename"],
                    profile=profile or "",
                    audit_detail={
                        "artifact_id": artifact.get("id"),
                        "label": artifact.get("label"),
                        "path": _relative_project_path(artifact.get("path")),
                    },
                    head_only=head_only,
                )
                return
            elif path == "/api/diagnostics":
                payload = data_provider.get_operational_diagnostics(profile, access_context=self._access_context())
            elif path == "/api/readiness":
                payload = data_provider.get_release_readiness(profile, access_context=self._access_context())
                self._send_json(
                    payload,
                    status=HTTPStatus.OK if payload.get("ok") else HTTPStatus.SERVICE_UNAVAILABLE,
                    head_only=head_only,
                )
                return
            elif path == "/api/request-trace":
                payload = request_trace.recent_request_trace(limit=_int(_first(query, "limit"), 8))
            elif path == "/api/client-events":
                payload = request_trace.recent_client_events(limit=_int(_first(query, "limit"), 8))
            elif path == "/api/review":
                payload = review_store.get_review_queue(profile)
            elif path == "/api/review/activity":
                payload = review_store.get_review_activity(profile)
            elif path == "/api/review/summary":
                payload = review_store.get_review_summary(profile, risk=_export_risk_settings(query))
            elif path == "/api/review/export":
                export = review_store.export_review_queue(
                    profile,
                    _first(query, "format"),
                    risk=_export_risk_settings(query),
                    filters=_export_review_filters(query),
                )
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=str(export.get("profile") or profile or ""),
                    audit_detail={"format": export.get("format")},
                    head_only=head_only,
                )
                return
            elif path == "/api/workspace/export":
                export = workspace_snapshot.export_workspace_snapshot(profile, risk=_export_risk_settings(query))
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=str(export.get("profile") or profile or ""),
                    head_only=head_only,
                )
                return
            elif path == "/api/workspace/backups":
                payload = workspace_snapshot.list_workspace_backups(
                    profile,
                    limit=_int(_first(query, "limit"), 12),
                )
            elif path == "/api/workspace/backups/download":
                export = workspace_snapshot.export_workspace_backup(_first(query, "filename") or "")
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=profile or "",
                    audit_detail={"backup_filename": export["filename"]},
                    head_only=head_only,
                )
                return
            elif path == "/api/workspace/backups/preview":
                payload = workspace_snapshot.preview_workspace_backup_restore(_first(query, "filename") or "")
            elif path == "/api/workspace/audit":
                payload = workspace_audit.get_workspace_audit(
                    limit=_int(_first(query, "limit"), 12),
                    query=_first(query, "query") or "",
                    category=_first(query, "category") or _first(query, "type") or "",
                )
            elif path == "/api/workspace/audit/export":
                audit_query = _first(query, "query") or ""
                audit_category = _first(query, "category") or _first(query, "type") or ""
                export = workspace_audit.export_workspace_audit(
                    limit=_int(_first(query, "limit"), 120),
                    query=audit_query,
                    category=audit_category,
                )
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=profile or "",
                    audit_detail={
                        "limit": _int(_first(query, "limit"), 120),
                        "category": audit_category,
                        "has_query": bool(audit_query),
                    },
                    head_only=head_only,
                )
                return
            elif path == "/api/session/report":
                export = session_report.export_session_report(
                    profile,
                    risk=_export_risk_settings(query),
                    format=_first(query, "format"),
                    session_date=_first(query, "date"),
                )
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=profile or "",
                    audit_detail={"format": _first(query, "format") or "md", "date": _first(query, "date") or ""},
                    head_only=head_only,
                )
                return
            elif path == "/api/support/bundle":
                export = support_bundle.export_support_bundle(profile, access_context=self._access_context())
                self._send_audited_download(
                    export["body"],
                    route=path,
                    content_type=export["content_type"],
                    filename=export["filename"],
                    profile=str(export.get("profile") or profile or ""),
                    head_only=head_only,
                )
                return
            elif path == "/api/jobs/current":
                payload = job_runner.current_job()
            elif path == "/api/jobs/history":
                payload = job_runner.job_history(limit=_int(_first(query, "limit"), 10))
            elif path == "/api/session/journal":
                payload = session_journal.get_session_journal(profile, session_date=_first(query, "date"))
            elif path == "/api/preferences":
                payload = workspace_store.get_preferences()
            elif path == "/api/health":
                payload = {
                    "ok": True,
                    "status": "ready",
                    "server": runtime_info.runtime_metadata(),
                    "csrf_token": self._csrf_token(),
                }
            else:
                self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            self._send_json(payload, head_only=head_only)
        except ValueError as exc:
            self._send_error_json(str(exc), status=HTTPStatus.BAD_REQUEST, head_only=head_only)
        except FileNotFoundError as exc:
            self._send_error_json(str(exc), status=HTTPStatus.NOT_FOUND, head_only=head_only)
        except Exception as exc:  # pragma: no cover - surfaced to browser
            self._send_error_json(str(exc), status=HTTPStatus.INTERNAL_SERVER_ERROR, head_only=head_only)

    def _handle_api_write(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        try:
            if path == "/api/client-events":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                event = payload.get("event", payload)
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                recorded = request_trace.record_client_event(event, profile=data_provider.normalize_profile(profile))
                self._send_json({"accepted": True, "event": recorded})
                return

            if path == "/api/jobs":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                mode = str(payload.get("mode") or "")
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                self._send_json(job_runner.start_job(mode, profile), status=HTTPStatus.CREATED)
                return

            if path == "/api/jobs/cancel":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                self._send_json(job_runner.cancel_job())
                return

            if path == "/api/preferences":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                self._send_json(workspace_store.save_preferences(self._read_json_body()))
                return

            if path == "/api/session/journal":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                self._send_json(session_journal.save_session_journal(profile, payload))
                return

            if path == "/api/workspace/import":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                snapshot = payload.get("snapshot", payload)
                if not isinstance(snapshot, dict):
                    raise ValueError("Workspace snapshot must be a JSON object")
                if str(payload.get("confirm") or "").strip().lower() != "import":
                    raise ValueError("confirm=import is required to import a workspace snapshot")
                imported = workspace_snapshot.import_workspace_snapshot(snapshot)
                _record_workspace_audit(
                    imported,
                    "import_workspace",
                    profile=str(imported.get("profile") or ""),
                    summary=f"Imported workspace for {imported.get('profile') or 'profile'}",
                    detail={
                        "backup_filename": (imported.get("backup") or {}).get("filename")
                        if isinstance(imported.get("backup"), dict)
                        else "",
                        "backup_recovery_only": bool((imported.get("backup") or {}).get("recovery_only"))
                        if isinstance(imported.get("backup"), dict)
                        else False,
                        "quarantined_store_count": len(imported.get("quarantined_stores") or []),
                        "review_count": len((imported.get("review") or {}).get("items", []))
                        if isinstance(imported.get("review"), dict)
                        else 0,
                    },
                )
                self._send_json(imported, status=HTTPStatus.CREATED)
                return

            if path == "/api/workspace/import/preview":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                snapshot = payload.get("snapshot", payload)
                if not isinstance(snapshot, dict):
                    raise ValueError("Workspace snapshot must be a JSON object")
                self._send_json(workspace_snapshot.preview_workspace_import(snapshot))
                return

            if path == "/api/workspace/backups/restore":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                filename = str(payload.get("filename") or "")
                if str(payload.get("confirm") or "").strip().lower() != "restore":
                    raise ValueError("confirm=restore is required to restore a workspace backup")
                expected_sha256_12 = payload.get("expected_sha256_12", payload.get("sha256_12"))
                restored = workspace_snapshot.restore_workspace_backup(
                    filename,
                    expected_sha256_12=expected_sha256_12,
                )
                restored_from = restored.get("restored_from_backup") if isinstance(restored.get("restored_from_backup"), dict) else {}
                _record_workspace_audit(
                    restored,
                    "restore_backup",
                    profile=str(restored.get("profile") or ""),
                    summary=f"Restored backup {restored_from.get('filename') or filename}",
                    detail={
                        "filename": restored_from.get("filename") or filename,
                        "sha256_12": restored_from.get("sha256_12") or "",
                        "backup_recovery_only": bool((restored.get("backup") or {}).get("recovery_only"))
                        if isinstance(restored.get("backup"), dict)
                        else False,
                        "quarantined_store_count": len(restored.get("quarantined_stores") or []),
                    },
                )
                self._send_json(restored, status=HTTPStatus.CREATED)
                return

            if path == "/api/workspace/backups":
                if method != "DELETE":
                    self._send_method_not_allowed("DELETE")
                    return
                payload = self._read_json_body()
                filename = str(payload.get("filename") or _first(query, "filename") or "")
                if str(payload.get("confirm") or _first(query, "confirm") or "").strip().lower() != "delete":
                    raise ValueError("confirm=delete is required to delete a workspace backup")
                expected_sha256_12 = payload.get("expected_sha256_12", payload.get("sha256_12"))
                deleted = workspace_snapshot.delete_workspace_backup(
                    filename,
                    expected_sha256_12=expected_sha256_12,
                )
                backup = deleted.get("backup") if isinstance(deleted.get("backup"), dict) else {}
                _record_workspace_audit(
                    deleted,
                    "delete_backup",
                    profile=str(backup.get("profile") or ""),
                    summary=f"Deleted backup {backup.get('filename') or filename}",
                    detail={
                        "filename": backup.get("filename") or filename,
                        "sha256_12": backup.get("sha256_12") or "",
                    },
                )
                self._send_json(deleted)
                return

            if path == "/api/workspace/temp-files/cleanup":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                if str(payload.get("confirm") or "").strip().lower() != "cleanup":
                    raise ValueError("confirm=cleanup is required to clean workspace temp files")
                cleanup = data_provider.cleanup_workspace_atomic_temp_files()
                _record_workspace_audit(
                    cleanup,
                    "cleanup_temp_files",
                    summary="Cleaned interrupted workspace temp files",
                    detail={
                        "deleted_count": cleanup.get("deleted_count"),
                        "failed_count": cleanup.get("failed_count"),
                    },
                )
                self._send_json(cleanup)
                return

            if path == "/api/workspace/audit/repair":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                if str(payload.get("confirm") or "").strip().lower() != "repair":
                    raise ValueError("confirm=repair is required to repair the workspace audit store")
                repair = workspace_audit.repair_workspace_audit_store()
                if repair.get("repaired"):
                    _record_workspace_audit(
                        repair,
                        "repair_audit_store",
                        summary="Repaired workspace audit store",
                        detail={
                            "quarantine_path": repair.get("quarantine_path"),
                            "reason": repair.get("reason"),
                        },
                    )
                self._send_json(repair)
                return

            if path == "/api/review/bulk":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                items = payload.get("items")
                if not isinstance(items, list):
                    raise ValueError("Review items must be a JSON array")
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                self._send_json(review_store.add_review_items(profile, items), status=HTTPStatus.CREATED)
                return

            if path == "/api/review/actions":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                action = str(payload.get("action") or "").strip().lower()
                if action == "prices":
                    self._send_json(review_store.bulk_update_review_prices(profile, payload.get("prices")))
                    return
                tickers = payload.get("tickers")
                if not isinstance(tickers, list):
                    raise ValueError("tickers must be a JSON array")
                if action == "status":
                    self._send_json(
                        review_store.bulk_update_review_items(
                            profile,
                            tickers,
                            {"decision_status": payload.get("decision_status")},
                        )
                    )
                    return
                if action == "priority":
                    self._send_json(
                        review_store.bulk_update_review_items(
                            profile,
                            tickers,
                            {"review_priority": payload.get("review_priority")},
                        )
                    )
                    return
                if action == "tags":
                    self._send_json(
                        review_store.bulk_tag_review_items(
                            profile,
                            tickers,
                            payload.get("review_tags", payload.get("tags")),
                            mode=str(payload.get("mode") or "add"),
                        )
                    )
                    return
                if action == "remove":
                    self._send_json(review_store.bulk_remove_review_items(profile, tickers))
                    return
                raise ValueError("action must be one of: status, priority, tags, prices, remove")

            if path == "/api/review/undo":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                activity_at = str(payload.get("activity_at") or payload.get("at") or "")
                self._send_json(review_store.restore_review_activity(profile, activity_at))
                return

            if path == "/api/review/import-tickers":
                if method != "POST":
                    self._send_method_not_allowed("POST")
                    return
                payload = self._read_json_body()
                profile = str(payload.get("profile") or _first(query, "profile") or "")
                ticker_input = payload.get("tickers", payload.get("text", ""))
                prepared = data_provider.get_review_items_for_tickers(ticker_input, profile)
                if prepared["items"]:
                    queue = review_store.add_review_items(prepared["profile"], prepared["items"])
                else:
                    queue = review_store.get_review_queue(prepared["profile"])
                queue["imported"] = {
                    "requested": prepared["requested"],
                    "imported_count": len(prepared["items"]),
                    "failures": prepared["failures"],
                    "truncated_count": prepared["truncated_count"],
                    "limit": prepared["limit"],
                }
                self._send_json(queue, status=HTTPStatus.CREATED)
                return

            if path != "/api/review":
                self._send_error_json("Not found", status=HTTPStatus.NOT_FOUND)
                return

            profile = _first(query, "profile")
            if method == "POST":
                payload = self._read_json_body()
                item = payload.get("item", payload)
                if not isinstance(item, dict):
                    raise ValueError("Review item must be a JSON object")
                profile = str(payload.get("profile") or profile or "")
                self._send_json(review_store.add_review_item(profile, item), status=HTTPStatus.CREATED)
                return

            if method == "DELETE":
                ticker = _first(query, "ticker")
                if ticker:
                    self._send_json(review_store.remove_review_item(profile, ticker))
                else:
                    if _first(query, "confirm") != "clear":
                        raise ValueError("confirm=clear is required to clear the review queue")
                    self._send_json(review_store.clear_review_queue(profile))
                return

            self._send_method_not_allowed("POST, DELETE")
        except request_trace.RateLimitExceeded as exc:
            self._send_error_json(
                str(exc),
                status=HTTPStatus.TOO_MANY_REQUESTS,
                extra_headers={"Retry-After": str(exc.retry_after_seconds)},
            )
        except PayloadTooLarge as exc:
            self._send_error_json(str(exc), status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        except UnsupportedMediaType as exc:
            self._send_error_json(str(exc), status=HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
        except ValueError as exc:
            self._send_error_json(str(exc), status=HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._send_error_json(str(exc), status=HTTPStatus.CONFLICT)
        except Exception as exc:  # pragma: no cover - surfaced to browser
            self._send_error_json(str(exc), status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_static(self, request_path: str, *, head_only: bool = False) -> None:
        rel_path = _static_rel_path(request_path)
        target = (STATIC_ROOT / rel_path).resolve()
        try:
            target.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if not target.exists() or not target.is_file():
            if _static_request_requires_file(request_path):
                self._send_plain("Static asset not found\n", status=HTTPStatus.NOT_FOUND, head_only=head_only)
                return
            target = STATIC_ROOT / "index.html"
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        payload = target.read_bytes()
        self._send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_plain(
        self,
        body: str,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        head_only: bool = False,
    ) -> None:
        encoded = body.encode("utf-8")
        self._send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not head_only:
            self.wfile.write(encoded)

    def _send_json(
        self,
        payload: object,
        *,
        status: HTTPStatus = HTTPStatus.OK,
        head_only: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not head_only:
            self.wfile.write(encoded)

    def _send_error_json(
        self,
        message: str,
        *,
        status: HTTPStatus,
        head_only: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        public_message = redaction.redact_local_paths(message)
        self._dashboard_error_code = _error_code(status)
        self._dashboard_error = public_message
        self._send_json(
            {
                "error": public_message,
                "code": self._dashboard_error_code,
                "request_id": self._request_id(),
            },
            status=status,
            head_only=head_only,
            extra_headers=extra_headers,
        )

    def _send_method_not_allowed(self, allowed: str) -> None:
        self._send_error_json(
            "Method not allowed",
            status=HTTPStatus.METHOD_NOT_ALLOWED,
            extra_headers={"Allow": allowed},
        )

    def _send_download(self, body: str, *, content_type: str, filename: str, head_only: bool = False) -> None:
        encoded = body.encode("utf-8")
        checksum = _sha256_hex(encoded)
        self._send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", _attachment_header(filename))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-SHA256", checksum)
        self.send_header("X-Content-SHA256-12", checksum[:12])
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if not head_only:
            self.wfile.write(encoded)

    def _send_audited_download(
        self,
        body: str,
        *,
        route: str,
        content_type: str,
        filename: str,
        profile: str = "",
        audit_detail: dict[str, object] | None = None,
        head_only: bool = False,
    ) -> None:
        encoded = body.encode("utf-8")
        checksum = _sha256_hex(encoded)
        self._record_download_audit(
            route=route,
            filename=filename,
            content_type=content_type,
            profile=profile,
            checksum_12=checksum[:12],
            size_bytes=len(encoded),
            detail=audit_detail,
            head_only=head_only,
        )
        self._send_download(body, content_type=content_type, filename=filename, head_only=head_only)

    def _send_file_download(self, path: Path, *, content_type: str, filename: str, head_only: bool = False) -> None:
        payload = path.read_bytes()
        checksum = _sha256_hex(payload)
        self._send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", _attachment_header(filename))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-SHA256", checksum)
        self.send_header("X-Content-SHA256-12", checksum[:12])
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _send_audited_file_download(
        self,
        path: Path,
        *,
        route: str,
        content_type: str,
        filename: str,
        profile: str = "",
        audit_detail: dict[str, object] | None = None,
        head_only: bool = False,
    ) -> None:
        payload = path.read_bytes()
        checksum = _sha256_hex(payload)
        self._record_download_audit(
            route=route,
            filename=filename,
            content_type=content_type,
            profile=profile,
            checksum_12=checksum[:12],
            size_bytes=len(payload),
            detail=audit_detail,
            head_only=head_only,
        )
        self._send_file_download(path, content_type=content_type, filename=filename, head_only=head_only)

    def _read_json_body(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length <= 0:
            return {}
        max_body_bytes = _max_json_body_bytes(self.server)
        if length > max_body_bytes:
            raise PayloadTooLarge(f"Request body exceeds {max_body_bytes} byte limit")
        if not _json_content_type_allowed(self.headers.get("Content-Type")):
            raise UnsupportedMediaType("Content-Type must be application/json")
        raw = self.rfile.read(length)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Request body must be valid UTF-8") from exc
        try:
            payload = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _csrf_token(self) -> str:
        token = str(getattr(self.server, "csrf_token", "") or "")
        if not token:
            token = secrets.token_urlsafe(32)
            self.server.csrf_token = token  # type: ignore[attr-defined]
        return token

    def _csrf_token_allowed(self, path: str) -> bool:
        if path in CSRF_EXEMPT_WRITE_PATHS:
            return True
        supplied = str(self.headers.get(CSRF_HEADER) or "")
        return bool(supplied) and secrets.compare_digest(supplied, self._csrf_token())

    def _download_token_allowed(self) -> bool:
        supplied = str(self.headers.get(CSRF_HEADER) or "")
        return bool(supplied) and secrets.compare_digest(supplied, self._csrf_token())

    def _record_download_audit(
        self,
        *,
        route: str,
        filename: str,
        content_type: str,
        profile: str,
        checksum_12: str,
        size_bytes: int,
        detail: dict[str, object] | None = None,
        head_only: bool = False,
    ) -> None:
        if head_only or getattr(self, "command", "") != "GET":
            return
        event_detail = {
            "route": route,
            "filename": _safe_download_filename(filename),
            "content_type": content_type,
            "sha256_12": checksum_12,
            "size_bytes": size_bytes,
        }
        for key, value in (detail or {}).items():
            if value not in (None, ""):
                event_detail[str(key)] = value
        action = DOWNLOAD_AUDIT_ACTIONS.get(route, "download_export")
        try:
            workspace_audit.record_workspace_event(
                action,
                profile=profile,
                summary=f"Downloaded {_safe_download_filename(filename)}",
                detail=event_detail,
            )
        except ValueError:
            return

    def _access_context(self) -> dict[str, object]:
        return {
            "allow_remote": bool(getattr(self.server, "allow_remote", False)),
            "auth_enabled": getattr(self.server, "auth_credentials", None) is not None,
            "require_auth": bool(getattr(self.server, "require_auth", False)),
            "auth_env": str(getattr(self.server, "auth_env", DEFAULT_AUTH_ENV) or ""),
            "auth_failure_limit": int(getattr(self.server, "auth_failure_limit", AUTH_FAILURE_LIMIT) or AUTH_FAILURE_LIMIT),
            "auth_failure_window_seconds": int(
                getattr(self.server, "auth_failure_window_seconds", AUTH_FAILURE_WINDOW_SECONDS)
                or AUTH_FAILURE_WINDOW_SECONDS
            ),
            "auth_lockout_seconds": int(getattr(self.server, "auth_lockout_seconds", AUTH_LOCKOUT_SECONDS) or AUTH_LOCKOUT_SECONDS),
            "max_json_body_bytes": _max_json_body_bytes(self.server),
            "write_rate_limit": _write_rate_limit(self.server),
            "write_rate_window_seconds": _write_rate_window_seconds(self.server),
            "request_timeout_seconds": _request_timeout_seconds(self.server),
        }


def run(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    quiet: bool = False,
    allow_remote: bool = False,
    open_browser: bool = False,
    auth: str | None = None,
    auth_env: str | None = None,
    require_auth: bool = False,
) -> None:
    """Start the local dashboard server."""
    validate_bind_host(host, allow_remote=allow_remote)
    auth_credentials = resolve_auth_credentials(auth=auth, auth_env=auth_env)
    validate_auth_requirement(auth_credentials, require_auth=require_auth)
    server = ThreadingHTTPServer((host, port), DashboardRequestHandler)
    server.quiet = quiet  # type: ignore[attr-defined]
    server.allow_remote = allow_remote  # type: ignore[attr-defined]
    server.auth_credentials = auth_credentials  # type: ignore[attr-defined]
    server.require_auth = require_auth  # type: ignore[attr-defined]
    server.auth_env = auth_env if auth_env is not None else DEFAULT_AUTH_ENV  # type: ignore[attr-defined]
    server.csrf_token = secrets.token_urlsafe(32)  # type: ignore[attr-defined]
    server.auth_failures = {}  # type: ignore[attr-defined]
    server.auth_failure_limit = AUTH_FAILURE_LIMIT  # type: ignore[attr-defined]
    server.auth_failure_window_seconds = AUTH_FAILURE_WINDOW_SECONDS  # type: ignore[attr-defined]
    server.auth_lockout_seconds = AUTH_LOCKOUT_SECONDS  # type: ignore[attr-defined]
    server.max_json_body_bytes = MAX_JSON_BODY_BYTES  # type: ignore[attr-defined]
    server.write_rate_buckets = {}  # type: ignore[attr-defined]
    server.write_rate_limit = WRITE_RATE_LIMIT  # type: ignore[attr-defined]
    server.write_rate_window_seconds = WRITE_RATE_WINDOW_SECONDS  # type: ignore[attr-defined]
    server.request_timeout_seconds = REQUEST_TIMEOUT_SECONDS  # type: ignore[attr-defined]
    url = dashboard_url(host, port)
    print(f"CAN SLIM dashboard: {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the CAN SLIM browser dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding to non-loopback hosts. Use only behind your own network/auth controls.",
    )
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open the dashboard in a browser")
    parser.add_argument(
        "--auth",
        metavar="USER:PASSWORD",
        help="Require HTTP Basic authentication for all dashboard requests",
    )
    parser.add_argument(
        "--auth-env",
        default=DEFAULT_AUTH_ENV,
        metavar="ENV_VAR",
        help=f"Read Basic Auth credentials from an environment variable when --auth is omitted (default: {DEFAULT_AUTH_ENV})",
    )
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="Refuse to start unless Basic Auth credentials are configured",
    )
    args = parser.parse_args()
    try:
        run(
            args.host,
            args.port,
            quiet=args.quiet,
            allow_remote=args.allow_remote,
            open_browser=args.open_browser,
            auth=args.auth,
            auth_env=args.auth_env,
            require_auth=args.require_auth,
        )
    except ValueError as exc:
        parser.error(str(exc))


def _first(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def validate_bind_host(host: str, *, allow_remote: bool = False) -> None:
    """Reject remote dashboard binds unless explicitly allowed."""
    if allow_remote or _is_loopback_host(host):
        return
    raise ValueError(
        "Refusing to bind dashboard to a non-loopback host without --allow-remote. "
        "Use 127.0.0.1/localhost for local use, or add --allow-remote behind your own network/auth controls."
    )


def validate_auth_requirement(
    credentials: tuple[str, str] | None,
    *,
    require_auth: bool = False,
) -> None:
    """Reject fail-closed deployments that forgot auth credentials."""
    if require_auth and credentials is None:
        raise ValueError(
            "Dashboard authentication is required but no credentials were configured. "
            f"Set --auth USER:PASSWORD or {DEFAULT_AUTH_ENV}=USER:PASSWORD."
        )


def parse_auth_credentials(value: str | None) -> tuple[str, str] | None:
    """Parse a USER:PASSWORD Basic Auth setting."""
    if value in (None, ""):
        return None
    text = str(value)
    if ":" not in text:
        raise ValueError("--auth must be formatted as USER:PASSWORD")
    username, password = text.split(":", 1)
    if not username or not password:
        raise ValueError("--auth must include both USER and PASSWORD")
    return username, password


def resolve_auth_credentials(
    *,
    auth: str | None = None,
    auth_env: str | None = None,
    environ: dict[str, str] | None = None,
) -> tuple[str, str] | None:
    """Resolve Basic Auth credentials from an explicit value or environment variable."""
    if auth not in (None, ""):
        return parse_auth_credentials(auth)
    env_name = str(auth_env or "").strip()
    if not env_name:
        return None
    return parse_auth_credentials((environ or os.environ).get(env_name))


def dashboard_url(host: str, port: int) -> str:
    """Return a browser-friendly URL for the dashboard listener."""
    browser_host = _browser_host(host)
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    return f"http://{browser_host}:{int(port)}"


def _browser_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized in {"", "0.0.0.0", "::"}:
        return "127.0.0.1"
    return normalized


def _is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _host_header_allowed(host_header: str | None, *, allow_remote: bool = False) -> bool:
    host = _header_hostname(host_header)
    if allow_remote:
        return bool(host)
    return bool(host and _is_loopback_host(host))


def _origin_header_allowed(
    origin_header: str | None,
    host_header: str | None,
    *,
    allow_remote: bool = False,
) -> bool:
    if not origin_header:
        return False
    parsed = urlparse(origin_header)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if not allow_remote and parsed.scheme != "http":
        return False
    if not allow_remote and not _is_loopback_host(parsed.hostname):
        return False
    host = _header_host_origin_parts(host_header)
    if host is None:
        return False
    origin_port = parsed.port if parsed.port is not None else _default_origin_port(parsed.scheme)
    host_name, host_port = host
    if parsed.hostname.lower() != host_name.lower():
        return False
    return host_port is None or origin_port == host_port


def _basic_auth_allowed(
    authorization_header: str | None,
    credentials: tuple[str, str] | None,
) -> bool:
    if credentials is None:
        return True
    scheme, _, token = str(authorization_header or "").partition(" ")
    if scheme.lower() != "basic" or not token:
        return False
    try:
        decoded = base64.b64decode(token.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, separator, password = decoded.partition(":")
    if not separator:
        return False
    expected_user, expected_password = credentials
    return secrets.compare_digest(username, expected_user) and secrets.compare_digest(password, expected_password)


def _auth_failure_key(client_address: object) -> str:
    if isinstance(client_address, tuple) and client_address:
        return str(client_address[0] or "unknown")
    return "unknown"


def _auth_retry_after(server_obj: object, key: str) -> int:
    state = _auth_failure_state(server_obj, key)
    now = time.time()
    locked_until = float(state.get("locked_until") or 0)
    if locked_until > now:
        return max(1, int(locked_until - now + 0.999))
    if locked_until:
        state["locked_until"] = 0.0
    state["failures"] = _recent_auth_failures(server_obj, state, now)
    return 0


def _record_auth_failure(server_obj: object, key: str) -> int:
    state = _auth_failure_state(server_obj, key)
    now = time.time()
    failures = _recent_auth_failures(server_obj, state, now)
    failures.append(now)
    state["failures"] = failures
    limit = max(1, int(getattr(server_obj, "auth_failure_limit", AUTH_FAILURE_LIMIT) or AUTH_FAILURE_LIMIT))
    if len(failures) >= limit:
        lockout_seconds = max(1, int(getattr(server_obj, "auth_lockout_seconds", AUTH_LOCKOUT_SECONDS) or AUTH_LOCKOUT_SECONDS))
        state["locked_until"] = now + lockout_seconds
        return lockout_seconds
    return 0


def _clear_auth_failures(server_obj: object, key: str) -> None:
    failures = getattr(server_obj, "auth_failures", None)
    if isinstance(failures, dict):
        failures.pop(key, None)


def _auth_failure_state(server_obj: object, key: str) -> dict[str, object]:
    failures = getattr(server_obj, "auth_failures", None)
    if not isinstance(failures, dict):
        failures = {}
        setattr(server_obj, "auth_failures", failures)
    state = failures.setdefault(key, {"failures": [], "locked_until": 0.0})
    if not isinstance(state, dict):
        state = {"failures": [], "locked_until": 0.0}
        failures[key] = state
    return state


def _recent_auth_failures(server_obj: object, state: dict[str, object], now: float) -> list[float]:
    window_seconds = max(
        1,
        int(getattr(server_obj, "auth_failure_window_seconds", AUTH_FAILURE_WINDOW_SECONDS) or AUTH_FAILURE_WINDOW_SECONDS),
    )
    failures = state.get("failures")
    if not isinstance(failures, list):
        return []
    cutoff = now - window_seconds
    return [float(value) for value in failures if _is_recent_failure(value, cutoff)]


def _is_recent_failure(value: object, cutoff: float) -> bool:
    try:
        return float(value) >= cutoff
    except (TypeError, ValueError):
        return False


def _write_rate_key(client_address: object) -> str:
    if isinstance(client_address, tuple) and client_address:
        return str(client_address[0] or "unknown")
    return "unknown"


def _record_write_rate_request(server_obj: object, key: str) -> int:
    state = _write_rate_state(server_obj, key)
    now = time.monotonic()
    requests = _recent_write_rate_requests(server_obj, state, now)
    if len(requests) >= _write_rate_limit(server_obj):
        window_seconds = _write_rate_window_seconds(server_obj)
        oldest = min(requests) if requests else now
        state["requests"] = requests
        return max(1, int((oldest + window_seconds) - now + 0.999))
    requests.append(now)
    state["requests"] = requests
    return 0


def _write_rate_state(server_obj: object, key: str) -> dict[str, object]:
    buckets = getattr(server_obj, "write_rate_buckets", None)
    if not isinstance(buckets, dict):
        buckets = {}
        setattr(server_obj, "write_rate_buckets", buckets)
    state = buckets.setdefault(key, {"requests": []})
    if not isinstance(state, dict):
        state = {"requests": []}
        buckets[key] = state
    return state


def _recent_write_rate_requests(server_obj: object, state: dict[str, object], now: float) -> list[float]:
    requests = state.get("requests")
    if not isinstance(requests, list):
        return []
    cutoff = now - _write_rate_window_seconds(server_obj)
    return [float(value) for value in requests if _is_recent_write_request(value, cutoff)]


def _is_recent_write_request(value: object, cutoff: float) -> bool:
    try:
        return float(value) >= cutoff
    except (TypeError, ValueError):
        return False


def _write_rate_limit(server_obj: object) -> int:
    try:
        value = int(getattr(server_obj, "write_rate_limit", WRITE_RATE_LIMIT) or WRITE_RATE_LIMIT)
    except (TypeError, ValueError):
        return WRITE_RATE_LIMIT
    return max(1, value)


def _write_rate_window_seconds(server_obj: object) -> int:
    try:
        value = int(getattr(server_obj, "write_rate_window_seconds", WRITE_RATE_WINDOW_SECONDS) or WRITE_RATE_WINDOW_SECONDS)
    except (TypeError, ValueError):
        return WRITE_RATE_WINDOW_SECONDS
    return max(1, value)


def _request_timeout_seconds(server_obj: object) -> int:
    try:
        value = int(getattr(server_obj, "request_timeout_seconds", REQUEST_TIMEOUT_SECONDS) or REQUEST_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        return REQUEST_TIMEOUT_SECONDS
    return max(1, value)


def _header_hostname(value: str) -> str | None:
    host = _header_host_port(value)
    return host[0] if host else None


def _header_host_origin_parts(value: str | None) -> tuple[str, int | None] | None:
    if not value or "," in value:
        return None
    try:
        parsed = urlparse(f"//{value.strip()}")
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    return parsed.hostname, parsed.port


def _default_origin_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _header_host_port(value: str | None) -> tuple[str, int] | None:
    if not value:
        return None
    if "," in value:
        return None
    try:
        parsed = urlparse(f"//{value.strip()}")
        if not parsed.hostname:
            return None
        return parsed.hostname, parsed.port if parsed.port is not None else 80
    except ValueError:
        return None


def _static_request_requires_file(request_path: str) -> bool:
    rel_path = request_path.lstrip("/")
    return request_path.startswith("/assets/") or bool(Path(rel_path).suffix)


def _static_rel_path(request_path: str) -> str:
    if request_path in {"", "/"}:
        return "index.html"
    if request_path == "/favicon.ico":
        return "assets/favicon.svg"
    return request_path.lstrip("/")


def _json_content_type_allowed(content_type: str | None) -> bool:
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def _max_json_body_bytes(server_obj: object) -> int:
    try:
        value = int(getattr(server_obj, "max_json_body_bytes", MAX_JSON_BODY_BYTES) or MAX_JSON_BODY_BYTES)
    except (TypeError, ValueError):
        return MAX_JSON_BODY_BYTES
    return max(1, value)


def _error_code(status: HTTPStatus) -> str:
    return (status.phrase or status.name).lower().replace(" ", "_")


def _attachment_header(filename: str) -> str:
    safe_filename = _safe_download_filename(filename)
    return f'attachment; filename="{safe_filename}"'


def _safe_download_filename(filename: str) -> str:
    safe_filename = Path(str(filename or "download")).name
    safe_filename = "".join(ch for ch in safe_filename if ch not in '\r\n";\\/')
    safe_filename = " ".join(safe_filename.split())
    return safe_filename[:160] or "download"


def _relative_project_path(value: object) -> str:
    try:
        return str(Path(str(value or "")).resolve().relative_to(data_provider.PROJECT_ROOT.resolve()))
    except (OSError, ValueError):
        return str(value or "")


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _record_workspace_audit(
    payload: dict[str, object],
    action: str,
    *,
    profile: str = "",
    summary: str = "",
    detail: dict[str, object] | None = None,
) -> None:
    try:
        payload["audit_event"] = workspace_audit.record_workspace_event(
            action,
            profile=profile,
            summary=summary,
            detail=detail,
        )
    except ValueError as exc:
        payload["audit_error"] = str(exc)


def _export_risk_settings(query: dict[str, list[str]]) -> dict[str, float]:
    preferences = workspace_store.get_preferences()
    risk = dict(preferences.get("risk") or {})
    account_equity = _float(_first(query, "account_equity"))
    risk_pct = _float(_first(query, "risk_pct"))
    max_capital_pct = _float(_first(query, "max_capital_pct"))
    max_queue_risk_pct = _float(_first(query, "max_queue_risk_pct"))
    max_open_position_risk_pct = _float(_first(query, "max_open_position_risk_pct"))
    max_concentration_pct = _float(_first(query, "max_concentration_pct"))
    max_open_concentration_pct = _float(_first(query, "max_open_concentration_pct"))
    if account_equity is not None:
        risk["account_equity"] = account_equity
    if risk_pct is not None:
        risk["risk_pct"] = risk_pct
    if max_capital_pct is not None:
        risk["max_capital_pct"] = max_capital_pct
    if max_queue_risk_pct is not None:
        risk["max_queue_risk_pct"] = max_queue_risk_pct
    if max_open_position_risk_pct is not None:
        risk["max_open_position_risk_pct"] = max_open_position_risk_pct
    if max_concentration_pct is not None:
        risk["max_concentration_pct"] = max_concentration_pct
    if max_open_concentration_pct is not None:
        risk["max_open_concentration_pct"] = max_open_concentration_pct
    return risk


def _export_review_filters(query: dict[str, list[str]]) -> dict[str, object]:
    return {
        "status": _first(query, "status") or "",
        "priority": _first(query, "priority") or "",
        "tag": _first(query, "tag") or "",
        "query": _first(query, "q") or _first(query, "query") or "",
        "tickers": _first(query, "tickers") or "",
    }


if __name__ == "__main__":
    main()
