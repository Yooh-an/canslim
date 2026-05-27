"""HTTP handler smoke tests for the local web dashboard server."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from email.message import Message
from email.parser import Parser
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.web import (
    atomic_store,
    data_provider,
    job_runner,
    request_trace,
    review_store,
    runtime_info,
    security_headers,
    server,
    session_journal,
    workspace_snapshot,
    workspace_audit,
    workspace_store,
)


@pytest.fixture
def dashboard_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    request_trace.clear_request_trace()
    monkeypatch.setattr(review_store, "STORE_PATH", tmp_path / "review_queue.json")
    monkeypatch.setattr(workspace_store, "STORE_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(session_journal, "STORE_PATH", tmp_path / "session_journal.json")
    monkeypatch.setattr(workspace_snapshot, "BACKUP_DIR", tmp_path / "backups")
    monkeypatch.setattr(workspace_audit, "STORE_PATH", tmp_path / "workspace_audit.json")
    monkeypatch.setattr(job_runner, "JOB_HISTORY_PATH", tmp_path / "job_history.json")
    monkeypatch.setattr(job_runner, "_CURRENT_JOB", None)
    monkeypatch.setattr(job_runner, "_CURRENT_PROCESS", None)
    monkeypatch.setattr(
        data_provider,
        "get_data_provenance",
        lambda profile=None: {"profile": profile or "canslim_score_rank", "source_count": 0, "sources": []},
    )
    return HandlerClient()


def test_dashboard_handler_serves_static_assets_and_health(
    dashboard_client: "HandlerClient",
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    response = dashboard_client.request("GET", "/")

    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Server"] == "CANSLIMDashboard/1.0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Content-Security-Policy"] == security_headers.CONTENT_SECURITY_POLICY
    assert response.headers["Permissions-Policy"] == security_headers.PERMISSIONS_POLICY
    assert "camera=()" in response.headers["Permissions-Policy"]
    assert "microphone=()" in response.headers["Permissions-Policy"]
    assert "geolocation=()" in response.headers["Permissions-Policy"]
    assert "payment=()" in response.headers["Permissions-Policy"]
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert "object-src 'none'" in response.headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in response.headers["Content-Security-Policy"]
    assert "CANSLIM SEPA Dashboard" in response.text
    assert 'class="skip-link" href="#mainWorkspace"' in response.text
    assert 'id="mainWorkspace" tabindex="-1"' in response.text
    assert 'id="workspaceImportModal" role="dialog"' in response.text
    assert 'id="workspaceBackupModal" role="dialog"' in response.text
    assert 'id="securityPosturePanel"' in response.text
    assert 'id="clientEventsPanel"' in response.text

    response = dashboard_client.request("HEAD", "/")
    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert response.body == b""

    response = dashboard_client.request("GET", "/assets/favicon.svg")
    assert response.status == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.text

    response = dashboard_client.request("GET", "/manifest.webmanifest")
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/manifest+json"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["name"] == "CANSLIM SEPA Dashboard"
    assert response.json["display"] == "standalone"

    response = dashboard_client.request("GET", "/favicon.ico")
    assert response.status == 200
    assert response.headers["Content-Type"] == "image/svg+xml"
    assert "<svg" in response.text

    response = dashboard_client.request("GET", "/assets/missing.js")
    assert response.status == 404
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Static asset not found" in response.text
    assert "CANSLIM SEPA Dashboard" not in response.text

    response = dashboard_client.request("HEAD", "/assets/missing.css")
    assert response.status == 404
    assert response.body == b""

    response = dashboard_client.request("GET", "/workspace")
    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert "CANSLIM SEPA Dashboard" in response.text

    response = dashboard_client.request("GET", "/api/health")
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["ok"] is True
    assert response.json["status"] == "ready"
    _assert_runtime_metadata(response.json["server"])
    _assert_csrf_token(response.json["csrf_token"])

    response = dashboard_client.request("HEAD", "/api/health")
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.body == b""

    response = dashboard_client.request("GET", "/api/request-trace?limit=3&private=value")
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["returned"] >= 1
    assert response.json["limit"] == request_trace.TRACE_LIMIT
    assert response.json["requests"][0]["path"] == "/api/health"
    assert "query" not in response.json["requests"][0]
    assert "body" not in response.json["requests"][0]

    response = dashboard_client.request("HEAD", "/api/request-trace?limit=1")
    assert response.status == 200
    assert response.body == b""

    response = dashboard_client.request("GET", "/api/provenance?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json == {"profile": "canslim_score_rank", "source_count": 0, "sources": []}

    monkeypatch.setattr(
        data_provider,
        "get_operational_diagnostics",
        lambda profile=None, **kwargs: {
            "profile": profile or "canslim_score_rank",
            "level": "ready",
            "summary": "1/1 ready",
            "checks": [{"id": "web_static", "level": "ready"}],
        },
    )
    response = dashboard_client.request("GET", "/api/diagnostics?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json["level"] == "ready"
    assert response.json["checks"][0]["id"] == "web_static"

    monkeypatch.setattr(
        data_provider,
        "export_candidates",
        lambda profile=None, **kwargs: {
            "body": "ticker,canslim_score\nIESC,91\n",
            "content_type": "text/csv; charset=utf-8",
            "filename": f"canslim-screener-{profile or 'canslim_score_rank'}-score80.csv",
        },
    )
    response = dashboard_client.request(
        "GET",
        "/api/screener/export?profile=canslim_score_rank&min_score=80&sort_by=score&sort_dir=desc",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-screener-canslim_score_rank-score80.csv"'
    assert "IESC,91" in response.text

    monkeypatch.setattr(
        data_provider,
        "get_candidate_comparison",
        lambda profile=None, tickers="": {
            "profile": profile or "canslim_score_rank",
            "tickers": ["IESC", "MISS"],
            "missing": ["MISS"],
            "count": 1,
            "candidates": [{"ticker": "IESC", "canslim_score": 91}],
        },
    )
    response = dashboard_client.request("GET", "/api/compare?profile=canslim_score_rank&tickers=IESC,MISS")
    assert response.status == 200
    assert response.json["profile"] == "canslim_score_rank"
    assert response.json["missing"] == ["MISS"]
    assert response.json["candidates"][0]["ticker"] == "IESC"

    artifact_path = tmp_path / "results.csv"
    artifact_path.write_text("ticker,canslim_score\nIESC,91\n")
    artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        data_provider,
        "get_artifacts",
        lambda profile=None, **kwargs: {
            "profile": profile or "canslim_score_rank",
            "artifacts": [
                {
                    "id": "results_csv",
                    "label": "Results CSV",
                    "exists": True,
                    "filename": "results.csv",
                    "path": "data/processed/results.csv",
                    "download_url": "/api/artifacts/download?profile=canslim_score_rank&id=results_csv",
                }
            ],
        },
    )
    monkeypatch.setattr(
        data_provider,
        "get_artifact_file",
        lambda artifact_id, profile=None: {
            "path": artifact_path,
            "content_type": "text/csv; charset=utf-8",
            "filename": "results.csv",
        },
    )
    response = dashboard_client.request("GET", "/api/artifacts?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json["artifacts"][0]["id"] == "results_csv"

    response = dashboard_client.request(
        "GET",
        "/api/artifacts/download?profile=canslim_score_rank&id=results_csv",
        download_token=False,
    )
    assert response.status == 403
    assert response.json["error"] == "Download token is invalid or missing"

    response = dashboard_client.request("GET", "/api/artifacts/download?profile=canslim_score_rank&id=results_csv")
    assert response.status == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="results.csv"'
    assert response.headers["X-Content-SHA256"] == artifact_sha
    assert response.headers["X-Content-SHA256-12"] == artifact_sha[:12]
    assert "IESC,91" in response.text

    response = dashboard_client.request("HEAD", "/api/artifacts/download?profile=canslim_score_rank&id=results_csv")
    assert response.status == 200
    assert response.body == b""
    assert response.headers["Content-Length"] == str(artifact_path.stat().st_size)
    assert response.headers["X-Content-SHA256"] == artifact_sha

    monkeypatch.setattr(
        data_provider,
        "get_artifact_file",
        lambda artifact_id, profile=None: {
            "path": artifact_path,
            "content_type": "text/csv; charset=utf-8",
            "filename": '../bad";\r\nX-Evil: yes.csv',
        },
    )
    response = dashboard_client.request("GET", "/api/artifacts/download?profile=canslim_score_rank&id=results_csv")
    assert response.status == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="badX-Evil: yes.csv"'
    assert "X-Evil" not in response.headers

    response = dashboard_client.request("GET", "/api/review/activity?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json["activity"] == []

    job_runner._record_history(
        {
            "id": 1,
            "mode": "screen",
            "profile": "canslim_score_rank",
            "status": "succeeded",
            "running": False,
            "command": "python run_screener.py --mode screen",
            "started_at": "2026-05-26T00:00:00+00:00",
            "finished_at": "2026-05-26T00:01:00+00:00",
            "returncode": 0,
            "log": ["done"],
        }
    )
    response = dashboard_client.request("GET", "/api/jobs/history?limit=1")
    assert response.status == 200
    assert response.json["jobs"][0]["mode"] == "screen"
    assert response.json["jobs"][0]["status"] == "succeeded"

    response = dashboard_client.request("POST", "/api/jobs/cancel", body={})
    assert response.status == 200
    assert response.json == {"status": "idle", "running": False}

    response = dashboard_client.request(
        "POST",
        "/api/review/bulk",
        body={
            "profile": "canslim_score_rank",
            "items": [
                {"ticker": "LINC", "name": "Lincoln"},
                {"ticker": "IESC", "name": "IES Holdings"},
            ],
        },
    )
    assert response.status == 201
    assert [item["ticker"] for item in response.json["items"]] == ["LINC", "IESC"]
    assert response.json["activity"][0]["action"] == "bulk_added"


def test_dashboard_handler_exports_support_bundle(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}

    def fake_diagnostics(profile=None, **kwargs):
        captured["profile"] = profile
        captured["access_context"] = kwargs.get("access_context")
        return {
            "profile": profile or "canslim_score_rank",
            "level": "warning",
            "summary": "1/2 ready",
            "checks": [{"id": "workspace_store_integrity", "level": "ready"}],
        }

    monkeypatch.setattr(
        data_provider,
        "get_operational_diagnostics",
        fake_diagnostics,
    )
    monkeypatch.setattr(
        data_provider,
        "get_artifacts",
        lambda profile=None: {
            "profile": profile or "canslim_score_rank",
            "artifacts": [{"id": "results_csv", "exists": True, "rows": 49}],
        },
    )
    monkeypatch.setattr(
        workspace_audit,
        "get_workspace_audit",
        lambda limit=20: (_ for _ in ()).throw(ValueError("audit store unavailable")),
    )
    trace_seed = dashboard_client.request("GET", "/api/missing")
    assert trace_seed.status == 404
    client_seed = dashboard_client.request(
        "POST",
        "/api/client-events",
        body={
            "profile": "canslim_score_rank",
            "event": {
                "kind": "error",
                "message": "Dashboard render failed",
                "source": "http://127.0.0.1:8765/assets/app.js?debug=true",
                "page_path": "/",
            },
        },
    )
    assert client_seed.status == 200

    response = dashboard_client.request(
        "GET",
        "/api/support/bundle?profile=canslim_score_rank",
        download_token=False,
    )
    assert response.status == 403
    assert response.json["error"] == "Download token is invalid or missing"

    response = dashboard_client.request(
        "GET",
        "/api/support/bundle?profile=canslim_score_rank&download_token=test-csrf-token-123456",
        download_token=False,
    )
    assert response.status == 403
    assert response.json["error"] == "Download token is invalid or missing"

    response = dashboard_client.request("GET", "/api/support/bundle?profile=canslim_score_rank")

    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-support-canslim_score_rank.json"'
    bundle_sha = hashlib.sha256(response.body).hexdigest()
    assert response.headers["X-Content-SHA256"] == bundle_sha
    assert response.headers["X-Content-SHA256-12"] == bundle_sha[:12]
    assert response.json["schema_version"] == 2
    assert response.json["profile"] == "canslim_score_rank"
    assert response.json["research_disclosure"]["title"] == "Research aid only"
    assert response.json["privacy"]["redaction_level"] == "operational_metadata_only"
    assert response.json["environment"]["project"] == data_provider.PROJECT_ROOT.name
    _assert_runtime_metadata(response.json["runtime"])
    assert "project_root" not in response.json["environment"]
    assert str(data_provider.PROJECT_ROOT.resolve()) not in response.text
    assert response.json["sections"] == {
        "total": 9,
        "ok_count": 8,
        "failed_count": 1,
        "failed": ["workspace_audit"],
    }
    assert response.json["diagnostics"]["ok"] is True
    assert response.json["diagnostics"]["data"]["level"] == "warning"
    assert response.json["readiness"]["ok"] is True
    assert response.json["readiness"]["data"]["ok"] is True
    assert response.json["readiness"]["data"]["status"] == "degraded"
    assert response.json["readiness"]["data"]["deployment"]["auth_env"] == server.DEFAULT_AUTH_ENV
    assert captured == {
        "profile": "canslim_score_rank",
        "access_context": {
            "allow_remote": False,
            "auth_enabled": False,
            "require_auth": False,
            "auth_env": server.DEFAULT_AUTH_ENV,
            "auth_failure_limit": server.AUTH_FAILURE_LIMIT,
            "auth_failure_window_seconds": server.AUTH_FAILURE_WINDOW_SECONDS,
            "auth_lockout_seconds": server.AUTH_LOCKOUT_SECONDS,
            "max_json_body_bytes": server.MAX_JSON_BODY_BYTES,
            "write_rate_limit": server.WRITE_RATE_LIMIT,
            "write_rate_window_seconds": server.WRITE_RATE_WINDOW_SECONDS,
            "request_timeout_seconds": server.REQUEST_TIMEOUT_SECONDS,
        },
    }
    assert response.json["artifacts"]["data"]["artifacts"][0]["id"] == "results_csv"
    assert response.json["request_trace"]["ok"] is True
    missing_request = next(
        request for request in response.json["request_trace"]["data"]["requests"] if request["path"] == "/api/missing"
    )
    assert missing_request["status"] == 404
    assert missing_request["error_code"] == "not_found"
    assert missing_request["run_id"] == runtime_info.RUN_ID
    assert "query" not in missing_request
    assert response.json["client_events"]["ok"] is True
    assert response.json["client_events"]["data"]["events"][0]["kind"] == "error"
    assert response.json["client_events"]["data"]["events"][0]["source"] == "/assets/app.js"
    assert response.json["client_events"]["data"]["events"][0]["run_id"] == runtime_info.RUN_ID
    assert "query" not in response.json["client_events"]["data"]["events"][0]
    assert response.json["provenance"]["data"] == {
        "profile": "canslim_score_rank",
        "source_count": 0,
        "sources": [],
    }
    assert response.json["workspace_audit"] == {"ok": False, "error": "audit store unavailable"}
    assert "items" not in response.json
    assert "journal" not in response.json

    response = dashboard_client.request("HEAD", "/api/support/bundle?profile=canslim_score_rank")
    assert response.status == 200
    assert response.body == b""
    assert response.headers["X-Content-SHA256"]


def test_dashboard_handler_audits_sensitive_downloads(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        data_provider,
        "get_operational_diagnostics",
        lambda profile=None: {
            "profile": profile or "canslim_score_rank",
            "level": "ready",
            "summary": "1/1 ready",
            "checks": [{"id": "web_static", "level": "ready"}],
        },
    )
    monkeypatch.setattr(
        data_provider,
        "get_artifacts",
        lambda profile=None: {"profile": profile or "canslim_score_rank", "artifacts": []},
    )

    response = dashboard_client.request("GET", "/api/support/bundle?profile=canslim_score_rank")

    assert response.status == 200
    audit = dashboard_client.request("GET", "/api/workspace/audit?limit=3")
    assert audit.status == 200
    event = audit.json["events"][0]
    assert event["action"] == "support_bundle_export"
    assert event["profile"] == "canslim_score_rank"
    assert event["summary"] == "Downloaded canslim-support-canslim_score_rank.json"
    assert event["detail"]["route"] == "/api/support/bundle"
    assert event["detail"]["filename"] == "canslim-support-canslim_score_rank.json"
    assert event["detail"]["content_type"] == "application/json; charset=utf-8"
    assert event["detail"]["sha256_12"] == response.headers["X-Content-SHA256-12"]
    assert event["detail"]["size_bytes"] == len(response.body)
    assert "download_token" not in json.dumps(event)
    assert "body" not in event["detail"]
    assert "query" not in event["detail"]


def test_dashboard_handler_filters_workspace_audit_before_limit(dashboard_client: "HandlerClient"):
    workspace_audit.record_workspace_event(
        "support_bundle_export",
        profile="canslim_score_rank",
        summary="Downloaded support bundle",
        detail={"filename": "support.json", "route": "/api/support/bundle"},
    )
    workspace_audit.record_workspace_event(
        "restore_backup",
        profile="canslim_score_rank",
        summary="Restored backup alpha",
        detail={"filename": "backup-alpha.json"},
    )
    workspace_audit.record_workspace_event(
        "cleanup_temp_files",
        profile="canslim_score_rank",
        summary="Cleaned temp files",
        detail={"deleted_count": 2},
    )

    response = dashboard_client.request("GET", "/api/workspace/audit?limit=1&category=download&query=support")

    assert response.status == 200
    assert response.json["query"] == "support"
    assert response.json["category"] == "download"
    assert response.json["total_count"] == 3
    assert response.json["filtered_count"] == 1
    assert [event["action"] for event in response.json["events"]] == ["support_bundle_export"]
    assert response.json["events"][0]["detail"]["route"] == "/api/support/bundle"

    response = dashboard_client.request("GET", "/api/workspace/audit?limit=5&category=maintenance")

    assert response.status == 200
    assert response.json["filtered_count"] == 1
    assert response.json["events"][0]["action"] == "cleanup_temp_files"

    response = dashboard_client.request("GET", "/api/workspace/audit/export?limit=5&category=workspace&query=backup")

    assert response.status == 200
    assert response.json["query"] == "backup"
    assert response.json["category"] == "workspace"
    assert response.json["event_count"] == 1
    assert response.json["filtered_count"] == 1
    assert response.json["events"][0]["action"] == "restore_backup"


def test_dashboard_handler_includes_request_ids_on_responses_and_errors(dashboard_client: "HandlerClient"):
    response = dashboard_client.request("GET", "/api/health")
    _assert_request_id(response.headers["X-Request-ID"])
    assert "request_id" not in response.json

    response = dashboard_client.request("GET", "/api/missing")
    error_request_id = _assert_request_id(response.headers["X-Request-ID"])
    assert response.status == 404
    assert response.json["error"] == "Not found"
    assert response.json["code"] == "not_found"
    assert response.json["request_id"] == error_request_id

    trace = request_trace.recent_request_trace(limit=5)
    assert trace["requests"][0]["request_id"] == error_request_id
    assert trace["requests"][0]["method"] == "GET"
    assert trace["requests"][0]["path"] == "/api/missing"
    assert trace["requests"][0]["status"] == 404
    assert trace["requests"][0]["outcome"] == "error"
    assert trace["requests"][0]["error_code"] == "not_found"
    assert trace["requests"][0]["run_id"] == runtime_info.RUN_ID
    assert trace["requests"][1]["path"] == "/api/health"
    assert trace["requests"][1]["outcome"] == "ok"

    response = dashboard_client.request("HEAD", "/api/missing")
    _assert_request_id(response.headers["X-Request-ID"])
    assert response.status == 404
    assert response.body == b""


def test_dashboard_handler_redacts_local_paths_from_errors_and_trace(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    project_file = data_provider.PROJECT_ROOT / "data" / "private" / "store.json"
    home_file = Path.home() / ".canslim-sepa" / "token.json"

    def fail_with_local_paths(profile: str | None = None) -> dict[str, Any]:
        raise ValueError(f"Cannot read {project_file} with token {home_file}")

    monkeypatch.setattr(data_provider, "get_data_provenance", fail_with_local_paths)

    response = dashboard_client.request("GET", "/api/provenance?profile=canslim_score_rank")

    assert response.status == 400
    assert "./data/private/store.json" in response.json["error"]
    assert "~/.canslim-sepa/token.json" in response.json["error"]
    assert str(data_provider.PROJECT_ROOT.resolve()) not in response.text
    assert str(Path.home()) not in response.text

    trace = request_trace.recent_request_trace(limit=1)
    error = trace["requests"][0]["error"]
    assert "./data/private/store.json" in error
    assert "~/.canslim-sepa/token.json" in error
    assert str(data_provider.PROJECT_ROOT.resolve()) not in json.dumps(trace)
    assert str(Path.home()) not in json.dumps(trace)


def test_dashboard_handler_records_redacted_client_events(dashboard_client: "HandlerClient"):
    response = dashboard_client.request(
        "POST",
        "/api/client-events",
        body={
            "profile": "canslim_score_rank",
            "event": {
                "kind": "unhandledrejection",
                "message": "Cannot render queue for account 123",
                "source": "http://127.0.0.1:8765/assets/app.js?cache=private",
                "page_path": "/workspace?profile=canslim_score_rank",
                "line": 25,
                "column": 9,
                "body": {"not": "kept"},
            },
        },
    )

    assert response.status == 200
    assert response.json["accepted"] is True
    assert response.json["event"] == {
        "at": response.json["event"]["at"],
        "profile": "canslim_score_rank",
        "kind": "unhandledrejection",
        "message": "Cannot render queue for account 123",
        "page_path": "/workspace",
        "source": "/assets/app.js",
        "run_id": runtime_info.RUN_ID,
        "line": 25,
        "column": 9,
    }
    assert "body" not in response.json["event"]

    events = request_trace.recent_client_events(limit=3)
    assert events["events"][0]["kind"] == "unhandledrejection"
    assert events["events"][0]["source"] == "/assets/app.js"
    assert events["events"][0]["run_id"] == runtime_info.RUN_ID
    assert "query" not in events["events"][0]

    response = dashboard_client.request("GET", "/api/client-events?limit=3")
    assert response.status == 200
    assert response.json["returned"] == 1
    assert response.json["events"][0]["message"] == "Cannot render queue for account 123"
    assert "body" not in response.json["events"][0]

    response = dashboard_client.request("DELETE", "/api/client-events", body={})
    assert response.status == 405
    assert response.headers["Allow"] == "POST"


def test_dashboard_handler_rate_limits_client_events(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(request_trace, "CLIENT_EVENT_RATE_LIMIT", 1)
    monkeypatch.setattr(request_trace, "CLIENT_EVENT_RATE_WINDOW_SECONDS", 60)

    response = dashboard_client.request(
        "POST",
        "/api/client-events",
        body={"profile": "canslim_score_rank", "event": {"kind": "error", "message": "first"}},
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/client-events",
        body={"profile": "canslim_score_rank", "event": {"kind": "error", "message": "second"}},
    )

    assert response.status == 429
    assert response.headers["Retry-After"].isdigit()
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert response.json["error"] == "Client event intake is rate limited"
    assert response.json["code"] == "too_many_requests"
    _assert_request_id(response.json["request_id"])

    events = request_trace.recent_client_events(limit=5)
    assert [event["message"] for event in events["events"]] == ["first"]
    trace = request_trace.recent_request_trace(limit=2)
    assert trace["requests"][0]["status"] == 429
    assert trace["requests"][0]["error_code"] == "too_many_requests"


def test_dashboard_handler_rejects_corrupt_workspace_store_without_overwrite(
    dashboard_client: "HandlerClient",
):
    workspace_store.STORE_PATH.write_text('{"profile": ')

    response = dashboard_client.request("GET", "/api/preferences")
    assert response.status == 400
    assert response.json["error"] == "Workspace preferences store is not valid JSON"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={"profile": "canslim_score_rank", "risk": {"account_equity": 250000}},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace preferences store is not valid JSON"
    assert workspace_store.STORE_PATH.read_text() == '{"profile": '


def test_dashboard_handler_review_preferences_summary_and_export(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={
            "profile": "canslim_score_rank",
            "review": {"sort_by": "risk", "sort_dir": "asc", "status": "ready", "priority": "high"},
            "review_views": [
                {
                    "id": "ready-risk",
                    "name": "Ready risk",
                    "sort_by": "risk",
                    "sort_dir": "asc",
                    "status": "ready",
                    "priority": "high",
                    "tag": "leader",
                }
            ],
            "risk": {
                "account_equity": 100000,
                "risk_pct": 0.5,
                "max_capital_pct": 60,
                "max_queue_risk_pct": 2,
                "max_open_position_risk_pct": 4,
                "max_concentration_pct": 50,
                "max_open_concentration_pct": 45,
            },
        },
    )
    assert response.status == 200
    assert response.json["review"] == {
        "query": "",
        "sort_by": "risk",
        "sort_dir": "asc",
        "status": "ready",
        "priority": "high",
        "tag": "",
    }
    assert response.json["review_views"] == [
        {
            "id": "ready-risk",
            "name": "Ready risk",
            "query": "",
            "sort_by": "risk",
            "sort_dir": "asc",
            "status": "ready",
            "priority": "high",
            "tag": "leader",
        }
    ]

    response = dashboard_client.request(
        "POST",
        "/api/review",
        body={
            "profile": "canslim_score_rank",
            "item": {
                "ticker": "IESC",
                "name": "IES Holdings",
                "decision_status": "ready",
                "buy_zone_low": 220,
                "buy_zone_high": 231,
                "stop_loss_price": 210,
                "review_tags": "leader,breakout",
            },
        },
    )
    assert response.status == 201
    assert response.json["items"][0]["ticker"] == "IESC"

    response = dashboard_client.request(
        "GET",
        "/api/review/summary?profile=canslim_score_rank&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.json["total_risk_amount"] == 500.0
    assert response.json["total_planned_capital"] == 11000.0
    assert response.json["status_counts"]["ready"] == 1

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=csv&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "text/csv; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-review-canslim_score_rank.csv"'
    assert "risk_amount,risk_per_share,planned_shares,planned_capital" in response.text
    assert "IESC,IES Holdings,,,ready" in response.text
    assert "leader,breakout" in response.text
    assert "500.0,10.0,50,11000.0" in response.text

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=csv&status=watch&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-review-canslim_score_rank-watch.csv"'
    assert "risk_amount,risk_per_share,planned_shares,planned_capital" in response.text
    assert "IESC,IES Holdings,ready" not in response.text

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=txt&tickers=IESC",
    )
    assert response.status == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-review-canslim_score_rank-selected.txt"'
    assert response.text == "IESC\n"

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=txt&tag=leader",
    )
    assert response.status == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-review-canslim_score_rank-leader.txt"'
    assert response.text == "IESC\n"

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=txt&q=IES",
    )
    assert response.status == 200
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-review-canslim_score_rank-search.txt"'
    assert response.text == "IESC\n"

    response = dashboard_client.request(
        "GET",
        "/api/review/export?profile=canslim_score_rank&format=tradingview&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == (
        'attachment; filename="canslim-tradingview-review-canslim_score_rank.json"'
    )
    assert response.json["source"] == "web_review_queue"
    assert response.json["symbols"] == ["IESC"]
    assert response.json["candidates"][0]["alert_plan"][0]["tool"] == "alert_create"

    response = dashboard_client.request(
        "POST",
        "/api/session/journal",
        body={
            "profile": "canslim_score_rank",
            "date": "2026-05-26",
            "market_thesis": "Risk-on but selective",
            "watchlist_focus": "Near-pivot construction leaders",
            "risk_notes": "Keep new buys at half size",
            "post_session_review": "No late chases",
        },
    )
    assert response.status == 200
    assert response.json["date"] == "2026-05-26"
    assert response.json["market_thesis"] == "Risk-on but selective"

    response = dashboard_client.request("GET", "/api/session/journal?profile=canslim_score_rank&date=2026-05-26")
    assert response.status == 200
    assert response.json["watchlist_focus"] == "Near-pivot construction leaders"

    response = dashboard_client.request(
        "GET",
        "/api/workspace/export?profile=canslim_score_rank&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-workspace-canslim_score_rank.json"'
    assert response.json["schema_version"] == 1
    assert response.json["profile"] == "canslim_score_rank"
    assert response.json["research_disclosure"]["title"] == "Research aid only"
    assert response.json["preferences"]["review"] == {
        "query": "",
        "sort_by": "risk",
        "sort_dir": "asc",
        "status": "ready",
        "priority": "high",
        "tag": "",
    }
    assert response.json["preferences"]["review_views"][0]["name"] == "Ready risk"
    assert response.json["review"]["items"][0]["ticker"] == "IESC"
    assert response.json["journal"]["entries"][0]["market_thesis"] == "Risk-on but selective"
    assert response.json["review_summary"]["total_planned_capital"] == 11000.0
    assert response.json["provenance"] == {"profile": "canslim_score_rank", "source_count": 0, "sources": []}

    monkeypatch.setattr(
        data_provider,
        "get_overview",
        lambda profile=None: {
            "profile": profile or "canslim_score_rank",
            "research_disclosure": {"title": "Research aid only"},
            "data_health": {
                "level": "ready",
                "readiness_pct": 100,
                "next_action": "none",
                "result_age_hours": 0.5,
                "market_age_days": 1,
                "candidate_count": 1,
                "source_findings": [],
            },
            "profile_summary": {
                "label": "Score rank",
                "result_file": "data/processed/results.csv",
                "rules": [{"label": "Score", "value": ">= 70"}],
            },
            "market_direction": {"market_direction_status": "confirmed_uptrend"},
            "action_center": {
                "posture": "risk_on",
                "market_status": "confirmed_uptrend",
                "recommended_exposure": 0.8,
                "high_quality_count": 1,
                "tasks": [{"label": "Validate chart", "detail": "Confirm volume"}],
                "focus_candidates": [
                    {
                        "ticker": "IESC",
                        "action": "watch_breakout",
                        "canslim_score": 91,
                        "setup_status": "near_pivot",
                        "pivot_distance_pct": 2.5,
                    }
                ],
            },
            "candidate_stats": {"count": 1},
            "top_candidates": [{"ticker": "IESC", "canslim_score": 91}],
        },
    )
    monkeypatch.setattr(
        data_provider,
        "get_artifacts",
        lambda profile=None: {
            "profile": profile or "canslim_score_rank",
            "artifacts": [
                {
                    "id": "results_csv",
                    "label": "Results CSV",
                    "exists": True,
                    "path": "data/processed/results.csv",
                    "age_hours": 0.5,
                    "rows": 1,
                }
            ],
        },
    )
    monkeypatch.setattr(
        job_runner,
        "job_history",
        lambda limit=6, store_path=None: {
            "jobs": [
                {
                    "mode": "screen",
                    "profile": "canslim_score_rank",
                    "status": "succeeded",
                    "finished_at": "2026-05-26T00:01:00+00:00",
                    "returncode": 0,
                }
            ]
        },
    )
    response = dashboard_client.request(
        "GET",
        "/api/session/report?profile=canslim_score_rank&date=2026-05-26&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-session-canslim_score_rank.md"'
    assert "# CANSLIM SEPA Session Report" in response.text
    assert "Research aid only" in response.text
    assert "## Session Journal" in response.text
    assert "Risk-on but selective" in response.text
    assert "Total planned risk: $500.00" in response.text
    assert "| IESC | watch_breakout | 91 | near_pivot | 2.5% |" in response.text

    response = dashboard_client.request(
        "GET",
        "/api/session/report?profile=canslim_score_rank&date=2026-05-26&format=json&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-session-canslim_score_rank.json"'
    assert response.json["schema_version"] == 1
    assert response.json["research_disclosure"]["title"] == "Research aid only"
    assert response.json["review_summary"]["total_risk_amount"] == 500.0
    assert response.json["review_export"]["items"][0]["planned_shares"] == 50
    assert response.json["data_health"]["level"] == "ready"
    assert response.json["journal"]["risk_notes"] == "Keep new buys at half size"

    response = dashboard_client.request(
        "HEAD",
        "/api/session/report?profile=canslim_score_rank&account_equity=100000&risk_pct=0.5",
    )
    assert response.status == 200
    assert response.body == b""
    assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"

    import_snapshot = {
        "schema_version": 1,
        "profile": "canslim_score_rank",
        "preferences": {
            "profile": "canslim_score_rank",
            "review": {
                "query": "lin",
                "sort_by": "ticker",
                "sort_dir": "desc",
                "status": "watch",
                "priority": "low",
                "tag": "leader",
            },
            "review_views": [
                {
                    "id": "watch-leaders",
                    "name": "Watch leaders",
                    "query": "lin",
                    "sort_by": "ticker",
                    "sort_dir": "desc",
                    "status": "watch",
                    "priority": "low",
                    "tag": "leader",
                }
            ],
            "risk": {
                "account_equity": 250000,
                "risk_pct": 0.4,
                "max_capital_pct": 55,
                "max_queue_risk_pct": 1.5,
                "max_open_position_risk_pct": 3.5,
                "max_concentration_pct": 50,
                "max_open_concentration_pct": 45,
            },
        },
        "review": {
            "items": [
                {
                    "ticker": "LINC",
                    "name": "Lincoln",
                    "decision_status": "watch",
                    "buy_zone_low": 100,
                    "stop_loss_price": 96,
                },
                {
                    "ticker": "LINC",
                    "name": "Duplicate Lincoln",
                    "decision_status": "ready",
                },
            ]
        },
        "journal": {"entries": [{"date": "2026-05-27", "market_thesis": "Imported session"}]},
    }

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import/preview",
        body={"snapshot": import_snapshot},
    )
    assert response.status == 200
    assert response.json["requires_confirmation"] is True
    assert response.json["preferences"]["incoming_review_view_count"] == 1
    assert response.json["review"] == {
        "profile": "canslim_score_rank",
        "limit": 50,
        "requested_count": 2,
        "imported_count": 1,
        "duplicate_count": 1,
        "truncated_count": 0,
        "existing_count": 1,
        "new_count": 1,
        "updated_count": 0,
        "removed_count": 1,
        "will_replace": True,
        "incoming_tickers": ["LINC"],
        "new_tickers": ["LINC"],
        "updated_tickers": [],
        "removed_tickers": ["IESC"],
    }
    assert response.json["journal"] == {
        "will_replace": True,
        "existing_count": 1,
        "incoming_count": 1,
        "removed_count": 0,
    }

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["IESC"]

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={"snapshot": import_snapshot},
    )
    assert response.status == 400
    assert response.json["error"] == "confirm=import is required to import a workspace snapshot"

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["IESC"]

    invalid_snapshot = {**import_snapshot, "journal": {"entries": "bad"}}
    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={"snapshot": invalid_snapshot, "confirm": "import"},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace snapshot journal.entries must be a JSON array"

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["IESC"]

    response = dashboard_client.request("GET", "/api/preferences?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json["review"] == {
        "query": "",
        "sort_by": "risk",
        "sort_dir": "asc",
        "status": "ready",
        "priority": "high",
        "tag": "",
    }

    response = dashboard_client.request("GET", "/api/session/journal?profile=canslim_score_rank&date=2026-05-26")
    assert response.status == 200
    assert response.json["market_thesis"] == "Risk-on but selective"

    invalid_review_snapshot = {
        **import_snapshot,
        "preferences": {
            **import_snapshot["preferences"],
            "review": {
                "query": "mutate-me",
                "sort_by": "ticker",
                "sort_dir": "asc",
                "status": "watch",
                "priority": "low",
                "tag": "bad",
            },
        },
        "review": {"items": [{"ticker": "../BAD", "decision_status": "watch"}]},
    }
    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={"snapshot": invalid_review_snapshot, "confirm": "import"},
    )
    assert response.status == 400
    assert response.json["error"] == "Ticker must be 1-15 uppercase letters, numbers, underscores, or hyphens"

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["IESC"]

    response = dashboard_client.request("GET", "/api/preferences?profile=canslim_score_rank")
    assert response.status == 200
    assert response.json["review"] == {
        "query": "",
        "sort_by": "risk",
        "sort_dir": "asc",
        "status": "ready",
        "priority": "high",
        "tag": "",
    }

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={"snapshot": import_snapshot, "confirm": "import"},
    )
    assert response.status == 201
    assert response.json["preferences"]["review"] == {
        "query": "lin",
        "sort_by": "ticker",
        "sort_dir": "desc",
        "status": "watch",
        "priority": "low",
        "tag": "leader",
    }
    assert response.json["preferences"]["review_views"][0]["id"] == "watch-leaders"
    assert response.json["preferences"]["risk"] == {
        "account_equity": 250000.0,
        "risk_pct": 0.4,
        "max_capital_pct": 55.0,
        "max_queue_risk_pct": 1.5,
        "max_open_position_risk_pct": 3.5,
        "max_concentration_pct": 50.0,
        "max_open_concentration_pct": 45.0,
    }
    assert response.json["journal"]["entries"][0]["market_thesis"] == "Imported session"
    assert response.json["review"]["items"][0]["ticker"] == "LINC"
    assert response.json["review"]["activity"][0]["action"] == "imported"
    assert response.json["review_summary"]["total_planned_capital"] == 25000.0
    assert response.json["backup"]["profile"] == "canslim_score_rank"
    assert response.json["backup"]["filename"].startswith("canslim-workspace-backup-canslim_score_rank-")
    backup_path = Path(response.json["backup"]["path"])
    assert backup_path.exists()
    backup_payload = json.loads(backup_path.read_text())
    assert backup_payload["backup_reason"] == "pre_workspace_import"
    assert backup_payload["review"]["items"][0]["ticker"] == "IESC"
    assert backup_payload["preferences"]["review"]["sort_by"] == "risk"
    assert backup_payload["journal"]["entries"][0]["market_thesis"] == "Risk-on but selective"

    response = dashboard_client.request(
        "POST",
        "/api/review/bulk",
        body={
            "profile": "canslim_score_rank",
            "items": [
                {"ticker": "IESC", "decision_status": "watch"},
                {"ticker": "MYRG", "decision_status": "watch"},
            ],
        },
    )
    assert response.status == 201

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={
            "profile": "canslim_score_rank",
            "action": "status",
            "tickers": ["IESC", "MYRG"],
            "decision_status": "ready",
        },
    )
    assert response.status == 200
    assert {item["ticker"]: item["decision_status"] for item in response.json["items"]} == {
        "IESC": "ready",
        "MYRG": "ready",
        "LINC": "watch",
    }
    assert response.json["activity"][0]["action"] == "bulk_updated"
    assert response.json["activity"][0]["updated_count"] == 2
    assert [item["ticker"] for item in response.json["activity"][0]["restorable_items"]] == ["IESC", "MYRG"]
    activity_at = response.json["activity"][0]["at"]

    response = dashboard_client.request(
        "POST",
        "/api/review/undo",
        body={"profile": "canslim_score_rank", "activity_at": activity_at},
    )
    assert response.status == 200
    assert {item["ticker"]: item["decision_status"] for item in response.json["items"]} == {
        "IESC": "watch",
        "MYRG": "watch",
        "LINC": "watch",
    }
    assert response.json["activity"][0]["action"] == "restored"
    assert response.json["activity"][0]["source_action"] == "bulk_updated"
    assert response.json["activity"][0]["restored_count"] == 2

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={
            "profile": "canslim_score_rank",
            "action": "priority",
            "tickers": ["IESC", "MYRG"],
            "review_priority": "high",
        },
    )
    assert response.status == 200
    assert {item["ticker"]: item["review_priority"] for item in response.json["items"]} == {
        "IESC": "high",
        "MYRG": "high",
        "LINC": "normal",
    }
    assert response.json["activity"][0]["action"] == "bulk_updated"
    assert response.json["activity"][0]["changed_fields"] == ["review_priority"]
    assert response.json["activity"][0]["updated_count"] == 2

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={
            "profile": "canslim_score_rank",
            "action": "tags",
            "tickers": ["IESC", "MYRG"],
            "review_tags": "Ready List, =Formula",
        },
    )
    assert response.status == 200
    assert {item["ticker"]: item.get("review_tags", []) for item in response.json["items"]} == {
        "IESC": ["ready-list", "formula"],
        "MYRG": ["ready-list", "formula"],
        "LINC": [],
    }
    assert response.json["activity"][0]["changed_fields"] == ["review_tags"]

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={
            "profile": "canslim_score_rank",
            "action": "prices",
            "prices": [
                {"ticker": "IESC", "current_price": 221.25},
                {"ticker": "MYRG", "price": "88.5"},
            ],
        },
    )
    assert response.status == 200
    assert {item["ticker"]: item.get("current_price") for item in response.json["items"]} == {
        "IESC": 221.25,
        "MYRG": 88.5,
        "LINC": None,
    }
    assert response.json["activity"][0]["changed_fields"] == ["current_price"]

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={"profile": "canslim_score_rank", "action": "remove", "tickers": ["MYRG"]},
    )
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["IESC", "LINC"]
    assert response.json["activity"][0]["action"] == "bulk_removed"

    monkeypatch.setattr(
        data_provider,
        "get_review_items_for_tickers",
        lambda ticker_input, profile=None: {
            "profile": profile or "canslim_score_rank",
            "requested": ["STRL", "NOPE"],
            "items": [
                {
                    "ticker": "STRL",
                    "name": "Sterling",
                    "canslim_score": 90,
                    "buy_zone_low": 120,
                    "stop_loss_price": 112,
                }
            ],
            "failures": [{"ticker": "NOPE", "error": "Ticker was not found in the enriched company list"}],
            "truncated_count": 0,
            "limit": 25,
        },
    )
    response = dashboard_client.request(
        "POST",
        "/api/review/import-tickers",
        body={"profile": "canslim_score_rank", "text": "STRL NOPE"},
    )
    assert response.status == 201
    assert response.json["items"][0]["ticker"] == "STRL"
    assert response.json["imported"] == {
        "requested": ["STRL", "NOPE"],
        "imported_count": 1,
        "failures": [{"ticker": "NOPE", "error": "Ticker was not found in the enriched company list"}],
        "truncated_count": 0,
        "limit": 25,
    }
    assert response.json["activity"][0]["action"] == "bulk_added"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={"snapshot": {"schema_version": 999, "review": {"items": []}}, "confirm": "import"},
    )
    assert response.status == 400
    assert "Unsupported workspace snapshot schema" in response.json["error"]

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import/preview",
        body={"snapshot": {"schema_version": 1, "review": {"items": "bad"}}},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace snapshot review.items must be a JSON array"

    response = dashboard_client.request("DELETE", "/api/review?profile=canslim_score_rank&ticker=IESC")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["STRL", "LINC"]

    response = dashboard_client.request("DELETE", "/api/review?profile=canslim_score_rank")
    assert response.status == 400
    assert response.json["error"] == "confirm=clear is required to clear the review queue"

    response = dashboard_client.request("DELETE", "/api/review?profile=canslim_score_rank&confirm=clear")
    assert response.status == 200
    assert response.json["items"] == []


def test_dashboard_handler_lists_and_restores_workspace_backups(dashboard_client: "HandlerClient"):
    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={
            "profile": "canslim_score_rank",
            "review": {"query": "orig", "sort_by": "ticker", "sort_dir": "asc", "status": "ready"},
            "risk": {"account_equity": 150000, "risk_pct": 0.6},
        },
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/review",
        body={
            "profile": "canslim_score_rank",
            "item": {"ticker": "ORIG1", "name": "Original", "decision_status": "ready"},
        },
    )
    assert response.status == 201

    response = dashboard_client.request(
        "POST",
        "/api/session/journal",
        body={
            "profile": "canslim_score_rank",
            "date": "2026-05-26",
            "market_thesis": "Original session",
        },
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={
            "confirm": "import",
            "snapshot": {
                "schema_version": 1,
                "profile": "canslim_score_rank",
                "preferences": {
                    "profile": "canslim_score_rank",
                    "review": {"query": "new", "sort_by": "added_at", "sort_dir": "desc", "status": "watch"},
                    "risk": {"account_equity": 90000, "risk_pct": 0.4},
                },
                "review": {"items": [{"ticker": "NEW1", "decision_status": "watch"}]},
                "journal": {"entries": [{"date": "2026-05-26", "market_thesis": "New session"}]},
            }
        },
    )
    assert response.status == 201
    backup_filename = response.json["backup"]["filename"]
    backup_path = workspace_snapshot.BACKUP_DIR / backup_filename
    backup_full_sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()
    backup_sha = backup_full_sha[:12]
    assert response.json["review"]["items"][0]["ticker"] == "NEW1"
    assert response.json["audit_event"]["action"] == "import_workspace"
    assert response.json["audit_event"]["profile"] == "canslim_score_rank"

    response = dashboard_client.request("GET", "/api/workspace/backups?profile=canslim_score_rank&limit=5")
    assert response.status == 200
    assert response.json["backups"][0]["filename"] == backup_filename
    assert response.json["backups"][0]["sha256_12"] == backup_sha
    assert response.json["backups"][0]["review_item_count"] == 1
    assert response.json["backups"][0]["journal_entry_count"] == 1

    response = dashboard_client.request(
        "GET",
        f"/api/workspace/backups/download?filename={backup_filename}",
    )
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == f'attachment; filename="{backup_filename}"'
    assert response.headers["X-Content-SHA256"] == backup_full_sha
    assert response.headers["X-Content-SHA256-12"] == backup_sha
    assert response.json["backup_reason"] == "pre_workspace_import"
    assert response.json["review"]["items"][0]["ticker"] == "ORIG1"

    response = dashboard_client.request("GET", "/api/workspace/backups/download?filename=../bad.json")
    assert response.status == 400
    assert response.json["error"] == "Invalid workspace backup filename"

    response = dashboard_client.request(
        "GET",
        f"/api/workspace/backups/preview?filename={backup_filename}",
    )
    assert response.status == 200
    assert response.json["requires_confirmation"] is True
    assert response.json["backup"]["filename"] == backup_filename
    assert response.json["backup"]["sha256_12"] == backup_sha
    assert response.json["review"]["imported_count"] == 1
    assert response.json["review"]["new_tickers"] == ["ORIG1"]
    assert response.json["review"]["removed_tickers"] == ["NEW1"]
    assert response.json["journal"]["incoming_count"] == 1

    response = dashboard_client.request("GET", "/api/workspace/backups/preview?filename=../bad.json")
    assert response.status == 400
    assert response.json["error"] == "Invalid workspace backup filename"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": backup_filename},
    )
    assert response.status == 400
    assert response.json["error"] == "confirm=restore is required to restore a workspace backup"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": backup_filename, "confirm": "restore", "expected_sha256_12": "bad"},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace backup fingerprint must be a 12-character SHA-256 prefix"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": backup_filename, "confirm": "restore", "expected_sha256_12": "000000000000"},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace backup fingerprint changed; refresh backups and try again"

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["NEW1"]

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": backup_filename, "confirm": "restore", "expected_sha256_12": backup_sha},
    )
    assert response.status == 201
    assert response.json["restored_from_backup"]["filename"] == backup_filename
    assert response.json["restored_from_backup"]["sha256_12"] == backup_sha
    assert response.json["review"]["items"][0]["ticker"] == "ORIG1"
    assert response.json["preferences"]["review"]["query"] == "orig"
    assert response.json["journal"]["entries"][0]["market_thesis"] == "Original session"
    assert response.json["backup"]["filename"] != backup_filename
    assert response.json["audit_event"]["action"] == "restore_backup"
    assert response.json["audit_event"]["detail"]["sha256_12"] == backup_sha

    response = dashboard_client.request("GET", "/api/review?profile=canslim_score_rank")
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["ORIG1"]

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": "../bad.json", "confirm": "restore"},
    )
    assert response.status == 400
    assert response.json["error"] == "Invalid workspace backup filename"

    response = dashboard_client.request(
        "DELETE",
        "/api/workspace/backups",
        body={"filename": backup_filename},
    )
    assert response.status == 400
    assert response.json["error"] == "confirm=delete is required to delete a workspace backup"

    response = dashboard_client.request(
        "DELETE",
        "/api/workspace/backups",
        body={"filename": backup_filename, "confirm": "delete", "expected_sha256_12": "000000000000"},
    )
    assert response.status == 400
    assert response.json["error"] == "Workspace backup fingerprint changed; refresh backups and try again"
    assert backup_path.exists()

    response = dashboard_client.request(
        "DELETE",
        "/api/workspace/backups",
        body={"filename": backup_filename, "confirm": "delete", "expected_sha256_12": backup_sha},
    )
    assert response.status == 200
    assert response.json["deleted"] is True
    assert response.json["backup"]["filename"] == backup_filename
    assert response.json["backup"]["sha256_12"] == backup_sha
    assert response.json["audit_event"]["action"] == "delete_backup"
    assert not backup_path.exists()

    response = dashboard_client.request("GET", f"/api/workspace/backups/download?filename={backup_filename}")
    assert response.status == 404
    assert response.json["error"] == f"Workspace backup not found: {backup_filename}"

    response = dashboard_client.request("GET", "/api/workspace/backups?profile=canslim_score_rank&limit=5")
    assert response.status == 200
    assert backup_filename not in {backup["filename"] for backup in response.json["backups"]}

    response = dashboard_client.request(
        "DELETE",
        "/api/workspace/backups",
        body={"filename": "../bad.json", "confirm": "delete"},
    )
    assert response.status == 400
    assert response.json["error"] == "Invalid workspace backup filename"

    response = dashboard_client.request("GET", "/api/workspace/audit?limit=5")
    assert response.status == 200
    assert [event["action"] for event in response.json["events"][:4]] == [
        "delete_backup",
        "restore_backup",
        "workspace_backup_download",
        "import_workspace",
    ]
    assert response.json["events"][0]["summary"] == f"Deleted backup {backup_filename}"
    assert response.json["events"][2]["detail"]["backup_filename"] == backup_filename

    response = dashboard_client.request("GET", "/api/workspace/audit/export?limit=5")
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-workspace-audit.json"'
    exported_sha = hashlib.sha256(response.body).hexdigest()
    assert response.headers["X-Content-SHA256"] == exported_sha
    assert response.headers["X-Content-SHA256-12"] == exported_sha[:12]
    assert response.json["schema_version"] == 1
    assert response.json["event_count"] == 4
    assert response.json["events"][0]["action"] == "delete_backup"


def test_dashboard_handler_restores_backup_when_workspace_stores_are_corrupt(
    dashboard_client: "HandlerClient",
):
    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={
            "profile": "canslim_score_rank",
            "review": {"query": "orig", "sort_by": "ticker", "sort_dir": "asc"},
            "risk": {"account_equity": 150000, "risk_pct": 0.6},
        },
    )
    assert response.status == 200
    response = dashboard_client.request(
        "POST",
        "/api/review",
        body={"profile": "canslim_score_rank", "item": {"ticker": "ORIG1", "decision_status": "ready"}},
    )
    assert response.status == 201
    response = dashboard_client.request(
        "POST",
        "/api/session/journal",
        body={"profile": "canslim_score_rank", "date": "2026-05-26", "market_thesis": "Original session"},
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={
            "confirm": "import",
            "snapshot": {
                "schema_version": 1,
                "profile": "canslim_score_rank",
                "preferences": {
                    "profile": "canslim_score_rank",
                    "review": {"query": "new", "sort_by": "added_at", "sort_dir": "desc"},
                },
                "review": {"items": [{"ticker": "NEW1", "decision_status": "watch"}]},
                "journal": {"entries": [{"date": "2026-05-26", "market_thesis": "New session"}]},
            },
        },
    )
    assert response.status == 201
    backup_filename = response.json["backup"]["filename"]
    backup_path = workspace_snapshot.BACKUP_DIR / backup_filename
    backup_sha = hashlib.sha256(backup_path.read_bytes()).hexdigest()[:12]

    workspace_store.STORE_PATH.write_text('{"profile": ')
    review_store.STORE_PATH.write_text('{"profiles": ')
    session_journal.STORE_PATH.write_text('{"profiles": ')

    response = dashboard_client.request(
        "GET",
        f"/api/workspace/backups/preview?filename={backup_filename}",
    )
    assert response.status == 200
    assert response.json["recovery"]["quarantine_required"] is True
    assert {error["label"] for error in response.json["recovery"]["current_store_errors"]} == {
        "preferences",
        "review queue",
        "session journal",
    }
    assert response.json["review"]["current_unavailable"] is True
    assert response.json["journal"]["current_unavailable"] is True

    response = dashboard_client.request(
        "POST",
        "/api/workspace/backups/restore",
        body={"filename": backup_filename, "confirm": "restore", "expected_sha256_12": backup_sha},
    )
    assert response.status == 201
    assert response.json["backup"]["recovery_only"] is True
    assert response.json["backup"]["filename"].startswith("canslim-workspace-recovery-canslim_score_rank-")
    assert response.json["review"]["items"][0]["ticker"] == "ORIG1"
    assert response.json["preferences"]["review"]["query"] == "orig"
    assert response.json["journal"]["entries"][0]["market_thesis"] == "Original session"
    assert response.json["audit_event"]["action"] == "restore_backup"
    assert response.json["audit_event"]["detail"]["quarantined_store_count"] == 3
    assert response.json["audit_event"]["detail"]["backup_recovery_only"] is True

    quarantined = response.json["quarantined_stores"]
    assert {item["label"] for item in quarantined} == {"preferences", "review queue", "session journal"}
    for item in quarantined:
        quarantine_path = Path(item["quarantine_path"])
        assert quarantine_path.exists()
        assert quarantine_path.name.startswith(
            {
                "preferences": "preferences.corrupt-",
                "review queue": "review_queue.corrupt-",
                "session journal": "session_journal.corrupt-",
            }[item["label"]]
        )

    response = dashboard_client.request("GET", "/api/workspace/backups?profile=canslim_score_rank&limit=20")
    assert response.status == 200
    assert response.json["backups"]
    assert not any(backup.get("recovery_only") for backup in response.json["backups"])
    assert response.json["backups"][0]["filename"].startswith("canslim-workspace-backup-")


def test_workspace_backup_atomic_write_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    target = tmp_path / "canslim-workspace-backup-canslim_score_rank-20260526T100000Z.json"
    target.write_text("existing backup\n")
    original_replace = type(target).replace

    def fail_replace(self: Path, replacement: object) -> Path:
        if self.name.startswith(f".{target.name}.") and Path(replacement) == target:
            raise OSError("replace failed")
        return original_replace(self, replacement)

    monkeypatch.setattr(type(target), "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_store.write_json_atomic(
            target,
            {"profile": "canslim_score_rank", "schema_version": 1},
            trailing_newline=True,
        )

    assert target.read_text() == "existing backup\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_dashboard_handler_cleans_workspace_atomic_temp_files(
    dashboard_client: "HandlerClient",
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    project = tmp_path
    workspace_dir = project / "data" / "web_workspace"
    workspace_dir.mkdir(parents=True)
    temp_path = workspace_dir / ".preferences.json.interrupted.tmp"
    temp_path.write_text("{}")
    keep_path = workspace_dir / "preferences.json.tmp"
    keep_path.write_text("{}")
    monkeypatch.setattr(data_provider, "PROJECT_ROOT", project)

    response = dashboard_client.request(
        "POST",
        "/api/workspace/temp-files/cleanup",
        body={},
    )
    assert response.status == 400
    assert response.json["error"] == "confirm=cleanup is required to clean workspace temp files"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/temp-files/cleanup",
        body={"confirm": "cleanup"},
    )
    assert response.status == 200
    assert response.json["deleted_count"] == 1
    assert response.json["failed_count"] == 0
    assert response.json["deleted"] == ["data/web_workspace/.preferences.json.interrupted.tmp"]
    assert response.json["audit_event"]["action"] == "cleanup_temp_files"
    assert response.json["audit_event"]["detail"]["deleted_count"] == 1
    assert not temp_path.exists()
    assert keep_path.exists()


def test_dashboard_handler_repairs_corrupt_workspace_audit_store(dashboard_client: "HandlerClient"):
    workspace_audit.STORE_PATH.write_text('{"events": {}}')

    response = dashboard_client.request("GET", "/api/workspace/audit?limit=5")
    assert response.status == 400
    assert response.json["error"] == "Workspace audit store events must be a JSON array"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/audit/repair",
        body={},
    )
    assert response.status == 400
    assert response.json["error"] == "confirm=repair is required to repair the workspace audit store"
    assert workspace_audit.STORE_PATH.read_text() == '{"events": {}}'

    response = dashboard_client.request(
        "POST",
        "/api/workspace/audit/repair",
        body={"confirm": "repair"},
    )
    assert response.status == 200
    assert response.json["repaired"] is True
    assert response.json["reason"] == "Workspace audit store events must be a JSON array"
    assert response.json["audit_event"]["action"] == "repair_audit_store"

    quarantine_path = Path(response.json["quarantine_path"])
    if not quarantine_path.is_absolute():
        quarantine_path = data_provider.PROJECT_ROOT / quarantine_path
    assert quarantine_path.name.startswith("workspace_audit.corrupt-")
    assert quarantine_path.name.endswith(".json")
    assert quarantine_path.read_text() == '{"events": {}}'

    store = json.loads(workspace_audit.STORE_PATH.read_text())
    assert store["events"][0]["action"] == "repair_audit_store"
    assert store["events"][0]["summary"] == "Repaired workspace audit store"
    assert store["events"][0]["detail"]["quarantine_path"] == response.json["quarantine_path"]

    response = dashboard_client.request("GET", "/api/workspace/audit?limit=5")
    assert response.status == 200
    assert response.json["events"][0]["action"] == "repair_audit_store"

    response = dashboard_client.request(
        "POST",
        "/api/workspace/audit/repair",
        body={"confirm": "repair"},
    )
    assert response.status == 200
    assert response.json["repaired"] is False
    assert response.json["reason"] == "audit store is already readable"


def test_workspace_backup_retention_prunes_old_profile_backups(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(workspace_snapshot, "BACKUP_LIMIT", 2)

    response = dashboard_client.request(
        "POST",
        "/api/review",
        body={"profile": "canslim_score_rank", "item": {"ticker": "BASE", "decision_status": "watch"}},
    )
    assert response.status == 201

    imported_filenames = []
    for index in range(3):
        response = dashboard_client.request(
            "POST",
            "/api/workspace/import",
            body={
                "confirm": "import",
                "snapshot": {
                    "schema_version": 1,
                    "profile": "canslim_score_rank",
                    "preferences": {"profile": "canslim_score_rank"},
                    "review": {"items": [{"ticker": f"NEW{index}", "decision_status": "watch"}]},
                }
            },
        )
        assert response.status == 201
        imported_filenames.append(response.json["backup"]["filename"])

    response = dashboard_client.request(
        "POST",
        "/api/review",
        body={"profile": "canslim_watchlist", "item": {"ticker": "WATCH", "decision_status": "watch"}},
    )
    assert response.status == 201

    response = dashboard_client.request(
        "POST",
        "/api/workspace/import",
        body={
            "confirm": "import",
            "snapshot": {
                "schema_version": 1,
                "profile": "canslim_watchlist",
                "preferences": {"profile": "canslim_watchlist"},
                "review": {"items": [{"ticker": "WATCH2", "decision_status": "watch"}]},
            }
        },
    )
    assert response.status == 201
    watchlist_backup = response.json["backup"]["filename"]

    response = dashboard_client.request("GET", "/api/workspace/backups?profile=canslim_score_rank&limit=20")
    assert response.status == 200
    score_rank_filenames = [item["filename"] for item in response.json["backups"]]
    assert len(score_rank_filenames) == 2
    assert imported_filenames[0] not in score_rank_filenames
    assert set(score_rank_filenames) == set(imported_filenames[1:])

    response = dashboard_client.request("GET", "/api/workspace/backups?profile=canslim_watchlist&limit=20")
    assert response.status == 200
    assert [item["filename"] for item in response.json["backups"]] == [watchlist_backup]


def test_dashboard_handler_rejects_invalid_export_format(dashboard_client: "HandlerClient"):
    response = dashboard_client.request("GET", "/api/review/export?profile=canslim_score_rank&format=xlsx")

    assert response.status == 400
    assert response.json["error"] == "format must be one of: csv, json, tradingview, txt"

    response = dashboard_client.request("GET", "/api/review/export?profile=canslim_score_rank&status=maybe")

    assert response.status == 400
    assert response.json["error"] == "status filter must be one of: watch, ready, pass, bought, sold"

    response = dashboard_client.request("GET", "/api/review/export?profile=canslim_score_rank&tickers=../bad")

    assert response.status == 400
    assert response.json["error"] == "Ticker must be 1-15 uppercase letters, numbers, underscores, or hyphens"

    response = dashboard_client.request("GET", "/api/session/report?profile=canslim_score_rank&format=pdf")

    assert response.status == 400
    assert response.json["error"] == "format must be one of: json, md"


def test_dashboard_handler_exports_stock_dossier(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        data_provider,
        "export_stock_dossier",
        lambda ticker, profile=None: {
            "body": json.dumps({"ticker": ticker, "profile": profile}),
            "content_type": "application/json; charset=utf-8",
            "filename": f"canslim-dossier-{profile}-{ticker}.json",
        },
    )

    response = dashboard_client.request("GET", "/api/analyze/export?profile=canslim_score_rank&ticker=IESC")

    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert response.headers["Content-Disposition"] == 'attachment; filename="canslim-dossier-canslim_score_rank-IESC.json"'
    assert response.json == {"ticker": "IESC", "profile": "canslim_score_rank"}

    response = dashboard_client.request("HEAD", "/api/analyze/export?profile=canslim_score_rank&ticker=IESC")
    assert response.status == 200
    assert response.body == b""
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"


def test_dashboard_handler_rejects_invalid_json_bodies(dashboard_client: "HandlerClient"):
    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={"profile": "canslim_score_rank"},
        csrf=False,
    )

    assert response.status == 403
    assert response.json["error"] == "CSRF token is invalid or missing"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={"profile": "canslim_score_rank"},
        headers={server.CSRF_HEADER: "bad-token"},
        csrf=False,
    )

    assert response.status == 403
    assert response.json["error"] == "CSRF token is invalid or missing"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        raw_body=b"{}",
        headers={"Content-Type": "text/plain"},
    )

    assert response.status == 415
    assert response.json["error"] == "Content-Type must be application/json"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        raw_body=b'{"profile":"canslim_score_rank"}',
        headers={"Content-Type": "application/vnd.api+json; charset=utf-8"},
    )

    assert response.status == 200
    assert response.json["profile"] == "canslim_score_rank"

    response = dashboard_client.request("POST", "/api/preferences", raw_body=b"\xff")

    assert response.status == 400
    assert response.json["error"] == "Request body must be valid UTF-8"

    response = dashboard_client.request("POST", "/api/preferences", raw_body=b"{")

    assert response.status == 400
    assert response.json["error"] == "Request body must be valid JSON"

    response = dashboard_client.request("POST", "/api/preferences", raw_body=b"[]")

    assert response.status == 400
    assert response.json["error"] == "Request body must be a JSON object"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        raw_body=b"{}",
        headers={"Content-Length": str(server.MAX_JSON_BODY_BYTES + 1)},
    )

    assert response.status == 413
    assert response.json["error"] == f"Request body exceeds {server.MAX_JSON_BODY_BYTES} byte limit"


def test_dashboard_handler_rate_limits_write_apis(dashboard_client: "HandlerClient"):
    dashboard_client.server.write_rate_limit = 2
    dashboard_client.server.write_rate_window_seconds = 60
    dashboard_client.server.write_rate_buckets = {}

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        body={"profile": "canslim_score_rank"},
        csrf=False,
    )
    assert response.status == 403

    first = dashboard_client.request("POST", "/api/preferences", body={"profile": "canslim_score_rank"})
    second = dashboard_client.request("POST", "/api/preferences", body={"profile": "canslim_score_rank"})
    limited = dashboard_client.request("POST", "/api/preferences", body={"profile": "canslim_score_rank"})

    assert first.status == 200
    assert second.status == 200
    assert limited.status == 429
    assert limited.json["error"] == "Write API is rate limited"
    assert limited.json["code"] == "too_many_requests"
    assert 1 <= int(limited.headers["Retry-After"]) <= 60

    dashboard_client.server.write_rate_buckets["127.0.0.1"]["requests"] = []
    recovered = dashboard_client.request("POST", "/api/preferences", body={"profile": "canslim_score_rank"})
    assert recovered.status == 200


def test_dashboard_handler_reports_allowed_methods(dashboard_client: "HandlerClient"):
    response = dashboard_client.request("DELETE", "/api/preferences")

    assert response.status == 405
    assert response.headers["Allow"] == "POST"
    assert response.json["error"] == "Method not allowed"

    response = dashboard_client.request("PUT", "/api/review?profile=canslim_score_rank")

    assert response.status == 405
    assert response.headers["Allow"] == "POST, DELETE"
    assert response.json["error"] == "Method not allowed"


def test_dashboard_handler_exposes_machine_readable_readiness(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, Any] = {}

    def fake_readiness(profile=None, **kwargs):
        captured["profile"] = profile
        captured["access_context"] = kwargs.get("access_context")
        return {
            "ok": True,
            "status": "ready",
            "profile": profile or "canslim_score_rank",
            "summary": "11/11 release gates ready",
            "gates": [{"id": "web_static", "level": "ready"}],
        }

    monkeypatch.setattr(data_provider, "get_release_readiness", fake_readiness)

    response = dashboard_client.request("GET", "/api/readiness?profile=canslim_score_rank")

    assert response.status == 200
    assert response.json["ok"] is True
    assert response.json["status"] == "ready"
    assert response.json["summary"] == "11/11 release gates ready"
    assert response.json["gates"][0]["id"] == "web_static"
    assert captured == {
        "profile": "canslim_score_rank",
        "access_context": {
            "allow_remote": False,
            "auth_enabled": False,
            "require_auth": False,
            "auth_env": server.DEFAULT_AUTH_ENV,
            "auth_failure_limit": server.AUTH_FAILURE_LIMIT,
            "auth_failure_window_seconds": server.AUTH_FAILURE_WINDOW_SECONDS,
            "auth_lockout_seconds": server.AUTH_LOCKOUT_SECONDS,
            "max_json_body_bytes": server.MAX_JSON_BODY_BYTES,
            "write_rate_limit": server.WRITE_RATE_LIMIT,
            "write_rate_window_seconds": server.WRITE_RATE_WINDOW_SECONDS,
            "request_timeout_seconds": server.REQUEST_TIMEOUT_SECONDS,
        },
    }

    monkeypatch.setattr(
        data_provider,
        "get_release_readiness",
        lambda profile=None, **kwargs: {
            "ok": False,
            "status": "blocked",
            "profile": profile or "canslim_score_rank",
            "summary": "9/11 release gates ready",
        },
    )

    response = dashboard_client.request("GET", "/api/readiness?profile=canslim_score_rank")

    assert response.status == 503
    assert response.json["ok"] is False
    assert response.json["status"] == "blocked"

    response = dashboard_client.request("HEAD", "/api/readiness?profile=canslim_score_rank")
    assert response.status == 503
    assert response.body == b""


def test_dashboard_handler_restores_removed_review_activity(dashboard_client: "HandlerClient"):
    response = dashboard_client.request(
        "POST",
        "/api/review/bulk",
        body={
            "profile": "canslim_score_rank",
            "items": [
                {"ticker": "LINC", "name": "Lincoln"},
                {"ticker": "MYRG", "name": "MYR Group"},
            ],
        },
    )
    assert response.status == 201

    response = dashboard_client.request(
        "POST",
        "/api/review/actions",
        body={"profile": "canslim_score_rank", "action": "remove", "tickers": ["MYRG"]},
    )
    assert response.status == 200
    activity_at = response.json["activity"][0]["at"]
    assert response.json["activity"][0]["restorable_items"][0]["ticker"] == "MYRG"

    response = dashboard_client.request(
        "POST",
        "/api/review/undo",
        body={"profile": "canslim_score_rank", "activity_at": activity_at},
    )
    assert response.status == 200
    assert [item["ticker"] for item in response.json["items"]] == ["MYRG", "LINC"]
    assert response.json["activity"][0]["action"] == "restored"


def test_dashboard_handler_rejects_untrusted_host_and_origin(dashboard_client: "HandlerClient"):
    response = dashboard_client.request("GET", "/api/health", headers={"Host": "127.0.0.1:8765"})
    assert response.status == 200

    response = dashboard_client.request("GET", "/api/health", headers={"Host": ""})
    assert response.status == 403
    assert response.json["error"] == "Host header is not allowed"

    response = dashboard_client.request("GET", "/api/health", headers={"Host": "evil.example"})
    assert response.status == 403
    assert response.json["error"] == "Host header is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": ""},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": "https://evil.example"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:9999"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://localhost:8765"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": "https://127.0.0.1:8765"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "localhost:8765", "Origin": "http://localhost:8765"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 200

    dashboard_client.server.allow_remote = True

    response = dashboard_client.request("GET", "/api/health", headers={"Host": ""})
    assert response.status == 403
    assert response.json["error"] == "Host header is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "dashboard.example", "Origin": "https://evil.example"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "dashboard.example:8443", "Origin": "https://dashboard.example"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 403
    assert response.json["error"] == "Origin is not allowed"

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "dashboard.example", "Origin": "https://dashboard.example"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 200

    response = dashboard_client.request(
        "POST",
        "/api/preferences",
        headers={"Host": "dashboard.example:8443", "Origin": "https://dashboard.example:8443"},
        body={"profile": "canslim_score_rank"},
    )
    assert response.status == 200


def test_dashboard_handler_enforces_optional_basic_auth(dashboard_client: "HandlerClient"):
    dashboard_client.server.auth_credentials = ("desk", "secret")

    response = dashboard_client.request("GET", "/")
    assert response.status == 401
    assert response.headers["WWW-Authenticate"] == 'Basic realm="CANSLIM SEPA", charset="UTF-8"'
    assert response.json["error"] == "Authentication is required"

    response = dashboard_client.request("GET", "/", headers={"Authorization": "Basic bad"})
    assert response.status == 401

    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "wrong")})
    assert response.status == 401

    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "secret")})
    assert response.status == 200
    assert "CANSLIM SEPA Dashboard" in response.text

    response = dashboard_client.request(
        "POST",
        "/api/client-events",
        headers={"Authorization": _basic_auth_header("desk", "secret")},
        body={"event": {"kind": "error", "message": "authorized event"}},
    )
    assert response.status == 200
    assert response.json["accepted"] is True


def test_dashboard_handler_throttles_repeated_basic_auth_failures(dashboard_client: "HandlerClient"):
    dashboard_client.server.auth_credentials = ("desk", "secret")
    dashboard_client.server.auth_failure_limit = 2
    dashboard_client.server.auth_failure_window_seconds = 60
    dashboard_client.server.auth_lockout_seconds = 7

    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "wrong")})
    assert response.status == 401
    assert response.json["error"] == "Authentication is required"

    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "wrong-again")})
    assert response.status == 429
    assert response.json["error"] == "Authentication is temporarily locked"
    assert response.headers["Retry-After"] == "7"

    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "secret")})
    assert response.status == 429

    dashboard_client.server.auth_failures["127.0.0.1"]["locked_until"] = 0
    response = dashboard_client.request("GET", "/", headers={"Authorization": _basic_auth_header("desk", "secret")})
    assert response.status == 200
    assert dashboard_client.server.auth_failures == {}


def test_dashboard_handler_passes_runtime_access_context_to_diagnostics(
    dashboard_client: "HandlerClient",
    monkeypatch: pytest.MonkeyPatch,
):
    captured = {}
    dashboard_client.server.allow_remote = True
    dashboard_client.server.auth_credentials = ("desk", "secret")
    dashboard_client.server.require_auth = True
    dashboard_client.server.auth_env = "DASH_AUTH"

    def fake_diagnostics(profile=None, **kwargs):
        captured["profile"] = profile
        captured["access_context"] = kwargs.get("access_context")
        return {
            "profile": profile or "canslim_score_rank",
            "level": "ready",
            "summary": "ok",
            "checks": [],
        }

    monkeypatch.setattr(data_provider, "get_operational_diagnostics", fake_diagnostics)

    response = dashboard_client.request(
        "GET",
        "/api/diagnostics?profile=canslim_score_rank",
        headers={"Authorization": _basic_auth_header("desk", "secret")},
    )

    assert response.status == 200
    assert captured == {
        "profile": "canslim_score_rank",
        "access_context": {
            "allow_remote": True,
            "auth_enabled": True,
            "require_auth": True,
            "auth_env": "DASH_AUTH",
            "auth_failure_limit": server.AUTH_FAILURE_LIMIT,
            "auth_failure_window_seconds": server.AUTH_FAILURE_WINDOW_SECONDS,
            "auth_lockout_seconds": server.AUTH_LOCKOUT_SECONDS,
            "max_json_body_bytes": server.MAX_JSON_BODY_BYTES,
            "write_rate_limit": server.WRITE_RATE_LIMIT,
            "write_rate_window_seconds": server.WRITE_RATE_WINDOW_SECONDS,
            "request_timeout_seconds": server.REQUEST_TIMEOUT_SECONDS,
        },
    }


def test_dashboard_server_rejects_remote_bind_without_explicit_opt_in():
    server.validate_bind_host("127.0.0.1")
    server.validate_bind_host("localhost")
    server.validate_bind_host("::1")
    server.validate_bind_host("0.0.0.0", allow_remote=True)

    with pytest.raises(ValueError, match="--allow-remote"):
        server.validate_bind_host("0.0.0.0")


def test_dashboard_handler_sets_client_socket_timeout(monkeypatch):
    setup_calls = []

    class FakeSocket:
        def __init__(self) -> None:
            self.timeout = None

        def settimeout(self, value):
            self.timeout = value

    def fake_parent_setup(handler):
        setup_calls.append(handler.request.timeout)

    handler = server.DashboardRequestHandler.__new__(server.DashboardRequestHandler)
    handler.request = FakeSocket()
    handler.server = SimpleNamespace(request_timeout_seconds=3)
    monkeypatch.setattr(server.BaseHTTPRequestHandler, "setup", fake_parent_setup)

    handler.setup()

    assert setup_calls == [3]


def test_dashboard_server_can_open_browser_to_friendly_local_url(monkeypatch, capsys):
    calls = []
    opened = []

    class FakeHTTPServer:
        def __init__(self, address, handler):
            self.address = address
            self.handler = handler
            calls.append(("init", address, handler))

        def serve_forever(self):
            calls.append(("serve_forever", self.quiet, self.allow_remote, bool(self.csrf_token)))

        def server_close(self):
            calls.append(("server_close",))

    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeHTTPServer)
    monkeypatch.setattr(server.webbrowser, "open", lambda url: opened.append(url))

    server.run("0.0.0.0", 9999, quiet=True, allow_remote=True, open_browser=True, auth="desk:secret")

    assert calls[0] == ("init", ("0.0.0.0", 9999), server.DashboardRequestHandler)
    assert calls[1] == ("serve_forever", True, True, True)
    assert calls[2] == ("server_close",)
    assert opened == ["http://127.0.0.1:9999"]
    assert "CAN SLIM dashboard: http://127.0.0.1:9999" in capsys.readouterr().out


def test_dashboard_server_can_require_auth_before_starting(monkeypatch):
    calls = []

    class FakeHTTPServer:
        def __init__(self, address, handler):
            calls.append(("init", address, handler))

        def serve_forever(self):
            calls.append(("serve_forever",))

        def server_close(self):
            calls.append(("server_close",))

    monkeypatch.setattr(server, "ThreadingHTTPServer", FakeHTTPServer)

    with pytest.raises(ValueError, match="authentication is required"):
        server.run("0.0.0.0", 9999, allow_remote=True, require_auth=True, auth_env="")

    assert calls == []

    server.run("0.0.0.0", 9999, allow_remote=True, require_auth=True, auth="desk:secret")

    assert calls == [
        ("init", ("0.0.0.0", 9999), server.DashboardRequestHandler),
        ("serve_forever",),
        ("server_close",),
    ]


def test_dashboard_server_cli_reports_missing_required_auth_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["server.py", "--port", "8770", "--require-auth", "--auth-env", ""])

    with pytest.raises(SystemExit) as exc_info:
        server.main()

    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Dashboard authentication is required" in stderr
    assert "Traceback" not in stderr


def test_dashboard_auth_parser_requires_user_and_password():
    assert server.parse_auth_credentials(None) is None
    assert server.parse_auth_credentials("desk:secret") == ("desk", "secret")
    assert server.parse_auth_credentials("desk:long:secret") == ("desk", "long:secret")

    with pytest.raises(ValueError, match="USER:PASSWORD"):
        server.parse_auth_credentials("desk")
    with pytest.raises(ValueError, match="both USER and PASSWORD"):
        server.parse_auth_credentials(":secret")
    with pytest.raises(ValueError, match="both USER and PASSWORD"):
        server.parse_auth_credentials("desk:")


def test_dashboard_auth_can_resolve_credentials_from_environment():
    environ = {"CANSLIM_DASHBOARD_AUTH": "desk:secret", "OTHER_AUTH": "other:secret"}

    assert server.resolve_auth_credentials(auth_env="CANSLIM_DASHBOARD_AUTH", environ=environ) == ("desk", "secret")
    assert server.resolve_auth_credentials(auth="direct:secret", auth_env="CANSLIM_DASHBOARD_AUTH", environ=environ) == (
        "direct",
        "secret",
    )
    assert server.resolve_auth_credentials(auth_env="", environ=environ) is None
    assert server.resolve_auth_credentials(auth_env="MISSING_AUTH", environ=environ) is None
    assert server.resolve_auth_credentials(auth_env="OTHER_AUTH", environ=environ) == ("other", "secret")

    with pytest.raises(ValueError, match="USER:PASSWORD"):
        server.resolve_auth_credentials(auth_env="BAD_AUTH", environ={"BAD_AUTH": "bad"})


def test_dashboard_auth_requirement_rejects_missing_credentials():
    server.validate_auth_requirement(("desk", "secret"), require_auth=True)
    server.validate_auth_requirement(None, require_auth=False)

    with pytest.raises(ValueError, match="Dashboard authentication is required"):
        server.validate_auth_requirement(None, require_auth=True)


def test_dashboard_url_formats_ipv6_loopback():
    assert server.dashboard_url("::1", 8765) == "http://[::1]:8765"
    assert server.dashboard_url("localhost", 8765) == "http://localhost:8765"


class HandlerResponse:
    def __init__(self, raw: bytes):
        header_bytes, _, body = raw.partition(b"\r\n\r\n")
        header_text = header_bytes.decode("iso-8859-1")
        status_line, _, header_lines = header_text.partition("\r\n")
        self.status = int(status_line.split()[1])
        self.headers = Parser().parsestr(header_lines)
        self.body = body
        self.text = body.decode("utf-8")

    @property
    def json(self) -> Any:
        return json.loads(self.text)


class HandlerClient:
    def __init__(self) -> None:
        self.server = SimpleNamespace(quiet=True, csrf_token="test-csrf-token-123456", auth_credentials=None)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        raw_body: bytes | None = None,
        csrf: bool = True,
        download_token: bool = True,
    ) -> HandlerResponse:
        handler = server.DashboardRequestHandler.__new__(server.DashboardRequestHandler)
        if body is not None and raw_body is not None:
            raise AssertionError("body and raw_body cannot both be provided")
        encoded_body = raw_body if raw_body is not None else json.dumps(body).encode("utf-8") if body is not None else b""
        handler.server = self.server
        handler.client_address = ("127.0.0.1", 0)
        handler.command = method
        handler.path = path
        handler.requestline = f"{method} {path} HTTP/1.1"
        handler.request_version = "HTTP/1.1"
        handler.close_connection = True
        handler.rfile = BytesIO(encoded_body)
        handler.wfile = BytesIO()
        request_headers = dict(headers or {})
        request_headers.setdefault("Host", "127.0.0.1:8765")
        if method.upper() in server.WRITE_METHODS:
            request_headers.setdefault("Origin", "http://127.0.0.1:8765")
        if _test_request_needs_csrf(method, path, request_headers, csrf=csrf):
            request_headers[server.CSRF_HEADER] = self.server.csrf_token
        if _test_request_needs_download_token(method, path, request_headers, download_token=download_token):
            request_headers[server.CSRF_HEADER] = self.server.csrf_token
        handler.headers = _headers_for(
            encoded_body if body is not None or raw_body is not None else None,
            extra=request_headers,
        )
        if method == "GET":
            handler.do_GET()
        elif method == "HEAD":
            handler.do_HEAD()
        elif method == "POST":
            handler.do_POST()
        elif method == "DELETE":
            handler.do_DELETE()
        elif method == "PUT":
            handler.do_PUT()
        elif method == "PATCH":
            handler.do_PATCH()
        else:  # pragma: no cover - tests only use explicit methods above
            raise AssertionError(f"Unsupported method: {method}")
        return HandlerResponse(handler.wfile.getvalue())


def _headers_for(raw_body: bytes | None, *, extra: dict[str, str] | None = None) -> Message:
    headers = Message()
    if raw_body is not None:
        headers["Content-Length"] = str(len(raw_body))
        headers["Content-Type"] = "application/json"
    for key, value in (extra or {}).items():
        if key in headers:
            headers.replace_header(key, value)
        else:
            headers[key] = value
    return headers


def _basic_auth_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _test_request_needs_csrf(method: str, path: str, headers: dict[str, str], *, csrf: bool) -> bool:
    if not csrf or method.upper() not in server.WRITE_METHODS:
        return False
    path_only = path.split("?", 1)[0]
    if path_only in server.CSRF_EXEMPT_WRITE_PATHS:
        return False
    return not any(key.lower() == server.CSRF_HEADER.lower() for key in headers)


def _test_request_needs_download_token(
    method: str,
    path: str,
    headers: dict[str, str],
    *,
    download_token: bool,
) -> bool:
    if not download_token or method.upper() not in {"GET", "HEAD"}:
        return False
    path_only = path.split("?", 1)[0]
    if path_only not in server.SENSITIVE_DOWNLOAD_PATHS:
        return False
    return not any(key.lower() == server.CSRF_HEADER.lower() for key in headers)


def _assert_request_id(value: str) -> str:
    assert len(value) == 12
    int(value, 16)
    return value


def _assert_csrf_token(value: str) -> None:
    assert isinstance(value, str)
    assert len(value) >= 16


def _assert_runtime_metadata(value: dict[str, Any]) -> None:
    assert value["run_id"] == runtime_info.RUN_ID
    assert value["started_at"] == runtime_info.STARTED_AT.isoformat()
    assert isinstance(value["uptime_seconds"], float)
    assert value["uptime_seconds"] >= 0
    assert value["app"] == {
        "name": runtime_info.APP_NAME,
        "version": runtime_info.APP_VERSION,
    }
    assert value["source"]["git_available"] == runtime_info.SOURCE_METADATA["git_available"]
    assert value["source"]["git_commit"] == runtime_info.SOURCE_METADATA["git_commit"]
    assert value["source"]["git_branch"] == runtime_info.SOURCE_METADATA["git_branch"]
    assert isinstance(value["source"]["git_dirty"], bool)
    assert isinstance(value["source"]["git_untracked"], bool)
