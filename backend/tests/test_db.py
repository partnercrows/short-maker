from app.db.connection import get_connection, init_db
from app.db.schema import SCHEMA_STATEMENTS


def test_init_db_creates_all_tables():
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    table_names = {row["name"] for row in rows}
    for table in ("projects", "clips", "social_kits", "social_kit_versions", "ai_providers", "jobs"):
        assert table in table_names


def test_init_db_is_idempotent():
    init_db()
    init_db()  # must not raise on re-run
    assert len(SCHEMA_STATEMENTS) == 6


def test_init_db_migration_adds_subtitle_and_intro_columns():
    init_db()
    init_db()  # migrations must not raise "duplicate column" on re-run
    with get_connection() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(clips)").fetchall()}
    assert "subtitle_json_path" in columns
    assert "intro_json_path" in columns


def test_init_db_is_idempotent_including_the_unique_name_index():
    init_db()
    init_db()  # must not raise on the second run


def test_init_db_survives_a_database_that_already_has_duplicate_project_names():
    """The index exists to prevent duplicates, but a database made before it
    can already contain them -- refusing to start would strand the user with
    an app that won't open."""
    init_db()
    with get_connection() as conn:
        conn.execute("DROP INDEX IF EXISTS idx_projects_name_unique")
        for project_id in ("dup-a", "dup-b"):
            conn.execute(
                "INSERT INTO projects (id, name, source_video_path, status, created_at, updated_at) "
                "VALUES (?, 'same name', 'v.mp4', 'queued', 'now', 'now')",
                (project_id,),
            )
        conn.commit()

    init_db()  # must not raise

    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 2
