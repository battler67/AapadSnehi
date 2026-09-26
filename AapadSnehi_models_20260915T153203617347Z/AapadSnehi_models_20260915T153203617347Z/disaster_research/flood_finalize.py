from __future__ import annotations

import json, time
import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.compose import TransformedTargetRegressor
from sklearn.metrics import PrecisionRecallDisplay, ConfusionMatrixDisplay
from xgboost import XGBClassifier, XGBRegressor
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, RandomForestClassifier, ExtraTreesClassifier
from .flood_classical import _features, _preprocessor, _validation_f2_threshold
from .metrics import classification_metrics, regression_metrics
from .paths import ARTIFACTS, PROCESSED, REPORTS, RUNS, ensure_runtime_dirs
from .run_registry import RunRegistry
from .model_registry import classification_models,load_optional

REG_CONFIGS=[{"family":"random_forest","n_estimators":120,"max_depth":16,"min_samples_leaf":4,"max_features":.7},
             {"family":"random_forest","n_estimators":180,"max_depth":20,"min_samples_leaf":4,"max_features":.7},
             {"family":"extra_trees","n_estimators":120,"max_depth":18,"min_samples_leaf":3,"max_features":.8},
             {"family":"extra_trees","n_estimators":180,"max_depth":22,"min_samples_leaf":4,"max_features":.8},
             {"family":"xgboost","n_estimators":180,"max_depth":6,"learning_rate":.05},
             {"family":"xgboost","n_estimators":240,"max_depth":7,"learning_rate":.035}]
CLS_CONFIGS=[{"family":"extra_trees","n_estimators":120,"max_depth":18,"min_samples_leaf":3,"max_features":.8,"class_weight":"balanced"},
             {"family":"random_forest","n_estimators":120,"max_depth":16,"min_samples_leaf":4,"max_features":.7,"class_weight":"balanced_subsample"},
             {"family":"xgboost","n_estimators":180,"max_depth":6,"learning_rate":.05,"scale_pos_weight":1},
             {"family":"xgboost","n_estimators":240,"max_depth":7,"learning_rate":.035,"scale_pos_weight":5}]

def _base_data():
    d=pd.read_parquet(PROCESSED/"flood"/"features.parquet"); return d,d[d.split=="train"],d[d.split=="validation"],d[d.split=="test"]

def _reg_model(numeric,config,seed):
    kwargs=dict(config);family=kwargs.pop("family","xgboost")
    if family=="xgboost":estimator=XGBRegressor(**kwargs,subsample=.8,colsample_bytree=.8,objective="reg:squarederror",n_jobs=8,random_state=seed)
    else:estimator=({"random_forest":RandomForestRegressor,"extra_trees":ExtraTreesRegressor}[family])(**kwargs,n_jobs=8,random_state=seed)
    return TransformedTargetRegressor(regressor=Pipeline([("preprocess",_preprocessor(numeric,False)),("model",estimator)]),func=np.log1p,inverse_func=np.expm1,check_inverse=False)

def _cls_model(numeric,config,seed):
    kwargs=dict(config);family=kwargs.pop("family","xgboost")
    if not kwargs:
        models,specs=classification_models(seed);optional,_=load_optional(specs);models.update(optional)
        estimator=models[family][0]
    elif family=="xgboost":estimator=XGBClassifier(**kwargs,subsample=.8,colsample_bytree=.8,eval_metric="logloss",n_jobs=8,random_state=seed)
    else:estimator=({"random_forest":RandomForestClassifier,"extra_trees":ExtraTreesClassifier}[family])(**kwargs,n_jobs=8,random_state=seed)
    return Pipeline([("preprocess",_preprocessor(numeric,False)),("model",estimator)])

def run(seed_repeats=(42,43,44)):
    global CLS_CONFIGS
    board=pd.read_csv(REPORTS/"flood_classification_screening_leaderboard.csv").sort_values("f2",ascending=False)
    CLS_CONFIGS=[{"family":name} for name in board.head(3).model]
    ensure_runtime_dirs(); data,train,val,test=_base_data(); xv,numeric=_features(val); xtest,_=_features(test); xtrain,_=_features(train)
    tuning=[]; trained_reg=[]
    for i,config in enumerate(REG_CONFIGS):
        start=time.perf_counter(); model=_reg_model(numeric,config,42); model.fit(xtrain,train.target_discharge); p=np.maximum(0,model.predict(xv)); metric=regression_metrics(val.target_discharge,p)
        tuning.append({"task":"regression","candidate":i,"config":config,"validation":metric,"seconds":time.perf_counter()-start}); trained_reg.append(model)
    best_reg_index=min(range(len(REG_CONFIGS)),key=lambda i:tuning[i]["validation"]["rmse"]); best_reg_config=REG_CONFIGS[best_reg_index]
    trained_cls=[]
    for i,config in enumerate(CLS_CONFIGS):
        start=time.perf_counter(); model=_cls_model(numeric,config,42); model.fit(xtrain,train.target_high_flow); raw=model.predict_proba(xv)[:,1]
        calibrator=LogisticRegression().fit(np.log(np.clip(raw,1e-6,1-1e-6)/(1-np.clip(raw,1e-6,1-1e-6))).reshape(-1,1),val.target_high_flow)
        calibrated=calibrator.predict_proba(np.log(np.clip(raw,1e-6,1-1e-6)/(1-np.clip(raw,1e-6,1-1e-6))).reshape(-1,1))[:,1]; threshold=_validation_f2_threshold(val.target_high_flow,calibrated); metric=classification_metrics(val.target_high_flow,calibrated,threshold)
        tuning.append({"task":"classification","candidate":i,"config":config,"validation":metric,"threshold":threshold,"seconds":time.perf_counter()-start}); trained_cls.append((model,calibrator,threshold))
    cls_offset=len(REG_CONFIGS); best_cls_index=max(range(len(CLS_CONFIGS)),key=lambda i:tuning[cls_offset+i]["validation"]["f2"]); best_cls_config=CLS_CONFIGS[best_cls_index]
    (REPORTS/"flood_finalist_tuning.json").write_text(json.dumps(tuning,indent=2),encoding="utf-8")
    thresholds=pd.read_csv(PROCESSED/"flood"/"selected_catchments.csv",dtype={"catchment_id":str}).set_index("catchment_id")["train_q95_m3_s"]
    seed_results=[]; selected_dir=ARTIFACTS/"flood"; selected_dir.mkdir(parents=True,exist_ok=True); registry=RunRegistry(REPORTS/"run_registry.csv")
    selected_predictions=None
    for seed in seed_repeats:
        start=time.perf_counter(); reg=_reg_model(numeric,best_reg_config,seed); reg.fit(xtrain,train.target_discharge); regp=np.maximum(0,reg.predict(xtest))
        cls=_cls_model(numeric,best_cls_config,seed); cls.fit(xtrain,train.target_high_flow); valraw=cls.predict_proba(xv)[:,1]; logit=lambda p:np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6))).reshape(-1,1)
        calibrator=LogisticRegression().fit(logit(valraw),val.target_high_flow); valp=calibrator.predict_proba(logit(valraw))[:,1]; threshold=_validation_f2_threshold(val.target_high_flow,valp); raw=cls.predict_proba(xtest)[:,1]; clsp=calibrator.predict_proba(logit(raw))[:,1]
        reg_event=np.array([prediction>thresholds[str(cid).zfill(5)] for prediction,cid in zip(regp,test.catchment_id)],dtype=float)
        result={"seed":seed,"regression":regression_metrics(test.target_discharge,regp),"regression_threshold_event":classification_metrics(test.target_high_flow,reg_event),"separate_classifier":classification_metrics(test.target_high_flow,clsp,threshold),"duration_seconds":time.perf_counter()-start}
        seed_results.append(result); run_id=f"flood-final-xgboost-s{seed}"; metrics_path=RUNS/"flood"/"finalist"/f"seed_{seed}.json"; metrics_path.parent.mkdir(parents=True,exist_ok=True); metrics_path.write_text(json.dumps(result,indent=2),encoding="utf-8")
        registry.upsert({"run_id":run_id,"disaster":"flood","stage":"finalist","task":"regression_and_event","model":"xgboost","training_scope":"full_train","seed":seed,"status":"completed","duration_seconds":result["duration_seconds"],"metrics_path":metrics_path})
        if seed==42:
            joblib.dump({"model":reg,"feature_columns":list(xtrain.columns),"version":f"camels-ind-{best_reg_config['family']}-reg-v2","issue":"end of day t","horizon":"day t+1"},selected_dir/"xgboost_regression.joblib")
            joblib.dump({"model":cls,"calibrator":calibrator,"threshold":threshold,"feature_columns":list(xtrain.columns),"version":f"camels-ind-{best_cls_config['family']}-event-v2","issue":"end of day t","horizon":"day t+1"},selected_dir/"xgboost_event.joblib")
            selected_predictions=(regp,clsp,threshold)
    regp,clsp,threshold=selected_predictions
    per=[]
    for cid,group in test.assign(reg_prediction=regp,event_probability=clsp).groupby("catchment_id"):
        m=regression_metrics(group.target_discharge,group.reg_prediction); m.update({"catchment_id":cid,"high_flow_days":int(group.target_high_flow.sum())}); per.append(m)
    perframe=pd.DataFrame(per).sort_values("rmse"); perframe.to_csv(REPORTS/"flood_final_per_catchment.csv",index=False)
    pred=test.assign(reg_prediction=regp,event_probability=clsp); pred.to_parquet(RUNS/"flood"/"finalist"/"heldout_predictions.parquet",index=False)
    fig,axes=plt.subplots(1,2,figsize=(10,4)); ConfusionMatrixDisplay.from_predictions(test.target_high_flow,clsp>=threshold,ax=axes[0]); PrecisionRecallDisplay.from_predictions(test.target_high_flow,clsp,ax=axes[1]); fig.tight_layout(); fig.savefig(REPORTS/"flood_event_curves.png",dpi=150); plt.close(fig)
    typical=perframe.iloc[len(perframe)//2].catchment_id; poor=perframe.iloc[-1].catchment_id
    fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=False)
    for ax,cid,title in zip(axes,[typical,poor],["Typical catchment (median RMSE)","Poor catchment (largest RMSE)"]):
        g=pred[pred.catchment_id==cid].head(365); ax.plot(g.date,g.target_discharge,label="observed",lw=1); ax.plot(g.date,g.reg_prediction,label="forecast",lw=1); ax.set_title(f"{title}: {cid}, first 365 held-out days"); ax.set_ylabel("m³/s"); ax.legend()
    fig.tight_layout(); fig.savefig(REPORTS/"flood_hydrographs.png",dpi=150); plt.close(fig)
    # Timed, repeated batch inference and reload equality check.
    artifact=selected_dir/"xgboost_regression.joblib"; loaded=joblib.load(artifact); sample=xtest.head(256); t=time.perf_counter(); repeat=[loaded["model"].predict(sample) for _ in range(20)]; latency=(time.perf_counter()-t)/20
    reload_equal=bool(np.allclose(repeat[0],joblib.load(artifact)["model"].predict(sample)))
    summary={"selected_regression_config":best_reg_config,"selected_classifier_config":best_cls_config,"selection_rule":"lowest validation RMSE for discharge; highest validation F2 for event classifier","seed_results":seed_results,"model_sizes_bytes":{"regression":(selected_dir/"xgboost_regression.joblib").stat().st_size,"classifier":(selected_dir/"xgboost_event.joblib").stat().st_size},"batch_256_inference_seconds":latency,"checkpoint_reload_equal":reload_equal,"typical_plot_catchment":typical,"poor_plot_catchment":poor}
    (REPORTS/"flood_final_results.json").write_text(json.dumps(summary,indent=2),encoding="utf-8"); return summary
