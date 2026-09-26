"""Finish validation tuning, repeats and held-out analyses after the main driver.

Run only after execute.py exits. Every job is sequential and checkpointed.
"""
import json
import os
import subprocess
import sys
import time
from .paths import REPORTS,RUNS,ROOT

def run_job(name,module,args=(),limit=3600):
    ledger=REPORTS/"finishing_execution.json"
    state=json.loads(ledger.read_text()) if ledger.exists() else {}
    if state.get(name,{}).get("status")=="completed":return
    directory=RUNS/"finishing";directory.mkdir(parents=True,exist_ok=True)
    command=[sys.executable,"-m",module,*args]
    start=time.time();state[name]={"status":"running","command":command,"started_unix":start,"timeout_seconds":limit}
    ledger.write_text(json.dumps(state,indent=2))
    with (directory/f"{name}.log").open("w",encoding="utf-8") as log:
        try:
            result=subprocess.run(command,cwd=ROOT.parent,env=dict(os.environ,OMP_NUM_THREADS="8",MKL_NUM_THREADS="8",OPENBLAS_NUM_THREADS="8"),stdout=log,stderr=subprocess.STDOUT,timeout=limit)
            state[name]["status"]="completed" if result.returncode==0 else "failed"
        except subprocess.TimeoutExpired:state[name]["status"]="timed_out"
    state[name]["duration_seconds"]=time.time()-start;ledger.write_text(json.dumps(state,indent=2));print(name,state[name]["status"],flush=True)
    if state[name]["status"]!="completed":raise RuntimeError(f"{name} did not complete; inspect {directory/name}.log")

def main():
    # The user runs this after execute; no simultaneous model fits permitted.
    initial=json.loads((REPORTS/"execution_v2.json").read_text())
    if initial.get("wildfire-unet",{}).get("status")!="completed":raise RuntimeError("Run execute.py to completion first")
    run_job("real_data_smoke","disaster_research.smoke",limit=300)
    candidates=[json.loads(p.read_text()) for p in (RUNS/"flood"/"screening"/"dl").glob("*/metrics.json")]
    best=min([r for r in candidates if r["config"]["seed"]==42 and r["config"]["architecture"]=="lstm" and r["config"]["hidden"]==64],key=lambda r:r["validation"]["regression"]["rmse"])
    length=str(best["config"]["sequence_length"])
    run_job("flood_lstm_128","disaster_research",["train-flood-dl","--sequence-length",length,"--hidden","128"],1800)
    run_job("flood_dl_repeats","disaster_research.repeat_flood",limit=2400)
    run_job("flood_analysis","disaster_research.flood_analysis",limit=1200)
    run_job("flood_unseen","disaster_research.unseen_flood",limit=900)
    run_job("flood_replay","disaster_research.replay",["flood"],300)
    run_job("wildfire_weight3","disaster_research",["train-wildfire-dl","--positive-weight","3"],3600)
    run_job("wildfire_classical_final","disaster_research",["finalize-wildfire"],3600)
    run_job("wildfire_dl_final","disaster_research.repeat_wildfire",limit=7200)
    run_job("wildfire_replay","disaster_research.replay",["wildfire"],600)
    run_job("registry","disaster_research.complete_registry",limit=300)
    run_job("verify_models","disaster_research.verify_models",limit=300)
    run_job("verify_dl_adapters","disaster_research.verify_dl_adapters",limit=300)
    run_job("environment","disaster_research.environment",limit=300)
    run_job("report","disaster_research.report",limit=300)
    run_job("report_verified_adapters","disaster_research.report",limit=300)

if __name__ == "__main__":main()
