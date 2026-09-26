"""Export local real-data adapter examples and portable model metadata; no upload."""
import hashlib
import json
import joblib
import numpy as np
import pandas as pd
import torch
from .paths import ROOT, ARTIFACTS, REPORTS, RUNS
from .inference import predict, predict_fire_map
from .wildfire_data import FEATURES, records


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def describe(path):
    with path.open("rb") as stream:
        checksum=hashlib.file_digest(stream,"sha256").hexdigest()
    return {"path_relative_to_disaster_research":path.relative_to(ROOT).as_posix(),
            "bytes":path.stat().st_size,"sha256":checksum}


def main():
    torch.set_num_threads(8)
    output=ARTIFACTS/"handoff";output.mkdir(parents=True,exist_ok=True)
    manifest={"purpose":"Trusted local model handoff; this command does not upload anything",
              "models":{},"examples":{},"example_directory":"artifacts/handoff"}
    held=pd.read_parquet(RUNS/"flood"/"finalist"/"heldout_predictions.parquet")
    for name,filename in [("random_forest","selected_regression.joblib"),("xgboost","selected_event.joblib")]:
        path=ARTIFACTS/"flood"/filename;saved=joblib.load(path)
        columns=saved["feature_columns"]
        # Same deterministic first complete eligible row for each artifact schema.
        chosen=held.sort_values(["date","catchment_id"]).dropna(subset=columns).iloc[[0]]
        issue=(chosen.date.iloc[0]+pd.Timedelta(days=1)).tz_localize("UTC")
        payload={"prediction_time":issue.isoformat(),"latest_input_available_at":issue.isoformat(),
                 "latest_observation_time":(issue-pd.Timedelta(seconds=1)).isoformat(),
                 "units_confirmed":True,"rows":chosen[columns].to_dict("records")}
        result=predict(path,payload);assert result["status"]=="prediction",result
        expected=chosen.reg_prediction.to_numpy() if name=="random_forest" else chosen.event_probability.to_numpy()
        actual=result["discharge_m3_s"] if name=="random_forest" else result["probability"]
        assert np.allclose(actual,expected)
        write(output/f"{name}_input.json",payload);write(output/f"{name}_output.json",result)
        manifest["models"][name]={**describe(path),"version":saved["version"],
            "feature_columns":columns,"feature_count":len(columns),"contains_saved_preprocessing":True}
        if "threshold" in saved:manifest["models"][name]["validation_alert_cutoff"]=float(saved["threshold"])
        manifest["examples"][name]={"rule":"First date/catchment-sorted held-out row with complete required features",
            "catchment_id":str(chosen.catchment_id.iloc[0]),"input_day":str(chosen.date.iloc[0].date()),
            "timestamp_caveat":"Assumed retrospective day-end availability, not verified publication timestamps",
            "matches_saved_heldout_prediction":True}
    final=json.loads((REPORTS/"wildfire_unet_final_results.json").read_text())
    path=RUNS/"wildfire"/"screening"/"dl"/final["screen_run"]/"best.pt"
    saved=torch.load(path,map_location="cpu",weights_only=False)
    record=next(records("test"))
    payload={"prediction_time":"2020-01-02T00:00:00+00:00",
             "latest_input_available_at":"2020-01-02T00:00:00+00:00",
             "latest_observation_time":"2020-01-01T23:59:59+00:00",
             "units_confirmed":True,"channels":{name:record[name].tolist() for name in FEATURES}}
    result=predict_fire_map(path,payload);assert result["status"]=="prediction",result
    with np.load(RUNS/"wildfire"/"replay"/"unet_scene_0.npz") as replay:
        assert np.allclose(result["uncalibrated_probability_map"],replay["probability"],rtol=1e-5,atol=1e-6)
    write(output/"unet_input.json",payload);write(output/"unet_output.json",result)
    manifest["models"]["unet"]={**describe(path),"version":final["screen_run"],
        "config":saved["config"],"input_channels":FEATURES,"shape_per_channel":[64,64],
        "validation_alert_cutoff":float(saved["threshold"]),
        "preprocessing":"wildfire_data.normalized_inputs; constants in STATS, not embedded in checkpoint"}
    manifest["examples"]["unet"]={"rule":"First published test scene (index 0); deliberately not selected for good performance",
        "timestamp_caveat":"Illustrative adapter-test dates only; TFRecords do not supply historical scene dates",
        "observed_target_not_in_request":True,"matches_saved_replay_prediction":True}
    write(output/"example_provenance.json",manifest["examples"])
    write(REPORTS/"model_handoff_manifest.json",manifest)
    print(json.dumps({"example_directory":str(output),"models":{k:{"bytes":v["bytes"],"sha256":v["sha256"]} for k,v in manifest["models"].items()}},indent=2))


if __name__=="__main__":main()
