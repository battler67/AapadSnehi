from __future__ import annotations

import json, random, time
from dataclasses import asdict, dataclass
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from .metrics import classification_metrics, regression_metrics
from .paths import PROCESSED, REPORTS, RUNS, ensure_runtime_dirs
from .run_registry import RunRegistry

DYNAMIC = ["discharge", "prcp(mm/day)", "tavg(C)", "rel_hum(%)", "sm_lvl1(kg/m2)",
           "sm_lvl2(kg/m2)", "sm_lvl3(kg/m2)", "sm_lvl4(kg/m2)"]

@dataclass
class Config:
    architecture: str = "lstm"
    sequence_length: int = 60
    hidden: int = 64
    batch_size: int = 1024
    epochs: int = 10
    patience: int = 3
    learning_rate: float = 1e-3
    seed: int = 42

class SequenceData(Dataset):
    def __init__(self, frame, split, length, means, stds, catchments):
        self.length, self.groups, self.samples = length, [], []
        mapping = {name: idx for idx, name in enumerate(catchments)}
        for catchment, group in frame.groupby("catchment_id"):
            group = group.sort_values("date").reset_index(drop=True)
            raw = group[DYNAMIC].to_numpy(np.float32); missing = ~np.isfinite(raw)
            scaled = (np.where(missing, means, raw)-means)/stds
            inputs = np.concatenate([scaled, missing.astype(np.float32)], axis=1)
            dates = group.date.to_numpy(dtype="datetime64[D]")
            self.groups.append((inputs, group.target_discharge.to_numpy(np.float32),
                group.target_high_flow.to_numpy(np.float32), dates, mapping[str(catchment)]))
            gi = len(self.groups)-1
            for end in np.flatnonzero(group.split.to_numpy() == split):
                start = end-length+1
                if start >= 0 and (dates[end]-dates[start]).astype(int) == length-1:
                    self.samples.append((gi, end))
    def __len__(self): return len(self.samples)
    def __getitem__(self, index):
        gi, end = self.samples[index]; x,q,event,_,catchment = self.groups[gi]; start=end-self.length+1
        return torch.from_numpy(x[start:end+1]), torch.tensor(catchment), torch.tensor(np.log1p(q[end])), torch.tensor(event[end])

class LSTM(nn.Module):
    def __init__(self, features, hidden, catchments):
        super().__init__(); self.embedding=nn.Embedding(catchments,8); self.encoder=nn.LSTM(features,hidden,batch_first=True)
        self.shared=nn.Sequential(nn.Linear(hidden+8,hidden),nn.ReLU(),nn.Dropout(.1)); self.q=nn.Linear(hidden,1); self.event=nn.Linear(hidden,1)
    def forward(self,x,c):
        z=self.encoder(x)[0][:,-1]; z=self.shared(torch.cat([z,self.embedding(c)],1)); return self.q(z).squeeze(1),self.event(z).squeeze(1)

class CausalBlock(nn.Module):
    def __init__(self,ins,outs,dilation):
        super().__init__(); self.padding=2*dilation; self.conv=nn.Conv1d(ins,outs,3,padding=self.padding,dilation=dilation)
        self.norm=nn.BatchNorm1d(outs); self.skip=nn.Conv1d(ins,outs,1) if ins!=outs else nn.Identity()
    def forward(self,x):
        z=self.conv(x); z=z[:,:,:-self.padding]; return torch.relu(self.norm(z)+self.skip(x))

class TCN(nn.Module):
    def __init__(self,features,hidden,catchments):
        super().__init__(); self.embedding=nn.Embedding(catchments,8)
        self.encoder=nn.Sequential(CausalBlock(features,hidden,1),CausalBlock(hidden,hidden,2),CausalBlock(hidden,hidden,4),CausalBlock(hidden,hidden,8))
        self.shared=nn.Sequential(nn.Linear(hidden+8,hidden),nn.ReLU(),nn.Dropout(.1)); self.q=nn.Linear(hidden,1); self.event=nn.Linear(hidden,1)
    def forward(self,x,c):
        z=self.encoder(x.transpose(1,2))[:,:,-1]; z=self.shared(torch.cat([z,self.embedding(c)],1)); return self.q(z).squeeze(1),self.event(z).squeeze(1)

def _evaluate(model, loader, device, threshold=None):
    model.eval(); qs=[]; qp=[]; events=[]; probs=[]
    with torch.inference_mode():
        for x,c,q,event in loader:
            qhat,logit=model(x.to(device),c.to(device)); qs.append(torch.expm1(q).numpy()); qp.append(torch.expm1(qhat.cpu()).numpy())
            events.append(event.numpy()); probs.append(torch.sigmoid(logit).cpu().numpy())
    yq,pq=np.concatenate(qs),np.maximum(0,np.concatenate(qp)); ye,pe=np.concatenate(events),np.concatenate(probs)
    if threshold is None:
        from .flood_classical import _validation_f2_threshold
        threshold=_validation_f2_threshold(ye,pe)
    return {"regression":regression_metrics(yq,pq),"classification":classification_metrics(ye,pe,threshold)},threshold

def train(config: Config):
    ensure_runtime_dirs(); random.seed(config.seed); np.random.seed(config.seed); torch.manual_seed(config.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(config.seed)
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet"); frame["catchment_id"]=frame.catchment_id.astype(str).str.zfill(5)
    tr=frame[frame.split=="train"]; means=tr[DYNAMIC].mean().to_numpy(np.float32); stds=tr[DYNAMIC].std().replace(0,1).to_numpy(np.float32)
    catchments=sorted(frame.catchment_id.unique()); td=SequenceData(frame,"train",config.sequence_length,means,stds,catchments); vd=SequenceData(frame,"validation",config.sequence_length,means,stds,catchments)
    loaders={"train":DataLoader(td,batch_size=config.batch_size,shuffle=True,num_workers=0,pin_memory=torch.cuda.is_available()),
             "validation":DataLoader(vd,batch_size=config.batch_size*2,num_workers=0,pin_memory=torch.cuda.is_available())}
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); cls=LSTM if config.architecture=="lstm" else TCN
    model=cls(len(DYNAMIC)*2,config.hidden,len(catchments)).to(device); optimizer=torch.optim.AdamW(model.parameters(),lr=config.learning_rate,weight_decay=1e-4)
    pos=float(tr.target_high_flow.sum()); bce=nn.BCEWithLogitsLoss(pos_weight=torch.tensor((len(tr)-pos)/max(1,pos),device=device))
    run_id=f"flood-screen-dl-{config.architecture}-l{config.sequence_length}-s{config.seed}"+(f"-h{config.hidden}" if config.hidden!=64 else ""); directory=RUNS/"flood"/"screening"/"dl"/run_id; directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/"best.pt"; registry=RunRegistry(REPORTS/"run_registry.csv"); started=time.perf_counter(); start_utc=registry.now(); history=[]; best=1e99; stale=0
    start_epoch=0
    if (directory/"metrics.json").exists():
        return json.loads((directory/"metrics.json").read_text())
    if (directory/"last.pt").exists():
        last=torch.load(directory/"last.pt",map_location=device,weights_only=False)
        if last["config"] != asdict(config): raise ValueError("Resume configuration differs")
        model.load_state_dict(last["state_dict"]);optimizer.load_state_dict(last["optimizer"])
        start_epoch=last["epoch"];best=last["best"];stale=last["stale"]
        history=json.loads((directory/"history.json").read_text())[:start_epoch]
        if "torch_rng" in last: torch.set_rng_state(last["torch_rng"].cpu())
        if device.type=="cuda" and "cuda_rng" in last: torch.cuda.set_rng_state_all([state.cpu() for state in last["cuda_rng"]])
    registry.upsert({"run_id":run_id,"disaster":"flood","stage":"screening","task":"multitask","model":config.architecture,"training_scope":f"full_sequences_l{config.sequence_length}","seed":config.seed,"status":"running","started_at_utc":start_utc})
    for epoch in range(start_epoch,config.epochs):
        model.train(); total=count=0
        for x,c,q,event in loaders["train"]:
            x,c,q,event=x.to(device),c.to(device),q.to(device),event.to(device); optimizer.zero_grad(set_to_none=True); qhat,logit=model(x,c)
            loss=nn.functional.smooth_l1_loss(qhat,q)+.2*bce(logit,event); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1); optimizer.step(); total+=loss.detach().item()*len(q); count+=len(q)
        metrics,threshold=_evaluate(model,loaders["validation"],device); objective=metrics["regression"]["rmse"]
        history.append({"epoch":epoch+1,"train_loss":total/count,"validation_rmse":objective,"validation_f2":metrics["classification"]["f2"]})
        (directory/"history.json").write_text(json.dumps(history,indent=2),encoding="utf-8")
        print(json.dumps(history[-1]), flush=True)
        if objective<best:
            best=objective; stale=0; torch.save({"state_dict":model.state_dict(),"config":asdict(config),"means":means,"stds":stds,"catchments":catchments,"threshold":threshold,"epoch":epoch+1},checkpoint)
        else:
            stale+=1
            if stale>=config.patience: break
        torch.save({"state_dict":model.state_dict(),"optimizer":optimizer.state_dict(),"config":asdict(config),"epoch":epoch+1,"best":best,"stale":stale,"torch_rng":torch.get_rng_state(),"cuda_rng":torch.cuda.get_rng_state_all() if device.type=="cuda" else []},directory/"last.pt")
    saved=torch.load(checkpoint,map_location=device,weights_only=False); model.load_state_dict(saved["state_dict"]); final,_=_evaluate(model,loaders["validation"],device,saved["threshold"]); duration=time.perf_counter()-started
    result={"run_id":run_id,"architecture":config.architecture,"config":asdict(config),"device":str(device),"train_sequences":len(td),"validation_sequences":len(vd),"best_epoch":saved["epoch"],"validation":final,"duration_seconds":duration,"parameters":sum(p.numel() for p in model.parameters()),"checkpoint":str(checkpoint)}
    (directory/"metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8"); (directory/"history.json").write_text(json.dumps(history,indent=2),encoding="utf-8"); hist=pd.DataFrame(history); hist.to_csv(directory/"history.csv",index=False)
    fig,axes=plt.subplots(1,2,figsize=(9,3)); axes[0].plot(hist.epoch,hist.train_loss); axes[1].plot(hist.epoch,hist.validation_rmse); axes[0].set_title("training loss"); axes[1].set_title("validation RMSE"); fig.tight_layout(); fig.savefig(directory/"curves.png",dpi=140); plt.close(fig)
    registry.upsert({"run_id":run_id,"disaster":"flood","stage":"screening","task":"multitask","model":config.architecture,"training_scope":f"full_sequences_l{config.sequence_length}","seed":config.seed,"status":"completed","started_at_utc":start_utc,"ended_at_utc":registry.now(),"duration_seconds":duration,"metrics_path":directory/"metrics.json","artifact_path":checkpoint})
    return result

def evaluate_best_on_test(selected_run=None):
    candidates=[]
    for path in (RUNS/"flood"/"screening"/"dl").glob("*/metrics.json"):
        if selected_run and path.parent.name!=selected_run:continue
        result=json.loads(path.read_text(encoding="utf-8")); result["checkpoint"]=str(path.parent/"best.pt"); candidates.append((result["validation"]["regression"]["rmse"],path,result))
    if not candidates: raise FileNotFoundError("No completed flood DL screen")
    _,_,screen=min(candidates,key=lambda x:x[0]); checkpoint=torch.load(screen["checkpoint"],map_location="cpu",weights_only=False); config=Config(**checkpoint["config"])
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet"); frame["catchment_id"]=frame.catchment_id.astype(str).str.zfill(5)
    test=SequenceData(frame,"test",config.sequence_length,checkpoint["means"],checkpoint["stds"],checkpoint["catchments"]); loader=DataLoader(test,batch_size=config.batch_size*2,num_workers=0)
    cls=LSTM if config.architecture=="lstm" else TCN; model=cls(len(DYNAMIC)*2,config.hidden,len(checkpoint["catchments"])); model.load_state_dict(checkpoint["state_dict"]); metrics,_=_evaluate(model,loader,torch.device("cpu"),checkpoint["threshold"])
    first=next(iter(loader)); with_reload=cls(len(DYNAMIC)*2,config.hidden,len(checkpoint["catchments"])); with_reload.load_state_dict(torch.load(screen["checkpoint"],map_location="cpu",weights_only=False)["state_dict"]); model.eval(); with_reload.eval()
    with torch.inference_mode(): equal=bool(torch.allclose(model(first[0],first[1])[0],with_reload(first[0],first[1])[0]))
    result={"selected_by":"lowest validation RMSE among LSTM/TCN and sequence lengths","screen_run":screen["run_id"],"test":metrics,"test_sequences":len(test),"model_size_bytes":__import__('pathlib').Path(screen["checkpoint"]).stat().st_size,"checkpoint_reload_equal":equal}
    (REPORTS/"flood_dl_final_results.json").write_text(json.dumps(result,indent=2),encoding="utf-8"); return result
