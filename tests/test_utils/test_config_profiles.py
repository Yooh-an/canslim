"""Tests for strategy profile configuration overlays."""

from src.utils.config_loader import load_config_file


def test_canslim_watchlist_profile_is_broader_than_pure_profile():
    pure = load_config_file("config/base.json", profile="canslim_pure")
    watchlist = load_config_file("config/base.json", profile="canslim_watchlist")

    assert watchlist["profile_name"] == "canslim_watchlist"
    assert watchlist["data_paths"]["output_file"].endswith("results_canslim_watchlist.csv")
    assert watchlist["institutional_criteria"]["require_institutional_sponsorship"] is False
    assert watchlist["leadership_criteria"]["rs_rating_min"] < pure["leadership_criteria"]["rs_rating_min"]
    assert watchlist["screening_criteria"]["quarterly_eps_growth"] < pure["screening_criteria"]["quarterly_eps_growth"]
