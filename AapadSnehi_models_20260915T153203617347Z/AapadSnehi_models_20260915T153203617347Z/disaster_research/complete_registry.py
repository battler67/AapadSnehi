"""Reconcile completed measurements, preserve exclusions and publish artifact names."""
import json
import shutil
import joblib
from .paths import REPORTS,ARTIFACTS,RUNS
from .run_registry import RunRegistry
from .model_registry import classification_models

def run():
    registry=RunRegistry(REPORTS/"run_registry.csv")
    models,optional=classification_models()
    for name in [*models,*[x[0] for x in optional],"gru","tcn"]:
        registry.upsert({"run_id":f"landslide-screen-{name}-s42","disaster":"landslide","stage":"screening","task":"next_day_occurrence","model":name,"seed":42,"status":"skipped","reason":"Label provenance/day accuracy and independent storm grouping not accepted; no training dataset. Weather joins not attempted before label gate."})
    for name,reason in [("unseen_catchment","No independent spatial holdout implemented; catchments may share basins"),("expanded_catchments","Retained predeclared 30-basin cohort to keep model comparisons on common units")]:
        done=name=="unseen_catchment" and (REPORTS/"flood_unseen_results.json").exists()
        registry.upsert({"run_id":f"flood-{name}","disaster":"flood","stage":"extension","task":name,"model":"random_forest" if done else "not_applicable","status":"completed" if done else "skipped","reason":"Separate fixed-config historical-discharge regression extension" if done else reason,"metrics_path":REPORTS/"flood_unseen_results.json" if done else ""})
    registry.upsert({"run_id":"flood-v1-tcn-interrupted","disaster":"flood","stage":"superseded","task":"multitask","model":"tcn","status":"failed","reason":"Initial TCN process was manually interrupted before a completed metric record; subsequent restart completed. Duration not measured. V1 protocol is superseded."})
    failures=REPORTS/"execution_failure_history.json"
    if failures.exists():
        for attempt,entry in enumerate(json.loads(failures.read_text())):
            for name,detail in entry["failures"].items():
                registry.upsert({"run_id":f"execution-{name}-failed-attempt-{attempt}","disaster":"wildfire" if "wildfire" in name else "flood","stage":"execution_attempt","task":name,"model":name,"status":detail["status"],"duration_seconds":detail.get("duration_seconds"),"reason":"Preserved failed process attempt; see append-only execution log and failure history. Later retries have separate completed records."})
    for disaster in ["flood","wildfire"]:
        repeats=REPORTS/f"{disaster}_dl_seed_results.json"
        if repeats.exists():
            for row in json.loads(repeats.read_text())["seed_results"]:
                registry.upsert({"run_id":f"{disaster}-final-dl-s{row['seed']}","disaster":disaster,"stage":"finalist","task":"multitask" if disaster=="flood" else "pixel_mask","model":"lstm" if disaster=="flood" else "unet","seed":row["seed"],"status":"completed","metrics_path":repeats,"artifact_path":RUNS/disaster/"screening"/"dl"/row["screen_run"]/"best.pt"})
    for disaster in ["flood","wildfire"]:
        summary_path=REPORTS/("flood_final_results.json" if disaster=="flood" else "wildfire_classical_final_results.json")
        if not summary_path.exists():continue
        summary=json.loads(summary_path.read_text())
        for row in registry.read():
            if row["disaster"]==disaster and row["stage"]=="finalist" and "final-dl" not in row["run_id"]:
                row["model"]=(summary["selected_regression_config"]["family"]+" + "+summary["selected_classifier_config"]["family"]) if disaster=="flood" else summary["selected_config"]["family"]
                registry.upsert(row)
        if disaster=="flood":
            for task,old in [("regression","xgboost_regression.joblib"),("event","xgboost_event.joblib")]:
                shutil.copy2(ARTIFACTS/disaster/old,ARTIFACTS/disaster/f"selected_{task}.joblib")
        else:
            source=ARTIFACTS/disaster/"xgboost_pixel.joblib"
            saved=joblib.load(source);saved["version"]=f"ndws-{summary['selected_config']['family']}-v2"
            joblib.dump(saved,ARTIFACTS/disaster/"selected_pixel.joblib")

if __name__ == "__main__":run()
