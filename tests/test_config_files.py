"""Tests for static configuration files."""

import json
import re


def test_institutional_managers_seed_list_has_valid_ciks():
    with open("config/institutional_managers.json") as f:
        payload = json.load(f)

    managers = payload["managers"]
    assert len(managers) >= 5
    assert all(re.fullmatch(r"\d{10}", manager["cik"]) for manager in managers)
    assert {"name", "cik", "category"}.issubset(managers[0])
