"""Request-scoped access to the services ``create_app`` puts on ``app.state``.

Routers read their collaborators through these dependencies instead of closing
over locals, so each router module stays importable and testable on its own.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from alert2attack.api.auth import AuthConfig
from alert2attack.api.factory import ChatFactory
from alert2attack.api.jobs import JobStore
from alert2attack.api.progress_hub import ProgressHub
from alert2attack.api.reviews import ReviewStore
from alert2attack.retrieval.retriever import Retriever


def job_store(request: Request) -> JobStore:
    store: JobStore = request.app.state.job_store
    return store


def review_store(request: Request) -> ReviewStore:
    store: ReviewStore = request.app.state.review_store
    return store


def progress_hub(request: Request) -> ProgressHub:
    hub: ProgressHub = request.app.state.progress_hub
    return hub


def auth_config(request: Request) -> AuthConfig:
    config: AuthConfig = request.app.state.auth_config
    return config


def chat_factory(request: Request) -> ChatFactory:
    factory: ChatFactory = request.app.state.chat_factory
    return factory


def chat_factory_injected(request: Request) -> bool:
    injected: bool = request.app.state.chat_factory_injected
    return injected


def retriever(request: Request) -> Retriever:
    # Built on first use, not at startup: a dense retriever embeds the whole
    # corpus, and an API that never gets a search should not pay for it.
    state = request.app.state
    if state.retriever is None:
        from alert2attack.retrieval.factory import shared_retriever

        state.retriever = shared_retriever()
    found: Retriever = state.retriever
    return found


JobStoreDep = Annotated[JobStore, Depends(job_store)]
ReviewStoreDep = Annotated[ReviewStore, Depends(review_store)]
ProgressHubDep = Annotated[ProgressHub, Depends(progress_hub)]
AuthConfigDep = Annotated[AuthConfig, Depends(auth_config)]
ChatFactoryDep = Annotated[ChatFactory, Depends(chat_factory)]
ChatFactoryInjectedDep = Annotated[bool, Depends(chat_factory_injected)]
RetrieverDep = Annotated[Retriever, Depends(retriever)]
