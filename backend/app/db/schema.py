"""SQLite schema (PRD S34 + a durable jobs table).

Plain sqlite3, no ORM — matches the pattern validated in the auto-clipper
audit. Video binaries never go into the DB (PRD S35); only metadata and
filesystem paths do.

`ai_providers.encrypted_api_key` is intentionally unused for the actual
secret: real key material lives in the OS keychain via Tauri's secure
storage (PRD S5/S40) and is passed to the backend per-request, never
persisted here. The column stays nullable for a future opaque reference
id if one becomes useful, not for the key itself.
"""

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_video_path TEXT NOT NULL,
        source_duration REAL,
        source_resolution TEXT,
        status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS clips (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        start_time REAL NOT NULL,
        end_time REAL NOT NULL,
        duration REAL NOT NULL,
        score REAL,
        analysis_json TEXT,
        transcript_json TEXT,
        video_path TEXT,
        subtitle_path TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_kits (
        id TEXT PRIMARY KEY,
        clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
        platform TEXT NOT NULL,
        titles_json TEXT,
        description TEXT,
        hashtags TEXT,
        thumbnail_idea TEXT,
        thumbnail_prompt TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS social_kit_versions (
        id TEXT PRIMARY KEY,
        social_kit_id TEXT NOT NULL REFERENCES social_kits(id) ON DELETE CASCADE,
        version INTEGER NOT NULL,
        content_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_providers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        provider_type TEXT NOT NULL,
        base_url TEXT,
        model TEXT,
        encrypted_api_key TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        progress REAL NOT NULL DEFAULT 0,
        current_step TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        finished_at TEXT
    )
    """,
]
