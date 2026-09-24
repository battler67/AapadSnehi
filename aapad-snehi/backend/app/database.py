from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def apply_schema_compatibility_migrations(target_engine: Engine = engine) -> None:
    """Apply small additive migrations needed by existing SQLite MVP databases."""

    if target_engine.dialect.name != "sqlite":
        return
    inspector = inspect(target_engine)
    if inspector.has_table("volunteers"):
        volunteer_columns = {
            column["name"] for column in inspector.get_columns("volunteers")
        }
    else:
        volunteer_columns = set()
    if volunteer_columns and "preferred_places_json" not in volunteer_columns:
        with target_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE volunteers ADD COLUMN preferred_places_json "
                    "TEXT NOT NULL DEFAULT '[]'"
                )
            )

    if not inspector.has_table("citizen_reports"):
        return
    report_columns = {
        column["name"] for column in inspect(target_engine).get_columns("citizen_reports")
    }
    additions = {
        "ai_caption": "TEXT NOT NULL DEFAULT ''",
        "ai_decision": "VARCHAR(30) NOT NULL DEFAULT 'needs_volunteer_review'",
        "ai_reason": "TEXT NOT NULL DEFAULT ''",
        "ai_model": "VARCHAR(180) NOT NULL DEFAULT ''",
        "ai_provider": "VARCHAR(80) NOT NULL DEFAULT ''",
        "ai_prompt_version": "VARCHAR(80) NOT NULL DEFAULT ''",
        "ai_analysis_json": "TEXT NOT NULL DEFAULT '{}'",
        "reviewed_by": "VARCHAR(120) NOT NULL DEFAULT ''",
        "reviewed_at": "DATETIME",
        "cloudinary_public_id": "VARCHAR(255) NOT NULL DEFAULT ''",
        "cloudinary_asset_id": "VARCHAR(255) NOT NULL DEFAULT ''",
        "cloudinary_format": "VARCHAR(20) NOT NULL DEFAULT ''",
        "image_storage_status": "VARCHAR(30) NOT NULL DEFAULT 'local'",
    }
    with target_engine.begin() as connection:
        for column, definition in additions.items():
            if column not in report_columns:
                connection.execute(
                    text(f"ALTER TABLE citizen_reports ADD COLUMN {column} {definition}")
                )
        connection.execute(
            text(
                "UPDATE citizen_reports "
                "SET moderation_status = 'needs_volunteer_review', "
                "ai_decision = 'needs_volunteer_review', "
                "ai_reason = 'Legacy report requires human review' "
                "WHERE moderation_status = 'pending'"
            )
        )
        if inspector.has_table("incidents"):
            connection.execute(
                text(
                    "UPDATE incidents SET is_active = 0 WHERE id IN ("
                    "SELECT incident_id FROM citizen_reports "
                    "WHERE moderation_status = 'needs_volunteer_review'"
                    ")"
                )
            )


def initialize_database() -> None:
    from . import models  # noqa: F401
    from .flood import models as flood_models  # noqa: F401
    from .flood.migration import migrate_coordinates
    from .seed import seed_database

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    migrate_coordinates(engine)
    apply_schema_compatibility_migrations()
    with SessionLocal() as db:
        seed_database(db)
