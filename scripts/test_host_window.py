#!/usr/bin/env python3
"""
test_host_window — hermetic, adversarial selftest for anima/host_window.py.

Stands up a MOCK Argus (loopback ThreadingHTTPServer serving /capabilities,
/mri, /timeline) using the same certified-caps profile as
scripts/certify_argus_integration.py.  Never touches the real Argus.

Asserted (NON-NEGOTIABLEs):
  (a) host_awareness OFF   → capture_host_state returns unavailable record, not raises
  (b) ON + certified mock  → capture_host_state returns shape + counts
  (c) host_window_delta    → computes shape_delta + null-or-number resource deltas
  (d) Argus down           → graceful unavailable, no raise
  (e) real .anima byte-identical (hermetic — no writes)

Additional invariants checked:
  * read-only: no mutating endpoint ever called on the mock
  * certified read set: only /mri used by capture_host_state (/ask, /timeline available
    to host_awareness but not called from this module's entry points directly)
  * graceful: host_window() with unavailable Argus returns the graceful record
  * shape_delta correctly diffs two shapes

Run:
  PYTHONPATH=/Users/lamarmichael/collatiolabs.com python3 scripts/test_host_window.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Mock fixtures (same certified-caps profile as certify_argus_integration.py)
# ---------------------------------------------------------------------------
MOCK_TOKEN = "MOCKtok_abcdef0123456789ABCDEFraND"

_CERTIFIED_CAPS = {
    "name": "Argus",
    "release": "v0.1-host-mri-prime",
    "certification": "ARGUS PRIME: PASS",
    "loopback_only": True,
    "read_only": True,
    "third_party_python_dependencies": 0,
    "security": {"bind": "127.0.0.1", "loopback_only": True, "read_only": True},
}

# /mri payload with shape + counts + resources
_MRI = {
    "ts": 1780788476.0,
    "host": "test-host.local",
    "status": "running",
    "shape": {
        "cpu_load": 0.4,
        "memory_pressure": -0.2,
        "network_activity": 1.1,
        "disk_io": 0.0,
    },
    "findings": [
        {
            "id": "flow:1",
            "kind": "flow",
            "severity": "high",
            "title": "weird-daemon -> 203.0.113.9:443",
            "what_happened": "weird-daemon connected to 203.0.113.9:443.",
            "why_it_matters": "Unsigned binary reaching an unknown public host.",
            "recommended_action": "investigate",
            "confidence": 0.9,
            "related_flows": ["1"],
        },
    ],
    "counts": {"by_severity": {"high": 1, "watch": 1, "low": 0, "info": 3}},
    "blind_spots": ["Running unprivileged."],
    "resources": {
        "cpu_pct": 12.5,
        "memory_mb": 4096.0,
        "swap_mb": 512.0,
        "disk_io_mb": 3.2,
        "network_mb": 1.8,
    },
    "thermal": "nominal",
}

# A second MRI payload with shifted resource values (simulates "after")
_MRI_AFTER = {
    **_MRI,
    "ts": 1780788480.0,
    "shape": {
        "cpu_load": 0.9,       # +0.5
        "memory_pressure": 0.1, # +0.3
        "network_activity": 1.1, # 0.0
        "disk_io": -0.2,        # -0.2
    },
    "resources": {
        "cpu_pct": 55.0,        # +42.5
        "memory_mb": 5120.0,    # +1024
        "swap_mb": 640.0,
        "disk_io_mb": 8.4,
        "network_mb": 3.2,
    },
}


class _MockArgus(BaseHTTPRequestHandler):
    server_version = "MockArgus/0.1"
    caps_override = None
    mri_payload = _MRI
    counts: dict = {}
    mutating_calls: list = []

    def log_message(self, *a):
        pass

    def _count(self, p):
        _MockArgus.counts[p] = _MockArgus.counts.get(p, 0) + 1

    def _j(self, code, obj, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        self._count(path)
        if path == "/":
            tok = f'<script>const token="{MOCK_TOKEN}";</script>'
            return self._j(200, f"<!doctype html><html>{tok}</html>".encode(), "text/html")
        if path == "/capabilities":
            return self._j(200, _MockArgus.caps_override or _CERTIFIED_CAPS)
        if path == "/mri":
            return self._j(200, _MockArgus.mri_payload)
        if path == "/timeline":
            return self._j(200, {"hours": 12, "events": [{"ts": 1, "what": "started"}]})
        return self._j(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        self._count(path)
        ln = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            body = {}
        if path == "/ask":
            return self._j(200, {"question": body.get("question", ""), "answer": "deterministic", "confidence": 0.8})
        # Mutating endpoints — the client MUST NEVER call these
        if path in ("/pause", "/resume", "/block", "/kill", "/quarantine"):
            _MockArgus.mutating_calls.append(path)
            return self._j(200, {"ok": True, "MUTATED": True})
        return self._j(404, {"error": "not found"})


def _start_mock(caps_override=None, mri_payload=None):
    _MockArgus.caps_override = caps_override
    _MockArgus.mri_payload = mri_payload if mri_payload is not None else _MRI
    _MockArgus.counts = {}
    _MockArgus.mutating_calls = []
    for p in range(8787, 8799):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), _MockArgus)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            return srv, f"http://127.0.0.1:{p}"
        except OSError:
            continue
    raise RuntimeError("no free port 8787-8798 for the mock")


def _footprint(root: Path) -> str:
    h = hashlib.sha256()
    if root.exists():
        for p in sorted(root.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(root).as_posix().encode())
                h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests(*, verbose: bool = True) -> tuple[bool, list]:
    checks: list[tuple[str, bool, str]] = []

    def ck(label: str, cond: bool, detail: str = ""):
        checks.append((label, bool(cond), detail))
        if verbose:
            marker = "  ok   " if cond else "  XX   "
            print(marker + label + (f"   [{detail}]" if detail else ""))

    import anima.tools.argus_client as ac
    from anima.tools.argus_client import ArgusClient
    from anima import caps

    real_store = caps.STORE if caps.STORE.is_absolute() else (Path.cwd() / caps.STORE)
    fp_before = _footprint(real_store)
    td = Path(tempfile.mkdtemp(prefix="hostwin-test-"))
    old_caps_store = caps.STORE
    old_default = ac._DEFAULT
    caps.STORE = td
    srv = None

    try:
        # -----------------------------------------------------------------------
        # (a) host_awareness OFF -> capture_host_state returns unavailable record
        # -----------------------------------------------------------------------
        from anima.host_window import capture_host_state, host_window_delta, host_window

        # No caps written for OffCreature -> host_awareness is OFF
        result = capture_host_state("OffCreature")
        ck("(a) host_awareness OFF -> unavailable record",
           result.get("unavailable") is True and "OFF" in result.get("reason", ""))
        ck("(a) OFF -> no raise (returned a dict)",
           isinstance(result, dict))

        # -----------------------------------------------------------------------
        # (b) ON + certified mock -> capture_host_state returns shape + counts
        # -----------------------------------------------------------------------
        srv, url = _start_mock()
        ac._DEFAULT = ArgusClient(base_url=url, token=MOCK_TOKEN)
        test_name = "HostWinTestCreature"
        caps.save(test_name, {"host_awareness": True})

        snap = capture_host_state(test_name)
        ck("(b) ON + certified mock -> returns dict",
           isinstance(snap, dict) and not snap.get("unavailable"),
           str(snap.get("unavailable", "")))
        ck("(b) shape present and is a dict",
           isinstance(snap.get("shape"), dict),
           str(snap.get("shape")))
        ck("(b) counts present",
           isinstance(snap.get("counts"), dict))
        ck("(b) by_severity present",
           isinstance(snap.get("by_severity"), dict))
        ck("(b) blind_spots is a list",
           isinstance(snap.get("blind_spots"), list))
        ck("(b) status present",
           snap.get("status") is not None)
        # Resource fields from mock's resources sub-dict
        ck("(b) cpu_pct is a number from /mri resources",
           isinstance(snap.get("cpu_pct"), float),
           str(snap.get("cpu_pct")))
        ck("(b) memory_mb is a number",
           isinstance(snap.get("memory_mb"), float),
           str(snap.get("memory_mb")))
        ck("(b) thermal is present",
           snap.get("thermal") == "nominal")
        ck("(b) ts is a float (epoch seconds)",
           isinstance(snap.get("ts"), float))

        # -----------------------------------------------------------------------
        # (c) host_window_delta computes shape_delta + null-or-number resource deltas
        # -----------------------------------------------------------------------
        # Manufacture a "before" snapshot with slightly different values
        snap_before = dict(snap)
        snap_before["shape"] = dict(_MRI["shape"])
        snap_before["cpu_pct"] = 12.5
        snap_before["memory_mb"] = 4096.0
        snap_before["disk_io_mb"] = 3.2
        snap_before["network_mb"] = 1.8

        # "after" snapshot with shifted resources
        _MockArgus.mri_payload = _MRI_AFTER
        snap_after = capture_host_state(test_name)
        _MockArgus.mri_payload = _MRI  # reset

        delta = host_window_delta(snap_before, snap, snap_after)
        ck("(c) host_window_delta returns dict",
           isinstance(delta, dict) and "host_window" not in delta)
        ck("(c) shape_delta is present and is a dict",
           isinstance(delta.get("shape_delta"), dict),
           str(delta.get("shape_delta")))

        # Check specific shape dims
        sdelta = delta.get("shape_delta") or {}
        ck("(c) shape_delta cpu_load is a float",
           isinstance(sdelta.get("cpu_load"), float),
           str(sdelta.get("cpu_load")))
        ck("(c) shape_delta cpu_load value correct (0.9 - 0.4 = 0.5)",
           abs((sdelta.get("cpu_load") or 0.0) - 0.5) < 1e-9,
           str(sdelta.get("cpu_load")))
        ck("(c) shape_delta memory_pressure value correct (0.1 - (-0.2) = 0.3)",
           abs((sdelta.get("memory_pressure") or 0.0) - 0.3) < 1e-9,
           str(sdelta.get("memory_pressure")))

        # Resource deltas: either a float (real) or None (honest null)
        cpu_d = delta.get("cpu_delta")
        mem_d = delta.get("memory_delta_mb")
        ck("(c) cpu_delta is float or None",
           cpu_d is None or isinstance(cpu_d, float),
           str(cpu_d))
        ck("(c) memory_delta_mb is float or None",
           mem_d is None or isinstance(mem_d, float),
           str(mem_d))
        ck("(c) disk_io_delta is float or None",
           delta.get("disk_io_delta") is None or isinstance(delta.get("disk_io_delta"), float))
        ck("(c) network_delta is float or None",
           delta.get("network_delta") is None or isinstance(delta.get("network_delta"), float))

        # When /mri exposes cpu_pct (our mock does), cpu_delta should be numeric
        ck("(c) cpu_delta is a float when /mri exposes cpu_pct",
           isinstance(cpu_d, float),
           str(cpu_d))
        ck("(c) cpu_delta value correct (55.0 - 12.5 = 42.5)",
           abs((cpu_d or 0.0) - 42.5) < 1e-9,
           str(cpu_d))

        ck("(c) blind_spots is a list (union)",
           isinstance(delta.get("blind_spots"), list))
        ck("(c) host_before / host_during / host_after present",
           all(k in delta for k in ("host_before", "host_during", "host_after")))
        ck("(c) thermal from after snapshot",
           delta.get("thermal") == "nominal")

        # -----------------------------------------------------------------------
        # (d) Argus down -> graceful unavailable, no raise
        # -----------------------------------------------------------------------
        class _DownClient:
            def available(self):
                return False

        old_client = ac._DEFAULT
        ac._DEFAULT = _DownClient()

        snap_down = capture_host_state(test_name)
        ck("(d) Argus down -> capture_host_state returns unavailable",
           snap_down.get("unavailable") is True)
        ck("(d) Argus down -> no raise (returned dict)",
           isinstance(snap_down, dict))

        # host_window with unavailable Argus: use two good + one bad snapshot
        delta_down = host_window_delta(snap_down, snap, snap)
        ck("(d) host_window_delta with unavailable before -> graceful",
           delta_down.get("host_window") == "unavailable")
        ck("(d) host_window_delta graceful -> no raise",
           isinstance(delta_down, dict))

        # host_window convenience entry point with Argus down
        hw_down = host_window(test_name)
        ck("(d) host_window() with Argus down -> graceful unavailable record",
           hw_down.get("host_window") == "unavailable")
        ck("(d) host_window() with Argus down -> no raise",
           isinstance(hw_down, dict))

        ac._DEFAULT = old_client

        # -----------------------------------------------------------------------
        # Read-only + certified-read-set assertions
        # -----------------------------------------------------------------------
        ck("READ-ONLY: no mutating endpoint ever called",
           len(_MockArgus.mutating_calls) == 0,
           str(_MockArgus.mutating_calls))
        ck("CERTIFIED-READ-SET: /mri called at least once",
           _MockArgus.counts.get("/mri", 0) >= 1,
           str(dict(_MockArgus.counts)))
        # /system and /events must NOT have been called
        ck("CERTIFIED-READ-SET: /system NOT called",
           _MockArgus.counts.get("/system", 0) == 0)
        ck("CERTIFIED-READ-SET: /events NOT called",
           _MockArgus.counts.get("/events", 0) == 0)

        # host_window convenience path
        ac._DEFAULT = ArgusClient(base_url=url, token=MOCK_TOKEN)
        hw = host_window(test_name)
        ck("host_window() returns a delta dict (not unavailable) with real Argus",
           isinstance(hw, dict) and "host_window" not in hw)
        ck("host_window() has shape_delta key",
           "shape_delta" in hw)

        # host_window with explicit snapshots
        hw_explicit = host_window(test_name, before=snap, during=snap, after=snap)
        ck("host_window() with explicit snapshots returns delta dict",
           isinstance(hw_explicit, dict) and "host_window" not in hw_explicit)

        srv.shutdown()
        srv = None

    finally:
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
        ac._DEFAULT = old_default
        caps.STORE = old_caps_store

    # -----------------------------------------------------------------------
    # (e) real .anima byte-identical (hermetic — no writes by host_window.py)
    # -----------------------------------------------------------------------
    fp_after = _footprint(real_store)
    ck("(e) HERMETIC: real .anima byte-identical (host_window.py writes nothing)",
       fp_before == fp_after,
       f"{fp_before[:12]}->{fp_after[:12]}")

    ok = all(c for _, c, _ in checks)
    return ok, checks


def main(argv=None) -> int:
    print("HOST WINDOW SELFTEST  (Phase 2 — Whole-System MRI)")
    print("=" * 60)
    ok, checks = run_tests(verbose=True)
    print()
    print("HOST WINDOW SELFTEST: " + ("PASS" if ok else "FAIL"))
    if not ok:
        print()
        print("FAILED checks:")
        for label, cond, detail in checks:
            if not cond:
                print(f"   FAILED: {label}" + (f"   [{detail}]" if detail else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
