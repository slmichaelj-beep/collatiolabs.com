#!/usr/bin/env python3
"""
test_host_awareness_live — the host-awareness LIVE-ANSWER test, through the REAL anima.server._turn
reply path, hermetically.

The deterministic host seam short-circuits BEFORE the LLM, so this needs no model: it proves the
four canned behaviors ship through `_turn` with backend "host:awareness", that the reply passes
the SAME #1-rule final gate (no second return path), and that the MRI records the seam:
    input -> host_awareness_match -> capability_check -> deterministic_reply -> final_gate -> shipped
Every store is redirected to a temp dir (reusing gate0_prime_experience._temp_store); the REAL
.anima is never read or written.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# reuse the hermetic store-redirect context manager from the experience harness
_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store

_MRI = {
    "ts": 1.0, "status": "running",
    "findings": [
        {"id": "f1", "kind": "flow", "severity": "high", "title": "weird → 203.0.113.9:443",
         "what_happened": "weird connected to 203.0.113.9:443.",
         "why_it_matters": "Unsigned binary, unknown host.", "recommended_action": "investigate",
         "confidence": 0.9, "related_flows": ["f1"]},
    ],
    "counts": {"by_severity": {"high": 1, "watch": 0, "low": 0, "info": 2}},
    "blind_spots": [],
}


class _Stub:
    """A stand-in argus_client: available()/mri()/timeline()/action_log() only — no host action."""
    def __init__(self, up, mri=None):
        self._up, self._mri = up, mri

    def available(self):
        return self._up

    def mri(self):
        return self._mri

    def timeline(self, hours=12):
        return {"events": []}

    def action_log(self):
        return {"actions": []}


_HOST_STAGES = {"host_awareness_match", "capability_check", "deterministic_host_reply", "final_gate"}


def main() -> int:
    import anima.server as server
    import anima.tools.argus_client as ac
    from anima import caps, telemetry, host_awareness as ha, mouth

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    # (label, caps, stub, prompt, expected-exact OR None for "Argus shows…")
    scenarios = [
        ("Host Awareness OFF -> off message", {}, _Stub(False),
         "what is my mac doing on the network", ha.OFF_MESSAGE),
        ("ON + action ask -> read-only refusal", {"host_awareness": True}, _Stub(False),
         "please block this connection to 1.2.3.4", ha.READ_ONLY_REFUSAL),
        ("ON + Argus down -> not connected", {"host_awareness": True}, _Stub(False),
         "is anything phoning home", ha.NOT_CONNECTED_MESSAGE),
        ("ON + connected -> 'Argus shows…'", {"host_awareness": True}, _Stub(True, _MRI),
         "what is my mac doing", None),
    ]

    print("host-awareness LIVE-ANSWER test (through anima.server._turn)")
    print("=" * 62)
    with _temp_store():
        for i, (label, capdict, stub, prompt, expected) in enumerate(scenarios):
            name = f"HostLive{i}"
            server._ensure(name, 64)
            caps.save(name, capdict)
            ac._DEFAULT = stub
            res = server._turn(name, prompt, voice=False)
            reply = (res or {}).get("reply", "")
            backend = (res or {}).get("backend", "")
            if expected is None:
                ck(f"{label}: reply starts 'Argus shows'", reply.startswith("Argus shows"))
            else:
                ck(f"{label}: reply exact", reply == expected)
            ck(f"{label}: backend == host:awareness", backend == "host:awareness")
            ck(f"{label}: reply non-empty (output integrity)", bool(reply.strip()))
            # MRI seam — the deterministic host stages were recorded for this turn
            tr = telemetry.last_trace(name) or {}
            stages = {s.get("stage") for s in (tr.get("stages") or [])}
            ck(f"{label}: MRI records host seam {sorted(_HOST_STAGES)}", _HOST_STAGES <= stages)
            # shipped text EQUALS the certified final text (final_output_gate output) — the host
            # reply did NOT bypass the final gate, and nothing mutated it after the gate.
            certified = mouth.final_output_gate(ha.respond(name, prompt, cloud_safe=False))
            ck(f"{label}: shipped == certified final text (no gate bypass)", reply == certified)
            ck(f"{label}: response completeness guard passes", mouth.response_complete(reply))

        # NON-host turns must NOT be hijacked by the seam (classify is the gate). We assert at the
        # classify layer (a non-host _turn would call the live model, out of scope for this test).
        ck("non-host turn -> classify None (no hijack)",
           all(ha.classify(t) is None for t in
               ("Do you ever get lonely?", "do you have a soul?", "I love you", "kill the process")))

    print("\nHOST-AWARENESS LIVE TEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
