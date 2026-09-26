from __future__ import annotations

import json,time
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.metrics import ConfusionMatrixDisplay,PrecisionRecallDisplay
from xgboost import XGBClassifier
from .flood_classical import _validation_f2_threshold
from .metrics import wildfire_metrics
from .paths import ARTIFACTS,PROCESSED,REPORTS,RUNS,ensure_runtime_dirs
from .run_registry import RunRegistry
from .wildfire_classical import PIXEL_FEATURES,scene_table
from .wildfire_data import records

CONFIGS=[{"family":"extra_trees","n_estimators":120,"max_depth":18,"min_samples_leaf":3,"max_features":.8,"class_weight":"balanced"},
         {"family":"extra_trees","n_estimators":180,"max_depth":22,"min_samples_leaf":5,"max_features":.8,"class_weight":"balanced"},
         {"family":"random_forest","n_estimators":120,"max_depth":16,"min_samples_leaf":4,"max_features":.7,"class_weight":"balanced_subsample"},
         {"family":"random_forest","n_estimators":180,"max_depth":20,"min_samples_leaf":5,"max_features":.7,"class_weight":"balanced_subsample"},
         {"family":"xgboost","n_estimators":180,"max_depth":6,"learning_rate":.05},
         {"family":"xgboost","n_estimators":240,"max_depth":7,"learning_rate":.035}]
def _model(config,seed):
    kwargs=dict(config); family=kwargs.pop("family")
    if family == "xgboost": estimator=XGBClassifier(**kwargs,subsample=.8,colsample_bytree=.8,eval_metric="logloss",n_jobs=8,random_state=seed)
    else: estimator=({"extra_trees":ExtraTreesClassifier,"random_forest":RandomForestClassifier}[family])(**kwargs,n_jobs=8,random_state=seed)
    return Pipeline([("imputer",SimpleImputer(strategy="median")),("model",estimator)])
def _logit(p): p=np.clip(p,1e-6,1-1e-6); return np.log(p/(1-p)).reshape(-1,1)
def _evaluate(model,calibrator,threshold,split="test",keep_maps=False):
    ys=[];ps=[];currents=[];scene_rows=[];maps=[]
    for scene_id,record in enumerate(records(split)):
        x,y,current=scene_table(record)
        p=calibrator.predict_proba(_logit(model.predict_proba(x)[:,1]))[:,1] if len(y) else np.empty(0,dtype=np.float32)
        m=wildfire_metrics(y,p,current,threshold)
        scene_rows.append({"scene":scene_id,"positive_pixels":int(y.sum()),"iou":m["iou"],"dice":m["dice"],"precision":m["precision"],"recall":m["recall"]}); ys.append(y);ps.append(p);currents.append(current)
        if keep_maps: maps.append((record,p))
    return wildfire_metrics(np.concatenate(ys),np.concatenate(ps),np.concatenate(currents),threshold),pd.DataFrame(scene_rows),maps
def run(seeds=(42,43,44)):
    ensure_runtime_dirs(); sample=np.load(PROCESSED/"wildfire"/"classical_screen_samples.npz"); tx,ty=sample["train_x"],sample["train_y"]; vx,vy=sample["validation_x"],sample["validation_y"]
    tuning=[]; candidates=[]
    for index,config in enumerate(CONFIGS):
        start=time.perf_counter(); model=_model(config,42); model.fit(tx,ty); raw=model.predict_proba(vx)[:,1]; cal=LogisticRegression().fit(_logit(raw),vy); p=cal.predict_proba(_logit(raw))[:,1]; threshold=_validation_f2_threshold(vy,p); metric=wildfire_metrics(vy,p,sample["validation_current"],threshold)
        tuning.append({"candidate":index,"config":config,"validation":metric,"seconds":time.perf_counter()-start}); candidates.append((model,cal,threshold))
    best=max(range(len(CONFIGS)),key=lambda i:tuning[i]["validation"]["f2"]); (REPORTS/"wildfire_finalist_tuning.json").write_text(json.dumps(tuning,indent=2),encoding="utf-8")
    results=[]; selected=None; artifacts=ARTIFACTS/"wildfire"; artifacts.mkdir(parents=True,exist_ok=True); registry=RunRegistry(REPORTS/"run_registry.csv")
    for seed in seeds:
        start=time.perf_counter(); model=_model(CONFIGS[best],seed); model.fit(tx,ty); raw=model.predict_proba(vx)[:,1]; cal=LogisticRegression().fit(_logit(raw),vy); vp=cal.predict_proba(_logit(raw))[:,1]; threshold=_validation_f2_threshold(vy,vp); metric,per_scene,maps=_evaluate(model,cal,threshold,keep_maps=seed==42); duration=time.perf_counter()-start
        result={"seed":seed,"test":metric,"duration_seconds":duration};results.append(result); out=RUNS/"wildfire"/"finalist";out.mkdir(parents=True,exist_ok=True); (out/f"classical_seed_{seed}.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        registry.upsert({"run_id":f"wildfire-final-xgboost-s{seed}","disaster":"wildfire","stage":"finalist","task":"pixel_mask","model":"xgboost","training_scope":"classical_scene_sample","seed":seed,"status":"completed","duration_seconds":duration,"metrics_path":out/f"classical_seed_{seed}.json"})
        if seed==42: selected=(model,cal,threshold,per_scene,maps);joblib.dump({"model":model,"calibrator":cal,"threshold":threshold,"features":PIXEL_FEATURES,"version":"ndws-xgb-v1","issue":"dataset day t","horizon":"next supplied day"},artifacts/"xgboost_pixel.joblib")
    model,cal,threshold,per_scene,maps=selected; per_scene.to_csv(REPORTS/"wildfire_classical_test_per_scene.csv",index=False)
    y=[];p=[]
    for record,prob in maps:
        _,yi,_=scene_table(record);y.append(yi);p.append(prob)
    y=np.concatenate(y);p=np.concatenate(p);fig,axes=plt.subplots(1,2,figsize=(10,4));ConfusionMatrixDisplay.from_predictions(y,p>=threshold,ax=axes[0]);PrecisionRecallDisplay.from_predictions(y,p,ax=axes[1]);fig.tight_layout();fig.savefig(REPORTS/"wildfire_classical_curves.png",dpi=150);plt.close(fig)
    eligible=per_scene[per_scene.positive_pixels>0].sort_values("iou"); chosen=[int(eligible.iloc[len(eligible)//2].scene),int(eligible.iloc[0].scene)]
    fig,axes=plt.subplots(2,3,figsize=(9,6))
    for row,scene_id in enumerate(chosen):
        record,prob=maps[scene_id];target=record["FireMask"];valid=target>=0;pred=np.full((64,64),np.nan);pred[valid]=prob
        for ax,image,title in zip(axes[row],[record["PrevFireMask"],pred,target],["current fire","predicted probability","observed next day"]):ax.imshow(image,cmap="inferno",vmin=0,vmax=1);ax.set_title(f"scene {scene_id}: {title}");ax.axis("off")
    fig.tight_layout();fig.savefig(REPORTS/"wildfire_replay_examples.png",dpi=150);plt.close(fig)
    artifact=artifacts/"xgboost_pixel.joblib";loaded=joblib.load(artifact); samplex=vx[:256]; t=time.perf_counter();a=loaded["model"].predict_proba(samplex);lat=time.perf_counter()-t;equal=bool(np.allclose(a,joblib.load(artifact)["model"].predict_proba(samplex)))
    summary={"selected_config":CONFIGS[best],"selection_rule":"highest validation F2 after Platt calibration","seed_results":results,"model_size_bytes":artifact.stat().st_size,"batch_256_inference_seconds":lat,"checkpoint_reload_equal":equal,"typical_scene":chosen[0],"poor_scene":chosen[1]};(REPORTS/"wildfire_classical_final_results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8");return summary
