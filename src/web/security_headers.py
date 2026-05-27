"""Browser security policy constants for the local web dashboard."""

from __future__ import annotations


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "frame-src 'none'; "
    "worker-src 'none'; "
    "connect-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "manifest-src 'self'; "
    "img-src 'self' data:"
)
PERMISSIONS_POLICY = (
    "camera=(), "
    "microphone=(), "
    "geolocation=(), "
    "payment=(), "
    "usb=(), "
    "serial=(), "
    "bluetooth=(), "
    "clipboard-read=(), "
    "clipboard-write=()"
)
CROSS_ORIGIN_OPENER_POLICY = "same-origin"
CROSS_ORIGIN_RESOURCE_POLICY = "same-origin"
REFERRER_POLICY = "no-referrer"
X_FRAME_OPTIONS = "DENY"
X_CONTENT_TYPE_OPTIONS = "nosniff"


def security_header_map() -> dict[str, str]:
    """Return the configured browser safety headers."""
    return {
        "Content-Security-Policy": CONTENT_SECURITY_POLICY,
        "Permissions-Policy": PERMISSIONS_POLICY,
        "Cross-Origin-Opener-Policy": CROSS_ORIGIN_OPENER_POLICY,
        "Cross-Origin-Resource-Policy": CROSS_ORIGIN_RESOURCE_POLICY,
        "Referrer-Policy": REFERRER_POLICY,
        "X-Frame-Options": X_FRAME_OPTIONS,
        "X-Content-Type-Options": X_CONTENT_TYPE_OPTIONS,
    }
