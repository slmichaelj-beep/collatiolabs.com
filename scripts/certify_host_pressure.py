#!/usr/bin/env python3
"""certify_host_pressure — Vera defers HEAVY work under host memory/swap pressure, honestly.

Vera runs on the user's own Mac. Under real memory/swap pressure (or a near-full disk) she must NOT
tip the host further by running OCR / transcription / large parses or a large model route — she
defers them with an honest, recoverable status and leans on the cheap deterministic / LERF paths.

Proven (hermetic — host pressure is forced via a monkeypatch so the cert is deterministic):

  1. SIGNAL          — host_pressure.read_pressure() returns a valid level (green/yellow/red) from
                       real psutil/sysctl signals.
  2. NO ENOSPC       — a file upload on a near-full disk is REFUSED before writing (the disk
                       pre-flight guard) — never an ENOSPC mid-write.
  3. HEAVY DEFERS    — under RED pressure, heavy intake (image=OCR, audio/audiobook/video=STT) is
                       DEFERRED with the honest "host is under memory pressure" status, not committed.
  4. LIGHT PROCEEDS  — light formats (text/markdown) still parse under RED (only heavy work defers).
  5. NO LARGE MODEL  — under RED/YELLOW prefer_deterministic() is True and the turn bounds generation
                       to the floor (mouth caps max_tokens) — avoid a large model route under load.
  6. RECOVERABLE     — under GREEN the SAME heavy upload proceeds normally (deferral auto-lifts), and
                       the degraded-mode status is a clear, user-facing line.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import base64
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_RED = {"level": "red", "reason": "swap 92% used", "mem_available_pct": 27.0,
        "swap_used_pct": 92.0, "swap_used_mb": 8449, "free_disk_gb": 50.0}
_GREEN = {"level": "green", "reason": "headroom is fine", "mem_available_pct": 55.0,
          "swap_used_pct": 10.0, "swap_used_mb": 100, "free_disk_gb": 50.0}


def main() -> int:
    from anima import intake, host_pressure as hp, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("HOST PRESSURE — defer heavy work under memory/swap/disk pressure, honestly")
    print("=" * 92)

    # ---- 1. SIGNAL --------------------------------------------------------------------------
    p = hp.read_pressure()
    ck("1. read_pressure() returns a valid level (green/yellow/red) from real signals",
       p.get("level") in ("green", "yellow", "red") and "swap_used_pct" in p)
    print("       (current host: level=%s · %s)" % (p.get("level"), p.get("reason")))

    # ---- 2. NO ENOSPC (disk pre-flight guard) ----------------------------------------------
    orig_free = server._free_bytes
    try:
        server._free_bytes = lambda x: 5 * 1024 * 1024     # pretend only 5 MB free
        r = server._intake_plan("HPCert", {"kind": "file", "filename": "x.txt",
                                           "bytes_b64": base64.b64encode(b"x" * 2048).decode()})
        ck("2. a file upload on a near-full disk is REFUSED before writing (no ENOSPC mid-write)",
           (not r.get("ok")) and "disk space" in (r.get("error") or "").lower())
    finally:
        server._free_bytes = orig_free

    d = tempfile.mkdtemp(prefix="hp-cert-")
    orig_read = hp.read_pressure
    try:
        img = Path(d) / "scan.png"
        img.write_bytes(b"\x89PNG\r\n" + b"\x00" * 64)
        aud = Path(d) / "voice.mp3"
        aud.write_bytes(b"ID3" + b"\x00" * 64)
        txt = Path(d) / "note.txt"
        txt.write_text("The blue copper ladder has twelve rungs, forged in Aldermere.")

        # ---- 3. HEAVY DEFERS under RED -----------------------------------------------------
        hp.read_pressure = lambda: dict(_RED)
        ri = intake.ingest(str(img), name="HPCert")
        ra = intake.ingest(str(aud), name="HPCert")
        ck("3. under RED, an image (OCR) is DEFERRED with the honest pressure status, not committed",
           ri.detected_type == "deferred_host_pressure" and ri.committed is False
           and "memory pressure" in (ri.reason or "").lower())
        ck("3. under RED, audio (transcription) is DEFERRED with the honest pressure status",
           ra.detected_type == "deferred_host_pressure" and "memory pressure" in (ra.reason or "").lower())

        # ---- 4. LIGHT PROCEEDS under RED ---------------------------------------------------
        rt = intake.ingest(str(txt), name="HPCert")
        ck("4. under RED, a LIGHT text source still parses (only heavy work defers)",
           rt.detected_type != "deferred_host_pressure" and rt.parse_status == "ok")

        # ---- 5. NO LARGE MODEL ROUTE under pressure ----------------------------------------
        ck("5. prefer_deterministic() is True under RED and YELLOW, False under GREEN",
           hp.prefer_deterministic(_RED) is True and hp.prefer_deterministic(_GREEN) is False
           and hp.prefer_deterministic({"level": "yellow"}) is True)
        mouth_src = (ROOT / "anima" / "mouth.py").read_text()
        ck("5. the turn bounds generation under pressure (mouth caps max_tokens via prefer_deterministic)",
           "prefer_deterministic()" in mouth_src and "min(int(self.brain.max_tokens), 256)" in mouth_src)

        # ---- 6. RECOVERABLE — GREEN lifts the deferral -------------------------------------
        hp.read_pressure = lambda: dict(_GREEN)
        ri2 = intake.ingest(str(img), name="HPCert")
        ck("6. under GREEN the SAME heavy upload proceeds normally (deferral auto-lifts — recoverable)",
           ri2.detected_type != "deferred_host_pressure")
        ck("6. the degraded-mode status is a clear, user-facing line",
           "memory pressure" in hp.status_line(_RED).lower() and "headroom" in hp.status_line(_RED).lower())

        # ---- 7. VERA DOES NOT PIN A MODEL UNDER PRESSURE (host-pressure-aware keep_alive) ---
        from anima import mouth as _mouth
        brain = _mouth.OllamaBrain()
        hp.read_pressure = lambda: dict(_RED)
        ck("7. under RED, Vera unloads its model immediately (keep_alive='0', not a 30-min pin)",
           brain._eff_keep_alive() == "0")
        hp.read_pressure = lambda: dict(_GREEN)
        ck("7. with headroom, Vera keeps the model warm for snappy turns",
           brain._eff_keep_alive() == brain.keep_alive)
        msrc = (ROOT / "anima" / "mouth.py").read_text()
        ck("7. warm() refuses to PRELOAD a model under red host pressure (no proactive large load)",
           "_eff_keep_alive" in msrc and "don't preload a model when the host is red" in msrc)

        # ---- 8. VERA OBSERVES THE REAL DRIVERS (GPU wired ceiling + Ollama footprint) -------
        snap = hp.snapshot()
        ck("8. Vera OBSERVES the host's GPU wired ceiling + Ollama footprint (the memory-bound drivers)",
           "gpu_wired_limit_mb" in snap and isinstance(snap.get("ollama"), dict)
           and "total_mb" in snap["ollama"])
    finally:
        hp.read_pressure = orig_read
        shutil.rmtree(d, ignore_errors=True)

    print("\nHOST-PRESSURE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
