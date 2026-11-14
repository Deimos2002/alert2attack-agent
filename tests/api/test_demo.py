"""What a public demo needs from the API: a cap on live runs, and the console served alongside."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alert2attack.api.app import create_app
from alert2attack.api.jobs import InMemoryJobStore
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
