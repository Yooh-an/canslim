"""Security posture contract tests."""

from __future__ import annotations

from src.web import security_posture


def _control(posture: dict, control_id: str) -> dict:
    return next(control for control in posture["controls"] if control["id"] == control_id)


def test_security_posture_reports_loopback_access_as_ready() -> None:
    posture = security_posture.security_posture(
        access_context={
            "allow_remote": False,
            "auth_enabled": False,
            "require_auth": False,
            "auth_env": security_posture.DEFAULT_AUTH_ENV,
        }
    )

    assert posture["level"] == "ready"
    assert posture["summary"] == "11/11 controls ready"
    access = _control(posture, "access_control")
    assert access["level"] == "ready"
    assert access["detail"] == "loopback-only dashboard; Basic Auth optional for local use"
    throttle = _control(posture, "auth_failure_throttle")
    assert throttle["level"] == "ready"
    assert throttle["detail"] == "inactive until Basic Auth is enabled"
    body_limit = _control(posture, "request_body_limit")
    assert body_limit["level"] == "ready"
    assert body_limit["detail"] == "JSON write bodies capped at 1000000 byte(s)"
    write_limit = _control(posture, "write_rate_limit")
    assert write_limit["level"] == "ready"
    assert write_limit["detail"] == "write APIs capped at 180 request(s) per 60s per client"
    timeout = _control(posture, "request_timeout")
    assert timeout["level"] == "ready"
    assert timeout["detail"] == "client sockets time out after 15s of inactivity"


def test_security_posture_blocks_remote_access_without_auth() -> None:
    posture = security_posture.security_posture(
        access_context={
            "allow_remote": True,
            "auth_enabled": False,
            "require_auth": False,
            "auth_env": "DASH_AUTH",
        }
    )

    assert posture["level"] == "blocked"
    assert posture["counts"]["blocked"] == 1
    assert posture["summary"] == "10/11 controls ready"
    access = _control(posture, "access_control")
    assert access["level"] == "blocked"
    assert access["detail"] == "remote binding is enabled without Basic Auth; set --auth or DASH_AUTH"


def test_security_posture_warns_when_remote_auth_is_not_fail_closed() -> None:
    posture = security_posture.security_posture(
        access_context={
            "allow_remote": True,
            "auth_enabled": True,
            "require_auth": False,
            "auth_env": "DASH_AUTH",
        }
    )

    assert posture["level"] == "warning"
    assert posture["counts"]["warning"] == 1
    assert posture["summary"] == "10/11 controls ready"
    access = _control(posture, "access_control")
    assert access["level"] == "warning"
    assert access["detail"] == "remote binding is authenticated; add --require-auth for fail-closed startup"


def test_security_posture_reports_remote_fail_closed_auth_as_ready() -> None:
    posture = security_posture.security_posture(
        access_context={
            "allow_remote": True,
            "auth_enabled": True,
            "require_auth": True,
            "auth_env": "DASH_AUTH",
        }
    )

    assert posture["level"] == "ready"
    assert posture["summary"] == "11/11 controls ready"
    access = _control(posture, "access_control")
    assert access["level"] == "ready"
    assert access["detail"] == "remote binding authenticated and fail-closed via DASH_AUTH"
    throttle = _control(posture, "auth_failure_throttle")
    assert throttle["level"] == "ready"
    assert throttle["detail"] == "6 failed attempt(s) per 60s lock for 30s"
    body_limit = _control(posture, "request_body_limit")
    assert body_limit["level"] == "ready"
    assert body_limit["detail"] == "JSON write bodies capped at 1000000 byte(s)"
    write_limit = _control(posture, "write_rate_limit")
    assert write_limit["level"] == "ready"
    assert write_limit["detail"] == "write APIs capped at 180 request(s) per 60s per client"
    timeout = _control(posture, "request_timeout")
    assert timeout["level"] == "ready"
    assert timeout["detail"] == "client sockets time out after 15s of inactivity"
