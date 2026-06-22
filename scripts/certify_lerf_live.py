#!/usr/bin/env python3
"""certify_lerf_live — proves the REAL-model leg of lerf_runtime: a retrieved LERF skill RENDERED by
the live local model and SERVED as the answer, grounded-verified (real_use_in_answer + mri_trace).

The hermetic gate never calls a model, so retrieval + LERF-FIRST wiring are proven there. This cert
installs the REAL OllamaBrain and drives a real server._turn over a summarize skill whose facts the
request supplies (so the render is genuinely grounded), and asserts:

  A. the real model is available; the skill is retrieved and LERF is eligible.
  B. real_use_in_answer — the served backend is the LERF substrate (lerf:…): the small local model's
     render PASSED lerf.verify_rendered_output and was SERVED as the answer (not the LLM fallback).
  C. mri_trace — the route ledger recorded a `verified_local` solve for the turn (grounded=True).
  D. the verified-renders-only SAFETY still holds: the served reply is real and the solve is grounded.

Model output is non-deterministic, so it retries a few times and passes if the skill serves within
them (it serves reliably for a grounded summarize task). GUARDED: SKIP (exit 0) when Ollama is
unreachable, so the hermetic gate stays hermetic; on a Mac with Ollama up it runs the real model.
Hermetic except the model; real .anima byte-UNCHANGED. Exit 0 == CERTIFIED or SKIP; 1 == FAIL.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anima.server as server      # noqa: E402
import anima.lerf as lerf          # noqa: E402
import anima.mouth as mouth        # noqa: E402

_STORE_MODULES = [
    "server", "portrait", "memory_lirf", "constitution", "reliability", "world_state",
    "telemetry", "metrics", "curiosity", "loops", "opportunity", "world_model", "meaning",
    "dials", "whole_mri", "truth.ledger",
]


def _footprint(root):
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"?")
    return (h.hexdigest(), len(files))


def _ollama_up() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(
            os.environ.get("ANIMA_OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/tags",
            timeout=4).read()
        return True
    except Exception:
        return False


def main() -> int:
    if os.environ.get("ANIMA_LERF_LIVE", "1") == "0" or not _ollama_up():
        print("LERF-LIVE CERT: SKIP (Ollama not reachable — hermetic CI; runs on a Mac with Ollama up)")
        return 0

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LERF-LIVE — a retrieved skill RENDERED by the real model and SERVED, grounded-verified")
    print("=" * 90)

    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    mods = []
    for mp in _STORE_MODULES:
        try:
            mods.append(__import__("anima." + mp, fromlist=["_"]))
        except Exception:
            pass
    saved = [(m, getattr(m, "STORE", None)) for m in mods]
    import anima.reliability as reliability
    import anima.models as models
    saved_rel = getattr(reliability, "DEFAULT_STORE", None)
    saved_mu = getattr(models, "STORE", None)
    saved_lerf = lerf.STORE
    saved_lib = server._LERF_SKILL_LIBRARY
    saved_mouth = server._MOUTH

    td = tempfile.mkdtemp(prefix="lerf-live-cert-")
    tp = Path(td)
    try:
        for m in mods:
            if getattr(m, "STORE", None) is not None:
                m.STORE = tp
        lerf.STORE = tp
        if saved_rel is not None:
            reliability.DEFAULT_STORE = tp
        if saved_mu is not None:
            models.STORE = tp

        brain = mouth.OllamaBrain()
        ok("A1: the REAL Ollama brain reports available (live model, not a stub)", brain.available())
        server._MOUTH = mouth.Mouth(brain=brain, voice=None)

        name = "lerf_live_cert"
        library = "lerf_live_cert_lib"
        server._LERF_SKILL_LIBRARY = library
        server._ensure(name, 32)
        lerf.store_skill(lerf.make_skill(
            "summarize_medical_appointment", "health", state=lerf.ACTIVE,
            inputs=["raw doctor's note"],
            steps=["Identify the diagnosis", "Extract medications with dosage", "List follow-ups"],
            outputs=["plain summary", "medication list", "follow-up list"],
            failure_modes=["dropping a dosage"]), name=library)

        # The request SUPPLIES every fact, so a faithful render is grounded (no invented figure).
        text = ("Summarize my appointment: diagnosed with hypertension, prescribed lisinopril 10mg "
                "daily, follow up in 3 months")
        hits = lerf.retrieve_skills(text, name=library) or []
        ok("A2: the skill is RETRIEVED (deterministic keyword/domain match, no model)",
           any((h.get("name") if isinstance(h, dict) else "") == "summarize_medical_appointment"
               for h in hits))
        ok("A3: LERF is ELIGIBLE for this turn (the LERF-FIRST router would route here)",
           server._lerf_eligible(name, text, "", False) is not None)

        served = False
        backend = ""
        reply = ""
        tries = 0
        for tries in range(1, 5):                        # model is non-deterministic; serves reliably
            server._HISTORY.clear()
            out = server._turn(name, text)
            backend = str(out.get("backend", ""))
            reply = (out.get("reply") or "").strip()
            if backend.startswith("lerf:"):
                served = True
                break
        ok("B1: real_use_in_answer — the live model's skill render was SERVED (backend lerf:…) "
           "within %d tries" % tries, served)
        ok("B2: the served render is real + non-empty (the skill produced the answer)",
           bool(reply) and "offline voice" not in reply.lower())

        led = server._routes_path(name)
        from anima import secure_store
        recs = ([json.loads(l) for l in secure_store.read_jsonl_lines(led) if l.strip()]
                if led.exists() else [])
        verified = [r for r in recs if r.get("outcome") == "verified_local" and r.get("grounded")]
        ok("C1: mri_trace — the route ledger recorded a GROUNDED verified_local LERF solve",
           bool(verified))
        ok("D1: verified-renders-only SAFETY held — every served lerf: turn was grounded-verified "
           "(no un-verified render served)",
           all(r.get("grounded") for r in recs if str(r.get("route", "")).startswith("lerf")
               and r.get("solved")))
    finally:
        for m, s in saved:
            if s is not None:
                m.STORE = s
        if saved_rel is not None:
            reliability.DEFAULT_STORE = saved_rel
        if saved_mu is not None:
            models.STORE = saved_mu
        lerf.STORE = saved_lerf
        server._LERF_SKILL_LIBRARY = saved_lib
        server._MOUTH = saved_mouth
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    ok("H1: real .anima byte-UNCHANGED around the live cert (hermetic except the model)",
       fp_before == fp_after)

    print("\nLERF-LIVE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
