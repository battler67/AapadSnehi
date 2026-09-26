"""Repeat the validation-selected U-Net configuration without selecting a seed."""
import json
from .paths import RUNS,REPORTS
from .wildfire_dl import Config,train,evaluate_best_on_test

def run():
    candidates=[json.loads(p.read_text()) for p in (RUNS/"wildfire"/"screening"/"dl").glob("*/metrics.json")]
    best=max([r for r in candidates if r["config"]["seed"]==42],key=lambda r:r["validation"]["iou"])
    frozen=best["config"].copy();results=[]
    (REPORTS/"wildfire_dl_frozen_config.json").write_text(json.dumps({"config":frozen,"rule":"seed-42 validation IoU; no seed selection"},indent=2))
    for seed in [42,43,44]:
        result=train(Config(**{**frozen,"seed":seed}))
        final=evaluate_best_on_test(result["run_id"]);results.append({"seed":seed,**final})
        if seed==42:primary_scenes=(REPORTS/"wildfire_unet_test_per_scene.csv").read_text()
    (REPORTS/"wildfire_unet_final_results.json").write_text(json.dumps(results[0],indent=2))
    (REPORTS/"wildfire_unet_test_per_scene.csv").write_text(primary_scenes)
    (REPORTS/"wildfire_dl_seed_results.json").write_text(json.dumps({"frozen_config":frozen,"seed_results":results,"caveat":"Seed variation does not establish independent-event uncertainty"},indent=2))

if __name__ == "__main__":run()
