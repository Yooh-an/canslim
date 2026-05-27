"""Tests for the web background job runner."""

import sys
from pathlib import Path

import pytest

from src.web import job_runner


def test_normalize_mode_maps_next_action_aliases():
    assert job_runner.normalize_mode("institutional_data") == "enrich"
    assert job_runner.normalize_mode("tv_export") == "tv-export"
    assert job_runner.normalize_mode("screen_profiles") == "profile-sweep"


def test_normalize_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        job_runner.normalize_mode("rm -rf")


def test_build_command_uses_safe_argument_list():
    command = job_runner.build_command("screen", "canslim_score_rank")

    assert command[:4] == [sys.executable, "run_screener.py", "--mode", "screen"]
    assert "--config" in command
    assert command[-2:] == ["--profile", "canslim_score_rank"]


def test_build_command_omits_active_profile_for_profile_sweep():
    command = job_runner.build_command("profile-sweep", "canslim_score_rank")

    assert command[:4] == [sys.executable, "run_screener.py", "--mode", "profile-sweep"]
    assert "--config" in command
    assert "--profile" not in command


def test_current_job_is_idle_before_any_run(monkeypatch):
    monkeypatch.setattr(job_runner, "_CURRENT_JOB", None)

    assert job_runner.current_job() == {"status": "idle", "running": False}


def test_cancel_job_marks_running_job_and_terminates_process(tmp_path: Path, monkeypatch):
    class FakeProcess:
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

    job = {
        "id": 3,
        "mode": "screen",
        "profile": "canslim_score_rank",
        "status": "running",
        "running": True,
        "command": "python run_screener.py --mode screen",
        "started_at": "2026-05-26T00:00:00+00:00",
        "finished_at": None,
        "returncode": None,
        "log": [],
    }
    process = FakeProcess()
    monkeypatch.setattr(job_runner, "JOB_HISTORY_PATH", tmp_path / "job_history.json")
    monkeypatch.setattr(job_runner, "_CURRENT_JOB", job)
    monkeypatch.setattr(job_runner, "_CURRENT_PROCESS", process)

    cancelled = job_runner.cancel_job()

    assert process.terminated is True
    assert cancelled["status"] == "cancelling"
    assert cancelled["running"] is True
    assert cancelled["cancel_requested"] is True
    assert cancelled["log"] == ["Cancellation requested."]
    assert job_runner.job_history()["jobs"][0]["status"] == "cancelling"


def test_finish_status_treats_cancel_requested_job_as_cancelled():
    assert job_runner._finish_status({"cancel_requested": True}, -15) == "cancelled"
    assert job_runner._finish_status({}, 0) == "succeeded"
    assert job_runner._finish_status({}, 1) == "failed"


def test_job_history_records_latest_status_by_job_id(tmp_path: Path):
    store_path = tmp_path / "job_history.json"
    job = {
        "id": 7,
        "mode": "screen",
        "profile": "canslim_score_rank",
        "status": "running",
        "running": True,
        "command": "python run_screener.py --mode screen",
        "started_at": "2026-05-26T00:00:00+00:00",
        "finished_at": None,
        "returncode": None,
        "log": [f"line {index}" for index in range(20)],
    }

    job_runner._record_history(job, store_path=store_path)
    job.update(status="succeeded", running=False, finished_at="2026-05-26T00:01:00+00:00", returncode=0)
    job_runner._record_history(job, store_path=store_path)

    history = job_runner.job_history(store_path=store_path)
    assert len(history["jobs"]) == 1
    assert history["jobs"][0]["id"] == 7
    assert history["jobs"][0]["status"] == "succeeded"
    assert history["jobs"][0]["returncode"] == 0
    assert history["jobs"][0]["log_tail"] == [f"line {index}" for index in range(8, 20)]
