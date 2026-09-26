"""Export final comparisons without mixing different held-out populations."""
import json
import joblib
import pandas as pd
import torch
from .paths import REPORTS,RUNS,ARTIFACTS
from .metrics import classification_metrics

def run():
    matched=json.loads((REPORTS/"flood_matched_analysis.json").read_text())
    rows=[]
    for name,metric in matched["models"].items():
        label=matched["classical_family"] if name=="xgboost" else name
        rows.append({"model":label,"evaluation":"matched_test_days","training_scope":"full classical rows" if name=="xgboost" else "eligible sequences" if name=="lstm" else "baseline",**{k:v for k,v in metric.items() if not isinstance(v,dict)}})
    pd.DataFrame(rows).to_csv(REPORTS/"flood_final_regression_leaderboard.csv",index=False)
    frame=pd.read_parquet(RUNS/"flood"/"finalist"/"matched_predictions.parquet")
    classical=joblib.load(ARTIFACTS/"flood"/"selected_event.joblib")
    dl=json.loads((REPORTS/"flood_dl_final_results.json").read_text())
    checkpoint=torch.load(RUNS/"flood"/"screening"/"dl"/dl["screen_run"]/"best.pt",map_location="cpu",weights_only=False)
    rows=[]
    for name,col,threshold,note in [("separate_classical_classifier","event_probability",classical["threshold"],"validation Platt calibration"),("LSTM_event_head","dl_probability",checkpoint["threshold"],"uncalibrated weighted-loss score")]:
        rows.append({"model":name,"evaluation":"matched_test_days","calibration":note,**classification_metrics(frame.target_high_flow,frame[col],threshold)})
    for name,r in matched["models"].items():
        if "regression_exceedance" in r:rows.append({"model":(matched["classical_family"] if name=="xgboost" else name)+"_regression_threshold","evaluation":"matched_test_days","calibration":"not probability",**r["regression_exceedance"]})
    pd.DataFrame(rows).to_csv(REPORTS/"flood_final_high_flow_leaderboard.csv",index=False)
    classical=json.loads((REPORTS/"wildfire_classical_final_results.json").read_text())
    dl=json.loads((REPORTS/"wildfire_unet_final_results.json").read_text())
    baseline=json.loads((RUNS/"wildfire"/"screening"/"persistence_test.json").read_text())
    rows=[]
    for name,r,scope in [(classical["selected_config"]["family"],classical["seed_results"][0]["test"],"239001 sampled training pixels"),("unet",dl["test"],"14979 training scenes"),("persistence",baseline,"baseline")]:
        row={"model":name,"evaluation":"all_valid_test_map_pixels","training_scope":scope,**{k:v for k,v in r.items() if not isinstance(v,dict)}}
        row.update({"newly_active_"+k:v for k,v in r["newly_active"].items() if k in ["n","precision","recall","average_precision_sklearn","iou","dice"]})
        rows.append(row)
    pd.DataFrame(rows).to_csv(REPORTS/"wildfire_final_leaderboard.csv",index=False)

if __name__ == "__main__":run()
