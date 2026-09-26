"""Real-data one-step DL and checkpoint integrity checks; no fixtures for learning."""
import json
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from .paths import PROCESSED,REPORTS,RUNS
from .flood_dl import LSTM,TCN,DYNAMIC,SequenceData
from .wildfire_dl import UNet,batches,_loss
from .metrics import regression_metrics,wildfire_metrics

def run():
    torch.set_num_threads(4);torch.manual_seed(42)
    frame=pd.read_parquet(PROCESSED/"flood"/"features.parquet");tr=frame[frame.split=="train"]
    means=tr[DYNAMIC].mean().to_numpy(np.float32);std=tr[DYNAMIC].std().to_numpy(np.float32);ids=sorted(frame.catchment_id.unique())
    data=SequenceData(frame,"train",30,means,std,ids);x,c,q,e=next(iter(torch.utils.data.DataLoader(data,batch_size=8)))
    results={}
    with tempfile.TemporaryDirectory(dir=RUNS) as directory:
        path=Path(directory)/"model.pt"
        for name,cls in [("lstm",LSTM),("tcn",TCN)]:
            model=cls(16,64,len(ids));opt=torch.optim.Adam(model.parameters());prediction,_=model(x,c)
            loss=torch.nn.functional.mse_loss(prediction,q);loss.backward();opt.step();model.eval()
            torch.save(model.state_dict(),path);reload=cls(16,64,len(ids));reload.load_state_dict(torch.load(path,weights_only=True));reload.eval()
            with torch.inference_mode():a=model(x,c)[0];b=reload(x,c)[0]
            results[name]={"training_step_loss":float(loss.detach()),"checkpoint_reload_equal":bool(torch.equal(a,b)),"metrics":regression_metrics(torch.expm1(q),torch.expm1(a))}
        model=UNet();opt=torch.optim.Adam(model.parameters());x,y,valid,current=next(batches("train",2));prediction=model(x);loss=_loss(prediction,y,valid,torch.tensor(10.));loss.backward();opt.step();model.eval()
        torch.save(model.state_dict(),path);reload=UNet();reload.load_state_dict(torch.load(path,weights_only=True));reload.eval()
        with torch.inference_mode():a=model(x);b=reload(x)
        mask=valid.numpy().astype(bool)
        results["unet"]={"training_step_loss":float(loss.detach()),"checkpoint_reload_equal":bool(torch.equal(a,b)),"metrics":wildfire_metrics(y.numpy()[mask],torch.sigmoid(a).numpy()[mask],current.numpy()[mask])}
    (REPORTS/"real_data_smoke.json").write_text(json.dumps(results,indent=2))
    assert all(r["checkpoint_reload_equal"] for r in results.values())
    return results

if __name__ == "__main__":run()
