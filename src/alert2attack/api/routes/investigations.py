"""Investigation jobs: create, poll, stream progress, resolve evidence."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from alert2attack.agent.progress import DoneEvent, ErrorEvent
from alert2attack.api.auth import require_operator
from alert2attack.api.deps import (
    ChatFactoryDep,
    ChatFactoryInjectedDep,
    JobStoreDep,
    ProgressHubDep,
)
from alert2attack.api.evidence import (
    EvidenceNotInLedger,
    EvidenceResolution,
    EvidenceUnresolvable,
    resolve,
)
from alert2attack.api.factory import ChatFactory
from alert2attack.api.jobs import InvestigationJob, JobStore
from alert2attack.api.progress_hub import ProgressHub
from alert2attack.api.service import run_investigation
from alert2attack.api.sse import event_stream, parse_last_event_id

log = structlog.get_logger("alert2attack.api")
router = APIRouter(prefix="/investigations", dependencies=[Depends(require_operator)])


class CreateInvestigationRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    model: Literal["ollama", "local-7b", "openai", "teacher", "replay", "scripted"] = "ollama"
    sync: bool = False
    # A guided re-run: a person's hint, and the run it follows.
    guidance: str | None = Field(default=None, max_length=1000)
    follows_job_id: str | None = None


class InvestigationJobResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    scenario_id: str
    model: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    updated_at: str


def job_response(job: InvestigationJob) -> InvestigationJobResponse:
    return InvestigationJobResponse(
        id=job.id,
        status=job.status,
        scenario_id=job.scenario_id,
        model=job.model,
        result=job.result,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def get_job_or_404(store: JobStore, job_id: str) -> InvestigationJob:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job id={job_id!r}")
    return job


def execute(
    store: JobStore,
    hub: ProgressHub,
    resolve_chat: ChatFactory,
    job_id: str,
    scenario_id: str,
    model: str,
    guidance: str | None = None,
    follows_job_id: str | None = None,
) -> None:
    job = store.get(job_id)
    if job is None:
        return
    progress = hub.get(job_id) or hub.create(job_id)
    job.status = "running"
    store.update(job)
    try:
        # Resolve chat per run so scripted fixtures can reset.
        chat = resolve_chat(model)
        result = run_investigation(
            scenario_id=scenario_id,
            model=model,
            chat_factory=lambda _m: chat,
            investigation_id=job_id,
            progress=progress,
            guidance=guidance,
        )
        if guidance:
            result["analyst_guidance"] = {"text": guidance, "follows_job_id": follows_job_id}
        job = store.get(job_id)
        if job is None:
            return
        job.status = "succeeded"
        job.result = result
        job.error = None
        store.update(job)
        # done carries no case file: the client refetches over REST so there
        # is one authoritative representation of it.
        progress.emit(DoneEvent(job_id=job_id))
    except Exception as exc:  # noqa: BLE001 — surface as job failure
        # Without this line a failed run was visible only in the job store, never in the logs.
        log.exception("investigation.failed", investigation_id=job_id, scenario_id=scenario_id, model=model)
        progress.emit(ErrorEvent(message=str(exc)))
        job = store.get(job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = str(exc)
        store.update(job)
    finally:
        # Wakes any subscriber still waiting, including on a path that
        # emitted neither done nor error.
        progress.close()


LIVE_MODELS = frozenset({"ollama", "local-7b", "openai", "teacher"})
DAILY_LIVE_RUNS_ENV = "ALERT2ATTACK_DAILY_LIVE_RUNS"


def capped_model(model: str, store: JobStore) -> str:
    """Swap a live model for ``replay`` once today's live runs reach the cap.

    A public demo spends real tokens on every run, so the cap is counted here,
    from the job store, where no client can skip it. Unset means no cap. The job
    row records the model that actually ran, so the console can say which it was.
    """
    raw = os.environ.get(DAILY_LIVE_RUNS_ENV, "").strip()
    if not raw or model not in LIVE_MODELS:
        return model
    today = datetime.now(UTC).date().isoformat()
    used = sum(1 for j in store.list(limit=200) if j.model in LIVE_MODELS and j.created_at.startswith(today))
    return model if used < int(raw) else "replay"


def validate_model(model: str, *, chat_factory_injected: bool) -> None:
    # Avoid instantiating chat models here — ScriptedChat is stateful.
    if chat_factory_injected:
        return
    if model == "scripted":
        raise HTTPException(
            status_code=400,
            detail="scripted model requires an injected chat factory for tests",
        )
    if model in {"openai", "teacher"} and not (os.environ.get("EXPLABS_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise HTTPException(
            status_code=400,
            detail="EXPLABS_API_KEY or OPENAI_API_KEY required for openai/teacher model",
        )


@router.post(
    "",
    response_model=InvestigationJobResponse,
    # The async path answers 202, so it has to be declared: the console's
    # types are generated from this document, and a raw JSONResponse never
    # reaches response_model.
    responses={202: {"model": InvestigationJobResponse, "description": "Queued; poll or stream for the result"}},
)
def create_investigation(
    body: CreateInvestigationRequest,
    background_tasks: BackgroundTasks,
    store: JobStoreDep,
    hub: ProgressHubDep,
    resolve_chat: ChatFactoryDep,
    injected: ChatFactoryInjectedDep,
) -> InvestigationJobResponse | JSONResponse:
    validate_model(body.model, chat_factory_injected=injected)
    if body.follows_job_id is not None:
        previous = get_job_or_404(store, body.follows_job_id)
        if previous.scenario_id != body.scenario_id:
            raise HTTPException(status_code=422, detail="follows_job_id is a run of a different case")
    guidance = (body.guidance or "").strip() or None
    model = capped_model(body.model, store)
    job = store.create(scenario_id=body.scenario_id, model=model)
    # Created here, not in execute: the client gets the job id back and
    # opens the stream immediately, which can beat the background task to
    # the first event.
    hub.create(job.id)

    if body.sync:
        execute(store, hub, resolve_chat, job.id, body.scenario_id, model, guidance, body.follows_job_id)
        done = store.get(job.id)
        assert done is not None
        if done.status == "failed":
            raise HTTPException(status_code=400, detail=done.error or "investigation failed")
        return JSONResponse(status_code=200, content=job_response(done).model_dump(mode="json"))

    background_tasks.add_task(
        execute, store, hub, resolve_chat, job.id, body.scenario_id, model, guidance, body.follows_job_id
    )
    return JSONResponse(status_code=202, content=job_response(job).model_dump(mode="json"))


@router.get("/{job_id}", response_model=InvestigationJobResponse)
def get_investigation(job_id: str, store: JobStoreDep) -> InvestigationJobResponse:
    return job_response(get_job_or_404(store, job_id))


@router.get("", response_model=list[InvestigationJobResponse])
def list_investigations(
    store: JobStoreDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[InvestigationJobResponse]:
    return [job_response(j) for j in store.list(limit=limit)]


@router.get("/{job_id}/events")
async def stream_investigation(
    job_id: str,
    request: Request,
    store: JobStoreDep,
    hub: ProgressHubDep,
) -> StreamingResponse:
    """Live progress for one investigation, as server-sent events.

    Carries progress only. The case file is fetched over REST once `done`
    arrives, so there is one authoritative representation of it.
    """
    get_job_or_404(store, job_id)
    progress = hub.get(job_id)
    if progress is None:
        # The job exists but its buffer is gone: an old job, or one evicted
        # from the hub. Nothing to stream; the result is still on REST.
        raise HTTPException(
            status_code=409,
            detail=f"no live progress for job id={job_id!r}; fetch the result instead",
        )

    after_seq = parse_last_event_id(request.headers.get("last-event-id"))
    return StreamingResponse(
        event_stream(progress, after_seq=after_seq, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tells nginx and friends not to buffer, which would defeat the
            # entire point of streaming.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/evidence/{evidence_id}", response_model=EvidenceResolution)
def get_evidence(job_id: str, evidence_id: str, store: JobStoreDep) -> EvidenceResolution:
    """Resolve one citation from a finished run back to what the agent fetched."""
    job = get_job_or_404(store, job_id)
    if job.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"investigation is {job.status}; evidence is available once it succeeds",
        )
    try:
        return resolve(
            evidence_id=evidence_id,
            scenario_id=job.scenario_id,
            trace=job.result.get("trace", {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EvidenceNotInLedger as exc:
        # The verifier should have stripped this claim. A visible 404 here is a
        # bug indicator, and the console is the right place to notice it.
        raise HTTPException(
            status_code=404,
            detail=f"evidence_id={evidence_id!r} was never fetched in this run",
        ) from exc
    except EvidenceUnresolvable as exc:
        raise HTTPException(
            status_code=404,
            detail=f"evidence_id={evidence_id!r} is in the ledger but no longer resolvable",
        ) from exc
