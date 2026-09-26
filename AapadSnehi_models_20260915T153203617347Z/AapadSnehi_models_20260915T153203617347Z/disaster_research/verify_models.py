"""Check serialized artifacts against saved held-out predictions and adapter responses."""
import json
import time
import joblib
import numpy as np
import pandas as pd
from .paths import ARTIFACTS,REPORTS,RUNS
from .inference import predict

def run():
    result={}
    from .wildfire_classical import persistence_baseline
    result["wildfire_test_persistence"]=persistence_baseline("test")
    held=pd.read_parquet(RUNS/"flood"/"finalist"/"heldout_predictions.parquet")
    for task,name in [("regression","selected_regression.joblib"),("event","selected_event.joblib")]:
        path=ARTIFACTS/"flood"/name;saved=joblib.load(path)
        chosen=held[held.date==held.date.min()].dropna(subset=saved["feature_columns"]).head(32)
        rows=chosen[saved["feature_columns"]]
        issue=(chosen.date.iloc[0]+pd.Timedelta(days=1)).tz_localize("UTC")
        payload={"prediction_time":issue.isoformat(),"latest_input_available_at":issue.isoformat(),"latest_observation_time":(issue-pd.Timedelta(seconds=1)).isoformat(),"units_confirmed":True,"rows":rows.to_dict("records")}
        start=time.perf_counter();a=predict(path,payload);latency=time.perf_counter()-start
        assert a["status"]=="prediction",a
        if task=="regression":equal=np.allclose(a["discharge_m3_s"],chosen.reg_prediction)
        else:equal=np.allclose(a["probability"],chosen.event_probability)
        assert equal
        payload["rows"][0].pop("discharge");bad=predict(path,payload);assert bad["status"]=="insufficient_data"
        result[task]={"saved_heldout_prediction_equal":bool(equal),"missing_required_input_rejected":True,"batch_rows":len(rows),"adapter_load_and_batch_seconds":latency,"artifact_bytes":path.stat().st_size}
    (REPORTS/"model_verification.json").write_text(json.dumps(result,indent=2))

if __name__ == "__main__":run()
