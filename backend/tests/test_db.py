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
