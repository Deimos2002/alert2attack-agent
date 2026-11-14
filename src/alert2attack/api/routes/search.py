"""ATT&CK technique search; see ``alert2attack.retrieval``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from alert2attack.api.auth import require_operator
from alert2attack.api.deps import RetrieverDep
from alert2attack.retrieval.retriever import Hit, Mode, ModeUnavailable

router = APIRouter(dependencies=[Depends(require_operator)])


class SearchResponse(BaseModel):
    query: str
    mode: Mode
    available_modes: list[Mode]
    hits: list[Hit]
    # Enough to tell a real result from a demo one: the vendored fallback corpus
    # is 30 techniques chosen around the answer key and says so here.
    corpus_source: str
    n_techniques: int
    catalog_revision: str | None = None
    embedder: str | None = None


@router.get("/search/techniques", response_model=SearchResponse)
def search_techniques(
    found: RetrieverDep,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    mode: Annotated[Mode | None, Query()] = None,
    k: Annotated[int, Query(ge=1, le=25)] = 10,
) -> SearchResponse:
    """Find ATT&CK techniques by meaning, by shared words, or both.

    Defaults to hybrid when a dense channel is configured and lexical when it
    is not, so a bare checkout still answers.
    """
    chosen: Mode = mode or ("hybrid" if "hybrid" in found.modes else "lexical")
    try:
        hits = found.search(q, mode=chosen, k=k, kind="attack_technique")
    except ModeUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail=f"mode {chosen!r} is not available; available: {found.modes}",
        ) from exc
    return SearchResponse(
        query=q,
        mode=chosen,
        available_modes=found.modes,
        hits=hits,
        corpus_source=found.corpus.source,
        n_techniques=found.corpus.n_techniques,
        catalog_revision=found.corpus.catalog_revision,
        embedder=found.embedder_name,
    )
