from datetime import date

from src.utils.security_classifier import classify_company, apply_security_classification


def test_classifies_financials_by_sic_and_sector():
    company = {"ticker": "JPM", "name": "JPMorgan Chase", "sic": "6021"}

    classified = classify_company(company)

    assert classified["is_financial"] is True
    assert classified["security_profile"] == "financials"
    assert "sic_financial_range" in classified["classification_reasons"]


def test_classifies_adr_by_depositary_name():
    company = {"ticker": "ASML", "name": "ASML Holding NV American Depositary Shares"}

    classified = classify_company(company)

    assert classified["is_adr"] is True
    assert classified["security_profile"] == "adr_global"
    assert "depositary_receipt_name" in classified["classification_reasons"]


def test_classifies_recent_listing_from_first_price_date():
    company = {"ticker": "NEW", "name": "Newly Listed Inc", "first_price_date": "2026-01-20"}

    classified = classify_company(company, as_of=date(2026, 5, 19), recent_listing_days=730)

    assert classified["is_recent_listing"] is True
    assert classified["listing_age_days"] == 119
    assert classified["security_profile"] == "ipo_spinoff"


def test_apply_security_classification_updates_company_in_place():
    company = {"ticker": "ABC", "name": "ABC Corp", "sic": "7372"}

    result = apply_security_classification(company)

    assert result is company
    assert company["security_profile"] == "standard"
    assert company["is_financial"] is False
