"""sysinfo — read the Mac's resources and estimate whether a local model will fit.

On Apple Silicon, CPU and GPU share one pool of RAM (unified memory), so total RAM
is the number that decides what a local GGUF model can run. We estimate a model's
footprint from its name (parameter count + quantization) and compare, leaving room
for the OS and other apps. Estimates, not guarantees — but enough to keep you from
picking a model that crawls or won't load.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess

_RESERVE_GB = 8.0          # leave this much for macOS + other apps
_OVERHEAD_GB = 1.5         # runtime/context overhead on top of the weights


def ram_gb() -> float:
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except Exception:
        return 0.0


def chip() -> str:
    try:
        out = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                             capture_output=True, text=True, timeout=3).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return platform.processor() or platform.machine() or "this Mac"


def params_b(name: str) -> float:
    """Pull the parameter count (in billions) out of a model name, e.g. '...-8B-...' -> 8."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b", name or "")
    return float(m.group(1)) if m else 0.0


def _bytes_per_param(name: str) -> float:
    n = (name or "").lower()
    if any(q in n for q in ("q2", "q3", "iq2", "iq3")):
        return 0.45
    if any(q in n for q in ("q4", "iq4")):
        return 0.6
    if "q5" in n:
        return 0.72
    if "q6" in n:
        return 0.85
    if "q8" in n:
        return 1.1
    if any(q in n for q in ("f16", "fp16", "bf16")):
        return 2.1
    return 0.62                 # most Ollama pulls default to ~Q4_K_M


def need_gb(name: str) -> float:
    p = params_b(name)
    return round(p * _bytes_per_param(name) + _OVERHEAD_GB, 1) if p else 0.0


def comfy_params_b() -> float:
    """Biggest model (in B params, ~Q4) this Mac runs comfortably."""
    avail = max(0.0, ram_gb() - _RESERVE_GB)
    return max(0.0, round((avail * 0.7 - _OVERHEAD_GB) / 0.62))


def fit(name: str = "") -> dict:
    ram = ram_gb()
    need = need_gb(name)
    avail = max(0.0, ram - _RESERVE_GB)
    if not ram or not need:
        verdict = "unknown"
    elif need <= avail * 0.7:
        verdict = "comfortable"
    elif need <= avail:
        verdict = "tight"
    else:
        verdict = "too big"
    return {"ram_gb": ram, "chip": chip(), "params_b": params_b(name),
            "need_gb": need, "verdict": verdict, "comfy_b": comfy_params_b()}
