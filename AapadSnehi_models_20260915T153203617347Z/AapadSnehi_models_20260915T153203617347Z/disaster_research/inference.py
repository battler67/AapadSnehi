"""Strict research inference for saved, trusted classical artifacts.

Accepts already engineered features in the artifact schema, not raw sensor packets.
No endpoint or public-warning integration is installed.
"""
from datetime import datetime, timedelta
import argparse
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

def _observation_time(payload, issue, available):
    observed = datetime.fromisoformat(payload["latest_observation_time"])
    if observed.tzinfo is None or observed > available or issue-observed > timedelta(days=1):
        raise ValueError("Required daily observations are stale or have inconsistent timestamps")
    return observed

def predict(artifact_path, payload):
    issue = payload.get("prediction_time")
    base = {"prediction_time":issue, "horizon":"one dataset day", "operationally_validated":False}
    try:
        timestamp = datetime.fromisoformat(issue)
        available = datetime.fromisoformat(payload["latest_input_available_at"])
        if timestamp.tzinfo is None or available.tzinfo is None or available > timestamp:
            raise ValueError("Timezone-aware input availability must not be after issue time")
        observed=datetime.fromisoformat(payload["latest_observation_time"])
        if observed.tzinfo is None or observed>available or timestamp-observed>timedelta(days=1):
            raise ValueError("Required daily observations are stale or have inconsistent timestamps")
        if payload.get("units_confirmed") is not True:
            raise ValueError("Confirm the dataset-native feature units before inference")
        saved = joblib.load(artifact_path)
        columns = saved.get("feature_columns", saved.get("features"))
        rows = payload["rows"]
        if not rows or len(rows)>4096:
            raise ValueError("Expected 1 to 4096 engineered feature rows")
        for row in rows:
            missing = [c for c in columns if c not in row or row[c] is None]
            if missing:
                raise ValueError("Missing required features: " + ", ".join(missing))
        frame = pd.DataFrame(rows)[columns]
        numeric = frame.drop(columns=["catchment_id"],errors="ignore").to_numpy(dtype=float)
        if not np.isfinite(numeric).all():
            raise ValueError("Nonfinite required input")
        if "catchment_id" in frame:
            model = saved["model"]
            pipe = model.regressor_ if hasattr(model,"regressor_") else model
            known = set(pipe.named_steps["preprocess"].named_transformers_["catchment"].categories_[0])
            if not set(frame.catchment_id).issubset(known):
                raise ValueError("Unseen catchment; generalisation not validated")
            inputs = frame
        else:
            if payload.get("existing_fire_in_source_scene") is not True:
                raise ValueError("Existing fire context is required; this is not an ignition model")
            inputs = numeric.astype(np.float32)
        base.update(model_version=saved["version"],target_end=(timestamp+timedelta(days=1)).isoformat())
        if hasattr(saved["model"],"predict_proba"):
            p = saved["model"].predict_proba(inputs)[:,1]
            if "calibrator" in saved:
                p = np.clip(p,1e-6,1-1e-6)
                p = saved["calibrator"].predict_proba(np.log(p/(1-p)).reshape(-1,1))[:,1]
            base.update(probability=p.tolist(), exceeds_validation_alert_cutoff=(p>=saved["threshold"]).tolist())
        else:
            base["discharge_m3_s"] = np.maximum(0,saved["model"].predict(inputs)).tolist()
        return {**base,"data_quality_status":"complete_research_inputs","status":"prediction"}
    except (KeyError,ValueError,TypeError,FileNotFoundError) as exc:
        return {**base,"status":"insufficient_data","data_quality_status":"rejected","reason":str(exc)}

def predict_sequence(checkpoint_path, payload):
    """Flood DL adapter: chronological daily rows with dataset-native dynamic units."""
    from .flood_dl import DYNAMIC,LSTM,TCN
    import torch
    base={"prediction_time":payload.get("prediction_time"),"horizon":"one dataset day","operationally_validated":False}
    try:
        issue=datetime.fromisoformat(payload["prediction_time"])
        available=datetime.fromisoformat(payload["latest_input_available_at"])
        if issue.tzinfo is None or available.tzinfo is None or available>issue:
            raise ValueError("Timezone-aware availability must not exceed issue time")
        observed = _observation_time(payload, issue, available)
        if payload.get("units_confirmed") is not True:raise ValueError("Dataset-native units must be confirmed")
        saved=torch.load(checkpoint_path,map_location="cpu",weights_only=False)
        config=saved["config"];rows=pd.DataFrame(payload["history"])
        if len(rows)!=config["sequence_length"]:raise ValueError("History length differs from trained schema")
        dates=pd.to_datetime(rows["date"])
        if dates.iloc[-1].date() != observed.date():raise ValueError("History end differs from latest observation date")
        if dates.iloc[-1].date() >= issue.date():raise ValueError("Complete daily history must end before the issue date")
        if not (dates.diff().dropna()==pd.Timedelta(days=1)).all():raise ValueError("History must be calendar-contiguous")
        if dates.iloc[-1].date()>issue.date():raise ValueError("Future observations are not allowed")
        if (issue.date()-dates.iloc[-1].date()).days>1:raise ValueError("Stale daily history")
        raw=rows[DYNAMIC].to_numpy(np.float32)
        if not np.isfinite(raw).all():raise ValueError("Required daily inputs are missing or nonfinite")
        cid=payload["catchment_id"]
        if cid not in saved["catchments"]:raise ValueError("Unseen catchment")
        x=np.concatenate([(raw-saved["means"])/saved["stds"],np.zeros_like(raw)],axis=1)
        cls=LSTM if config["architecture"]=="lstm" else TCN
        model=cls(len(DYNAMIC)*2,config["hidden"],len(saved["catchments"]));model.load_state_dict(saved["state_dict"]);model.eval()
        with torch.inference_mode():q,p=model(torch.from_numpy(x[None]),torch.tensor([saved["catchments"].index(cid)]))
        return {**base,"status":"prediction","data_quality_status":"complete_research_inputs","model_version":Path(checkpoint_path).parent.name,"discharge_m3_s":float(torch.expm1(q).clamp_min(0)),"uncalibrated_event_score":float(torch.sigmoid(p)),"target_date":str(dates.iloc[-1].date()+timedelta(days=1))}
    except (KeyError,ValueError,TypeError,FileNotFoundError) as exc:
        return {**base,"status":"insufficient_data","data_quality_status":"rejected","reason":str(exc)}

def predict_fire_map(checkpoint_path,payload):
    """Predict one complete 64x64 supplied-style map from a trusted U-Net checkpoint."""
    import torch
    from .wildfire_data import FEATURES,normalized_inputs
    from .wildfire_dl import UNet
    base={"prediction_time":payload.get("prediction_time"),"horizon":"one dataset day","operationally_validated":False}
    try:
        issue=datetime.fromisoformat(payload["prediction_time"]);available=datetime.fromisoformat(payload["latest_input_available_at"])
        if issue.tzinfo is None or available.tzinfo is None or available>issue:raise ValueError("Invalid input availability")
        _observation_time(payload, issue, available)
        if payload.get("units_confirmed") is not True:raise ValueError("Dataset-native units must be confirmed")
        record={name:np.asarray(payload["channels"][name],dtype=np.float32) for name in FEATURES}
        if any(value.shape!=(64,64) or not np.isfinite(value).all() for value in record.values()):raise ValueError("Expected finite 64x64 maps for every channel")
        if not np.isin(record["PrevFireMask"],[-1,0,1]).all():raise ValueError("Invalid current-fire mask")
        if not (record["PrevFireMask"]==1).any():raise ValueError("No known existing fire; ignition prediction is outside this model's scope")
        saved=torch.load(checkpoint_path,map_location="cpu",weights_only=False);model=UNet(saved["config"]["base_channels"]);model.load_state_dict(saved["state_dict"]);model.eval()
        with torch.inference_mode():p=torch.sigmoid(model(torch.from_numpy(normalized_inputs(record)[None])))[0].numpy()
        return {**base,"status":"prediction","data_quality_status":"complete_research_inputs","model_version":Path(checkpoint_path).parent.name,"uncalibrated_probability_map":p.tolist(),"validation_alert_cutoff":saved["threshold"]}
    except (KeyError,ValueError,TypeError,FileNotFoundError) as exc:
        return {**base,"status":"insufficient_data","data_quality_status":"rejected","reason":str(exc)}

if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("artifact",type=Path);parser.add_argument("input",type=Path)
    args=parser.parse_args();print(json.dumps(predict(args.artifact,json.loads(args.input.read_text())),indent=2))
