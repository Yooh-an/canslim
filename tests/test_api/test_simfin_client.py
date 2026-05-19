import json
import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from src.api.simfin_client import SimFinClient


COMPACT_PAYLOAD = [
    {
        "found": True,
        "columns": [
            "Ticker",
            "Fiscal Year",
            "Fiscal Period",
            "Report Date",
            "Revenue",
            "Net Income",
            "EPS (Diluted)",
            "Total Debt",
            "Total Equity",
        ],
        "data": [
            ["TEST", 2025, "q1", "2025-03-31", 100, 10, 1.00, 50, 200],
            ["TEST", 2026, "q1", "2026-03-31", 130, 13, 1.30, 60, 240],
            ["TEST", 2023, "fy", "2023-12-31", 300, 30, 2.00, 45, 180],
            ["TEST", 2024, "fy", "2024-12-31", 400, 44, 2.40, 50, 220],
            ["TEST", 2025, "fy", "2025-12-31", 500, 60, 3.00, 60, 240],
        ],
    }
]


def test_simfin_client_reads_api_key_from_env_without_config(monkeypatch):
    monkeypatch.setenv("simfin_API_key", "test-key")

    client = SimFinClient({"data_paths": {"raw_data_dir": tempfile.mkdtemp()}})

    assert client.api_key == "test-key"


@patch("src.api.simfin_client.requests.get")
def test_get_fundamental_metrics_derives_canslim_fields_and_caches(mock_get, tmp_path):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = COMPACT_PAYLOAD
    mock_get.return_value = response
    client = SimFinClient(
        {
            "optional_api_keys": {"simfin_api_key": "test-key"},
            "data_paths": {"raw_data_dir": str(tmp_path)},
        }
    )

    metrics = client.get_fundamental_metrics("TEST")

    assert metrics["quarterly_eps_growth"] == pytest.approx(0.30)
    assert metrics["revenue_growth"] == pytest.approx(0.30)
    assert metrics["annual_eps_cagr"] == pytest.approx((3.0 / 2.0) ** 0.5 - 1)
    assert metrics["profit_margin"] == pytest.approx(0.10)
    assert metrics["roe"] == pytest.approx(60 / 240)
    assert metrics["debt_to_equity"] == pytest.approx(60 / 240)
    assert metrics["financial_data_source"] == "simfin"
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "test-key"

    cached = client.get_fundamental_metrics("TEST")
    assert cached["quarterly_eps_growth"] == pytest.approx(0.30)
    mock_get.assert_called_once()


def test_parse_compact_payload_accepts_wrapped_data_shape(tmp_path):
    client = SimFinClient(
        {
            "optional_api_keys": {"simfin_api_key": "test-key"},
            "data_paths": {"raw_data_dir": str(tmp_path)},
        }
    )

    metrics = client.metrics_from_payload({"data": COMPACT_PAYLOAD})

    assert metrics["ticker"] == "TEST"
    assert metrics["financial_data_source"] == "simfin"


def test_parse_v3_company_statements_shape(tmp_path):
    payload = [
        {
            "ticker": "TEST",
            "statements": [
                {
                    "statement": "PL",
                    "columns": ["Fiscal Period", "Fiscal Year", "Report Date", "Revenue", "Net Income"],
                    "data": [
                        ["Q1", 2025, "2025-03-31", 100, 10],
                        ["Q1", 2026, "2026-03-31", 130, 13],
                        ["FY", 2025, "2025-12-31", 500, 60],
                    ],
                },
                {
                    "statement": "DERIVED",
                    "columns": ["Fiscal Period", "Fiscal Year", "Report Date", "Earnings Per Share, Diluted", "Total Debt", "Return on Equity"],
                    "data": [
                        ["Q1", 2025, "2025-03-31", 1.0, 50, 0.20],
                        ["Q1", 2026, "2026-03-31", 1.3, 60, 0.25],
                        ["FY", 2025, "2025-12-31", 3.0, 60, 0.25],
                    ],
                },
                {
                    "statement": "BS",
                    "columns": ["Fiscal Period", "Fiscal Year", "Report Date", "Total Equity"],
                    "data": [
                        ["Q1", 2026, "2026-03-31", 240],
                        ["FY", 2025, "2025-12-31", 240],
                    ],
                },
            ],
        }
    ]
    client = SimFinClient(
        {
            "optional_api_keys": {"simfin_api_key": "test-key"},
            "data_paths": {"raw_data_dir": str(tmp_path)},
        }
    )

    metrics = client.metrics_from_payload(payload)

    assert metrics["ticker"] == "TEST"
    assert metrics["quarterly_eps_growth"] == pytest.approx(0.30)
    assert metrics["revenue_growth"] == pytest.approx(0.30)
    assert metrics["roe"] == pytest.approx(0.25)
    assert metrics["debt_to_equity"] == pytest.approx(60 / 240)
