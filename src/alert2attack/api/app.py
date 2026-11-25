"""FastAPI application for alert2attack investigations.

This module only wires things together: it builds the stores, puts them on
``app.state`` and mounts one router per resource from ``alert2attack.api.routes``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from alert2attack.api.auth import AuthConfig, auth_config_from_env
from alert2attack.api.factory import ChatFactory, default_chat_factory
from alert2attack.api.feedback import FeedbackStore, InMemoryFeedbackStore, SqliteFeedbackStore
from alert2attack.api.jobs import InMemoryJobStore, JobStore, SqliteJobStore, load_recorded_runs
from alert2attack.api.progress_hub import ProgressHub
from alert2attack.api.reviews import InMemoryReviewStore, ReviewStore, SqliteReviewStore
from alert2attack.api.routes import auth, investigations, reviews, scenarios, search, system
from alert2attack.retrieval.retriever import Retriever

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def cors_origins() -> list[str]:
    """Allowed browser origins, from ``ALERT2ATTACK_CORS_ORIGINS`` (comma-separated).

    Defaults to the Vite dev server on loopback. Never ``*``: these routes will
    carry an Authorization header once auth lands, and a wildcard origin plus
    credentials is the combination browsers refuse anyway.
    """
    raw = os.environ.get("ALERT2ATTACK_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def console_dist() -> Path | None:
    """The built console (``web/dist``) when ``ALERT2ATTACK_WEB_DIST`` points at one.

    Unset by default: the API stays an API, and the console runs from its own dev
    server. The demo image sets it so one container serves both from one origin.
    """
    raw = os.environ.get("ALERT2ATTACK_WEB_DIST")
    if not raw:
        return None
    dist = Path(raw).resolve()
    return dist if (dist / "index.html").is_file() else None


def default_job_store() -> JobStore:
    """Durable when ``ALERT2ATTACK_JOBS_DB`` is set, in-memory otherwise.

    In-memory stays the default so tests and the CLI keep their current
    behaviour and no test run leaves a database file behind. Compose sets the
    env var, because a console case link must survive an API restart.
    """
    db_path = os.environ.get("ALERT2ATTACK_JOBS_DB")
    if not db_path:
        return InMemoryJobStore()
    store = SqliteJobStore(db_path)
    store.fail_stale_running()
    return store


def default_review_store() -> ReviewStore:
    """Durable alongside the jobs DB when one is configured."""
    db_path = os.environ.get("ALERT2ATTACK_JOBS_DB")
    return SqliteReviewStore(db_path) if db_path else InMemoryReviewStore()


def default_feedback_store() -> FeedbackStore:
    db_path = os.environ.get("ALERT2ATTACK_JOBS_DB")
    return SqliteFeedbackStore(db_path) if db_path else InMemoryFeedbackStore()


def create_app(
    *,
    chat_factory: ChatFactory | None = None,
    job_store: JobStore | None = None,
    review_store: ReviewStore | None = None,
    feedback_store: FeedbackStore | None = None,
    auth_config: AuthConfig | None = None,
    retriever: Retriever | None = None,
) -> FastAPI:
    """Build the FastAPI app (injectable for tests)."""
    app = FastAPI(
        title="alert2attack",
        description="Local-first EDR investigation agent API",
        version="0.1.0",
    )
    app.state.job_store = job_store or default_job_store()
    # The demo image ships a few finished live runs so a visitor sees a case file at once.
    recorded = os.environ.get("ALERT2ATTACK_RECORDED_RUNS")
    app.state.public_job_ids = set()
    if recorded:
        load_recorded_runs(app.state.job_store, recorded)
        # The only runs a visitor may list when ADMIN_TOKEN is set.
        app.state.public_job_ids = {run["id"] for run in json.loads(Path(recorded).read_text(encoding="utf-8"))}
    app.state.review_store = review_store or default_review_store()
    app.state.feedback_store = feedback_store or default_feedback_store()
    app.state.progress_hub = ProgressHub()
    app.state.auth_config = auth_config or auth_config_from_env()
    app.state.chat_factory = chat_factory or default_chat_factory
    app.state.chat_factory_injected = chat_factory is not None
    # None until the first search builds it; see alert2attack.api.deps.retriever.
    app.state.retriever = retriever

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
    )

    dist = console_dist()
    if dist is not None:
        # Before the routers, so the console's page wins over the API's text banner at "/".
        app.add_api_route("/", lambda: FileResponse(dist / "index.html"), include_in_schema=False)

    for module in (system, auth, scenarios, investigations, search, reviews):
        app.include_router(module.router)

    if dist is not None:
        # After the routers, so every API path still wins. Anything else is a console
        # asset or a client-side route such as /cases/<id>, which gets the page itself.
        def console(path: str) -> FileResponse:
            target = (dist / path).resolve()
            if target.is_file() and target.is_relative_to(dist):
                return FileResponse(target)
            return FileResponse(dist / "index.html")

        app.add_api_route("/{path:path}", console, include_in_schema=False)
    return app


app = create_app()
