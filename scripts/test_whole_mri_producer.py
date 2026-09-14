#!/usr/bin/env python3
"""
test_whole_mri_producer — proves the Whole-System MRI PRODUCER wiring inside the REAL
anima.server._turn: every turn mints a turn_id, assembles a UnifiedTrace correlating the
cognitive trace (the mind) with the host trace (the machine), and records ONE append-only
JSONL line — without ever opening a second response path, mutating the reply, or touching the
real .anima.

It drives the deterministic host seam (which short-circuits BEFORE the LLM, so no model is
needed) through three host scenarios that exercise the whole producer:

  A. Host Awareness ON  + Argus UP    -> full host window (before/during/after) + deltas
  B. Host Awareness OFF + host ask    -> trace STILL recorded (turn_id on every turn)
  C. Host Awareness ON  + Argus DOWN  -> graceful-unavailable host window, trace still recorded

Every store is redirected to a temp dir (reusing gate0_prime_experience._temp_store, which now
redirects whole_mri.STORE); the REAL .anima is asserted byte-identical at the end.

NON-NEGOTIABLES asserted (whole_mri_contract.md):
  #4  host_action_taken == False (read-only wave; no action surface exists)
  #3  memory_contamination == False (host data never auto-promoted to durable memory)
  #5  final mouth gate stays last — shipped reply passes final_output_gate unchanged
  #6  no second response path — out["reply"] is byte-identical to the host seam's reply
  #7  no trace ships without a turn_id (and it matches the format + validates)
  #9  append-only; trace survives + replays
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# reuse the hermetic store-redirect context manager (now redirects whole_mri.STORE too)
_spec = importlib.util.spec_from_file_location(
    "g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


class _StubUp:
    """A live, certified-looking Argus whose /mri readings INCREASE per call, so the
    before/during/after window has real, non-zero deltas. Read surface only — no host action."""

    def __init__(self):
        self.n = 0

    def available(self):
        return True

    def mri(self):
        self.n += 1
        k = float(self.n)
        return {
            "ts": k, "status": "running",
            "shape": {"network": 1.0 * k, "cpu": 0.5 * k},
            "counts": {"by_severity": {"high": 1, "watch": 0, "low": 0, "info": 2}},
            "findings": [
                {"id": "f1", "kind": "flow", "severity": "high", "title": "weird → host",
                 "what_happened": "weird connected out.", "why_it_matters": "unknown host.",
                 "recommended_action": "investigate", "confidence": 0.9, "related_flows": ["f1"]},
            ],
            "blind_spots": [],
            "cpu_pct": 10.0 * k,
            "memory_mb": 100.0 * k,
        }

    def timeline(self, hours=12):
        return {"events": []}

    def action_log(self):
        return {"actions": []}


class _StubDown:
    """Argus unreachable/uncertified — available() is False, reads return None."""

    def available(self):
        return False

    def mri(self):
        return None

    def timeline(self, hours=12):
        return None

    def action_log(self):
        return None


def _dir_fingerprint(p: Path) -> str:
    h = hashlib.sha256()
    if not p.exists():
        return h.hexdigest()
    for fp in sorted(p.rglob("*")):
        if fp.is_file():
            h.update(fp.read_bytes())
    return h.hexdigest()


def main() -> int:
    import anima.server as server
    import anima.tools.argus_client as ac
    from anima import caps, whole_mri, host_awareness as ha, mouth

    fails: list[str] = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("whole-system MRI PRODUCER test (through anima.server._turn)")
    print("=" * 62)

    real_store = Path(".anima")
    fp_before = _dir_fingerprint(real_store)

    with _temp_store():
        # ---- Scenario A: Host Awareness ON + Argus UP -> full host window ---------------
        nameA = "WMProdA"
        server._ensure(nameA, 64)
        caps.save(nameA, {"host_awareness": True})
        ac._DEFAULT = _StubUp()
        resA = server._turn(nameA, "what is my mac doing on the network", voice=False)
        replyA = (resA or {}).get("reply", "")
        trA = whole_mri.last(nameA)

        ck("A: a UnifiedTrace was recorded", trA is not None)
        if trA:
            utA = whole_mri.UnifiedTrace.from_dict(trA)
            okA, problemsA = utA.validate()
            ck("A: trace validates (turn_id present + well-formed)", okA)
            ck("A: turn_id matches format", bool(whole_mri._TURN_ID_RE.match(utA.turn_id)))
            ck("A: input_kind == host_question", utA.input_kind == "host_question")
            ck("A: route == argus", utA.route == "argus")
            # host window — ON + UP => enabled, certified, three real snapshots, deltas computed
            ck("A: argus.enabled True", utA.argus.enabled is True)
            ck("A: argus.capabilities_ok True", utA.argus.capabilities_ok is True)
            ck("A: host_before captured (not unavailable)",
               isinstance(utA.argus.host_before, dict) and not utA.argus.host_before.get("unavailable"))
            ck("A: host_during captured", isinstance(utA.argus.host_during, dict)
               and not utA.argus.host_during.get("unavailable"))
            ck("A: host_after captured", isinstance(utA.argus.host_after, dict)
               and not utA.argus.host_after.get("unavailable"))
            ck("A: shape_delta computed (dict over dims)", isinstance(utA.argus.shape_delta, dict)
               and "cpu" in utA.argus.shape_delta)
            ck("A: cost.cpu_delta is a real number (window moved)",
               isinstance(utA.cost.cpu_delta, (int, float)) and utA.cost.cpu_delta is not None)
            ck("A: cost.memory_delta_mb real", isinstance(utA.cost.memory_delta_mb, (int, float))
               and utA.cost.memory_delta_mb is not None)
            ck("A: cost.argus_calls >= 3 (before/during/after at minimum)",
               (utA.cost.argus_calls or 0) >= 3)
            # safety non-negotiables
            ck("A: safety.host_action_taken == False (read-only wave)",
               utA.safety.host_action_taken is False)
            ck("A: safety.memory_contamination == False (no auto-LIRF of host data)",
               utA.safety.memory_contamination is False)
            ck("A: safety.final_gate_passed True (gate held)", utA.safety.final_gate_passed is True)
            ck("A: safety.identity_mutation == False", utA.safety.identity_mutation is False)
            # no second response path / no mutation: the shipped reply equals the certified
            # final text, and the trace's response length matches it exactly.
            certifiedA = mouth.final_output_gate(ha.respond(nameA, "what is my mac doing on the network",
                                                            cloud_safe=False))
            ck("A: shipped reply == certified final text (no gate bypass)", replyA == certifiedA)
            ck("A: trace.vera.response chars == len(shipped reply) (no post-gate mutation)",
               isinstance(utA.vera.response, dict) and utA.vera.response.get("chars") == len(replyA))
            ck("A: host_labeled True", utA.quality.host_labeled is True)

        # ---- Scenario B: Host Awareness OFF -> trace STILL recorded ---------------------
        nameB = "WMProdB"
        server._ensure(nameB, 64)
        caps.save(nameB, {})                       # host_awareness OFF
        ac._DEFAULT = _StubDown()
        resB = server._turn(nameB, "is anything phoning home", voice=False)
        replyB = (resB or {}).get("reply", "")
        trB = whole_mri.last(nameB)
        ck("B: a UnifiedTrace was recorded even with Host Awareness OFF", trB is not None)
        if trB:
            utB = whole_mri.UnifiedTrace.from_dict(trB)
            ck("B: trace validates (turn_id on every turn)", utB.validate()[0])
            ck("B: argus.enabled False (host awareness off)", utB.argus.enabled is False)
            ck("B: host_before is None (no host window when off)", utB.argus.host_before is None)
            ck("B: safety.host_action_taken False", utB.safety.host_action_taken is False)
            ck("B: reply is the OFF message (host seam, gate held)", replyB == ha.OFF_MESSAGE)

        # ---- Scenario C: Host Awareness ON + Argus DOWN -> graceful-unavailable ----------
        nameC = "WMProdC"
        server._ensure(nameC, 64)
        caps.save(nameC, {"host_awareness": True})
        ac._DEFAULT = _StubDown()
        resC = server._turn(nameC, "what is my mac doing", voice=False)
        replyC = (resC or {}).get("reply", "")
        trC = whole_mri.last(nameC)
        ck("C: a UnifiedTrace was recorded (Argus down)", trC is not None)
        if trC:
            utC = whole_mri.UnifiedTrace.from_dict(trC)
            ck("C: trace validates", utC.validate()[0])
            ck("C: argus.enabled True (feature on)", utC.argus.enabled is True)
            ck("C: argus.capabilities_ok False (handshake/up failed)",
               utC.argus.capabilities_ok is False)
            ck("C: host_before marks unavailable (graceful)",
               isinstance(utC.argus.host_before, dict) and bool(utC.argus.host_before.get("unavailable")))
            ck("C: cost.argus_calls == 0 (nothing readable)", (utC.cost.argus_calls or 0) == 0)
            ck("C: safety.host_action_taken False", utC.safety.host_action_taken is False)
            ck("C: reply is the not-connected message", replyC == ha.NOT_CONNECTED_MESSAGE)

        # ---- append-only: a second turn for nameA appends, never overwrites -------------
        server._turn(nameA, "is anything phoning home", voice=False)
        allA = whole_mri.all(nameA)
        ck("append-only: nameA now has 2 traces", len(allA) == 2)
        ck("append-only: first trace unchanged (turn_id stable)",
           trA is not None and allA[0].get("turn_id") == trA.get("turn_id"))

    # ---- HERMETIC: the REAL .anima is byte-identical before/after -----------------------
    fp_after = _dir_fingerprint(real_store)
    ck("HERMETIC: real .anima byte-identical before/after", fp_before == fp_after)
    if fp_before == fp_after:
        print(f"\n  byte-identical proof: SHA-256 = {fp_before}")

    print("\nWHOLE-SYSTEM MRI PRODUCER TEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
