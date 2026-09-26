from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .paths import REPORTS, ensure_runtime_dirs


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _memory() -> dict[str, int | None]:
    if os.name == "nt":
        state = _MemoryStatusEx()
        state.dwLength = ctypes.sizeof(state)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
            return {"total_bytes": state.ullTotalPhys, "available_bytes": state.ullAvailPhys}
    return {"total_bytes": None, "available_bytes": None}


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            command = ["powershell", "-NoProfile", "-Command",
                       "(Get-ItemProperty 'HKLM:\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0').ProcessorNameString"]
            return subprocess.check_output(command, text=True, timeout=10).strip()
        except Exception:
            pass
    return platform.processor() or "unknown"


def _nvidia() -> list[dict[str, object]]:
    command = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version",
               "--format=csv,noheader,nounits"]
    try:
        lines = subprocess.check_output(command, text=True, timeout=15).splitlines()
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    result = []
    for line in lines:
        name, total, free, driver = [item.strip() for item in line.split(",", 3)]
        result.append({"name": name, "memory_total_mib": int(total),
                       "memory_free_mib": int(free), "driver": driver})
    return result


def inspect(output: Path | None = None) -> dict[str, object]:
    ensure_runtime_dirs()
    usage = shutil.disk_usage(Path.cwd())
    report: dict[str, object] = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "os": {"platform": platform.platform(), "system": platform.system(),
               "release": platform.release(), "version": platform.version()},
        "cpu": {"name": _cpu_name(), "logical_threads": os.cpu_count()},
        "memory": _memory(),
        "workspace_disk": {"path": str(Path.cwd().resolve()), "total_bytes": usage.total,
                           "used_bytes": usage.used, "free_bytes": usage.free},
        "nvidia_gpus": _nvidia(),
    }
    try:
        import torch
        report["torch"] = {"version": torch.__version__, "cuda_available": torch.cuda.is_available(),
                           "cuda_version": torch.version.cuda,
                           "device_count": torch.cuda.device_count()}
    except ImportError:
        report["torch"] = {"installed": False}
    target = output or REPORTS / "hardware.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
