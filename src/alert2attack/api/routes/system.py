"""Liveness, Prometheus metrics and the root banner."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from alert2attack.api.metrics import RENDER_PROM

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics")
def metrics() -> Response:
    # Left open deliberately: a Prometheus scraper carries no bearer token,
    # and the published port binds to loopback.
    payload, content_type = RENDER_PROM()
    return Response(content=payload, media_type=content_type)


@router.get("/", response_class=PlainTextResponse)
def root() -> str:
    return "alert2attack api — see /docs"
