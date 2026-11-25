"""Analyst input on case files: whole-file reviews and per-item decisions (both append-only)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from alert2attack.api.auth import Operator, require_admin_token, require_operator
from alert2attack.api.deps import FeedbackStoreDep, JobStoreDep, ReviewStoreDep
from alert2attack.api.feedback import (
    FeedbackRequest,
    InvalidFeedback,
    ItemFeedback,
    build_feedback,
    export_disagreements,
)
from alert2attack.api.reviews import (
    EvalCaseCandidate,
    Review,
    ReviewRequest,
    build_review,
    export_candidates,
)
from alert2attack.api.routes.investigations import get_job_or_404

log = structlog.get_logger("alert2attack.api")
router = APIRouter(dependencies=[Depends(require_operator)])


@router.post("/investigations/{job_id}/review", response_model=Review, status_code=201)
def add_review(
    job_id: str,
    body: ReviewRequest,
    store: JobStoreDep,
    reviews: ReviewStoreDep,
    caller: Annotated[Operator | None, Depends(require_operator)] = None,
) -> Review:
    """Record agreement or disagreement with a case file.

    Never mutates the case file: a review is an observation about what the
    agent said on that run, and the run's record stays as it was.
    """
    job = get_job_or_404(store, job_id)
    if job.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"investigation is {job.status}; there is no case file to review",
        )
    if not body.agrees and body.corrected_verdict is None:
        raise HTTPException(
            status_code=422,
            detail="a disagreement needs a corrected_verdict to be actionable",
        )
    review = build_review(
        job_id=job_id,
        scenario_id=job.scenario_id,
        agent_verdict=str(job.result.get("case_file", {}).get("verdict", "unknown")),
        request=body,
        reviewer=caller.username if caller else "anonymous",
    )
    reviews.add(review)
    # The note is free text: only its length is logged.
    log.info("review.added", investigation_id=job_id, scenario_id=review.scenario_id,
             agent_verdict=review.agent_verdict, agrees=review.agrees,
             corrected_verdict=review.corrected_verdict, reviewer=review.reviewer,
             note_len=len(review.note))
    return review


@router.get("/reviews", response_model=list[Review], dependencies=[Depends(require_admin_token)])
def list_reviews(
    reviews: ReviewStoreDep,
    scenario_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[Review]:
    return reviews.list(scenario_id=scenario_id, limit=limit)


@router.get("/reviews/export", response_model=list[EvalCaseCandidate], dependencies=[Depends(require_admin_token)])
def export_reviews(
    reviews: ReviewStoreDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> list[EvalCaseCandidate]:
    """Candidate eval cases for a human to curate.

    Export rather than a direct write into the dev split: letting the
    agent's own output become its answer key is the contamination the eval
    protocol exists to prevent.
    """
    return export_candidates(reviews.list(limit=limit))


@router.post("/investigations/{job_id}/feedback", response_model=ItemFeedback, status_code=201)
def add_feedback(
    job_id: str,
    body: FeedbackRequest,
    store: JobStoreDep,
    feedback: FeedbackStoreDep,
    caller: Annotated[Operator | None, Depends(require_operator)] = None,
) -> ItemFeedback:
    """Approve or reject one recommended action, or dispute one claim.

    The case file is not changed. The latest decision on an item is the one shown.
    """
    job = get_job_or_404(store, job_id)
    if job.result is None:
        raise HTTPException(
            status_code=409,
            detail=f"investigation is {job.status}; there is no case file to give feedback on",
        )
    try:
        row = build_feedback(
            job_id=job_id,
            scenario_id=job.scenario_id,
            case_file=job.result.get("case_file", {}),
            request=body,
            reviewer=caller.username if caller else "anonymous",
        )
    except InvalidFeedback as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    feedback.add(row)
    log.info("feedback.added", investigation_id=job_id, scenario_id=row.scenario_id, target=row.target,
             decision=row.decision, reviewer=row.reviewer, reason_len=len(row.reason))
    return row


@router.get("/investigations/{job_id}/feedback", response_model=list[ItemFeedback])
def list_feedback(job_id: str, store: JobStoreDep, feedback: FeedbackStoreDep) -> list[ItemFeedback]:
    get_job_or_404(store, job_id)
    return feedback.list(job_id=job_id)


@router.get("/feedback/export", response_model=list[ItemFeedback], dependencies=[Depends(require_admin_token)])
def export_feedback(feedback: FeedbackStoreDep) -> list[ItemFeedback]:
    """Rejected actions and disputed claims, latest decision per item, for a person to curate."""
    return export_disagreements(feedback.list(limit=5000))
