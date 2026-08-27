from __future__ import annotations

import tempfile
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.database import Base, apply_schema_compatibility_migrations
from app.models import Incident, Source
from app.seed import seed_database


def test_preferred_places_column_is_added_to_legacy_sqlite_database():
    with tempfile.TemporaryDirectory(prefix="aapad_migration_1_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
        try:
            with legacy_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE volunteers ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR(140) NOT NULL, "
                        "home_location VARCHAR(180) NOT NULL"
                        ")"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO volunteers (id, name, home_location) "
                        "VALUES (1, 'Legacy Volunteer', 'Patna, Bihar')"
                    )
                )

            apply_schema_compatibility_migrations(legacy_engine)
            apply_schema_compatibility_migrations(legacy_engine)

            columns = {column["name"] for column in inspect(legacy_engine).get_columns("volunteers")}
            assert "preferred_places_json" in columns
            with legacy_engine.connect() as connection:
                stored = connection.execute(
                    text("SELECT preferred_places_json FROM volunteers WHERE id = 1")
                ).scalar_one()
            assert stored == "[]"
        finally:
            legacy_engine.dispose()


def test_ai_triage_columns_and_safe_review_state_are_added_to_legacy_reports():
    with tempfile.TemporaryDirectory(prefix="aapad_migration_2_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy-reports.db'}", future=True)
        try:
            with legacy_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE incidents ("
                        "id INTEGER PRIMARY KEY, "
                        "is_active BOOLEAN NOT NULL DEFAULT 1"
                        ")"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE citizen_reports ("
                        "id INTEGER PRIMARY KEY, "
                        "incident_id INTEGER NOT NULL, "
                        "moderation_status VARCHAR(30) NOT NULL DEFAULT 'pending'"
                        ")"
                    )
                )
                connection.execute(text("INSERT INTO incidents (id, is_active) VALUES (1, 1)"))
                connection.execute(
                    text(
                        "INSERT INTO citizen_reports (id, incident_id, moderation_status) "
                        "VALUES (1, 1, 'pending')"
                    )
                )

            apply_schema_compatibility_migrations(legacy_engine)
            apply_schema_compatibility_migrations(legacy_engine)

            columns = {
                column["name"] for column in inspect(legacy_engine).get_columns("citizen_reports")
            }
            assert {
                "ai_caption",
                "ai_decision",
                "ai_reason",
                "ai_model",
                "ai_provider",
                "ai_prompt_version",
                "ai_analysis_json",
                "reviewed_by",
                "reviewed_at",
                "cloudinary_public_id",
                "cloudinary_asset_id",
                "cloudinary_format",
                "image_storage_status",
            } <= columns
            with legacy_engine.connect() as connection:
                report = connection.execute(
                    text(
                        "SELECT moderation_status, ai_decision, ai_reason "
                        "FROM citizen_reports WHERE id = 1"
                    )
                ).one()
                active = connection.execute(
                    text("SELECT is_active FROM incidents WHERE id = 1")
                ).scalar_one()
            assert report.moderation_status == "needs_volunteer_review"
            assert report.ai_decision == "needs_volunteer_review"
            assert report.ai_reason == "Legacy report requires human review"
            assert active == 0
        finally:
            legacy_engine.dispose()


def test_legacy_sachet_state_sources_are_migrated_to_one_national_source():
    with tempfile.TemporaryDirectory(prefix="aapad_migration_3_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        migration_engine = create_engine(
            f"sqlite:///{tmp_path / 'sachet-source-migration.db'}",
            future=True,
        )
        try:
            Base.metadata.create_all(migration_engine)
            local_session = sessionmaker(bind=migration_engine, future=True)

            with local_session() as db:
                kerala = Source(
                    slug="sachet-kerala",
                    name="SACHET Kerala CAP alerts",
                    adapter_type="sachet",
                    endpoint="https://sachet.ndma.gov.in/cap_public_website/rss/rss_kerala.xml",
                    source_kind="official",
                )
                assam = Source(
                    slug="sachet-assam",
                    name="SACHET Assam CAP alerts",
                    adapter_type="sachet",
                    endpoint="https://sachet.ndma.gov.in/cap_public_website/rss/rss_assam.xml",
                    source_kind="official",
                )
                db.add_all([kerala, assam])
                db.flush()
                old_kerala_incident = Incident(
                    source_id=kerala.id,
                    external_id="legacy-kerala-alert",
                    title="Legacy Kerala warning",
                    disaster_type="flood",
                    severity=3,
                    latitude=10.8,
                    longitude=76.2,
                    location_name="Kerala, India",
                    occurred_at=datetime.now(timezone.utc),
                    source_kind="official",
                    verification_status="official",
                )
                old_assam_incident = Incident(
                    source_id=assam.id,
                    external_id="legacy-assam-alert",
                    title="Legacy Assam warning",
                    disaster_type="flood",
                    severity=3,
                    latitude=26.2,
                    longitude=92.9,
                    location_name="Assam, India",
                    occurred_at=datetime.now(timezone.utc),
                    source_kind="official",
                    verification_status="official",
                )
                db.add_all([old_kerala_incident, old_assam_incident])
                db.commit()

                seed_database(db)

                sachet_sources = list(
                    db.scalars(
                        select(Source)
                        .where(Source.adapter_type == "sachet")
                        .order_by(Source.id)
                    ).all()
                )
                enabled_sources = [source for source in sachet_sources if source.enabled]
                assert len(enabled_sources) == 1
                assert enabled_sources[0].slug == "sachet-india"
                assert enabled_sources[0].endpoint.endswith("/rss/rss_india.xml")
                assert enabled_sources[0].incidents[0].is_active is False
                superseded = next(source for source in sachet_sources if source.slug == "sachet-assam")
                assert superseded.status == "superseded"
                assert superseded.incidents[0].is_active is False
        finally:
            migration_engine.dispose()
