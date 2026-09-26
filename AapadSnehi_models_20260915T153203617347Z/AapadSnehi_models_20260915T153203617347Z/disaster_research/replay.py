"""Deterministic held-out replay selections and scene-level uncertainty artifacts."""
import argparse
import json
import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt
from .paths import REPORTS,RUNS
from .wildfire_data import records,normalized_inputs
from .wildfire_dl import UNet

def wildfire():
    result=json.loads((REPORTS/"wildfire_unet_final_results.json").read_text())
    path=RUNS/"wildfire"/"screening"/"dl"/result["screen_run"]/"best.pt"
    saved=torch.load(path,map_location="cpu",weights_only=False);model=UNet(saved["config"]["base_channels"]);model.load_state_dict(saved["state_dict"]);model.eval()
    scores=pd.read_csv(REPORTS/"wildfire_unet_test_per_scene.csv")
    positive_ids=[]
    for index,record in enumerate(records("test")):
        if (record["FireMask"]==1).any():positive_ids.append(index)
    ranked=scores[scores.scene.isin(positive_ids)].sort_values(["iou","scene"])
    chosen=[int(ranked.iloc[len(ranked)//2].scene),int(ranked.iloc[0].scene)]
    output=RUNS/"wildfire"/"replay";output.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(2,4,figsize=(12,6));cmap=plt.get_cmap("inferno").copy();cmap.set_bad("lightgray")
    for index,record in enumerate(records("test")):
        if index not in chosen:continue
        with torch.inference_mode():p=torch.sigmoid(model(torch.from_numpy(normalized_inputs(record)[None])))[0].numpy()
        np.savez_compressed(output/f"unet_scene_{index}.npz",current=record["PrevFireMask"],observed=record["FireMask"],probability=p,threshold=saved["threshold"])
        row=chosen.index(index)
        for ax,value,title in zip(axes[row],[record["PrevFireMask"],p,(p>=saved["threshold"]).astype(float),record["FireMask"]],["current","probability","predicted mask","observed next day"]):
            value=np.where((record["FireMask"]>=0)&(value>=0),value,np.nan)
            ax.imshow(value,cmap=cmap,vmin=0,vmax=1);ax.set_title(f"scene {index}: {title}");ax.axis("off")
    fig.tight_layout();fig.savefig(REPORTS/"wildfire_unet_replay.png",dpi=150);plt.close(fig)
    # Regenerate classical illustrations with explicit unknown/unevaluated masks.
    import joblib
    from .paths import ARTIFACTS
    from .wildfire_classical import scene_table
    classical=joblib.load(ARTIFACTS/"wildfire"/"xgboost_pixel.joblib")
    csummary=json.loads((REPORTS/"wildfire_classical_final_results.json").read_text())
    cchosen=[csummary["typical_scene"],csummary["poor_scene"]]
    fig,axes=plt.subplots(2,4,figsize=(12,6))
    for index,record in enumerate(records("test")):
        if index not in cchosen:continue
        x,_,_=scene_table(record);raw=np.clip(classical["model"].predict_proba(x)[:,1],1e-6,1-1e-6)
        probability=classical["calibrator"].predict_proba(np.log(raw/(1-raw)).reshape(-1,1))[:,1]
        p=np.full((64,64),np.nan);p[record["FireMask"]>=0]=probability
        for ax,value,title in zip(axes[cchosen.index(index)],[record["PrevFireMask"],p,(p>=classical["threshold"]).astype(float),record["FireMask"]],["current","probability","predicted mask","observed next day"]):
            value=np.where((record["FireMask"]>=0)&(value>=0),value,np.nan)
            ax.imshow(value,cmap=cmap,vmin=0,vmax=1);ax.set_title(f"scene {index}: {title}");ax.axis("off")
        np.savez_compressed(output/f"classical_scene_{index}.npz",current=record["PrevFireMask"],observed=record["FireMask"],probability=p,threshold=classical["threshold"])
    fig.tight_layout();fig.savefig(REPORTS/"wildfire_replay_examples.png",dpi=150);plt.close(fig)
    summary={"selection_rule":"median and lowest test IoU among positive-target scenes, tie by scene order","selected_scene_indices":chosen,"timestamp_limitation":"TFRecord order only; occurrence date/independent event identity unavailable","uncertainty":{}}
    rng=np.random.default_rng(42)
    for family,path in [("classical","wildfire_classical_test_per_scene.csv"),("unet","wildfire_unet_test_per_scene.csv")]:
        frame=pd.read_csv(REPORTS/path)
        values=frame.iou.dropna().to_numpy();draws=rng.choice(values,(1000,len(values)),replace=True).mean(axis=1)
        summary["uncertainty"][family]={"macro_scene_iou":float(values.mean()),"descriptive_scene_bootstrap_95":np.quantile(draws,[.025,.975]).tolist(),"positive_target_scene_macro_iou":float(frame[frame.scene.isin(positive_ids)].iou.mean()),"limitation":"Scene bootstrap, not independent-fire uncertainty; spatial/event overlap may make intervals too narrow"}
    (REPORTS/"wildfire_replay_and_uncertainty.json").write_text(json.dumps(summary,indent=2))

def flood():
    data=pd.read_parquet(RUNS/"flood"/"finalist"/"matched_predictions.parquet")
    scores=pd.read_csv(REPORTS/"flood_final_per_catchment.csv",dtype={"catchment_id":str}).sort_values("rmse")
    ids=[scores.iloc[len(scores)//2].catchment_id,scores.iloc[-1].catchment_id]
    output=RUNS/"flood"/"replay";output.mkdir(parents=True,exist_ok=True)
    for cid in ids:
        g=data[data.catchment_id==cid].sort_values("date").head(365)
        g[["catchment_id","date","target_discharge","reg_prediction","dl_prediction","discharge","target_high_flow","event_probability"]].to_csv(output/f"catchment_{cid}.csv",index=False)
    worst=data.loc[(data.dl_prediction-data.target_discharge).abs().idxmax()]
    typical=data[data.catchment_id==ids[0]].sort_values("date").head(90)
    poor=data[(data.catchment_id==worst.catchment_id)&data.date.between(worst.date-pd.Timedelta(days=45),worst.date+pd.Timedelta(days=45))]
    fig,axes=plt.subplots(2,1,figsize=(12,7))
    for ax,g,title in [(axes[0],typical,"Median classical-RMSE catchment, first 90 matched rows"),(axes[1],poor,"Largest absolute LSTM error, +/-45 calendar days")]:
        for column,label in [("target_discharge","observed"),("reg_prediction","classical"),("dl_prediction","LSTM"),("discharge","persistence")]:
            ax.plot(g.date+pd.Timedelta(days=1),g[column],label=label,linewidth=1)
        ax.set_title(f"{title}: {g.catchment_id.iloc[0]}");ax.set_ylabel("discharge (m3/s)");ax.legend()
    fig.tight_layout();fig.savefig(REPORTS/"flood_matched_hydrographs.png",dpi=150);plt.close(fig)
    poor.to_csv(output/"largest_lstm_error_window.csv",index=False)
    (output/"selection.json").write_text(json.dumps({"rule":"median/worst classical per-catchment RMSE, first 365 matched held-out rows","catchments":ids,"date_column":"input day; target date is date + 1 day","availability":"retrospective assumed availability; not measured operational lead time"},indent=2))

if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("disaster",choices=["flood","wildfire"]);args=parser.parse_args()
    (flood if args.disaster=="flood" else wildfire)()
