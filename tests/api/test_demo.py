"""What a public demo needs from the API: a cap on live runs, and the console served alongside."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alert2attack.api.app import create_app
from alert2attack.api.jobs import InMemoryJobStore, load_recorded_runs
from alert2attack.api.routes.investigations import DAILY_LIVE_RUNS_ENV, capped_model


def test_live_runs_fall_back_to_replay_once_the_daily_cap_is_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryJobStore()
    monkeypatch.setenv(DAILY_LIVE_RUNS_ENV, "2")

    assert capped_model("teacher", store) == "teacher"
    store.create(scenario_id="s", model="teacher")
    store.create(scenario_id="s", model="replay")  # replay runs cost nothing and do not count
    assert capped_model("teacher", store) == "teacher"
    store.create(scenario_id="s", model="ollama")
    assert capped_model("teacher", store) == "replay"
    assert capped_model("replay", store) == "replay"


def test_without_a_cap_the_requested_model_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryJobStore()
    monkeypatch.delenv(DAILY_LIVE_RUNS_ENV, raising=False)
    for _ in range(5):
        store.create(scenario_id="s", model="teacher")
    assert capped_model("teacher", store) == "teacher"


def test_yesterdays_runs_do_not_count(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemoryJobStore()
    monkeypatch.setenv(DAILY_LIVE_RUNS_ENV, "1")
    job = store.create(scenario_id="s", model="teacher")
    job.created_at = "2001-01-01T00:00:00+00:00"
    assert capped_model("teacher", store) == "teacher"


def test_console_is_served_beside_the_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>console</title>", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("outside the console folder", encoding="utf-8")
    monkeypatch.setenv("ALERT2ATTACK_WEB_DIST", str(tmp_path))
    client = TestClient(create_app())

    assert "<title>console</title>" in client.get("/").text
    assert "<title>console</title>" in client.get("/cases/some-case").text  # client-side route
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/health").json() == {"status": "ok"}  # API paths still win
    assert "outside" not in client.get("/%2e%2e/secret.txt").text


def test_without_a_built_console_the_api_keeps_its_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERT2ATTACK_WEB_DIST", raising=False)
    client = TestClient(create_app())
    assert client.get("/").text.startswith("alert2attack api")
    assert client.get("/cases/some-case").status_code == 404


RECORDED = Path(__file__).resolve().parents[2] / "datasets" / "demo" / "recorded_runs.json"


def test_recorded_runs_ship_as_finished_cases_whose_citations_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT2ATTACK_RECORDED_RUNS", str(RECORDED))
    client = TestClient(create_app())

    jobs = client.get("/investigations").json()
    assert jobs and all(j["status"] == "succeeded" for j in jobs)
    for job in jobs:
        case_file = job["result"]["case_file"]
        cited = {e for item in case_file["timeline"] + case_file["techniques"] for e in item["evidence"]}
        cited |= {e for a in case_file["next_actions"] for e in a["rationale"]["evidence"]}
        assert cited, f"{job['scenario_id']} cites nothing"
        for evidence_id in cited:
            assert client.get(f"/investigations/{job['id']}/evidence/{evidence_id}").status_code == 200


def test_a_recorded_run_that_did_not_finish_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "runs.json"
    bad.write_text(
        '[{"id": "x", "scenario_id": "otrf_empire_launcher_vbs", "model": "teacher", "status": "failed"}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not a finished case file"):
        load_recorded_runs(InMemoryJobStore(), bad)
