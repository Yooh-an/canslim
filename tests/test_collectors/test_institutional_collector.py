"""Tests for free SEC 13F institutional sponsorship enrichment."""

import json

from src.collectors.institutional_collector import (
    Institutional13FCollector,
    aggregate_institutional_trends,
    apply_institutional_trends,
    build_cusip_ticker_mapping,
    export_cusip_mapping_coverage,
    parse_13f_information_table,
)


INFO_TABLE_XML = """
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>APPLE INC</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>037833100</cusip>
    <value>1000</value>
    <shrsOrPrnAmt><sshPrnamt>5000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>2500</value>
    <shrsOrPrnAmt><sshPrnamt>7000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
  </infoTable>
</informationTable>
"""


def test_parse_13f_information_table_normalizes_values_and_cusips():
    holdings = parse_13f_information_table(
        INFO_TABLE_XML,
        manager_cik="0001067983",
        manager_name="Berkshire Hathaway",
        report_period="2025-12-31",
    )

    assert holdings[0]["cusip"] == "037833100"
    assert holdings[0]["issuer"] == "APPLE INC"
    assert holdings[0]["value_usd"] == 1000
    assert holdings[0]["shares"] == 5000
    assert holdings[0]["manager_cik"] == "0001067983"
    assert holdings[0]["report_period"] == "2025-12-31"


def test_aggregate_institutional_trends_counts_holders_flows_and_qoq_changes():
    current = [
        {"cusip": "037833100", "value_usd": 2_000_000, "shares": 5000, "manager_cik": "1", "manager_name": "Adder"},
        {"cusip": "037833100", "value_usd": 2_000_000, "shares": 8000, "manager_cik": "2", "manager_name": "New Fund"},
        {"cusip": "037833100", "value_usd": 500_000, "shares": 1000, "manager_cik": "3", "manager_name": "Reducer"},
        {"cusip": "594918104", "value_usd": 3_000_000, "shares": 9000, "manager_cik": "1"},
    ]
    previous = [
        {"cusip": "037833100", "value_usd": 1_000_000, "shares": 4000, "manager_cik": "1", "manager_name": "Adder"},
        {"cusip": "037833100", "value_usd": 1_000_000, "shares": 2000, "manager_cik": "3", "manager_name": "Reducer"},
        {"cusip": "037833100", "value_usd": 750_000, "shares": 1500, "manager_cik": "4", "manager_name": "Exited Fund"},
    ]

    trends = aggregate_institutional_trends(current, previous)
    aapl = trends.set_index("cusip").loc["037833100"]
    msft = trends.set_index("cusip").loc["594918104"]

    assert aapl["institutional_holders"] == 3
    assert aapl["institutional_value"] == 4_500_000
    assert aapl["institutional_holders_qoq_change"] == 0
    assert round(aapl["institutional_value_qoq_change"], 4) == 0.6364
    assert aapl["new_holder_count"] == 1
    assert aapl["increased_holder_count"] == 1
    assert aapl["decreased_holder_count"] == 1
    assert aapl["exited_holder_count"] == 1
    assert aapl["institutional_accumulation_score"] > 50
    assert aapl["top_accumulating_managers"][0]["manager_name"] == "New Fund"
    assert msft["institutional_holders_qoq_change"] == 1
    assert msft["institutional_value_qoq_change"] is None


def test_build_cusip_ticker_mapping_uses_name_similarity_and_reports_coverage(tmp_path):
    companies = [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "MSFT", "name": "Microsoft Corporation"},
    ]
    holdings = [
        {"cusip": "037833100", "issuer": "APPLE INC"},
        {"cusip": "594918104", "issuer": "MICROSOFT CORP"},
        {"cusip": "000000000", "issuer": "UNKNOWN HOLDING"},
    ]

    mapping, coverage = build_cusip_ticker_mapping(companies, holdings, min_score=0.5)
    output_file = tmp_path / "coverage.csv"
    export_cusip_mapping_coverage(coverage, str(output_file))

    assert mapping == {"037833100": "AAPL", "594918104": "MSFT"}
    assert coverage["mapped_count"] == 2
    assert coverage["unmapped_count"] == 1
    assert output_file.exists()


def test_apply_institutional_trends_uses_cusip_mapping_and_name_fallback():
    companies = [
        {"ticker": "AAPL", "name": "Apple Inc."},
        {"ticker": "MSFT", "name": "Microsoft Corporation"},
    ]
    current = [
        {"cusip": "037833100", "issuer": "APPLE INC", "value_usd": 1_000_000, "shares": 5000, "manager_cik": "1"},
        {"cusip": "594918104", "issuer": "MICROSOFT CORP", "value_usd": 2_000_000, "shares": 7000, "manager_cik": "1"},
    ]
    trends = aggregate_institutional_trends(current, [])
    mapping = {"037833100": "AAPL"}

    enriched = apply_institutional_trends(companies, trends, mapping)
    by_ticker = {company["ticker"]: company for company in enriched}

    assert by_ticker["AAPL"]["institutional_holders"] == 1
    assert by_ticker["AAPL"]["institutional_data_source"] == "sec_13f"
    assert by_ticker["MSFT"]["institutional_holders"] == 1
    assert by_ticker["MSFT"]["institutional_data_source"] == "sec_13f_name_match"


def test_collector_downloads_latest_and_previous_13f_information_tables(tmp_path):
    class FakeResponse:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class FakeSECClient:
        def __init__(self):
            self.urls = []

        def _make_request(self, url):
            self.urls.append(url)
            if "submissions" in url:
                return FakeResponse(
                    {
                        "name": "Test Manager",
                        "filings": {
                            "recent": {
                                "form": ["13F-HR", "13F-HR"],
                                "accessionNumber": ["0001-25-000001", "0001-24-000004"],
                                "filingDate": ["2026-02-14", "2025-11-14"],
                                "reportDate": ["2025-12-31", "2025-09-30"],
                            }
                        },
                    }
                )
            if "index.json" in url:
                return FakeResponse(
                    {
                        "directory": {
                            "item": [
                                {"name": "primary_doc.xml", "type": "XML"},
                                {"name": "infotable.xml", "type": "XML"},
                            ]
                        }
                    }
                )
            return FakeResponse(text=INFO_TABLE_XML)

    collector = Institutional13FCollector(FakeSECClient(), raw_dir=str(tmp_path))
    current, previous = collector.fetch_latest_and_previous_holdings(["1"])

    assert len(current) == 2
    assert len(previous) == 2
    assert current[0]["manager_name"] == "Test Manager"
    assert (tmp_path / "current" / "0000000001_2025-12-31.xml").exists()
    assert (tmp_path / "previous" / "0000000001_2025-09-30.xml").exists()
