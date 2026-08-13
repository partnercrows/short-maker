from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.ai_providers.registry import ConnectionTestResult, ProviderConfig, test_connection
from app.api.schemas import AIProvider, AIProviderCreate
from app.core.security import require_local_token
from app.db.connection import get_connection

router = APIRouter(prefix="/ai-providers", tags=["ai_providers"], dependencies=[Depends(require_local_token)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/test-connection", response_model=ConnectionTestResult)
async def test_provider_connection(config: ProviderConfig) -> ConnectionTestResult:
    return await test_connection(config)


@router.post("", response_model=AIProvider)
def save_provider(payload: AIProviderCreate) -> AIProvider:
    """Persists provider metadata only. The API key itself lives in the OS
    keychain via Tauri's secure storage (PRD S5/S40), never here."""
    provider_id = str(uuid.uuid4())
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_providers (id, name, provider_type, base_url, model, encrypted_api_key, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, NULL, 1, ?, ?)
            """,
            (provider_id, payload.name, payload.provider_type, payload.base_url, payload.model, now, now),
        )
        conn.commit()
    return get_provider(provider_id)


@router.get("", response_model=list[AIProvider])
def list_providers() -> list[AIProvider]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM ai_providers ORDER BY created_at DESC").fetchall()
    return [_row_to_provider(row) for row in rows]


@router.get("/{provider_id}", response_model=AIProvider)
def get_provider(provider_id: str) -> AIProvider:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM ai_providers WHERE id = ?", (provider_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _row_to_provider(row)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM ai_providers WHERE id = ?", (provider_id,))
        conn.commit()


def _row_to_provider(row) -> AIProvider:
    return AIProvider(
        id=row["id"],
        name=row["name"],
        provider_type=row["provider_type"],
        base_url=row["base_url"],
        model=row["model"],
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
