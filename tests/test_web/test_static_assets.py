"""Static asset guardrails for the local web dashboard."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dashboard_avoids_native_browser_dialogs_for_core_flows() -> None:
    source = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    forbidden_dialog_calls = (
        "window.confirm(",
        "window.prompt(",
        "confirm(",
        "prompt(",
    )
    for call in forbidden_dialog_calls:
        assert call not in source


def test_saved_view_dialog_exposes_inline_validation() -> None:
    source = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

    assert 'id="viewNameForm" novalidate' in source
    assert 'id="viewNameInput"' in source
    assert 'aria-describedby="viewNameError"' in source
    assert 'id="viewNameError" role="alert" hidden' in source


def test_data_operations_exposes_browser_diagnostics_panel() -> None:
    markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert 'id="clientEventsPanel"' in markup
    assert "/api/client-events" in script
    assert "renderClientEvents" in script


def test_data_operations_exposes_release_readiness_panel() -> None:
    markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
    styles = (ROOT / "web" / "assets" / "app.css").read_text(encoding="utf-8")

    assert 'id="releaseReadinessPanel"' in markup
    assert "renderReleaseReadiness" in script
    assert "renderDeploymentGuide" in script
    assert "renderReadinessProbe" in script
    assert "function handleDiagnosticAction" in script
    assert "els.releaseReadinessPanel.addEventListener" in script
    assert "Set ${authEnv} and restart with --require-auth" in script
    assert "release_readiness" in script
    assert ".release-readiness-panel" in styles
    assert ".deployment-guide" in styles
    assert ".readiness-probe" in styles


def test_dynamic_links_are_sanitized_before_rendering() -> None:
    script = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert "function safeExternalHref" in script
    assert "function safeSameOriginApiHref" in script
    assert "const href = safeExternalHref(item.url);" in script
    assert "safeSameOriginApiHref(artifact.download_url, fallbackHref)" in script
    assert 'const href = item.url || "#";' not in script
    assert "artifact.download_url ||" not in script


def test_dashboard_does_not_require_inline_styles() -> None:
    markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    script = (ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")

    assert "style=" not in markup
    assert "style=" not in script
    assert "'unsafe-inline'" not in script
    assert "component-meter" in script


def test_dashboard_exposes_mobile_install_metadata() -> None:
    markup = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "web" / "manifest.webmanifest").read_text(encoding="utf-8"))

    assert '<meta name="theme-color" content="#121417" />' in markup
    assert '<meta name="application-name" content="CANSLIM SEPA" />' in markup
    assert '<link rel="manifest" href="/manifest.webmanifest" />' in markup
    assert manifest["name"] == "CANSLIM SEPA Dashboard"
    assert manifest["short_name"] == "CANSLIM SEPA"
    assert manifest["start_url"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#121417"
    assert manifest["icons"][0]["src"] == "/assets/favicon.svg"


def test_dashboard_respects_reduced_motion_preferences() -> None:
    styles = (ROOT / "web" / "assets" / "app.css").read_text(encoding="utf-8")

    assert "@media (prefers-reduced-motion: reduce)" in styles
    assert "transition-duration: 0.01ms !important" in styles
    assert "animation-duration: 0.01ms !important" in styles
