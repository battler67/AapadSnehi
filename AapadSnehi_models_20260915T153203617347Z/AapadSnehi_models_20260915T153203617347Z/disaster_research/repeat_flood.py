"""Freeze architecture on seed-42 validation; repeat seeds without selecting a lucky seed."""
import json
from .paths import RUNS,REPORTS
from .flood_dl import train,Config,evaluate_best_on_test

def run():
    candidates=[json.loads(p.read_text()) for p in (RUNS/"flood"/"screening"/"dl").glob("*/metrics.json")]
    best=min([r for r in candidates if r["config"]["seed"]==42],key=lambda r:r["validation"]["regression"]["rmse"])
    frozen=best["config"].copy();results=[]
    (REPORTS/"flood_dl_frozen_config.json").write_text(json.dumps({"config":frozen,"rule":"minimum seed-42 validation RMSE; no seed selection"},indent=2))
    for seed in [42,43,44]:
        config=Config(**{**frozen,"seed":seed});screen=train(config)
        final=evaluate_best_on_test(screen["run_id"]);results.append({"seed":seed,**final})
    primary=results[0]
    (REPORTS/"flood_dl_final_results.json").write_text(json.dumps(primary,indent=2))
    (REPORTS/"flood_dl_seed_results.json").write_text(json.dumps({"frozen_config":frozen,"seed_results":results,"caveat":"Repeat variation is model randomness, not independent basin uncertainty"},indent=2))

if __name__ == "__main__":run()
