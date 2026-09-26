from __future__ import annotations

import json, random, time
from dataclasses import asdict, dataclass
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn
from .metrics import wildfire_metrics
from .paths import REPORTS, RUNS, ensure_runtime_dirs
from .run_registry import RunRegistry
from .wildfire_data import normalized_inputs, records

@dataclass
class Config:
    base_channels: int = 16
    batch_size: int = 32
    epochs: int = 6
    patience: int = 2
    learning_rate: float = 1e-3
    positive_weight: float = 10.0
    seed: int = 42

class Block(nn.Module):
    def __init__(self, ins, outs):
        super().__init__(); self.net=nn.Sequential(nn.Conv2d(ins,outs,3,padding=1),nn.BatchNorm2d(outs),nn.ReLU(),nn.Conv2d(outs,outs,3,padding=1),nn.BatchNorm2d(outs),nn.ReLU())
    def forward(self,x): return self.net(x)

class UNet(nn.Module):
    def __init__(self, base=16):
        super().__init__(); self.e1=Block(12,base); self.e2=Block(base,base*2); self.bottom=Block(base*2,base*4)
        self.pool=nn.MaxPool2d(2); self.up2=nn.ConvTranspose2d(base*4,base*2,2,2); self.d2=Block(base*4,base*2)
        self.up1=nn.ConvTranspose2d(base*2,base,2,2); self.d1=Block(base*2,base); self.out=nn.Conv2d(base,1,1)
    def forward(self,x):
        e1=self.e1(x); e2=self.e2(self.pool(e1)); z=self.bottom(self.pool(e2)); z=self.d2(torch.cat([self.up2(z),e2],1)); z=self.d1(torch.cat([self.up1(z),e1],1)); return self.out(z).squeeze(1)

def batches(split,batch_size,shuffle_buffer=0,seed=42):
    rng=np.random.default_rng(seed); bucket=[]
    for record in records(split):
        x=normalized_inputs(record); target=record["FireMask"]; y=(target==1).astype(np.float32); valid=(target>=0).astype(np.float32)
        bucket.append((x,y,valid,record["PrevFireMask"]))
        if len(bucket)>=batch_size:
            if shuffle_buffer: rng.shuffle(bucket)
            yield tuple(torch.from_numpy(np.stack(values)) for values in zip(*bucket)); bucket=[]
    if bucket: yield tuple(torch.from_numpy(np.stack(values)) for values in zip(*bucket))

def _loss(logits,y,valid,pos_weight):
    raw=nn.functional.binary_cross_entropy_with_logits(logits,y,reduction="none",pos_weight=pos_weight); bce=(raw*valid).sum()/valid.sum().clamp_min(1)
    probability=torch.sigmoid(logits)*valid; intersection=(probability*y).sum(); dice=1-(2*intersection+1)/(probability.sum()+(y*valid).sum()+1)
    return bce+.3*dice

def evaluate(model,split,device,threshold=None,per_scene=False):
    model.eval(); ys=[]; ps=[]; currents=[]; scene_rows=[]; scene_id=0
    with torch.inference_mode():
        for x,y,valid,current in batches(split,64):
            probability=torch.sigmoid(model(x.to(device))).cpu().numpy(); y=y.numpy(); valid=valid.numpy().astype(bool); current=current.numpy()
            for i in range(len(y)):
                yi=y[i][valid[i]]; pi=probability[i][valid[i]]; ci=current[i][valid[i]]; ys.append(yi); ps.append(pi); currents.append(ci)
                if per_scene and threshold is not None:
                    m=wildfire_metrics(yi,pi,ci,threshold); scene_rows.append({"scene":scene_id,"iou":m["iou"],"dice":m["dice"],"precision":m["precision"],"recall":m["recall"]})
                scene_id+=1
    y,p,current=np.concatenate(ys),np.concatenate(ps),np.concatenate(currents)
    if threshold is None:
        from .flood_classical import _validation_f2_threshold
        threshold=_validation_f2_threshold(y,p)
    return wildfire_metrics(y,p,current,threshold),threshold,scene_rows

def train(config:Config):
    ensure_runtime_dirs(); random.seed(config.seed); np.random.seed(config.seed); torch.manual_seed(config.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(config.seed)
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); model=UNet(config.base_channels).to(device); optimizer=torch.optim.AdamW(model.parameters(),lr=config.learning_rate,weight_decay=1e-4)
    pos_weight=torch.tensor(config.positive_weight,device=device); run_id=f"wildfire-screen-unet-b{config.base_channels}-s{config.seed}"+(f"-w{config.positive_weight:g}" if config.positive_weight!=10 else ""); directory=RUNS/"wildfire"/"screening"/"dl"/run_id; directory.mkdir(parents=True,exist_ok=True); checkpoint=directory/"best.pt"
    registry=RunRegistry(REPORTS/"run_registry.csv"); started=time.perf_counter(); start_utc=registry.now(); history=[]; best=-1.; stale=0
    start_epoch=0
    if (directory/"metrics.json").exists():return json.loads((directory/"metrics.json").read_text())
    if (directory/"last.pt").exists():
        last=torch.load(directory/"last.pt",map_location=device,weights_only=False)
        if last["config"] != asdict(config):raise ValueError("Resume configuration differs")
        model.load_state_dict(last["state_dict"]);optimizer.load_state_dict(last["optimizer"])
        start_epoch=last["epoch"];best=last["best"];stale=last["stale"]
        history=json.loads((directory/"history.json").read_text())[:start_epoch]
    registry.upsert({"run_id":run_id,"disaster":"wildfire","stage":"screening","task":"pixel_mask","model":"compact_unet","training_scope":"full_scenes","seed":config.seed,"status":"running","started_at_utc":start_utc})
    for epoch in range(start_epoch,config.epochs):
        model.train(); total=count=0
        for x,y,valid,_ in batches("train",config.batch_size,shuffle_buffer=1,seed=config.seed+epoch):
            x,y,valid=x.to(device),y.to(device),valid.to(device); optimizer.zero_grad(set_to_none=True); logits=model(x); loss=_loss(logits,y,valid,pos_weight); loss.backward(); optimizer.step(); total+=float(loss)*len(y); count+=len(y)
        metrics,threshold,_=evaluate(model,"eval",device); objective=metrics["iou"]; history.append({"epoch":epoch+1,"train_loss":total/count,"validation_iou":objective,"validation_f2":metrics["f2"]})
        (directory/"history.json").write_text(json.dumps(history,indent=2),encoding="utf-8")
        print(json.dumps(history[-1]), flush=True)
        if objective>best:
            best=objective; stale=0; torch.save({"state_dict":model.state_dict(),"config":asdict(config),"threshold":threshold,"epoch":epoch+1},checkpoint)
        else:
            stale+=1
            if stale>=config.patience: break
        torch.save({"state_dict":model.state_dict(),"optimizer":optimizer.state_dict(),"config":asdict(config),"epoch":epoch+1,"best":best,"stale":stale},directory/"last.pt")
    saved=torch.load(checkpoint,map_location=device,weights_only=False); model.load_state_dict(saved["state_dict"]); metrics,_,scene_rows=evaluate(model,"eval",device,saved["threshold"],True); duration=time.perf_counter()-started
    result={"run_id":run_id,"config":asdict(config),"device":str(device),"best_epoch":saved["epoch"],"validation":metrics,"duration_seconds":duration,"parameters":sum(p.numel() for p in model.parameters()),"checkpoint":str(checkpoint)}
    (directory/"metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8"); hist=pd.DataFrame(history); hist.to_csv(directory/"history.csv",index=False); pd.DataFrame(scene_rows).to_csv(directory/"validation_per_scene.csv",index=False)
    fig,axes=plt.subplots(1,2,figsize=(9,3)); axes[0].plot(hist.epoch,hist.train_loss); axes[1].plot(hist.epoch,hist.validation_iou); axes[0].set_title("training loss"); axes[1].set_title("validation IoU"); fig.tight_layout(); fig.savefig(directory/"curves.png",dpi=140); plt.close(fig)
    registry.upsert({"run_id":run_id,"disaster":"wildfire","stage":"screening","task":"pixel_mask","model":"compact_unet","training_scope":"full_scenes","seed":config.seed,"status":"completed","started_at_utc":start_utc,"ended_at_utc":registry.now(),"duration_seconds":duration,"metrics_path":directory/"metrics.json","artifact_path":checkpoint})
    return result

def evaluate_best_on_test(selected_run=None):
    candidates=[]
    for path in (RUNS/"wildfire"/"screening"/"dl").glob("*/metrics.json"):
        if selected_run and path.parent.name!=selected_run:continue
        result=json.loads(path.read_text(encoding="utf-8"));result["checkpoint"]=str(path.parent/"best.pt");candidates.append((result["validation"]["iou"],result))
    if not candidates:raise FileNotFoundError("No completed U-Net screen")
    _,screen=max(candidates,key=lambda x:x[0]);saved=torch.load(screen["checkpoint"],map_location="cpu",weights_only=False);model=UNet(saved["config"]["base_channels"]);model.load_state_dict(saved["state_dict"]);metrics,_,per_scene=evaluate(model,"test",torch.device("cpu"),saved["threshold"],True)
    reloaded=UNet(saved["config"]["base_channels"]);reloaded.load_state_dict(torch.load(screen["checkpoint"],map_location="cpu",weights_only=False)["state_dict"]);first=next(batches("test",2))[0]
    model.eval(); reloaded.eval()
    with torch.inference_mode():equal=bool(torch.allclose(model(first),reloaded(first)))
    pd.DataFrame(per_scene).to_csv(REPORTS/"wildfire_unet_test_per_scene.csv",index=False);result={"selected_by":"highest validation IoU","screen_run":screen["run_id"],"test":metrics,"model_size_bytes":__import__('pathlib').Path(screen["checkpoint"]).stat().st_size,"checkpoint_reload_equal":equal};(REPORTS/"wildfire_unet_final_results.json").write_text(json.dumps(result,indent=2),encoding="utf-8");return result
