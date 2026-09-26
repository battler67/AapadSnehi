"""Sequential, bounded, resumable experiment driver: python -m disaster_research.execute."""
import json
import os
import subprocess
import sys
import time
from .paths import REPORTS, RUNS, ROOT

def main():
    directory = RUNS / "execution_v2"
    directory.mkdir(parents=True, exist_ok=True)
    state_path = REPORTS / "execution_v2.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    failures={k:v for k,v in state.items() if v.get("status") in ["failed","timed_out"]}
    if failures:
        history_path=REPORTS/"execution_failure_history.json"
        history=json.loads(history_path.read_text()) if history_path.exists() else []
        history.append({"recorded_unix":time.time(),"failures":failures})
        history_path.write_text(json.dumps(history,indent=2))
    env = dict(os.environ, OMP_NUM_THREADS="8", MKL_NUM_THREADS="8", OPENBLAS_NUM_THREADS="8")
    from .model_registry import classification_models, regression_models
    jobs = [("baseline-flood", ["baseline-flood"], 300)]
    for task, factory in [("regression", regression_models), ("classification", classification_models)]:
        models, optional = factory()
        for name in [*models, *[s[0] for s in optional]]:
            jobs.append((f"flood-{task}-{name}", ["screen-flood", "--task", task, "--only", name], 900))
    for architecture, length in [("lstm",30),("lstm",60),("lstm",90),("tcn",60)]:
        jobs.append((f"flood-{architecture}-{length}", ["train-flood-dl", "--architecture",architecture,"--sequence-length",str(length)], 1200))
    jobs += [("finalize-flood",["finalize-flood"],1200),
             ("finalize-flood-dl",["finalize-flood-dl"],900),
             ("baseline-wildfire",["baseline-wildfire"],900),
             ("wildfire-unet",["train-wildfire-dl"],3600)]
    for name, args, limit in jobs:
        if state.get(name, {}).get("status") == "completed":
            continue
        start = time.time()
        state[name] = {"status":"running", "command":[sys.executable,"-m","disaster_research",*args], "timeout_seconds":limit, "started_unix":start}
        state_path.write_text(json.dumps(state, indent=2))
        with (directory / f"{name}.log").open("a", encoding="utf-8") as log:
            try:
                result = subprocess.run(state[name]["command"], cwd=ROOT.parent, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=limit)
                state[name]["status"] = "completed" if result.returncode == 0 else "failed"
                state[name]["exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                state[name]["status"] = "timed_out"
        state[name]["duration_seconds"] = time.time()-start
        state_path.write_text(json.dumps(state, indent=2))
        print(name, state[name]["status"], flush=True)

if __name__ == "__main__":
    main()
