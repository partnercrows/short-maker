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
        subtitle_json_path TEXT,
        intro_json_path TEXT,
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
    # One row per scene of a Recipe Clipper video, in playing order. The
    # recipe video itself is an ordinary `clips` row, so everything already
    # built around clips -- Social Kit, copy-to-folder, storage accounting,
    # cascade delete -- keeps working untouched.
    """
    CREATE TABLE IF NOT EXISTS recipe_scenes (
        id TEXT PRIMARY KEY,
        clip_id TEXT NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        label TEXT NOT NULL,
        title TEXT,
        source_start REAL NOT NULL,
        source_end REAL NOT NULL,
        is_hook INTEGER NOT NULL DEFAULT 0,
        vo_guide TEXT,
        on_screen_text TEXT,
        reason TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        plan_json TEXT,
        face_check_json TEXT,
        alternatives_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]

# `CREATE TABLE IF NOT EXISTS` above is a no-op on a database that already
# has the table -- new columns added to an existing table need an explicit
# migration. Each statement here must be idempotent (safe to re-run against
# a database that already has it applied); `init_db()` swallows the
# "duplicate column" error each one raises the second time it runs.
MIGRATIONS = [
    "ALTER TABLE clips ADD COLUMN subtitle_json_path TEXT",
    "ALTER TABLE clips ADD COLUMN intro_json_path TEXT",
    # Project names are the only handle the user has on a project in History,
    # so two projects sharing one is genuinely ambiguous -- and the way it
    # happened in practice (a second click while the source video was still
    # being copied) left a duplicate that analysis never touched, so its
    # Clips step sat empty while the real clips were on the other one. The
    # API rejects a taken name up front; this index is what settles two
    # requests that raced past that check.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_name_unique ON projects(name COLLATE NOCASE)",
    # Which flow a project belongs to: 'ai_clipper' (hot moments, many clips)
    # or 'recipe' (one condensed cooking video). Existing rows predate Recipe
    # Clipper, so the default is what they have always been.
    "ALTER TABLE projects ADD COLUMN mode TEXT NOT NULL DEFAULT 'ai_clipper'",
    # Recipe-only Social Kit fields (CTA, alternative hooks, thumbnail text)
    # that the shared columns have no place for.
    "ALTER TABLE social_kits ADD COLUMN extra_json TEXT",
]
