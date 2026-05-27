import pandas as pd

from src.api.kis_client import KISClient


class FakeResponse:
    def __init__(self, payload, status_code=200, headers=None, text=""):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.get_calls = []
        self.post_calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.get_calls.append({"url": url, "headers": headers, "params": params, "timeout": timeout})
        return self.responses.pop(0)

    def post(self, url, headers=None, data=None, timeout=None):
        self.post_calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        return self.responses.pop(0)


def test_kis_client_from_config_uses_env_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("KIS_APP_KEY", "app-key")
    monkeypatch.setenv("KIS_APP_SECRET", "app-secret")

    client = KISClient.from_config(
        {
            "data_paths": {"raw_data_dir": str(tmp_path)},
            "broker_api": {"enabled": True, "provider": "kis"},
        }
    )

    assert client is not None
    assert client.app_key == "app-key"
    assert client.app_secret == "app-secret"
    assert client.token_cache_file == tmp_path / "kis_token.json"


def test_kis_client_from_config_returns_none_without_credentials(tmp_path):
    client = KISClient.from_config(
        {
            "data_paths": {"raw_data_dir": str(tmp_path)},
            "broker_api": {"enabled": True, "provider": "kis"},
        }
    )

    assert client is None


def test_kis_overseas_daily_history_returns_yfinance_compatible_frame():
    session = FakeSession(
        [
            FakeResponse(
                {
                    "rt_cd": "0",
                    "output2": [
                        {"xymd": "20260102", "open": "100", "high": "105", "low": "99", "clos": "104", "tvol": "12345"},
                        {"xymd": "20260105", "open": "104", "high": "108", "low": "103", "clos": "107", "tvol": "23456"},
                    ],
                },
                headers={"tr_cont": ""},
            )
        ]
    )
    client = KISClient(
        app_key="app",
        app_secret="secret",
        access_token="token",
        session=session,
        exchange_overrides={"SPY": "AMS"},
        rate_limit_delay=0,
    )

    history = client.get_overseas_daily_history("SPY", period="2y", adjusted=True)

    assert isinstance(history, pd.DataFrame)
    assert list(history.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert history.iloc[-1]["Close"] == 107
    assert history.attrs["source"] == "kis_dailyprice"
    assert history.attrs["exchange"] == "AMS"
    call = session.get_calls[0]
    assert call["headers"]["authorization"] == "Bearer token"
    assert call["headers"]["tr_id"] == "HHDFS76240000"
    assert call["params"]["EXCD"] == "AMS"
    assert call["params"]["SYMB"] == "SPY"
    assert call["params"]["MODP"] == "1"


def test_kis_overseas_daily_history_tries_next_exchange_after_api_error():
    session = FakeSession(
        [
            FakeResponse({"rt_cd": "1", "msg1": "not found"}, headers={"tr_cont": ""}),
            FakeResponse(
                {
                    "rt_cd": "0",
                    "output2": [
                        {"xymd": "20260102", "open": "10", "high": "11", "low": "9", "clos": "10.5", "tvol": "1000"},
                    ],
                },
                headers={"tr_cont": ""},
            ),
        ]
    )
    client = KISClient(
        app_key="app",
        app_secret="secret",
        access_token="token",
        session=session,
        exchange_order=["NAS", "NYS"],
        rate_limit_delay=0,
    )

    history = client.get_overseas_daily_history("TEST", period="2y")

    assert history is not None
    assert history.attrs["exchange"] == "NYS"
    assert [call["params"]["EXCD"] for call in session.get_calls] == ["NAS", "NYS"]
