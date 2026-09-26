"""Separate fixed-config regression check on catchments excluded from fitting."""
import json
import time
import numpy as np
import pandas as pd
from .paths import PROCESSED,REPORTS
from .flood_finalize import _reg_model
from .flood_classical import _features
from .metrics import regression_metrics

def run():
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet")
    ids=sorted(frame.catchment_id.unique());held=ids[::5]
    train=frame[(frame.split=="train") & ~frame.catchment_id.isin(held)]
    test=frame[(frame.split=="test") & frame.catchment_id.isin(held)]
    x,numeric=_features(train);xt,_=_features(test)
    # Fixed initial-screen RF setting; no tuning on any held-catchment period.
    config={"family":"random_forest","n_estimators":120,"max_depth":16,"min_samples_leaf":4,"max_features":.7}
    start=time.perf_counter();model=_reg_model(numeric,config,42);model.fit(x,train.target_discharge);p=np.maximum(0,model.predict(xt))
    per=[]
    for cid,g in test.assign(prediction=p).groupby("catchment_id"):
        per.append({"catchment_id":cid,**regression_metrics(g.target_discharge,g.prediction)})
    pd.DataFrame(per).to_csv(REPORTS/"flood_unseen_per_catchment.csv",index=False)
    result={"held_catchments":held,"training_catchments":len(ids)-len(held),"training_rows":len(train),"test_rows":len(test),"config":config,"regression":regression_metrics(test.target_discharge,p),"persistence":regression_metrics(test.target_discharge,test.discharge),"duration_seconds":time.perf_counter()-start,"protocol":"Every fifth lexicographically sorted selected ID held out from all fitting; initial fixed RF configuration, no hyperparameter search. Unknown one-hot identity ignored; static maps and historical local discharge allowed.","limitations":"Local historical discharge is required, so not ungauged-basin forecasting. No held-out threshold estimated and no event classification reported. Basins may be nested and geographically correlated. This is a separate single-model extension, not an ML-versus-DL claim."}
    (REPORTS/"flood_unseen_results.json").write_text(json.dumps(result,indent=2))

if __name__ == "__main__":run()
