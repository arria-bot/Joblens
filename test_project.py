import sqlite3

from database import init_db

def test_init_db_creates_tables(tmp_path):
    # Arrange: prepare a separate database path for this test
    db_path = tmp_path / "test_jobs.db"

    # Act: run the function being tested
    init_db(db_path)

    # Assert: check which tables were created
    with sqlite3.connect(db_path) as db:
        rows = db.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
        """).fetchall()

    table_names = {row[0] for row in rows}

    assert {"jobs", "requirements", "user_skills"} <= table_names
