"""Sign-in and identity."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from alert2attack.api.auth import (
    LoginRequest,
    Operator,
    TokenResponse,
    authenticate,
    optional_operator,
)
from alert2attack.api.deps import AuthConfigDep

router = APIRouter()


@router.post("/auth/token", response_model=TokenResponse)
def login(body: LoginRequest, auth: AuthConfigDep) -> TokenResponse:
    if not auth.enabled:
        raise HTTPException(
            status_code=409,
            detail="authentication is not configured; set CONSOLE_PASSWORD_HASH",
        )
    return authenticate(auth, body)


@router.get("/me")
def me(
    auth: AuthConfigDep,
    caller: Annotated[Operator | None, Depends(optional_operator)] = None,
) -> dict[str, Any]:
    """Who the bearer token says you are, and whether auth is on at all.

    Answers anonymous callers on purpose: it is how the console learns
    whether to show a sign-in. It discloses only that auth is enabled.
    """
    if caller is None:
        return {"authenticated": False, "auth_enabled": auth.enabled}
    return {"authenticated": True, "auth_enabled": True, "username": caller.username}
