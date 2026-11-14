"""Technique grounding: ids come from a search over fetched evidence, not from the model."""

import json

import pytest

from alert2attack.agent.budget import Budget
from alert2attack.agent.investigator import Investigator
from alert2attack.agent.llm import ChatResponse, ScriptedChat, ToolCallRequest
from alert2attack.agent.technique_grounding import (
    GROUND_ENV,
    GROUND_K,
    grounding_query,
    propose_techniques,
    retriever_from_env,
)
from alert2attack.domain.scenario import Scenario
from alert2attack.knowledge.base import KnowledgeBase
from alert2attack.retrieval.corpus import build_corpus
from alert2attack.retrieval.retriever import Retriever


# Same case file as tests/agent/test_investigator.py; tests/ is not a package, so it is not imported.
def _casefile_json(*, evidence: str = "ev-0004") -> str:
    return json.dumps(
        {
            "verdict": "malicious",
            "confidence": "high",
            "summary": "Encoded PowerShell downloaded a remote script. Isolate the host.",
            "timeline": [
                {
                    "ts": "2024-03-12T10:00:00Z",
                    "text": "Suspicious encoded PowerShell launched.",
                    "evidence": [evidence],
                }
            ],
            "techniques": [{"technique_id": "T1059.001", "evidence": [evidence], "note": "encoded ps"}],
            "scope": {
                "root_process": {"text": "cmd launched powershell", "evidence": [evidence]},
                "involved_pids": [],
                "persistence": [],
                "beyond_process": False,
            },
            "next_actions": [
                {
                    "action": "isolate_host",
                    "rationale": {"text": "active download", "evidence": [evidence]},
                }
            ],
            "open_questions": [],
        }
    )


def _run(scenario: Scenario, retriever: Retriever | None):
    # The scripted model never calls lookup_attack_technique.
    chat = ScriptedChat(
        [
            ChatResponse(content="1. Confirm alert\n2. Expand process tree\n3. Write case file"),
            ChatResponse(
                tool_calls=(
                    ToolCallRequest(id="call_1", name="get_process_tree", arguments={"pid": 5288, "depth": 2}),
                )
            ),
            ChatResponse(content="Ready to write the case file."),
            ChatResponse(content=_casefile_json()),
            ChatResponse(content=_casefile_json()),
            ChatResponse(content=_casefile_json()),
        ]
    )
    investigator = Investigator(llm=chat, budget=Budget(max_tool_calls=12, max_llm_calls=8), retriever=retriever)
    return investigator.run_scenario(scenario)


def _attack_ids(result) -> set[str]:
    return {e for c in result.trace.tool_calls for e in c.evidence_ids if e.startswith("attack-")}


def test_off_by_default_the_ledger_gets_no_technique(downloader_scenario: Scenario, monkeypatch) -> None:
    monkeypatch.delenv(GROUND_ENV, raising=False)
    assert retriever_from_env() is None
    assert _attack_ids(_run(downloader_scenario, None)) == set()


def test_grounding_puts_evidence_backed_candidates_in_front_of_the_write_step(
    downloader_scenario: Scenario,
) -> None:
    result = _run(downloader_scenario, Retriever(build_corpus()))

    ids = _attack_ids(result)
    assert "attack-T1059.001" in ids  # encoded PowerShell, which the scripted model never looked up
    assert len(ids) <= GROUND_K
    write_prompt = next(c for c in result.trace.llm_calls if c.role == "write").messages[-1]["content"]
    assert "- T1059.001 (evidence attack-T1059.001)" in write_prompt
    assert "ground: ATT&CK techniques matched by search" in write_prompt
    assert result.verification is not None and result.verification.passed


def test_query_uses_fetched_evidence_and_never_an_attack_id(downloader_scenario: Scenario) -> None:
    knowledge = KnowledgeBase.load_default()
    public = downloader_scenario.public()
    rule = knowledge.rule(public.alert.rule_id)
    assert rule is not None and rule.attack_technique_ids  # the tags exist, and are not used

    query = grounding_query(public.alert.rule_title + " T1059.001", rule, public.events)

    assert "T1059" not in query and "attack." not in query
    assert "powershell" in query.lower()


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_proposes_nothing(query: str) -> None:
    assert propose_techniques(Retriever(build_corpus()), KnowledgeBase.load_default(), query) == []
