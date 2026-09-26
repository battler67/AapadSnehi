"""Post-selection CPU adapter checks on real held-out inputs; no fitting."""
import json
import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import torch
from .paths import PROCESSED, REPORTS, RUNS
from .flood_dl import DYNAMIC, LSTM, SequenceData
from .wildfire_data import FEATURES, records, normalized_inputs
from .wildfire_dl import UNet
from .inference import predict_sequence, predict_fire_map


def timed(call, repeats=10):
    call()  # Warm-up is excluded from timings.
    values=[]
    for _ in range(repeats):
        start=time.perf_counter();call();values.append(time.perf_counter()-start)
    return {"repeats":repeats,"median_seconds":float(np.median(values)),
            "min_seconds":min(values),"max_seconds":max(values)}


def run():
    torch.set_num_threads(8)
    result={"generated_at":datetime.now(timezone.utc).isoformat(),"device":"cpu",
            "torch_threads":8,"scope":"First eligible held-out sequence and first published test scene; latency is not an edge-device benchmark"}
    final=json.loads((REPORTS/"flood_dl_final_results.json").read_text())
    path=RUNS/"flood"/"screening"/"dl"/final["screen_run"]/"best.pt"
    saved=torch.load(path,map_location="cpu",weights_only=False);config=saved["config"]
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet")
    data=SequenceData(frame,"test",config["sequence_length"],saved["means"],saved["stds"],saved["catchments"])
    x,c,_,_=data[0];gi,end=data.samples[0]
    cid=saved["catchments"][int(c)]
    group=frame[frame.catchment_id==cid].sort_values("date").reset_index(drop=True)
    rows=group.iloc[end-config["sequence_length"]+1:end+1][["date"]+DYNAMIC].copy()
    issue=(rows.date.iloc[-1]+pd.Timedelta(days=1)).tz_localize("UTC")
    rows["date"]=rows.date.dt.strftime("%Y-%m-%d")
    payload={"prediction_time":issue.isoformat(),"latest_input_available_at":issue.isoformat(),
             "latest_observation_time":(issue-pd.Timedelta(seconds=1)).isoformat(),
             "units_confirmed":True,"catchment_id":cid,"history":rows.to_dict("records")}
    model=LSTM(len(DYNAMIC)*2,config["hidden"],len(saved["catchments"]));model.load_state_dict(saved["state_dict"]);model.eval()
    with torch.inference_mode():
        expected=float(torch.expm1(model(x[None],c[None])[0]).clamp_min(0))
        actual=predict_sequence(path,payload);assert actual["status"]=="prediction",actual
        assert np.isclose(actual["discharge_m3_s"],expected,rtol=1e-5)
        result["flood_lstm"]={"checkpoint_reload_adapter_equal":True,"catchment":cid,
                              "one_sequence_forward":timed(lambda:model(x[None],c[None])),
                              "load_preprocess_predict":timed(lambda:predict_sequence(path,payload),3)}
    payload["history"][-1]["prcp(mm/day)"]=None
    assert predict_sequence(path,payload)["status"]=="insufficient_data"
    result["flood_lstm"]["missing_rainfall_rejected"]=True

    final=json.loads((REPORTS/"wildfire_unet_final_results.json").read_text())
    path=RUNS/"wildfire"/"screening"/"dl"/final["screen_run"]/"best.pt"
    saved=torch.load(path,map_location="cpu",weights_only=False)
    record=next(records("test"));x=torch.from_numpy(normalized_inputs(record)[None])
    # TFRecords lack real timestamps; these are explicitly adapter-test timestamps,
    # never claimed as recovered historical publication/occurrence observations.
    payload={"prediction_time":"2020-01-02T00:00:00+00:00",
             "latest_input_available_at":"2020-01-02T00:00:00+00:00",
             "latest_observation_time":"2020-01-01T23:59:59+00:00",
             "units_confirmed":True,"channels":{k:record[k].tolist() for k in FEATURES}}
    model=UNet(saved["config"]["base_channels"]);model.load_state_dict(saved["state_dict"]);model.eval()
    with torch.inference_mode():
        expected=torch.sigmoid(model(x))[0].numpy()
        actual=predict_fire_map(path,payload);assert actual["status"]=="prediction",actual
        assert np.allclose(actual["uncalibrated_probability_map"],expected)
        result["wildfire_unet"]={"checkpoint_reload_adapter_equal":True,"test_scene_index":0,
            "timestamp_note":"Illustrative adapter-test timestamps; not historical evidence",
            "one_map_forward":timed(lambda:model(x)),
            "load_preprocess_predict":timed(lambda:predict_fire_map(path,payload),3)}
    payload["channels"].pop("pr")
    assert predict_fire_map(path,payload)["status"]=="insufficient_data"
    result["wildfire_unet"]["missing_rainfall_rejected"]=True
    result["missing_input_scope"]="Frozen adapters reject absent rainfall; no target changes and no imputed wildfire outage performance claim"
    (REPORTS/"dl_adapter_verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":run()
