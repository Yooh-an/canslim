"""Tests for free FINRA short-interest enrichment."""

import json

from src.collectors.short_interest_collector import (
    ShortInterestCollector,
    apply_short_interest,
    enrich_companies_with_short_interest_data,
    parse_short_interest_rows,
)


def test_parse_finra_rows_normalizes_current_and_previous_short_interest():
    rows = parse_short_interest_rows(
        [
            {
                "issueSymbolIdentifier": "FN",
                "settlementDate": "2026-04-30",
                "currentShortShareNumber": "1,500,000",
                "previousShortShareNumber": "1,000,000",
                "averageShortShareNumber": "300000",
                "daysToCoverNumber": "5.00",
            }
        ]
    )

    assert rows == [
        {
            "ticker": "FN",
            "short_interest_raw_ticker": "FN",
            "short_interest": 1_500_000,
            "short_interest_previous": 1_000_000,
            "short_interest_change": 500_000,
            "short_interest_change_pct": 0.5,
            "short_average_daily_volume": 300_000,
            "short_days_to_cover": 5.0,
            "short_interest_settlement_date": "2026-04-30",
            "short_interest_report_date": None,
            "short_interest_source": "finra_equity_short_interest",
        }
    ]


def test_apply_short_interest_calculates_short_percentages_when_denominators_exist():
    companies = [
        {
            "ticker": "FN",
            "shares_float": 10_000_000,
            "shares_outstanding": 12_500_000,
        }
    ]
    enriched = apply_short_interest(
        companies,
        {
            "FN": {
                "short_interest": 1_500_000,
                "short_days_to_cover": 5.0,
                "short_interest_settlement_date": "2026-04-30",
                "short_interest_source": "finra_equity_short_interest",
            }
        },
    )

    assert enriched[0]["short_interest"] == 1_500_000
    assert enriched[0]["short_percent_float"] == 0.15
    assert enriched[0]["short_percent_shares_outstanding"] == 0.12


def test_enrich_companies_reads_local_finra_csv_cache(tmp_path):
    raw_dir = tmp_path / "short_interest"
    raw_dir.mkdir()
    (raw_dir / "finra.csv").write_text(
        "\n".join(
            [
                "issueSymbolIdentifier,settlementDate,currentShortShareNumber,previousShortShareNumber,averageShortShareNumber,daysToCoverNumber",
                "FN,2026-03-31,1000000,900000,250000,4.00",
                "FN,2026-04-30,1500000,1000000,300000,5.00",
            ]
        )
    )
    companies = [{"ticker": "FN", "shares_outstanding": 10_000_000}]
    config = {
        "short_interest_data": {
            "enabled": True,
            "fetch_live": False,
            "raw_short_interest_dir": str(raw_dir),
        }
    }

    enriched = enrich_companies_with_short_interest_data(companies, config)

    assert enriched[0]["short_interest"] == 1_500_000
    assert enriched[0]["short_interest_settlement_date"] == "2026-04-30"
    assert enriched[0]["short_percent_shares_outstanding"] == 0.15


def test_live_fetch_uses_finra_symbol_filter_and_parses_json_response(tmp_path):
    class FakeResponse:
        headers = {"Content-Type": "application/json"}
        text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return [
                {
                    "issueSymbolIdentifier": "BRKB",
                    "settlementDate": "2026-04-30",
                    "currentShortShareNumber": 42,
                }
            ]

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json=None, headers=None, timeout=None):
            self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
            return FakeResponse()

    session = FakeSession()
    collector = ShortInterestCollector(raw_dir=str(tmp_path), session=session, limit_per_ticker=3)

    rows = collector.fetch_for_tickers(["brk.b"])

    assert rows[0]["issueSymbolIdentifier"] == "BRKB"
    assert session.calls[0]["json"] == {
        "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "issueSymbolIdentifier", "fieldValue": "BRKB"}
        ],
        "limit": 3,
    }


def test_enrich_companies_reads_local_json_payload(tmp_path):
    raw_dir = tmp_path / "short_interest"
    raw_dir.mkdir()
    (raw_dir / "finra.json").write_text(
        json.dumps(
            {
                "data": [
                    {
                        "symbolCode": "NVDA",
                        "settlementDate": "20260430",
                        "currentShortPositionQuantity": 100,
                        "previousShortPositionQuantity": 80,
                        "averageDailyVolumeQuantity": 50,
                    }
                ]
            }
        )
    )
    config = {
        "short_interest_data": {
            "enabled": True,
            "raw_short_interest_dir": str(raw_dir),
        }
    }

    enriched = enrich_companies_with_short_interest_data([{"ticker": "NVDA"}], config)

    assert enriched[0]["short_interest"] == 100
    assert enriched[0]["short_interest_change_pct"] == 0.25
    assert enriched[0]["short_days_to_cover"] == 2.0
    assert enriched[0]["short_interest_settlement_date"] == "2026-04-30"
