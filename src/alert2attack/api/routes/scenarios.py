"""Read-only scenario browsing; see ``alert2attack.api.scenarios`` for the gold boundary."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam

from alert2attack.api.auth import require_operator
from alert2attack.api.scenarios import (
    SCENARIO_ID_PATTERN,
    EventPage,
    ScenarioDetail,
    ScenarioNotFound,
    ScenarioSummary,
    case_store_for,
    detail,
    list_summaries,
)
from alert2attack.domain.events import EventKind

router = APIRouter(prefix="/scenarios", dependencies=[Depends(require_operator)])

ScenarioId = Annotated[str, PathParam(pattern=SCENARIO_ID_PATTERN)]


def _not_found(scenario_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"unknown scenario id={scenario_id!r}")


@router.get("", response_model=list[ScenarioSummary])
def get_scenarios(
    split: Annotated[Literal["dev", "test"] | None, Query()] = None,
    severity: Annotated[Literal["low", "medium", "high", "critical"] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[ScenarioSummary]:
    rows = list_summaries()
    if split is not None:
        rows = [r for r in rows if r.split == split]
    if severity is not None:
        rows = [r for r in rows if r.severity.value == severity]
    if q:
        needle = q.lower()
        rows = [
            r
            for r in rows
            if needle in r.scenario_id.lower() or needle in r.rule_title.lower() or needle in r.host.lower()
        ]
    return rows


@router.get("/{scenario_id}", response_model=ScenarioDetail)
def get_scenario(scenario_id: ScenarioId) -> ScenarioDetail:
    try:
        return detail(scenario_id)
    except ScenarioNotFound as exc:
        raise _not_found(scenario_id) from exc


@router.get("/{scenario_id}/events", response_model=EventPage)
def get_scenario_events(
    scenario_id: ScenarioId,
    pid: Annotated[int | None, Query()] = None,
    kind: Annotated[list[EventKind] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> EventPage:
    try:
        store = case_store_for(scenario_id)
    except ScenarioNotFound as exc:
        raise _not_found(scenario_id) from exc
    try:
        events, next_cursor = store.page_events(
            scenario_id,
            kinds=kind,
            pid=pid,
            contains=q,
            after=cursor,
            limit=limit,
        )
    except ValueError as exc:
        # A malformed cursor is the caller's mistake, not a server fault.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        store.close()
    return EventPage(events=events, next_cursor=next_cursor, limit=limit)
