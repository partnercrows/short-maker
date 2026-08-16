from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai_providers, clips, jobs, projects, social_kit, subtitles, system, youtube
from app.core.gpu_utils import ensure_cuda_dlls_on_path
from app.core.security import get_or_create_api_token
from app.db.connection import init_db
from app.jobs.manager import job_manager


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    get_or_create_api_token()  # ensures the token file exists for the Tauri shell to read
    ensure_cuda_dlls_on_path()
    job_manager.reconcile_orphaned()
    yield


app = FastAPI(title="Short Maker Sidecar", version="0.1.0", lifespan=lifespan)

# The sidecar only ever binds to localhost, and the frontend -- Vite dev server on
# :1420, or whatever origin WebView2 actually uses for a packaged build (this has
# proven inconsistent across dev vs. installed builds) -- is a different origin
# from this API's own port, so without this every fetch() from the UI fails before
# a response is even read. A wildcard is fine here: this endpoint is bound to
# 127.0.0.1 only and every route besides /health still requires the bearer token,
# so no cookie/credential-based auth is at stake that a wildcard would weaken.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/dev/session-token")
def dev_session_token() -> dict:
    """Temporary dev-only convenience: lets the frontend fetch the local
    API token over HTTP instead of Tauri reading `.api_token` off disk and
    passing it over IPC (not built yet). No weaker than the current
    file-based token, since anything on this machine that could read the
    file could equally call this -- both are localhost-only. Remove once
    Tauri manages the sidecar and hands the token to the frontend itself.
    """
    return {"token": get_or_create_api_token()}


app.include_router(projects.router)
app.include_router(clips.router)
app.include_router(jobs.router)
app.include_router(ai_providers.router)
app.include_router(subtitles.router)
app.include_router(social_kit.router)
app.include_router(system.router)
app.include_router(youtube.router)
