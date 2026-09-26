from __future__ import annotations

import argparse
import json

from .acquire import acquire
from .hardware import inspect
from .flood_data import audit_and_select, build_features
from .flood_classical import baselines as flood_baselines, screen as flood_screen
from .landslide_data import acquire_and_audit as audit_landslide
from .wildfire_data import audit as audit_wildfire
from .flood_dl import Config as FloodDLConfig, evaluate_best_on_test as finalize_flood_dl, train as train_flood_dl
from .wildfire_dl import Config as WildfireDLConfig, evaluate_best_on_test as finalize_wildfire_dl, train as train_wildfire_dl
from .flood_finalize import run as finalize_flood
from .wildfire_finalize import run as finalize_wildfire
from .wildfire_classical import (persistence_baseline as wildfire_baseline,
                                 prepare_screen_samples as prepare_wildfire,
                                 screen as wildfire_screen)
from .paths import REPORTS, ensure_runtime_dirs


def main() -> None:
    parser = argparse.ArgumentParser(description="AapadSnehi isolated disaster research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("hardware")
    download = sub.add_parser("acquire")
    download.add_argument("--dataset", choices=["all", "flood", "landslide", "wildfire"], default="all")
    sub.add_parser("status")
    sub.add_parser("audit-flood")
    sub.add_parser("prepare-flood")
    screen = sub.add_parser("screen-flood")
    screen.add_argument("--task", choices=["regression", "classification", "both"], default="both")
    screen.add_argument("--only", help="comma-separated model names for smoke/resume")
    sub.add_parser("baseline-flood")
    sub.add_parser("audit-landslide")
    sub.add_parser("audit-wildfire")
    dl = sub.add_parser("train-flood-dl")
    dl.add_argument("--architecture", choices=["lstm", "tcn"], default="lstm")
    dl.add_argument("--sequence-length", type=int, choices=[30, 60, 90], default=60)
    dl.add_argument("--epochs", type=int, default=10)
    dl.add_argument("--seed", type=int, default=42)
    dl.add_argument("--hidden", type=int, default=64)
    wc = sub.add_parser("screen-wildfire")
    wc.add_argument("--only", help="comma-separated model names")
    sub.add_parser("baseline-wildfire")
    wd = sub.add_parser("train-wildfire-dl")
    wd.add_argument("--epochs", type=int, default=6); wd.add_argument("--seed", type=int, default=42)
    wd.add_argument("--positive-weight", type=float, default=10.0)
    sub.add_parser("prepare-wildfire")
    sub.add_parser("finalize-flood")
    sub.add_parser("finalize-flood-dl")
    sub.add_parser("finalize-wildfire")
    sub.add_parser("finalize-wildfire-dl")
    args = parser.parse_args()
    ensure_runtime_dirs()
    if args.command == "hardware":
        print(json.dumps(inspect(), indent=2))
    elif args.command == "acquire":
        names = ["flood", "landslide", "wildfire"] if args.dataset == "all" else [args.dataset]
        print(json.dumps(acquire(names), indent=2))
    elif args.command == "audit-flood":
        print(json.dumps(audit_and_select(), indent=2))
    elif args.command == "prepare-flood":
        print(build_features())
    elif args.command == "baseline-flood":
        print(json.dumps(flood_baselines(), indent=2))
    elif args.command == "audit-landslide":
        print(json.dumps(audit_landslide(), indent=2))
    elif args.command == "audit-wildfire":
        print(json.dumps(audit_wildfire(), indent=2))
    elif args.command == "train-flood-dl":
        print(json.dumps(train_flood_dl(FloodDLConfig(architecture=args.architecture,
            sequence_length=args.sequence_length, epochs=args.epochs, seed=args.seed, hidden=args.hidden)), indent=2))
    elif args.command == "screen-wildfire":
        print(wildfire_screen(only=set(args.only.split(",")) if args.only else None).to_string(index=False))
    elif args.command == "baseline-wildfire":
        print(json.dumps(wildfire_baseline(),indent=2))
    elif args.command == "train-wildfire-dl":
        print(json.dumps(train_wildfire_dl(WildfireDLConfig(epochs=args.epochs,seed=args.seed,positive_weight=args.positive_weight)),indent=2))
    elif args.command == "prepare-wildfire":
        print(json.dumps(prepare_wildfire(), indent=2))
    elif args.command == "finalize-flood":
        print(json.dumps(finalize_flood(), indent=2))
    elif args.command == "finalize-flood-dl":
        print(json.dumps(finalize_flood_dl(), indent=2))
    elif args.command == "finalize-wildfire":
        print(json.dumps(finalize_wildfire(), indent=2))
    elif args.command == "finalize-wildfire-dl":
        print(json.dumps(finalize_wildfire_dl(), indent=2))
    elif args.command == "screen-flood":
        tasks = ["regression", "classification"] if args.task == "both" else [args.task]
        only = set(args.only.split(",")) if args.only else None
        for task in tasks:
            board = flood_screen(task, only=only)
            print(board.to_string(index=False))
    else:
        for name in ("hardware.json", "acquisition_manifest.json", "run_registry.csv"):
            path = REPORTS / name
            print(f"{name}: {'present' if path.exists() else 'missing'}")


if __name__ == "__main__":
    main()
