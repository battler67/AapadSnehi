from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
ARTIFACTS = ROOT / "artifacts"
RUNS = ROOT / "runs"
REPORTS = ROOT / "reports"
CONFIGS = ROOT / "configs"


def ensure_runtime_dirs() -> None:
    for path in (RAW, INTERIM, PROCESSED, ARTIFACTS, RUNS, REPORTS):
        path.mkdir(parents=True, exist_ok=True)
