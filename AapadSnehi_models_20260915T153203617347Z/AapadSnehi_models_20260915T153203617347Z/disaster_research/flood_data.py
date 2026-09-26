from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import INTERIM, PROCESSED, REPORTS, ensure_runtime_dirs

SOURCE = INTERIM / "flood"
FLOW = SOURCE / "streamflow_timeseries" / "streamflow_observed.csv"
SPLITS = {"train": ("1991-01-01", "2008-12-31"),
          "validation": ("2009-01-01", "2013-12-31"),
          "test": ("2014-01-01", "2018-12-31")}
DYNAMIC = ["prcp(mm/day)", "tavg(C)", "rel_hum(%)", "sm_lvl1(kg/m2)",
           "sm_lvl2(kg/m2)", "sm_lvl3(kg/m2)", "sm_lvl4(kg/m2)"]
STATIC_FILES = ["camels_ind_topo.csv", "camels_ind_soil.csv",
                "camels_ind_geol.csv"]


def _dates(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(frame[["year", "month", "day"]])


def audit_and_select(limit: int = 30) -> dict[str, object]:
    ensure_runtime_dirs()
    flow = pd.read_csv(FLOW)
    dates = _dates(flow)
    values = flow.drop(columns=["year", "month", "day"])
    candidates = []
    for column in values.columns:
        q = values[column]
        coverages = {name: float(q[dates.between(start, end)].notna().mean())
                     for name, (start, end) in SPLITS.items()}
        train = q[dates.between(*SPLITS["train"])].dropna()
        if train.empty:
            continue
        threshold = float(train.quantile(0.95))
        events = {name: int((q[dates.between(start, end)] > threshold).sum())
                  for name, (start, end) in SPLITS.items()}
        candidates.append({"catchment_id": str(column).zfill(5), **{f"{k}_coverage": v for k, v in coverages.items()},
                           "train_q95_m3_s": threshold, **{f"{k}_high_flow_days": v for k, v in events.items()},
                           "nonzero_train_days": int((train > 0).sum()), "negative_values": int((q < 0).sum()),
                           "selection_score": min(coverages.values())})
    table = pd.DataFrame(candidates).sort_values(
        ["train_coverage", "catchment_id"], ascending=[False, True])
    qualifies = table[(table[[f"{s}_coverage" for s in SPLITS]].min(axis=1) >= .95) &
                      (table["nonzero_train_days"] >= 365) &
                      (table["train_high_flow_days"] >= 20)].copy()
    selected = qualifies.head(limit).copy()
    PROCESSED.joinpath("flood").mkdir(parents=True, exist_ok=True)
    table.to_csv(REPORTS / "flood_catchment_audit.csv", index=False)
    selected.to_csv(PROCESSED / "flood" / "selected_catchments.csv", index=False)
    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "dataset": "CAMELS-IND 2.2",
        "geographic_unit": "CAMELS-IND catchment-day", "source_rows": int(len(flow)),
        "source_catchments": int(values.shape[1]), "date_min": str(dates.min().date()),
        "date_max": str(dates.max().date()), "overall_missing_fraction": float(values.isna().mean().mean()),
        "negative_observations": int((values < 0).sum().sum()), "zero_observations": int((values == 0).sum().sum()),
        "splits": SPLITS, "exclusion_gap": "No arbitrary gap: validation/test use earlier observations only as causal history; sequence windows are calendar-contiguous and targets are never interpolated",
        "selection": {"criteria": "30 catchments ordered by training coverage then ID; >=95% availability each split, >=365 nonzero training days and >=20 training high-flow days. Later discharge magnitudes/event counts are descriptive only, never selection criteria.",
                      "qualifying_count": int(len(qualifies)), "selected_count": int(len(selected)),
                      "selected_ids": selected["catchment_id"].tolist()},
        "target": {"regression": "next-day observed discharge, m3/s (India-WRIS/CWC)",
                   "classification": "next-day observed discharge > catchment training-only 95th percentile",
                   "missing": "blank/NaN; never filled or used as a target"},
        "timing": {"issue_time": "conceptual end of source dataset day t; local/UTC daily aggregation boundary not independently established", "input_interval": "daily values through source day t",
                   "forecast_horizon": "one dataset day", "target_interval": "source day t+1",
                   "availability": "retrospective: IMD/IMDAA publication timestamps unavailable; same-day operational availability is not established"},
        "provenance": "observed discharge compiled from India-WRIS/CWC; gridded forcings are catchment-area averages",
        "uncertainty": "gauge QC and metadata limitations remain; catchment delineation and coarse/reanalysis forcings add uncertainty",
        "excluded_leakage": {"lstm_pred_streamflow.csv": "model-generated flow excluded entirely",
                             "camels_ind_hydro.csv": "full-record target-derived streamflow signatures excluded",
                             "camels_ind_clim.csv": "full-record forcing summaries excluded to avoid future-period leakage",
                             "camels_ind_anth.csv": "time-varying/future-dated human attributes excluded from primary model"},
        "retained_static": "topography/location, soil and geology numeric attributes, treated as time-invariant retrospective maps; historical publication availability is not established. Land cover excluded because of snapshot-date leakage risk.",
        "intended_use": "retrospective model comparison and methods demonstration; not an official flood or inundation warning",
    }
    (REPORTS / "flood_dataset_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def _static_features(ids: list[str]) -> pd.DataFrame:
    frames = []
    for filename in STATIC_FILES:
        frame = pd.read_csv(SOURCE / "attributes_csv" / filename)
        frame["catchment_id"] = frame["gauge_id"].astype(str).str.zfill(5)
        frame = frame.drop(columns=["gauge_id"])
        numeric = frame.select_dtypes(include="number").columns.tolist()
        frames.append(frame[["catchment_id", *numeric]])
    result = frames[0]
    for frame in frames[1:]:
        result = result.merge(frame, on="catchment_id", how="outer", suffixes=(None, "_duplicate"))
    result = result.loc[:, ~result.columns.str.endswith("_duplicate")]
    return result[result["catchment_id"].isin(ids)]


def build_features() -> Path:
    selection_path = PROCESSED / "flood" / "selected_catchments.csv"
    if not selection_path.exists():
        audit_and_select()
    selected = pd.read_csv(selection_path, dtype={"catchment_id": str})
    ids = selected["catchment_id"].str.zfill(5).tolist()
    thresholds = dict(zip(ids, selected["train_q95_m3_s"]))
    flow_wide = pd.read_csv(FLOW)
    dates = _dates(flow_wide)
    records = []
    for catchment_id in ids:
        forcing = pd.read_csv(SOURCE / "catchment_mean_forcings" / f"{catchment_id}.csv")
        frame = forcing[["year", "month", "day", *DYNAMIC]].copy()
        frame["date"] = _dates(frame)
        if not frame["date"].equals(dates):
            raise ValueError(f"Forcing/flow dates do not align for {catchment_id}")
        source_column = str(int(catchment_id))
        frame["discharge"] = flow_wide[source_column].to_numpy(dtype=np.float32)
        frame["target_discharge"] = frame["discharge"].shift(-1)
        frame["target_high_flow"] = (frame["target_discharge"] > thresholds[catchment_id]).astype(np.int8)
        for lag in (1, 2, 3, 7, 14, 30):
            frame[f"discharge_lag_{lag}"] = frame["discharge"].shift(lag - 1)
        for days in (3, 7, 14, 30):
            frame[f"rain_sum_{days}"] = frame["prcp(mm/day)"].rolling(days, min_periods=days).sum()
        frame["discharge_trend_3"] = frame["discharge"] - frame["discharge"].shift(3)
        frame["discharge_trend_7"] = frame["discharge"] - frame["discharge"].shift(7)
        day = frame["date"].dt.dayofyear
        frame["season_sin"] = np.sin(2 * np.pi * day / 365.25)
        frame["season_cos"] = np.cos(2 * np.pi * day / 365.25)
        frame["catchment_id"] = catchment_id
        frame["split"] = "excluded"
        for name, (start, end) in SPLITS.items():
            frame.loc[(frame["date"] + pd.Timedelta(days=1)).between(start, end), "split"] = name
        records.append(frame[frame["split"] != "excluded"])
    data = pd.concat(records, ignore_index=True)
    data = data.merge(_static_features(ids), on="catchment_id", how="left")
    # Target gaps are never imputed. A 30-day history burn-in is enforced naturally.
    data = data[data["target_discharge"].notna() & data["discharge"].notna() & data["discharge_lag_30"].notna()].copy()
    path = PROCESSED / "flood" / "features.parquet"
    data.to_parquet(path, index=False)
    summary = {"rows": int(len(data)), "columns": data.columns.tolist(),
               "rows_by_split": data.groupby("split").size().astype(int).to_dict(),
               "high_flow_by_split": data.groupby("split")["target_high_flow"].agg(["sum", "mean"]).to_dict(),
               "selected_catchments": ids}
    (REPORTS / "flood_feature_manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return path
