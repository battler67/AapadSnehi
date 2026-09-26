"""Frozen-model matched evaluation, basin uncertainty and sensor ablation."""
import json
import time
import joblib
import numpy as np
import pandas as pd
import torch
from torch.utils.data import DataLoader
from .paths import PROCESSED, RUNS, REPORTS, ARTIFACTS
from .flood_classical import _features
from .flood_finalize import _reg_model
from .flood_dl import SequenceData, Config, DYNAMIC, LSTM, TCN
from .metrics import regression_metrics, classification_metrics

def episodes(frame, predicted):
    """Count contiguous within-catchment positive runs; gaps break episodes."""
    g=frame.copy(); g["alert"]=predicted
    counts={"observed_episodes":0,"missed_episodes":0,"alert_episodes":0,"false_alert_episodes":0}
    for _,part in g.groupby("catchment_id"):
        part=part.sort_values("date")
        for col,other,total,bad in [("target_high_flow","alert","observed_episodes","missed_episodes"),("alert","target_high_flow","alert_episodes","false_alert_episodes")]:
            active=part[col].astype(bool)
            starts=(active!=active.shift()) | (part.date.diff().dt.days!=1)
            for _,group in part.groupby(starts.cumsum()):
                if bool(group.iloc[0][col]):
                    counts[total]+=1; counts[bad]+=int(not group[other].astype(bool).any())
    counts["criterion"]="Any same-target-day overlap counts; this measures episode detection, not pre-onset lead time"
    return counts

def run():
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet")
    final=json.loads((REPORTS/"flood_dl_final_results.json").read_text())
    path=RUNS/"flood"/"screening"/"dl"/final["screen_run"]/"best.pt"
    saved=torch.load(path,map_location="cpu",weights_only=False); config=Config(**saved["config"])
    data=SequenceData(frame,"test",config.sequence_length,saved["means"],saved["stds"],saved["catchments"])
    cls=LSTM if config.architecture=="lstm" else TCN
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model=cls(len(DYNAMIC)*2,config.hidden,len(saved["catchments"])).to(device);model.load_state_dict(saved["state_dict"]);model.eval()
    predictions=[];probabilities=[]
    with torch.inference_mode():
        for x,c,_,_ in DataLoader(data,batch_size=1024):
            q,p=model(x.to(device),c.to(device));predictions.extend(torch.expm1(q).clamp_min(0).cpu().numpy());probabilities.extend(torch.sigmoid(p).cpu().numpy())
    keys=[]
    for gi,end in data.samples:
        _,_,_,dates,cid=data.groups[gi];keys.append({"catchment_id":saved["catchments"][cid],"date":pd.Timestamp(dates[end])})
    dl=pd.DataFrame(keys).assign(dl_prediction=predictions,dl_probability=probabilities)
    held=pd.read_parquet(RUNS/"flood"/"finalist"/"heldout_predictions.parquet")
    matched=held.merge(dl,on=["catchment_id","date"],validate="one_to_one")
    matched.to_parquet(RUNS/"flood"/"finalist"/"matched_predictions.parquet",index=False)
    per=[]
    for cid,g in matched.groupby("catchment_id"):
        for name,col in [("xgboost","reg_prediction"),(config.architecture,"dl_prediction"),("persistence","discharge")]:
            per.append({"catchment_id":cid,"model":name,**regression_metrics(g.target_discharge,g[col])})
    per=pd.DataFrame(per);per.to_csv(REPORTS/"flood_matched_per_catchment.csv",index=False)
    family=json.loads((REPORTS/"flood_final_results.json").read_text())["selected_regression_config"].get("family","xgboost")
    result={"matched_rows":len(matched),"catchments":matched.catchment_id.nunique(),"classical_family":family,"legacy_metric_key_note":"xgboost key below denotes selected classical regressor; see classical_family for actual estimator", "models":{},"uncertainty":{}}
    rng=np.random.default_rng(42)
    for name,col in [("xgboost","reg_prediction"),(config.architecture,"dl_prediction"),("persistence","discharge")]:
        result["models"][name]=regression_metrics(matched.target_discharge,matched[col])
        high=matched.target_high_flow==1
        result["models"][name]["high_flow_errors"]=regression_metrics(matched.loc[high,"target_discharge"],matched.loc[high,col])
        values=per.loc[per.model==name,"nse"].dropna().to_numpy()
        bootstrap=np.mean(rng.choice(values,size=(1000,len(values)),replace=True),axis=1)
        result["uncertainty"][name]={"macro_nse":float(values.mean()),"basin_bootstrap_95_interval":np.quantile(bootstrap,[.025,.975]).tolist(),"caveat":"Catchments may be nested or share storms; interval is descriptive, not independent-basin coverage guaranteed"}
    thresholds=pd.read_csv(PROCESSED/"flood"/"selected_catchments.csv",dtype={"catchment_id":str}).set_index("catchment_id").train_q95_m3_s
    for name,col in [("xgboost","reg_prediction"),(config.architecture,"dl_prediction")]:
        q95=matched.catchment_id.map(thresholds).to_numpy()
        # A monotone bounded exceedance score supplies ranking; it is not a probability.
        ratio=matched[col].to_numpy()/np.maximum(q95,1e-8)
        scores=ratio/(1+ratio)
        metrics=classification_metrics(matched.target_high_flow,scores,float(np.nextafter(.5,1.)))
        metrics["brier"]=None;metrics["score_interpretation"]="q forecast / (q forecast + training q95); ranking score, not probability"
        result["models"][name]["regression_exceedance"]=metrics
    event=joblib.load(ARTIFACTS/"flood"/"xgboost_event.joblib")
    result["episodes"]=episodes(held,held.event_probability>=event["threshold"])
    training=frame[frame.split=="train"].copy();training["doy"]=training.date.dt.dayofyear
    seasonal=training.groupby(["catchment_id","doy"]).target_discharge.median()
    local=training.groupby("catchment_id").target_discharge.median()
    seasonal_prediction=np.array([seasonal.get((r.catchment_id,r.date.dayofyear),local[r.catchment_id]) for r in held.itertuples()])
    result["full_test_baselines"]={"persistence":regression_metrics(held.target_discharge,held.discharge),"seasonal_training_median":regression_metrics(held.target_discharge,seasonal_prediction)}
    peaks=[]
    for cid,g in matched.groupby("catchment_id"):
        row=g.loc[g.target_discharge.idxmax()]
        peaks.append({"catchment_id":cid,"target_day":str(row.date+pd.Timedelta(days=1)),"observed_peak":float(row.target_discharge),"classical_error_at_observed_peak":float(row.reg_prediction-row.target_discharge),"dl_error_at_observed_peak":float(row.dl_prediction-row.target_discharge)})
    pd.DataFrame(peaks).to_csv(REPORTS/"flood_peak_errors.csv",index=False)
    # Evaluate frozen rich regressor under declared missing-input conditions.
    rich=joblib.load(ARTIFACTS/"flood"/"xgboost_regression.joblib")["model"]
    xtest,_=_features(held)
    xtest=xtest[rich.feature_names_in_]
    missing={}
    for label,columns in [("weather_outage",[c for c in xtest if c.startswith("rain_sum") or c in DYNAMIC[1:]]),("discharge_outage",[c for c in xtest if c.startswith("discharge")])]:
        corrupted=xtest.copy();corrupted[columns]=np.nan
        missing[label]=regression_metrics(held.target_discharge,np.maximum(0,rich.predict(corrupted)))
    result["frozen_missing_input_stress"]=missing
    # Reduced variables have dataset counterparts but are not field sensor validation.
    columns=[c for c in frame if c.startswith(("discharge","rain_sum","season_")) or c in ["prcp(mm/day)","tavg(C)","rel_hum(%)","sm_lvl1(kg/m2)","catchment_id"]]
    train=frame[frame.split=="train"];test=frame[frame.split=="test"]
    config_reg=json.loads((REPORTS/"flood_final_results.json").read_text())["selected_regression_config"]
    start=time.perf_counter();reduced=_reg_model([c for c in columns if c!="catchment_id"],config_reg,42)
    reduced.fit(train[columns],train.target_discharge)
    result["sensor_compatible_ablation"]={"features":columns,"test":regression_metrics(test.target_discharge,np.maximum(0,reduced.predict(test[columns]))),"training_seconds":time.perf_counter()-start,"limitation":"Discharge requires a rating curve; rainfall is catchment-averaged and soil moisture a layer-integrated reanalysis estimate, not point sensors"}
    joblib.dump({"model":reduced,"feature_columns":columns,"version":"camels-ind-sensor-ablation-v2"},ARTIFACTS/"flood"/"sensor_ablation.joblib")
    (REPORTS/"flood_matched_analysis.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result

if __name__ == "__main__":
    print(json.dumps(run(),indent=2))
