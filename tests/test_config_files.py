"""Tests for static configuration files."""

import json
import re


def test_default_profiles_disable_sparse_insider_data():
    with open("config/base.json") as f:
        base = json.load(f)
    with open("config/config.json") as f:
        legacy = json.load(f)

    assert base["insider_data"]["enabled"] is False
    assert legacy["insider_data"]["enabled"] is False


def test_short_interest_live_fetch_is_opt_in():
    with open("config/base.json") as f:
        base = json.load(f)
    with open("config/config.json") as f:
        legacy = json.load(f)

    assert base["short_interest_data"]["enabled"] is True
    assert legacy["short_interest_data"]["enabled"] is True
    assert base["short_interest_data"]["fetch_live"] is False
    assert legacy["short_interest_data"]["fetch_live"] is False


def test_institutional_managers_seed_list_has_valid_ciks():
    with open("config/institutional_managers.json") as f:
        payload = json.load(f)

    managers = payload["managers"]
    assert len(managers) >= 5
    assert all(re.fullmatch(r"\d{10}", manager["cik"]) for manager in managers)
    assert {"name", "cik", "category"}.issubset(managers[0])
