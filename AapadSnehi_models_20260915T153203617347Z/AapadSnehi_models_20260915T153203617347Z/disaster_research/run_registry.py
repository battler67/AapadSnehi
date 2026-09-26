from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ["run_id", "disaster", "stage", "task", "model", "training_scope", "seed",
          "status", "started_at_utc", "ended_at_utc", "duration_seconds", "reason",
          "config_path", "metrics_path", "artifact_path"]


class RunRegistry:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def upsert(self, record: dict[str, object]) -> None:
        rows = self.read()
        normalized = {key: str(record.get(key, "")) for key in FIELDS}
        found = False
        for index, row in enumerate(rows):
            if row["run_id"] == normalized["run_id"]:
                rows[index] = normalized
                found = True
                break
        if not found:
            rows.append(normalized)
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        temp.replace(self.path)

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
