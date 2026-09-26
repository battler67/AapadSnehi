"""Copy selected artifacts into a verified, self-contained local Drive handoff."""
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from .paths import ROOT, ARTIFACTS, REPORTS


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source,"sha256").hexdigest()


def main():
    metadata=json.loads((REPORTS/"model_handoff_manifest.json").read_text())
    files=list(ROOT.glob("*.py"))+list(ROOT.glob("*.md"))+[ROOT/"requirements.txt"]
    files+=list((ROOT/"configs").glob("*.json"))
    files += [p for p in REPORTS.iterdir() if p.is_file() and p.suffix in {".json",".csv",".png"}]
    files += list((ARTIFACTS/"handoff").glob("*.json"))
    for item in metadata["models"].values():
        path=ROOT/item["path_relative_to_disaster_research"]
        if sha256(path)!=item["sha256"]:raise ValueError(f"Source artifact hash differs: {path.name}")
        files.append(path)
    files=sorted(set(files))
    if len(list((ARTIFACTS/"handoff").glob("*_input.json")))!=3:
        raise FileNotFoundError("Run export_handoff first to create all three real-input examples")
    total=sum(p.stat().st_size for p in files)
    if shutil.disk_usage(ROOT).free < total*3+100_000_000:
        raise OSError("Not enough free space for verified folder and ZIP")
    base=ARTIFACTS/"drive_upload";base.mkdir(exist_ok=True)
    folder=base/("AapadSnehi_models_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir(exist_ok=False)
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),
              "contents":"Three selected models, source/preprocessing, real-input examples and research reports; no training data or credentials",
              "files":[]}
    for source in files:
        relative=source.relative_to(ROOT)
        target=folder/"disaster_research"/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        digest=sha256(target)
        if digest!=sha256(source):raise IOError(f"Copy mismatch: {relative}")
        manifest["files"].append({"path":target.relative_to(folder).as_posix(),"bytes":target.stat().st_size,"sha256":digest})
    # Import from the copied package, not the original checkout. Check real examples.
    check='''import json, pathlib, numpy as np, torch
from disaster_research.inference import predict, predict_fire_map
torch.set_num_threads(8)
p=pathlib.Path("disaster_research")
for name,filename,key in [("random_forest","selected_regression.joblib","discharge_m3_s"),("xgboost","selected_event.joblib","probability")]:
    request=json.loads((p/"artifacts/handoff"/(name+"_input.json")).read_text())
    expected=json.loads((p/"artifacts/handoff"/(name+"_output.json")).read_text())
    result=predict(p/"artifacts/flood"/filename,request)
    assert result["status"]=="prediction",result
    assert np.allclose(result[key],expected[key],rtol=1e-5,atol=1e-6)
request=json.loads((p/"artifacts/handoff/unet_input.json").read_text())
expected=json.loads((p/"artifacts/handoff/unet_output.json").read_text())
result=predict_fire_map(p/"runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt",request)
assert result["status"]=="prediction",result
assert np.allclose(result["uncalibrated_probability_map"],expected["uncalibrated_probability_map"],rtol=1e-5,atol=1e-6)
print("All three copied models reload and reproduce reference predictions.")
'''
    verification=subprocess.run([sys.executable,"-c",check],cwd=folder,capture_output=True,text=True,timeout=180)
    if verification.returncode:
        raise RuntimeError(f"Copied-package verification failed: {verification.stderr}")
    manifest["verification"]={"copied_package_reload_predictions_equal":True,
                              "scope":"Existing laptop research environment, CPU; not a clean dependency installation test"}
    (folder/"MANIFEST.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (folder/"START_HERE.md").write_text('''# AapadSnehi selected model handoff

This folder contains the already-trained selected models; no retraining is needed.

| Model | File relative to this folder |
|---|---|
| Random Forest discharge | disaster_research/artifacts/flood/selected_regression.joblib |
| XGBoost high-flow | disaster_research/artifacts/flood/selected_event.joblib |
| U-Net wildfire spread | disaster_research/runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt |

Read disaster_research/MODEL_USER_GUIDE.md and expressitvity.md. Source code and
preprocessing are included: do not distribute weights without them. Real request
and reference output JSONs are in disaster_research/artifacts/handoff/.

Extract the ZIP, open a terminal in THIS folder, and use a compatible isolated
Python environment. Check disaster_research/reports/environment_versions.json;
install disaster_research/requirements.txt and a compatible PyTorch separately.
No virtual environment or Python executable is bundled. CPU inference is supported.
The guide's .venv commands assume you create that environment here, or substitute
the path to your existing compatible interpreter.

MANIFEST.json lists hashes for every copied source/model/example/report file.
Only load files from a trusted sender: joblib/PyTorch deserialization can execute
code. All three copied models were reloaded and reproduced their reference
predictions on the original laptop. This does not certify another environment.

Upload the ZIP or this complete folder to Drive. Neither was automatically
uploaded. The GitHub publication status in the owner handoff is a dated snapshot;
this bundle now supplies the three selected artifacts missing from Git.

No raw training datasets, full training checkpoints, credentials or portal runtime
are bundled. Historical ledgers are evidence, not fresh-run state. Do not run
training/resume drivers from the bundle. The export command needs original data;
the already exported example JSONs do not. Additional typical/poor replay arrays
are not included; their plots are in reports/.

These models are research demonstrations, not official warnings. No landslide
model exists. Keep source and dataset attribution; check terms before public
redistribution, including the small historical example excerpts.
''',encoding="utf-8")
    archive=folder.with_suffix(".zip")
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():z.write(path,path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise IOError("ZIP integrity check failed")
    result={"folder":str(folder),"zip":str(archive),"zip_bytes":archive.stat().st_size,
            "zip_sha256":sha256(archive),"copied_files":len(files),"copied_models_verified":True}
    (REPORTS/"drive_package_latest.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
