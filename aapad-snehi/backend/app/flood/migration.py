"""Idempotent SQLite migration: unknown coordinates are NULL, never invented points."""
import re
import sqlite3
from pathlib import Path
from sqlalchemy import inspect, text


def migrate_coordinates(engine):
    if engine.dialect.name != "sqlite":
        return
    columns = inspect(engine).get_columns("incidents")
    if all(c["nullable"] for c in columns if c["name"] in {"latitude", "longitude"}):
        return
    database = engine.url.database
    if database and database != ":memory:":
        backup = Path(database).with_suffix(".before-flood.sqlite")
        if not backup.exists():
            with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
                source.backup(target)
    # SQLite has no ALTER COLUMN. Rebuild only this table and restore its indexes;
    # dependent foreign keys retain their original table name throughout.
    with engine.begin() as conn:
        sql = conn.scalar(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='incidents'"))
        indexes = conn.scalars(text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='incidents' AND sql IS NOT NULL")).all()
        sql = re.sub(r"CREATE TABLE incidents", "CREATE TABLE incidents_flood_migration", sql, count=1)
        sql = re.sub(r"(latitude|longitude)( FLOAT) NOT NULL", r"\1\2", sql)
        conn.execute(text(sql))
        names = ", ".join('"' + c["name"] + '"' for c in columns)
        conn.execute(text(f"INSERT INTO incidents_flood_migration ({names}) SELECT {names} FROM incidents"))
        conn.execute(text("DROP TABLE incidents"))
        conn.execute(text("ALTER TABLE incidents_flood_migration RENAME TO incidents"))
        for index in indexes:
            conn.execute(text(index))
