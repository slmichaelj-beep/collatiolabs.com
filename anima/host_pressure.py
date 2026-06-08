"""host_pressure — read the host's memory / swap / disk pressure and gate HEAVY work on it.

Vera runs on the user's own Mac, alongside everything else they're doing. Heavy intake (OCR,
transcription, large embedding/indexing) and large model routes can tip an already-strained host
into heavy swapping. This module reads the live pressure and exposes simple gates so the rest of
Vera can DEFER heavy work honestly under load and prefer the cheap deterministic / LERF paths —
then resume automatically when the host has headroom.

Signals (psutil first; macOS sysctl/vm_stat fallback; shutil for disk):
  * memory available %   (low  => pressure)
  * swap used %          (high => real pressure on macOS — the load-bearing signal)
  * free disk GB         (low  => ENOSPC risk for staging/decode)

Levels: green (work freely) / yellow (prefer deterministic, defer the biggest jobs) /
        red (defer ALL heavy intake + avoid large model routes). Pure reads, never raises.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# thresholds (tuned for a single-user Mac where heavy swap is the clearest distress signal)
_SWAP_RED, _SWAP_YELLOW = 80.0, 55.0          # % of swap in use
_MEMFREE_RED, _MEMFREE_YELLOW = 8.0, 15.0     # % memory available
_DISK_RED_GB, _DISK_YELLOW_GB = 2.0, 5.0      # free GB on the volume holding .anima

GREEN, YELLOW, RED = "green", "yellow", "red"


def _disk_free_gb(path="."):
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return shutil.disk_usage(str(p)).free / (1024 ** 3)
    except Exception:
        return None


def _mem_swap():
    """(mem_available_pct, swap_used_pct, swap_used_mb) — psutil first, macOS fallback."""
    try:
        import psutil
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        mem_free = round(vm.available / vm.total * 100, 1) if vm.total else None
        return mem_free, round(sw.percent, 1), round(sw.used / (1024 ** 2))
    except Exception:
        pass
    # macOS fallback: sysctl vm.swapusage  ->  "total = 9216.00M  used = 8473.25M  free = 742.75M"
    swap_pct = swap_mb = None
    try:
        out = subprocess.run(["sysctl", "vm.swapusage"], capture_output=True, text=True, timeout=5).stdout
        import re
        tot = re.search(r"total\s*=\s*([\d.]+)M", out)
        usd = re.search(r"used\s*=\s*([\d.]+)M", out)
        if tot and usd and float(tot.group(1)) > 0:
            swap_mb = round(float(usd.group(1)))
            swap_pct = round(float(usd.group(1)) / float(tot.group(1)) * 100, 1)
    except Exception:
        pass
    return None, swap_pct, swap_mb


def read_pressure() -> dict:
    """The current host pressure as {level, mem_available_pct, swap_used_pct, swap_used_mb,
    free_disk_gb, reason}. Never raises; unknown signals don't force a level."""
    mem_free, swap_pct, swap_mb = _mem_swap()
    disk_gb = _disk_free_gb(".")
    reasons = []
    red = yellow = False
    if swap_pct is not None:
        if swap_pct >= _SWAP_RED:
            red = True; reasons.append("swap %.0f%% used" % swap_pct)
        elif swap_pct >= _SWAP_YELLOW:
            yellow = True; reasons.append("swap %.0f%% used" % swap_pct)
    if mem_free is not None:
        if mem_free <= _MEMFREE_RED:
            red = True; reasons.append("memory %.0f%% free" % mem_free)
        elif mem_free <= _MEMFREE_YELLOW:
            yellow = True; reasons.append("memory %.0f%% free" % mem_free)
    if disk_gb is not None:
        if disk_gb < _DISK_RED_GB:
            red = True; reasons.append("disk %.1f GB free" % disk_gb)
        elif disk_gb < _DISK_YELLOW_GB:
            yellow = True; reasons.append("disk %.1f GB free" % disk_gb)
    level = RED if red else (YELLOW if yellow else GREEN)
    return {"level": level, "mem_available_pct": mem_free, "swap_used_pct": swap_pct,
            "swap_used_mb": swap_mb, "free_disk_gb": round(disk_gb, 1) if disk_gb is not None else None,
            "reason": ", ".join(reasons) or "headroom is fine"}


def heavy_ok(p: dict = None) -> tuple:
    """(allowed, reason). Heavy intake (OCR / transcription / large embed/index) is DEFERRED under
    red pressure. Honest reason for the deferral either way."""
    p = p if p is not None else read_pressure()
    if p["level"] == RED:
        return False, p["reason"]
    return True, p["reason"]


def prefer_deterministic(p: dict = None) -> bool:
    """True under yellow/red — bias the turn toward the cheap deterministic / LERF paths and away
    from large model routes, so a strained host isn't tipped further."""
    p = p if p is not None else read_pressure()
    return p["level"] in (YELLOW, RED)


def status_line(p: dict = None) -> str:
    """The user-facing honest line when heavy work is deferred."""
    p = p if p is not None else read_pressure()
    return ("Host is under memory pressure (%s); I'll defer heavy intake until the system has "
            "headroom." % p["reason"])


def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    p = read_pressure()
    ok("read_pressure returns a valid level", p["level"] in (GREEN, YELLOW, RED))
    ok("heavy_ok agrees with level (red => deferred)",
       heavy_ok(p)[0] == (p["level"] != RED))
    ok("prefer_deterministic agrees with level (green => False)",
       prefer_deterministic(p) == (p["level"] in (YELLOW, RED)))
    ok("status_line is a non-empty honest message",
       "memory pressure" in status_line(p))
    print("\nHOST-PRESSURE: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    print("  current:", p)
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print(read_pressure())
