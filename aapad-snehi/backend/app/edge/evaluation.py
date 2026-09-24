from __future__ import annotations

import json

from .detectors import HAZARDS, MODEL_DIR


def main() -> None:
    summary = {
        hazard: json.loads((MODEL_DIR / f"{hazard}-demo-v1.json").read_text(encoding="utf-8"))["metrics"]
        for hazard in HAZARDS
    }
    print(json.dumps({"syntheticOnly": True, "hazards": summary}, indent=2))


if __name__ == "__main__":
    main()
