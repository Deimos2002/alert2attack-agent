"""One structured log event per outcome a person would look for: a run, a failed run, a review."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from alert2attack.api.app import create_app
from alert2attack.api.factory import ChatFactory

SCENARIO = "otrf_empire_launcher_vbs"


def _events(logs: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [e for e in logs if e["event"] == name]


def test_a_run_and_the_reviews_on_it_are_logged_without_free_text(scripted_factory: ChatFactory) -> None:
    client = TestClient(create_app(chat_factory=scripted_factory))
    with capture_logs() as logs:
        job = client.post("/investigations", json={"scenario_id": SCENARIO, "model": "scripted", "sync": True}).json()
        client.post(f"/investigations/{job['id']}/review",
                    json={"agrees": False, "corrected_verdict": "likely_benign", "note": "my private words"})
        client.post(f"/investigations/{job['id']}/feedback",
                    json={"target": "timeline/0", "decision": "dispute", "reason": "secret reason"})

    (done,) = _events(logs, "investigation.done")
    assert done["model"] and done["duration_ms"] >= 0 and done["llm_calls"] >= 1
    assert {"verification_status", "budget_hit", "verification_errors", "guided"} <= done.keys()
    (review,) = _events(logs, "review.added")
    assert (review["agrees"], review["corrected_verdict"], review["note_len"]) == (False, "likely_benign", 16)
    (feedback,) = _events(logs, "feedback.added")
    assert (feedback["target"], feedback["decision"], feedback["reason_len"]) == ("timeline/0", "dispute", 13)
    assert "private" not in repr(logs) and "secret" not in repr(logs)


def test_a_failed_run_is_logged_with_its_error() -> None:
    def broken(_model: str) -> Any:
        raise RuntimeError("model endpoint down")

    client = TestClient(create_app(chat_factory=broken))
    with capture_logs() as logs:
        resp = client.post("/investigations", json={"scenario_id": SCENARIO, "model": "scripted", "sync": True})

    assert resp.status_code == 400
    (failed,) = _events(logs, "investigation.failed")
    assert (failed["scenario_id"], failed["model"], failed["log_level"]) == (SCENARIO, "scripted", "error")
    assert failed["exc_info"] is True
