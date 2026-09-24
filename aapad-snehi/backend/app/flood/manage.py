"""Local migration, identity provisioning and explicit isolated synthetic seed."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import uuid
from datetime import timedelta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["migrate", "seed", "provision", "revoke", "team"])
    parser.add_argument("--database", help="Explicit SQLite development database path")
    parser.add_argument("--credentials", help="Ignored output file for generated credentials; never commit")
    parser.add_argument("--name", default="Local coordinator")
    parser.add_argument("--role", choices=["coordinator", "responder"], default="coordinator")
    parser.add_argument("--scope", default="*")
    parser.add_argument("--team-id")
    parser.add_argument("--identity-id")
    args = parser.parse_args()
    if args.command == "seed" and (not args.database or "demo" not in Path(args.database).stem):
        parser.error("Seed requires an explicit database whose filename contains demo; never seed real reports")
    if args.command in {"seed", "provision"} and not args.credentials:
        parser.error("Provide an ignored --credentials output file")
    if args.credentials and Path(args.credentials).exists():
        parser.error("Credentials output already exists; choose a new file")
    if args.database:
        path = Path(args.database).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["AAPAD_DATABASE_URL"] = "sqlite:///" + path.as_posix()
    from ..database import initialize_database, SessionLocal
    from ..models import utcnow
    from .auth import digest
    from .models import Identity, Team, Operation, RescueTask, Media
    from .schemas import Submission
    from .service import create_report, audit, normalized
    from sqlalchemy import select
    from PIL import Image, ImageDraw
    initialize_database()
    credentials = {}
    with SessionLocal() as db:
        db.info["flood_access"] = True
        if args.command == "team":
            if not args.team_id or db.get(Team, args.team_id):
                parser.error("Provide a new unique --team-id")
            db.add(Team(id=args.team_id, name=args.name, scope=normalized(args.scope)))
            db.commit()
            print("Operational team created")
            return
        if args.command == "revoke":
            identity = db.get(Identity, args.identity_id or "")
            if not identity:
                parser.error("Provide an existing --identity-id")
            identity.enabled = False
            db.commit()
            print("Credential revoked")
            return
        if args.command == "provision":
            if args.role == "responder" and not db.get(Team, args.team_id or ""):
                parser.error("Responder provisioning requires an existing --team-id")
            token = secrets.token_urlsafe(40)
            identity = Identity(id=str(uuid.uuid4()), name=args.name, role=args.role, scope=normalized(args.scope), team_id=args.team_id, token_hash=digest(token))
            db.add(identity)
            credentials = {"identityId": identity.id, "token": token, "role": args.role}
        if args.command == "seed":
            if db.scalar(select(Operation.incident_id).where(Operation.demo.is_(True))):
                parser.error("Synthetic dataset already exists; seed is intentionally non-destructive")
            team = Team(id="synthetic-water-team", name="Synthetic Water Team", scope="demo city")
            db.add(team)
            db.flush()
            for role in ["coordinator", "responder"]:
                token = secrets.token_urlsafe(40)
                identity = Identity(id=str(uuid.uuid4()), name=f"Synthetic {role}", role=role, scope="demo city", team_id=team.id if role == "responder" else None, token_hash=digest(token))
                db.add(identity)
                credentials[role] = token
            reporter = secrets.token_urlsafe(40)
            credentials["reporter"] = reporter
            ids = []
            for index in range(8):
                address = {"state": "Demo State", "city": "Demo City", "locality": "Lotus Quarter", "ward": "Demo Ward 4", "street": "Canal Lane" if index != 2 else "Garden Lane", "door": "12-4/7A" if index in {0, 2} else str(20+index), "landmark": "Fictional Lantern Clock", "directions": "Synthetic access notes; not a usable route"}
                payload = Submission(idempotency_key="synthetic-report-"+str(index), reporter_token=reporter, kind="rescue" if index in {0, 1, 6, 7} else "blocked" if index == 5 else "flood", address=address,
                                     location={"source": "text"} if index == 3 else {"latitude": 17.431 + index*.0003, "longitude": 78.492 + index*.0002, "source": "manual_pin", "confirmed": True, "precision": "building"},
                                     observed_at=utcnow()-timedelta(hours=30 if index == 4 else 1), time_quality="approximate", water_level="knee", access="blocked" if index == 5 else "unknown", people=3 if index in {0, 1, 6, 7} else None, count_quality="estimated" if index in {0, 1, 6, 7} else "unknown", description="SYNTHETIC DEMO ONLY", contact="Fictional contact — no telephone")
                detail, _ = create_report(db, payload, True)
                ids.append({"reportId": detail.report_id, "incidentId": detail.incident_id})
                if index == 0:
                    for photo_index in range(2):
                        output = io.BytesIO()
                        im = Image.new("RGB", (480, 320), (25, 65 + photo_index*20, 90))
                        ImageDraw.Draw(im).text((30, 140), "SYNTHETIC FLOOD PHOTO FIXTURE - NOT REAL", fill="white")
                        im.save(output, format="JPEG")
                        content = output.getvalue()
                        db.add(Media(id=str(uuid.uuid4()), report_id=detail.report_id, sha256=digest(str(photo_index)), original=content, derivative=content))
                    corrected = {"source": "device_gps", "latitude": 17.45, "longitude": 78.50, "confirmed": False, "accuracy": 150}
                    audit(db, detail.incident_id, None, "location_confirmed", {"before": corrected, "after": payload.location.model_dump(), "reason": "Reporter corrected device GPS suggestion"})
                    retry, created = create_report(db, payload, True)
                    assert retry.report_id == detail.report_id and not created
                    conflict = payload.model_copy(update={"idempotency_key": "synthetic-conflicting-update", "kind": "update", "update_incident_id": detail.incident_id, "people": 7})
                    create_report(db, conflict, True)
                if index in {6, 7}:
                    op = db.get(Operation, detail.incident_id)
                    op.canonical_report_id = detail.report_id
                    op.verification = "responder_verified" if index == 7 else "unverified"
                    op.confirmed_people = 3 if index == 7 else None
                    task = db.scalar(select(RescueTask).where(RescueTask.incident_id == detail.incident_id))
                    task.team_id = team.id
                    task.state = "resolved" if index == 7 else "assigned"
                    task.outcome = "Synthetic evacuation complete" if index == 7 else ""
                    task.assisted = 3 if index == 7 else None
                    task.remaining = "none" if index == 7 else ""
                    audit(db, detail.incident_id, identity, "synthetic_task_fixture", {"state": task.state, "floodStatus": "active"})
            credentials["fixtures"] = ids
        db.commit()
    if credentials:
        path = Path(args.credentials)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(credentials, stream, indent=2)
        print("Generated credentials saved to the specified local file. Keep it private and ignored.")
    print("Development schema ready" + ("; isolated synthetic fixture created" if args.command == "seed" else ""))


if __name__ == "__main__":
    main()
