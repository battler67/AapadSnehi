from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .paths import RAW, INTERIM, REPORTS, ensure_runtime_dirs

SOURCES = {
    "flood": [
        {"name": "00_CAMELS_IND_Data_Description.pdf", "bytes": 543856,
         "md5": "19cf924c9a0a5417163ba773432ac274",
         "url": "https://zenodo.org/api/records/14999580/files/00_CAMELS_IND_Data_Description.pdf/content",
         "version": "CAMELS-IND 2.2 / Zenodo 14999580"},
        {"name": "CAMELS_IND_Catchments_Streamflow_Sufficient.zip", "bytes": 178141731,
         "md5": "3993c25ba7d7b86df0541de91e094f39",
         "url": "https://zenodo.org/api/records/14999580/files/CAMELS_IND_Catchments_Streamflow_Sufficient.zip/content",
         "version": "CAMELS-IND 2.2 / Zenodo 14999580"},
    ],
    "wildfire": [
        {"name": "next-day-wildfire-spread.zip", "bytes": 2235125032,
         "uncompressed_payload_bytes": 3955889585, "md5": None,
         "url": "https://www.kaggle.com/api/v1/datasets/download/fantineh/next-day-wildfire-spread?datasetVersionNumber=2",
         "version": "Kaggle dataset version 2 (published 2021-11-17)"},
    ],
}


def _hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path, expected_bytes: int | None) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    if partial.exists() and expected_bytes and partial.stat().st_size == expected_bytes:
        os.replace(partial, target)
        return
    have = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "AapadSnehi-research/0.1"}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        append = have > 0 and response.status == 206
        mode = "ab" if append else "wb"
        if not append:
            have = 0
        with partial.open(mode) as output:
            shutil.copyfileobj(response, output, length=8 * 1024 * 1024)
    if expected_bytes and partial.stat().st_size != expected_bytes:
        raise IOError(f"size mismatch for {target.name}: {partial.stat().st_size} != {expected_bytes}")
    os.replace(partial, target)


def acquire(names: Iterable[str]) -> list[dict[str, object]]:
    ensure_runtime_dirs()
    records: list[dict[str, object]] = []
    for dataset in names:
        if dataset == "landslide":
            records.append({"dataset": dataset, "status": "audit_pending", "reason":
                "COOLR inventory endpoint and usable event timing must be audited before credentialed joins."})
            continue
        directory = RAW / dataset
        directory.mkdir(parents=True, exist_ok=True)
        for item in SOURCES[dataset]:
            target = directory / str(item["name"])
            record = {"dataset": dataset, **item, "path": str(target),
                      "license": "CC BY 4.0; preserve dataset attribution and review upstream source conditions",
                      "terms_url": "https://zenodo.org/records/14999580" if dataset=="flood" else "https://www.kaggle.com/datasets/fantineh/next-day-wildfire-spread",
                      "checked_at_utc": datetime.now(timezone.utc).isoformat()}
            try:
                if not target.exists() or (item["bytes"] and target.stat().st_size != item["bytes"]):
                    required = int(item["bytes"]) + int(item.get("uncompressed_payload_bytes", 4*int(item["bytes"]))) + 2*1024**3
                    if shutil.disk_usage(directory).free < required:
                        raise OSError(f"Insufficient disk: need {required} free bytes including extraction reserve")
                    _download(str(item["url"]), target, int(item["bytes"]) if item["bytes"] else None)
                record.update({"status": "complete", "actual_bytes": target.stat().st_size,
                               "sha256": _hash(target)})
                if item["md5"]:
                    record["md5_verified"] = _hash(target, "md5") == item["md5"]
                    if not record["md5_verified"]:
                        raise IOError(f"published MD5 mismatch for {target.name}")
                if target.suffix == ".zip":
                    output = INTERIM / dataset
                    marker = output / ".extracted.json"
                    if not marker.exists():
                        with zipfile.ZipFile(target) as archive:
                            needed = sum(i.file_size for i in archive.infolist())
                            if shutil.disk_usage(directory).free < needed + 1024**3:
                                raise OSError("Insufficient extraction space")
                            for member in archive.infolist():
                                if not (output/member.filename).resolve().is_relative_to(output.resolve()):
                                    raise ValueError("Unsafe archive path")
                            archive.extractall(output)
                        marker.write_text(json.dumps({"sha256":record["sha256"]}),encoding="utf-8")
            except (OSError, urllib.error.URLError) as exc:
                record.update({"status": "failed", "reason": f"{type(exc).__name__}: {exc}"})
            records.append(record)
            _write_manifest(records)
    return records


def _write_manifest(records: list[dict[str, object]]) -> None:
    target = REPORTS / "acquisition_manifest.json"
    previous: list[dict[str, object]] = []
    if target.exists():
        try:
            previous = json.loads(target.read_text(encoding="utf-8")).get("records", [])
        except (OSError, json.JSONDecodeError):
            previous = []
    merged = {(str(item.get("dataset")), str(item.get("name"))): item for item in previous}
    merged.update({(str(item.get("dataset")), str(item.get("name"))): item for item in records})
    target.write_text(json.dumps({"records": list(merged.values())}, indent=2), encoding="utf-8")
