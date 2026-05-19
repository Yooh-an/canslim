"""Tests for SEC Form 4 insider transaction enrichment."""

from src.collectors.insider_collector import (
    InsiderForm4Collector,
    aggregate_insider_activity,
    apply_insider_activity,
    enrich_companies_with_insider_data,
    parse_form4_ownership_xml,
)


FORM4_XML = """
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0001000001</rptOwnerCik><rptOwnerName>Jane Insider</rptOwnerName></reportingOwnerId>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-10</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>150.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-20</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>50</value></transactionShares>
        <transactionPricePerShare><value>160.00</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_parse_form4_ownership_xml_extracts_buy_and_sell_values():
    rows = parse_form4_ownership_xml(FORM4_XML, filing_date="2026-01-21", accession="0001")

    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["issuer_cik"] == "0000320193"
    assert rows[0]["owner_name"] == "Jane Insider"
    assert rows[0]["transaction_code"] == "P"
    assert rows[0]["transaction_value"] == 15_000
    assert rows[1]["transaction_code"] == "S"
    assert rows[1]["transaction_value"] == -8_000


def test_aggregate_insider_activity_creates_net_buying_signal():
    transactions = parse_form4_ownership_xml(FORM4_XML, filing_date="2026-01-21", accession="0001")

    activity = aggregate_insider_activity(transactions)
    row = activity.set_index("ticker").loc["AAPL"]

    assert row["insider_buy_count_90d"] == 1
    assert row["insider_sell_count_90d"] == 1
    assert row["net_insider_buy_value_90d"] == 7000
    assert row["insider_signal"] == "net_buying"


def test_aggregate_insider_activity_ignores_transactions_older_than_lookback():
    old_and_new = [
        {"ticker": "AAPL", "issuer_cik": "0000320193", "transaction_date": "2025-01-01", "transaction_value": 10_000},
        {"ticker": "AAPL", "issuer_cik": "0000320193", "transaction_date": "2026-01-01", "transaction_value": -2_000},
    ]

    activity = aggregate_insider_activity(old_and_new, as_of="2026-01-15", lookback_days=90)
    row = activity.set_index("ticker").loc["AAPL"]

    assert row["insider_buy_count_90d"] == 0
    assert row["insider_sell_count_90d"] == 1
    assert row["net_insider_buy_value_90d"] == -2000


def test_apply_insider_activity_maps_by_ticker():
    companies = [{"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "MSFT", "name": "Microsoft"}]
    activity = aggregate_insider_activity(parse_form4_ownership_xml(FORM4_XML))

    enriched = apply_insider_activity(companies, activity)
    by_ticker = {company["ticker"]: company for company in enriched}

    assert by_ticker["AAPL"]["insider_buy_count_90d"] == 1
    assert by_ticker["AAPL"]["insider_data_source"] == "sec_form4"
    assert "insider_buy_count_90d" not in by_ticker["MSFT"]


def test_insider_enrichment_enabled_defaults_to_local_only_without_live_fetch(tmp_path):
    (tmp_path / "local.xml").write_text(FORM4_XML)

    class ExplodingSECClient:
        def _make_request(self, url):
            raise AssertionError("live SEC fetch should not run unless fetch_live=true")

    companies = [{"ticker": "AAPL", "cik": "0000320193"}]
    config = {"insider_data": {"enabled": True, "raw_form4_dir": str(tmp_path)}}

    enriched = enrich_companies_with_insider_data(companies, config, sec_client=ExplodingSECClient())

    assert enriched[0]["insider_signal"] == "net_buying"


def test_collector_fetches_recent_form4_transactions(tmp_path):
    class FakeResponse:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class FakeSECClient:
        def _make_request(self, url):
            if "submissions" in url:
                return FakeResponse(
                    {
                        "filings": {
                            "recent": {
                                "form": ["4", "10-Q"],
                                "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                                "filingDate": ["2026-01-21", "2026-01-22"],
                            }
                        }
                    }
                )
            if "index.json" in url:
                return FakeResponse({"directory": {"item": [{"name": "ownership.xml", "type": "XML", "size": "1000"}]}})
            return FakeResponse(text=FORM4_XML)

    collector = InsiderForm4Collector(FakeSECClient(), raw_dir=str(tmp_path))
    rows = collector.fetch_recent_transactions(["0000320193"])

    assert len(rows) == 2
    assert rows[0]["accession"] == "0000320193-26-000001"
    assert (tmp_path / "0000320193_000032019326000001.xml").exists()
