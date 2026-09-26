from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

from .paths import RAW, REPORTS, ensure_runtime_dirs

SERVICE = ("https://services9.arcgis.com/RrvMEynxDB8hycVO/arcgis/rest/services/"
           "nasa_global_landslide_catalog_point/FeatureServer/0/query")
RAIN_TRIGGERS = {"downpour", "rain", "continuous_rain", "monsoon", "tropical_cyclone"}


def acquire_and_audit() -> dict[str, object]:
    ensure_runtime_dirs()
    directory = RAW / "landslide"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "coolr_glc_india.geojson"
    if not target.exists():
        response = requests.get(SERVICE, params={"where": "ctry_code='IN'", "outFields": "*",
            "returnGeometry": "true", "outSR": 4326, "f": "geojson", "resultRecordCount": 2000}, timeout=120)
        response.raise_for_status()
        target.write_bytes(response.content)
    payload = json.loads(target.read_text(encoding="utf-8"))
    rows = []
    for feature in payload["features"]:
        row = dict(feature.get("properties", {}))
        coordinates = feature.get("geometry", {}).get("coordinates", [None, None])
        row["geometry_lon"], row["geometry_lat"] = coordinates[:2]
        rows.append(row)
    frame = pd.DataFrame(rows)
    frame["event_date"] = pd.to_datetime(frame["ev_date"], unit="ms", errors="coerce", utc=True)
    rain = frame[frame["ls_trig"].str.lower().isin(RAIN_TRIGGERS)].copy()
    rain["exact_duplicate"] = rain.duplicated(["event_date", "geometry_lat", "geometry_lon", "src_link"], keep=False)
    # Conservative proxy groups for audit only: named storm, otherwise 0.5-degree cell and 3-day bin.
    epoch_days = (rain["event_date"].dt.floor("D") - pd.Timestamp("1970-01-01", tz="UTC")).dt.days
    fallback_group = (np.floor(rain["geometry_lat"] * 2).astype("Int64").astype(str) + ":" +
                      np.floor(rain["geometry_lon"] * 2).astype("Int64").astype(str) + ":" +
                      (epoch_days // 3).astype("Int64").astype(str))
    named = rain["storm_name"].fillna("").str.strip()
    rain["proxy_storm_group"] = np.where(named.ne(""), "named:" + named.str.lower(), "prox:" + fallback_group)
    years = rain["event_date"].dt.year
    by_year = years.value_counts().sort_index().astype(int).to_dict()
    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Third-party historical ArcGIS mirror of COOLR report-based GLC/LRC inventory, India-only query; current NASA completeness/authenticity not independently verified",
        "source_service": SERVICE, "service_snapshot_note": "public ArcGIS item last data edit 2020-11-27; current NASA gis endpoint returned 404 during audit",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "all_india_reports": int(len(frame)),
        "rain_triggered_reports": int(len(rain)), "date_missing_all": int(frame.event_date.isna().sum()),
        "date_missing_rain": int(rain.event_date.isna().sum()), "date_min": str(rain.event_date.min()),
        "date_max": str(rain.event_date.max()), "rain_reports_by_year": {str(k): v for k, v in by_year.items()},
        "trigger_counts": frame["ls_trig"].fillna("<missing>").value_counts().astype(int).to_dict(),
        "location_accuracy_counts": rain["loc_accu"].fillna("<missing>").value_counts().astype(int).to_dict(),
        "event_time_missing_or_unknown_fraction": float(rain["ev_time"].fillna("").str.strip().str.lower().isin(["", "unknown"]).mean()),
        "named_storm_fraction": float(named.ne("").mean()), "proxy_independent_groups": int(rain.proxy_storm_group.nunique()),
        "exact_duplicate_rows": int(rain.exact_duplicate.sum()), "import_source_counts": rain["ev_imp_src"].fillna("<missing>").value_counts().astype(int).to_dict(),
        "quality_gate": {"next_day_labels": "not yet accepted",
            "reason": "Report dates are mostly day-resolved but reporting/media timing uncertainty, duplicate reports, sparse named-storm IDs, and a stale partial COOLR component require event-level review before treating day labels as occurrence time."},
        "weather_join_status": {"status": "not_attempted_pending_label_gate; credentials absent, not a verified denial for every distribution",
            "IMERG": "Earthdata account normally used for GES DISC granules; no regional download attempted before label gate",
            "ERA5_Land": "Copernicus CDS account, licence acceptance, and ~/.cdsapirc required",
            "SRTM": "NASA Earthdata Login/authorization required for official elevation tiles"},
        "geographic_unit_proposal": "0.1-degree cell-day only for records with location uncertainty <=10 km; exclude coarser/unknown locations. Region and calendar convention not yet accepted.",
        "timing_proposal": {"issue_time": "end of UTC day t", "input_interval": "antecedent observations through t",
                            "forecast_horizon": "day t+1", "target_interval": "UTC day t+1",
                            "availability": "retrospective unless IMERG Early/Late operational latency is replayed; ERA5-Land is delayed reanalysis"},
        "background_warning": "non-event cell-days would be sampled background, not confirmed negatives; COOLR reporting is spatially and temporally biased",
        "training_status": "blocked by unaccepted label provenance/day accuracy and independent storm grouping; no susceptibility substitute trained. Missing hour alone does not invalidate daily labels.",
    }
    (REPORTS / "landslide_dataset_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    rain.drop(columns=[]).to_csv(REPORTS / "landslide_india_rain_event_audit.csv", index=False)
    return audit
