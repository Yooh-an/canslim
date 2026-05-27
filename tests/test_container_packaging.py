"""Container packaging guardrails for the dashboard runtime."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_runs_dashboard_as_non_root_with_healthcheck() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/api/readiness" in dockerfile
    assert "/api/health" not in dockerfile
    assert "CANSLIM_DASHBOARD_AUTH" in dockerfile
    assert 'CMD ["python", "run_screener.py", "--mode", "web"' in dockerfile
    assert '"--host", "0.0.0.0"' in dockerfile
    assert '"--allow-remote"' in dockerfile
    assert '"--require-auth"' in dockerfile
    assert "COPY . ." not in dockerfile


def test_dockerignore_excludes_secrets_runtime_data_and_caches() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    ignored = {line.strip() for line in dockerignore if line.strip() and not line.startswith("#")}

    assert ".env" in ignored
    assert ".env.*" in ignored
    assert ".git/" in ignored
    assert "data/" in ignored
    assert "logs/" in ignored
    assert "canslimsepa/" in ignored
    assert "__pycache__/" in ignored
    assert "**/__pycache__/" in ignored
    assert "*.py[cod]" in ignored
    assert ".pytest_cache/" in ignored
    assert ".playwright-mcp/" in ignored
