from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Incident, Source, Volunteer
from .priority import compute_priority



SOURCE_SEEDS = [
    {
        "slug": "demo-seed",
        "name": "AapadSnehi verified demo stream",
        "adapter_type": "seed",
        "authority": "Demonstration data only",
        "source_kind": "demo",
        "status": "healthy",
        "enabled": True,
    },
    {
        "slug": "usgs-earthquakes",
        "name": "USGS Earthquake GeoJSON",
        "adapter_type": "usgs",
        "endpoint": "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson",
        "authority": "U.S. Geological Survey",
        "source_kind": "official",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "nasa-eonet",
        "name": "NASA EONET v3",
        "adapter_type": "eonet",
        "endpoint": "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=30&limit=50",
        "authority": "NASA Earth Observatory",
        "source_kind": "official",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "reliefweb-latest",
        "name": "ReliefWeb latest reports",
        "adapter_type": "reliefweb",
        "endpoint": "https://api.reliefweb.int/v2/reports",
        "authority": "UN OCHA ReliefWeb",
        "source_kind": "news",
        "status": "needs_config",
        "enabled": True,
    },
    {
        "slug": "gdelt-disaster-search",
        "name": "GDELT disaster web search",
        "adapter_type": "gdelt",
        "endpoint": "https://api.gdeltproject.org/api/v2/doc/doc",
        "authority": "GDELT Project",
        "source_kind": "search",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "imd-cap",
        "name": "IMD Common Alerting Protocol",
        "adapter_type": "government",
        "endpoint": "https://cap-sources.s3.amazonaws.com/in-imd-en/rss.xml",
        "authority": "India Meteorological Department",
        "source_kind": "official",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "serper-india-disasters",
        "name": "Serper India disaster search",
        "adapter_type": "serper",
        "endpoint": "https://google.serper.dev/search",
        "authority": "Google web results via Serper",
        "source_kind": "search",
        "status": "needs_config",
        "enabled": True,
    },
    {
        "slug": "google-news-india-headlines",
        "name": "Google News India headlines",
        "adapter_type": "google_news",
        "endpoint": "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
        "authority": "Google News RSS",
        "source_kind": "news",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "google-news-ai",
        "name": "Google News artificial intelligence",
        "adapter_type": "google_news",
        "endpoint": "https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en",
        "authority": "Google News RSS",
        "source_kind": "news",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "google-news-india-technology",
        "name": "Google News India technology",
        "adapter_type": "google_news",
        "endpoint": "https://news.google.com/rss/search?q=India+technology&hl=en-IN&gl=IN&ceid=IN:en",
        "authority": "Google News RSS",
        "source_kind": "news",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "sachet-india",
        "name": "SACHET India CAP alerts",
        "adapter_type": "sachet",
        "endpoint": "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml",
        "authority": "NDMA SACHET / authorized Indian alerting agencies",
        "source_kind": "official",
        "status": "ready",
        "enabled": True,
    },
    {
        "slug": "bluesky-helper-search",
        "name": "Bluesky disaster helper search",
        "adapter_type": "bluesky",
        "endpoint": "https://bsky.social",
        "authority": "Bluesky helper search",
        "source_kind": "social",
        "status": "needs_config",
        "enabled": True,
    },
]


INCIDENT_SEEDS = [
    ("assam-flood", "Assam flood relief corridor", "River levels have isolated several communities; food and shelter support is required.", "flood", 5, 26.2006, 92.9376, "Nagaon, Assam", 2, 18500, ["food", "shelter", "medical"], "official"),
    ("uttarkashi-slide", "Landslide blocks Uttarkashi access", "Debris has blocked a mountain access road and delayed medical movement.", "landslide", 4, 30.7268, 78.4354, "Uttarkashi, Uttarakhand", 7, 3400, ["rescue", "medical", "transport"], "official"),
    ("odisha-cyclone", "Coastal cyclone shelter readiness", "Coastal wards are moving vulnerable residents toward cyclone shelters.", "cyclone", 4, 19.8135, 85.8312, "Puri, Odisha", 18, 7200, ["shelter", "transport", "food"], "official"),
    ("mumbai-heat", "Urban heat support points", "Heat response teams need water distribution and first-aid support.", "heatwave", 3, 19.0760, 72.8777, "Mumbai, Maharashtra", 35, 12500, ["water", "medical"], "official"),
    ("kerala-flood", "Urban flooding affects low-lying roads", "Waterlogging is restricting access through several neighbourhood roads.", "flood", 3, 9.9312, 76.2673, "Kochi, Kerala", 82, 2800, ["transport", "food"], "corroborated"),
    ("sikkim-bridge", "Community report: footbridge damage", "A resident photo indicates possible damage to a pedestrian bridge; verification is pending.", "infrastructure", 2, 27.3389, 88.6065, "Gangtok, Sikkim", 216, 140, ["verification", "transport"], "unverified"),
    ("himachal-fire", "Forest fire recovery watch", "A previously active forest-fire zone remains under recovery monitoring.", "wildfire", 2, 31.1048, 77.1734, "Shimla, Himachal Pradesh", 552, 500, ["medical"], "official"),
]


VOLUNTEER_SEEDS = [
    ("Meera Joshi", "+91 90000 11001", "meera.demo@example.org", "Dehradun, Uttarakhand", 30.3165, 78.0322, ["Dehradun, Uttarakhand", "Uttarkashi, Uttarakhand"], ["medical", "shelter"], ["first aid", "triage"], ["hindi", "english"], True, 12),
    ("Arjun Das", "+91 90000 11002", "arjun.demo@example.org", "Guwahati, Assam", 26.1445, 91.7362, ["Guwahati, Assam", "Nagaon, Assam"], ["food", "rescue", "transport"], ["boat rescue", "logistics"], ["assamese", "hindi"], True, 8),
    ("Kavya Nair", "+91 90000 11003", "kavya.demo@example.org", "Kochi, Kerala", 9.9312, 76.2673, ["Kochi, Kerala", "Ernakulam, Kerala"], ["food", "medical", "verification"], ["first aid", "community outreach"], ["malayalam", "english"], False, 3),
    ("Rohan Patnaik", "+91 90000 11004", "rohan.demo@example.org", "Bhubaneswar, Odisha", 20.2961, 85.8245, ["Bhubaneswar, Odisha", "Puri, Odisha"], ["shelter", "transport", "food"], ["logistics", "driving"], ["odia", "hindi"], True, 17),
    ("Neelima Bora", "+91 90000 11005", "neelima.demo@example.org", "Nagaon, Assam", 26.3480, 92.6838, ["Nagaon, Assam", "Guwahati, Assam"], ["food", "shelter", "rescue"], ["community kitchens", "flood relief"], ["assamese", "hindi", "english"], True, 9),
    ("Aman Rawat", "+91 90000 11006", "aman.demo@example.org", "Uttarkashi, Uttarakhand", 30.7268, 78.4354, ["Uttarkashi, Uttarakhand", "Dehradun, Uttarakhand"], ["rescue", "medical", "transport"], ["mountain rescue", "first aid"], ["hindi", "english"], True, 14),
    ("Priya Behera", "+91 90000 11007", "priya.demo@example.org", "Puri, Odisha", 19.8135, 85.8312, ["Puri, Odisha", "Bhubaneswar, Odisha"], ["shelter", "food", "transport"], ["shelter operations", "logistics"], ["odia", "hindi", "english"], True, 11),
    ("Farah Sheikh", "+91 90000 11008", "farah.demo@example.org", "Mumbai, Maharashtra", 19.0760, 72.8777, ["Mumbai, Maharashtra", "Thane, Maharashtra"], ["water", "medical", "food"], ["first aid", "water distribution"], ["marathi", "hindi", "english"], True, 7),
    ("Joseph Thomas", "+91 90000 11009", "joseph.demo@example.org", "Kochi, Kerala", 9.9312, 76.2673, ["Kochi, Kerala", "Ernakulam, Kerala"], ["rescue", "transport", "medical"], ["boat operations", "driving"], ["malayalam", "english"], True, 10),
    ("Tashi Lepcha", "+91 90000 11010", "tashi.demo@example.org", "Gangtok, Sikkim", 27.3389, 88.6065, ["Gangtok, Sikkim", "Mangan, Sikkim"], ["verification", "transport", "rescue"], ["field verification", "mountain driving"], ["nepali", "hindi", "english"], True, 6),
    ("Isha Kapoor", "+91 90000 11011", "isha.demo@example.org", "Shimla, Himachal Pradesh", 31.1048, 77.1734, ["Shimla, Himachal Pradesh", "Solan, Himachal Pradesh"], ["medical", "verification", "shelter"], ["first aid", "damage assessment"], ["hindi", "english"], False, 4),
    ("Rahul Verma", "+91 90000 11012", "rahul.demo@example.org", "Patna, Bihar", 25.5941, 85.1376, ["Patna, Bihar", "Darbhanga, Bihar"], ["food", "water", "transport"], ["warehouse logistics", "driving"], ["hindi", "english"], True, 13),
]


def seed_database(db: Session) -> None:
    migration_changed = False
    sachet_sources = list(
        db.scalars(
            select(Source)
            .where(Source.adapter_type == "sachet")
            .order_by(Source.id)
        ).all()
    )
    national_sachet = next(
        (source for source in sachet_sources if source.slug == "sachet-india"),
        None,
    )
    legacy_sachet = [
        source for source in sachet_sources if source.slug != "sachet-india"
    ]
    if national_sachet is None and legacy_sachet:
        national_sachet = legacy_sachet.pop(0)
        national_sachet.slug = "sachet-india"
        national_sachet.name = "SACHET India CAP alerts"
        national_sachet.endpoint = (
            "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
        )
        national_sachet.authority = "NDMA SACHET / authorized Indian alerting agencies"
        national_sachet.source_kind = "official"
        national_sachet.status = "ready"
        national_sachet.enabled = True
        national_sachet.last_error = ""
        for incident in national_sachet.incidents:
            incident.is_active = False
        migration_changed = True
    for legacy_source in legacy_sachet:
        legacy_source.enabled = False
        legacy_source.status = "superseded"
        legacy_source.last_error = "Superseded by the all-India SACHET RSS source"
        for incident in legacy_source.incidents:
            incident.is_active = False
        migration_changed = True
    if migration_changed:
        db.commit()

    bluesky_source = db.scalar(
        select(Source).where(Source.adapter_type == "bluesky").order_by(Source.id)
    )
    if bluesky_source:
        bluesky_source.slug = "bluesky-helper-search"
        bluesky_source.name = "Bluesky disaster helper search"
        bluesky_source.endpoint = "https://bsky.social"
        bluesky_source.authority = "Bluesky helper search"
        bluesky_source.source_kind = "social"
        if bluesky_source.status == "ready":
            bluesky_source.status = "needs_config"
        db.commit()

    existing_source_slugs = set(db.scalars(select(Source.slug)).all())
    new_sources = [item for item in SOURCE_SEEDS if item["slug"] not in existing_source_slugs]
    if new_sources:
        for item in new_sources:
            db.add(Source(**item))
        db.commit()

    demo_source = db.scalar(select(Source).where(Source.slug == "demo-seed"))
    if demo_source and db.scalar(select(Incident.id).limit(1)) is None:
        now = datetime.now(timezone.utc)
        for external_id, title, description, kind, severity, lat, lon, location, age_hours, affected, needs, verification in INCIDENT_SEEDS:
            occurred_at = now - timedelta(hours=age_hours)
            score, breakdown = compute_priority(
                severity=severity,
                occurred_at=occurred_at,
                affected_estimate=affected,
                needs=needs,
                verification_status=verification,
                now=now,
            )
            db.add(
                Incident(
                    source_id=demo_source.id,
                    external_id=external_id,
                    title=title,
                    description=description,
                    disaster_type=kind,
                    severity=severity,
                    latitude=lat,
                    longitude=lon,
                    location_name=location,
                    occurred_at=occurred_at,
                    source_kind="community" if verification == "unverified" else "official",
                    verification_status=verification,
                    source_url="",
                    affected_estimate=affected,
                    needs_json=json.dumps(needs),
                    priority_score=score,
                    priority_breakdown_json=json.dumps(breakdown),
                )
            )
        db.commit()

    existing_volunteer_phones = set(db.scalars(select(Volunteer.phone)).all())
    missing_volunteers = [
        item for item in VOLUNTEER_SEEDS if item[1] not in existing_volunteer_phones
    ]
    if missing_volunteers:
        for name, phone, email, home, lat, lon, preferred_places, services, skills, languages, verified, missions in missing_volunteers:
            db.add(
                Volunteer(
                    name=name,
                    phone=phone,
                    email=email,
                    home_location=home,
                    latitude=lat,
                    longitude=lon,
                    preferred_places_json=json.dumps(preferred_places),
                    services_json=json.dumps(services),
                    skills_json=json.dumps(skills),
                    languages_json=json.dumps(languages),
                    verified=verified,
                    completed_missions=missions,
                )
            )
        db.commit()

    legacy_preferences_backfilled = False
    for volunteer in db.scalars(select(Volunteer)).all():
        try:
            preferred_places = json.loads(volunteer.preferred_places_json or "[]")
        except json.JSONDecodeError:
            preferred_places = []
        if not isinstance(preferred_places, list) or not any(
            isinstance(place, str) and place.strip() for place in preferred_places
        ):
            volunteer.preferred_places_json = json.dumps([volunteer.home_location])
            legacy_preferences_backfilled = True
    if legacy_preferences_backfilled:
        db.commit()
