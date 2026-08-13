"""Local-only API token auth between the Tauri shell and the FastAPI sidecar.

The sidecar only ever listens on localhost, but the PRD (S40) still asks
that secrets and the local API not be casually reachable by other
processes on the machine, so every request needs this token. Mirrors the
token-secured-local-API pattern validated in the auto-clipper audit,
reimplemented independently here.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


def get_or_create_api_token() -> str:
    settings = get_settings()
    if settings.api_token_path.exists():
        token = settings.api_token_path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    settings.api_token_path.write_text(token, encoding="utf-8")
    return token


async def require_local_token(authorization: str | None = Header(default=None)) -> None:
    expected = get_or_create_api_token()
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing local API token")
