"""Technique grounding: search ATT&CK with the evidence this run fetched.

The write step only names a technique whose ``attack-T####`` id is in the ledger,
and until now an id got there only if the model guessed it and called
``lookup_attack_technique``. Every miss on the frozen test was a real attack with
its technique left out. This step proposes ids from the evidence instead of from
the model's memory: build a query from the alert and the events already fetched,
search the technique corpus, and return the top ids for the graph to look up.

Proposals are candidates. The write prompt still decides which ones the telemetry
supports, and the verifier and the post-verify levers still run after it.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from alert2attack.domain.events import Event
from alert2attack.knowledge.base import KnowledgeBase, SigmaRule
from alert2attack.retrieval.bench import scrub_technique_ids
from alert2attack.retrieval.retriever import Mode, Retriever

GROUND_ENV = "ALERT2ATTACK_GROUND_TECHNIQUES"
# k=5 is the cut-off docs/RETRIEVAL_EVAL.md fixed before its first run.
GROUND_K = 5
_QUERY_CHARS = 1500


def grounding_query(rule_title: str, rule: SigmaRule | None, events: Iterable[Event]) -> str:
    """Alert text plus the fetched events' command lines and images, ids scrubbed.

    Sigma tags are left out on purpose: they name the technique outright, which
    would make this a lookup of the rule's own label rather than of the evidence.
    """
    parts: list[str] = [rule_title]
    if rule is not None:
        parts.append(rule.description)
    seen: set[str] = set()
    for event in events:
        for value in (
            event.command_line,
            event.image,
            event.parent_image,
            event.target_image,
            event.target_path,
            event.details,
        ):
            if value and value not in seen:
                seen.add(value)
                parts.append(value)
    return scrub_technique_ids(" ".join(p for p in parts if p))[:_QUERY_CHARS]


def propose_techniques(
    retriever: Retriever, knowledge: KnowledgeBase, query: str, *, k: int = GROUND_K
) -> list[str]:
    """Top-k technique ids for the query, limited to ids the knowledge base can explain."""
    if not query.strip():
        return []
    mode: Mode = "hybrid" if "hybrid" in retriever.modes else "lexical"
    hits = retriever.search(query, mode=mode, k=k, kind="attack_technique")
    ids = [h.doc_id.removeprefix("attack-") for h in hits]
    return [t for t in ids if knowledge.technique(t) is not None]


def retriever_from_env() -> Retriever | None:
    """The shared retriever when ``ALERT2ATTACK_GROUND_TECHNIQUES`` is on, else None.

    Off by default: the frozen OTRF rows were measured without this step.
    """
    if os.environ.get(GROUND_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    from alert2attack.retrieval.factory import shared_retriever

    return shared_retriever()
