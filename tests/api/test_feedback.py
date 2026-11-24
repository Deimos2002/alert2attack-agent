"""A person in the loop: per-item decisions on a case file, and a guided re-run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from alert2attack.agent.llm import ScriptedChat
from alert2attack.api.app import create_app
from alert2attack.api.factory import ChatFactory
from alert2attack.api.feedback import (
    FeedbackRequest,
    FeedbackStore,
    InMemoryFeedbackStore,
    InvalidFeedback,
    SqliteFeedbackStore,
    build_feedback,
    export_disagreements,
)

SCENARIO = "otrf_empire_launcher_vbs"
CASE_FILE: dict[str, Any] = {
    "timeline": [{"ts": "2020-09-04T20:09:55Z", "text": "encoded powershell", "evidence": ["ev-0001"]}],
    "techniques": [{"technique_id": "T1059.001", "evidence": ["attack-T1059.001"], "note": "powershell"}],
    "next_actions": [{"action": "isolate_host", "rationale": {"text": "active C2", "evidence": ["ev-0001"]}}],
}


def _feedback(target: str, decision: str, reason: str = "") -> Any:
    return build_feedback(
        job_id="job-1",
        scenario_id=SCENARIO,
        case_file=CASE_FILE,
        request=FeedbackRequest(target=target, decision=decision, reason=reason),  # type: ignore[arg-type]
        reviewer="analyst",
    )


# -- rules on what a person can say about which item ---------------------------


def test_an_action_is_approved_and_the_item_text_is_kept() -> None:
    row = _feedback("next_actions/0", "approve")
    assert (row.decision, row.item_text) == ("approve", "isolate_host: active C2")


@pytest.mark.parametrize(
    ("target", "decision", "reason", "message"),
    [
        ("timeline/0", "approve", "", "timeline items take dispute"),
        ("next_actions/0", "dispute", "x", "next_actions items take approve or reject"),
        ("techniques/0", "dispute", "  ", "needs a reason"),
        ("next_actions/0", "reject", "", "needs a reason"),
        ("timeline/3", "dispute", "wrong", "does not exist"),
    ],
)
def test_bad_feedback_is_refused(target: str, decision: str, reason: str, message: str) -> None:
    with pytest.raises(InvalidFeedback, match=message):
        _feedback(target, decision, reason)


def test_export_keeps_the_latest_disagreement_per_item() -> None:
    rejected = _feedback("next_actions/0", "reject", "backup host")
    approved_later = _feedback("next_actions/0", "approve")
    approved_later.created_at = "9999"  # a later change of mind
    disputed = _feedback("techniques/0", "dispute", "not PowerShell")
    exported = export_disagreements([rejected, approved_later, disputed])
    assert [r.target for r in exported] == ["techniques/0"]


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> FeedbackStore:
    if request.param == "memory":
        return InMemoryFeedbackStore()
    return SqliteFeedbackStore(tmp_path / "jobs.sqlite")


def test_store_lists_by_job(store: FeedbackStore) -> None:
    row = _feedback("timeline/0", "dispute", "wrong time")
    store.add(row)
    assert [r.id for r in store.list(job_id="job-1")] == [row.id]
    assert store.list(job_id="other") == []


# -- over HTTP ------------------------------------------------------------------


def _run(client: TestClient, **extra: Any) -> dict[str, Any]:
    resp = client.post("/investigations", json={"scenario_id": SCENARIO, "model": "scripted", "sync": True, **extra})
    assert resp.status_code == 200, resp.text
    job: dict[str, Any] = resp.json()
    return job


def test_feedback_is_recorded_without_touching_the_case_file(scripted_factory: ChatFactory) -> None:
    client = TestClient(create_app(chat_factory=scripted_factory))
    job = _run(client)
    before = client.get(f"/investigations/{job['id']}").json()["result"]

    resp = client.post(
        f"/investigations/{job['id']}/feedback",
        json={"target": "next_actions/0", "decision": "reject", "reason": "known admin script"},
    )
    assert resp.status_code == 201, resp.text
    assert client.get(f"/investigations/{job['id']}").json()["result"] == before
    assert [f["decision"] for f in client.get(f"/investigations/{job['id']}/feedback").json()] == ["reject"]
    assert [f["reason"] for f in client.get("/feedback/export").json()] == ["known admin script"]


def test_feedback_on_a_missing_item_is_422(scripted_factory: ChatFactory) -> None:
    client = TestClient(create_app(chat_factory=scripted_factory))
    job = _run(client)
    resp = client.post(
        f"/investigations/{job['id']}/feedback", json={"target": "next_actions/9", "decision": "approve"}
    )
    assert resp.status_code == 422


def test_a_guided_rerun_carries_the_hint_into_the_write_step(scripted_factory: ChatFactory) -> None:
    chats: list[ScriptedChat] = []

    def recording(model: str) -> Any:
        chat = scripted_factory(model)
        chats.append(chat)
        return chat

    client = TestClient(create_app(chat_factory=recording))
    first = _run(client)
    hint = "pid 4242 is the backup agent"
    second = _run(client, guidance=hint, follows_job_id=first["id"])

    assert second["result"]["analyst_guidance"] == {"text": hint, "follows_job_id": first["id"]}
    assert "analyst_guidance" not in first["result"]
    prompts = [m.content or "" for call in chats[-1].calls for m in call]
    assert any(hint in p and "Analyst guidance" in p for p in prompts)
    # The unguided run, which is what evaluation measures, never sees a guidance block.
    assert not any("Analyst guidance" in (m.content or "") for call in chats[0].calls for m in call)


def test_a_rerun_must_follow_a_run_of_the_same_case(scripted_factory: ChatFactory) -> None:
    client = TestClient(create_app(chat_factory=scripted_factory))
    first = _run(client)
    resp = client.post(
        "/investigations",
        json={
            "scenario_id": "otrf_cmd_mshta_vbscript_execute_psh",
            "model": "scripted",
            "sync": True,
            "guidance": "x",
            "follows_job_id": first["id"],
        },
    )
    assert resp.status_code == 422
