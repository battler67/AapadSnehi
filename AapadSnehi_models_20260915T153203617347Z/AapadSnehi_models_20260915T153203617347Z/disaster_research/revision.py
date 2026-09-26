"""Preserve the original flood run before correcting its scientific protocol."""
from pathlib import Path
import shutil
from .paths import ROOT, REPORTS, RUNS, ARTIFACTS, PROCESSED

def archive_original_flood():
    destination = ROOT / "superseded" / "flood_protocol_v1"
    if destination.exists():
        return
    destination.mkdir(parents=True)
    for parent in (RUNS, ARTIFACTS, PROCESSED):
        source = parent / "flood"
        if source.exists():
            shutil.move(str(source), str(destination / parent.name))
    for source in REPORTS.glob("flood*"):
        shutil.move(str(source), str(destination / source.name))
    shutil.copy2(REPORTS / "run_registry.csv", destination / "run_registry.csv")
    (destination / "README.md").write_text(
        "Superseded exploratory results. Selection used validation/test event counts; "
        "input-date splits placed boundary targets in the following period; land-cover "
        "snapshot availability was unaudited. Some estimators used random internal "
        "validation. Test scores were already inspected. Corrected re-evaluation cannot "
        "be represented as a pristine first test; corrections are protocol-driven, "
        "not selected to improve test performance. Do not rank these runs against v2.\n",
        encoding="utf-8")

if __name__ == "__main__":
    archive_original_flood()
