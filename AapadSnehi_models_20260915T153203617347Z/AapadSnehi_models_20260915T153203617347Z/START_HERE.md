# AapadSnehi selected model handoff

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
