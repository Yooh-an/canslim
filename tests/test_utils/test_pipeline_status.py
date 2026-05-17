"""Tests for pipeline status detection and recommendations."""

import json
from pathlib import Path

from src.utils.pipeline_status import collect_pipeline_status


def _config(tmp_path, require_institutional=True):
    return {
        "data_paths": {
            "raw_data_dir": str(tmp_path / "raw"),
            "processed_data_dir": str(tmp_path / "processed"),
            "company_facts_dir": str(tmp_path / "raw" / "company_facts"),
            "output_file": str(tmp_path / "processed" / "results_canslim_pure.csv"),
        },
        "institutional_criteria": {
            "require_institutional_sponsorship": require_institutional,
        },
        "institutional_data": {"enabled": False},
        "profile_name": "canslim_pure",
    }


def test_collect_pipeline_status_recommends_download_when_raw_data_missing(tmp_path):
    status = collect_pipeline_status(_config(tmp_path))

    assert status["download_ready"] is False
    assert status["parse_ready"] is False
    assert status["next_action"] == "download"
    assert any("download" in command for command in status["recommended_commands"])


def test_collect_pipeline_status_detects_missing_institutional_data_for_pure_profile(tmp_path):
    cfg = _config(tmp_path)
    facts_dir = Path(cfg["data_paths"]["company_facts_dir"])
    processed = Path(cfg["data_paths"]["processed_data_dir"])
    facts_dir.mkdir(parents=True)
    processed.mkdir(parents=True)
    (facts_dir / "CIK0000000001.json").write_text("{}")
    (processed / "companies_list.json").write_text(json.dumps([{"ticker": "AAA"}]))
    (processed / "financial_metrics.parquet").write_bytes(b"not-empty")
    (processed / "companies_list_enriched.json").write_text(json.dumps([{"ticker": "AAA", "rs_rating": 90}]))
    (processed / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))

    status = collect_pipeline_status(cfg)

    assert status["download_ready"] is True
    assert status["parse_ready"] is True
    assert status["enrich_ready"] is True
    assert status["institutional_ready"] is False
    assert status["next_action"] == "institutional_data"
    assert "institutional_data.enabled=false" in "\n".join(status["warnings"])


def test_collect_pipeline_status_reports_ready_when_outputs_exist(tmp_path):
    cfg = _config(tmp_path)
    facts_dir = Path(cfg["data_paths"]["company_facts_dir"])
    processed = Path(cfg["data_paths"]["processed_data_dir"])
    facts_dir.mkdir(parents=True)
    processed.mkdir(parents=True)
    (facts_dir / "CIK0000000001.json").write_text("{}")
    (processed / "companies_list.json").write_text(json.dumps([{"ticker": "AAA", "institutional_holders": 3}]))
    (processed / "financial_metrics.parquet").write_bytes(b"not-empty")
    (processed / "companies_list_enriched.json").write_text(json.dumps([{"ticker": "AAA", "rs_rating": 90, "institutional_holders": 3}]))
    (processed / "market_direction.json").write_text(json.dumps({"market_direction_status": "confirmed_uptrend"}))
    Path(cfg["data_paths"]["output_file"]).write_text("ticker\nAAA\n")
    Path(cfg["data_paths"]["output_file"]).with_suffix(".md").write_text("# report\n")

    status = collect_pipeline_status(cfg)

    assert status["screen_ready"] is True
    assert status["institutional_ready"] is True
    assert status["next_action"] == "none"
