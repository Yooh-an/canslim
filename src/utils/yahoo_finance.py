"""Compatibility helpers for Yahoo Finance/yfinance access."""

from __future__ import annotations

from typing import Any, Optional


# Yahoo currently accepts this generic browser User-Agent for the cookie/crumb
# endpoint, while some detailed Chrome UA strings still receive Edge 429s.
MODERN_USER_AGENT = "Mozilla/5.0"


def configure_yfinance_user_agent(
    data_module: Optional[Any] = None,
    cache_module: Optional[Any] = None,
) -> bool:
    """
    Force yfinance to use a modern browser User-Agent.

    Older yfinance releases ship a very old Chrome 39 User-Agent. Yahoo Edge can
    respond to the crumb request with HTTP 429 and the body "Edge: Too Many
    Requests". yfinance then caches that body as the crumb and later raises a
    JSONDecodeError. Updating the singleton's headers and clearing cached auth
    state lets yfinance request a fresh valid cookie/crumb pair.
    """
    try:
        if data_module is None:
            import yfinance.data as data_module  # type: ignore[no-redef]
        if cache_module is None:
            import yfinance.cache as cache_module  # type: ignore[no-redef]

        try:
            yf_data = data_module.YfData()
        except TypeError:
            # yfinance's singleton calls _set_session(*args) when an instance
            # already exists, and some versions require an explicit session.
            import requests

            yf_data = data_module.YfData(requests.Session())
        yf_data.user_agent_headers = {"User-Agent": MODERN_USER_AGENT}

        # Clear in-memory cookie/crumb state, especially if a previous call cached
        # "Edge: Too Many Requests" as the crumb.
        if hasattr(yf_data, "_crumb"):
            yf_data._crumb = None
        if hasattr(yf_data, "_cookie"):
            yf_data._cookie = None
        if hasattr(yf_data, "_cookie_strategy"):
            yf_data._cookie_strategy = "basic"

        # Clear persisted cookies too. A Yahoo edge-rate-limited cookie can keep
        # producing a bad crumb even after the User-Agent is fixed.
        try:
            cookie_cache = cache_module.get_cookie_cache()
            cookie_cache.store("basic", None)
            cookie_cache.store("csrf", None)
        except Exception:
            pass
        return True
    except Exception:
        return False
