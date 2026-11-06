"""Fail-closed authentication helpers for the LEYRA control API."""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status


def require_control_access(request: Request, expected_token: str) -> None:
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LEYRA control authentication is not configured.",
        )
    scheme, separator, supplied = request.headers.get("authorization", "").partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied
        or not hmac.compare_digest(supplied, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid LEYRA control token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
