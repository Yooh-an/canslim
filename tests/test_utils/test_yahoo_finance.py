"""Tests for Yahoo/yfinance compatibility helpers."""

from src.utils.yahoo_finance import MODERN_USER_AGENT, configure_yfinance_user_agent


class DummyYfData:
    def __init__(self):
        self.user_agent_headers = {"User-Agent": "old-yfinance-agent"}
        self._crumb = "Edge: Too Many Requests"
        self._cookie = object()


class DummyDataModule:
    def __init__(self):
        self.instance = DummyYfData()

    def YfData(self):
        return self.instance


class DummyCookieCache:
    def __init__(self):
        self.stored = []

    def store(self, strategy, cookie):
        self.stored.append((strategy, cookie))


class DummyCacheModule:
    def __init__(self):
        self.cookie_cache = DummyCookieCache()

    def get_cookie_cache(self):
        return self.cookie_cache


def test_configure_yfinance_user_agent_replaces_default_and_resets_cached_auth():
    data_module = DummyDataModule()
    cache_module = DummyCacheModule()

    configured = configure_yfinance_user_agent(
        data_module=data_module,
        cache_module=cache_module,
    )

    assert configured is True
    assert data_module.instance.user_agent_headers["User-Agent"] == MODERN_USER_AGENT
    assert data_module.instance._crumb is None
    assert data_module.instance._cookie is None
    assert ("basic", None) in cache_module.cookie_cache.stored
    assert ("csrf", None) in cache_module.cookie_cache.stored
