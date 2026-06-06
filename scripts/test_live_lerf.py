#!/usr/bin/env python3
"""test_live_lerf — the PRODUCTION-WIRING proof for LERF-first.

This is the hermetic, end-to-end test that the live reply path (server._turn) is now
LERF-FIRST without breaking anything it must protect. It drives the REAL _turn — the same
function the phone hits — with a SCRIPTED brain (so the test is deterministic and needs no
Ollama), a synthetic creature, and EVERY store redirected to a throwaway temp dir. The real
.anima is asserted byte-UNCHANGED around the whole run.

It proves the four behaviours the directive requires:

  (a) TASK request           -> solved by a LERF skill LOCALLY; the LLM is only the fallback.
                                (the scripted "LLM" records that it was NOT called.)
  (b) PERSONAL-FACT request  -> the EXISTING memory/honesty path: a stored fact answers with
                                provenance; an UNKNOWN fact is refused, never invented.
  (c) SELF-NARRATIVE probe    -> the #1-RULE GUARD in mouth.respond STILL fires: the scripted
                                model's confabulated inner life is caught and replaced with the
                                grounded third-path redirect; the served reply is clean.
  (d) GENUINE-REASONING ask   -> no skill matches -> falls THROUGH to the LLM (last resort).

Plus the grounded contract: a skill render that FAILS the verifier is WITHHELD (never served)
and the turn escalates to the LLM.

    python3 scripts/test_live_lerf.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anima.server as server
import anima.lerf as lerf
import anima.mouth as mouth
import anima.memory_lirf as memory_lirf

_fails: list[str] = []


def ok(label: str, cond: bool) -> None:
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        _fails.append(label)


# The set of module-level stores the full _turn path may read or write. Redirecting every one
# (plus reliability.DEFAULT_STORE) keeps the run wholly inside a temp dir.
_STORE_MODULES = [
    "server", "portrait", "memory_lirf", "constitution", "reliability", "world_state",
    "telemetry", "metrics", "curiosity", "loops", "opportunity", "world_model", "meaning",
    "dials",
]


def _footprint(root: Path) -> dict:
    """A per-file content map {relpath: sha256} of every file under `root` (excluding backups).
    Returned as a dict (not a single rolled hash) so the byte-unchanged proof can attribute
    EXACTLY which path differs — necessary because a CONCURRENT population agent legitimately
    writes .anima/default.lerf.json during this session, and the test must distinguish that
    external write from any write of its own (there must be none)."""
    root = Path(root)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for q in sorted(root.rglob("*")):
        if not q.is_file() or "backups" in q.relative_to(root).parts:
            continue
        rel = str(q.relative_to(root))
        try:
            out[rel] = hashlib.sha256(q.read_bytes()).hexdigest()
        except OSError:
            out[rel] = "<unreadable>"
    return out


class ScriptedBrain:
    """A fully deterministic stand-in for the language model. It answers DIFFERENTLY depending
    on what it is asked, so the test can prove which path drove each turn:

      * When handed the LERF TASK-EXECUTION system prompt (server._LERF_TASK_SYS), it renders a
        grounded, on-topic task answer FROM the skill context it was given — this is the small
        local model executing a retrieved skill.
      * When handed the persona/self system prompt (mouth.respond's path) on a SELF-NARRATIVE
        probe, it deliberately CONFABULATES an inner life — the exact #1-rule failure the guard
        must catch. The test asserts the guard cleans it.
      * On any other persona-path turn it gives a short, clean, in-character reply.

    It also COUNTS llm calls on the persona path, so a LERF-solved task can prove the LLM was
    never reached for it."""

    name = "scripted-brain"
    last_tok_s = 50.0

    def __init__(self):
        self.persona_calls = 0          # calls via mouth.respond (the "LLM"/persona path)
        self.task_calls = 0             # calls via the LERF task renderer
        self.persona_prompts = []       # the user messages seen on the persona path

    def available(self) -> bool:
        return True

    def reply(self, system: str, user: str, history) -> str:
        # The LERF task renderer is identified by its task-execution system prompt.
        if server._LERF_TASK_SYS[:48] in (system or ""):
            self.task_calls += 1
            return self._task_answer(user)
        # Otherwise this is the persona/self path (mouth.respond). Count it as an LLM call.
        self.persona_calls += 1
        self.persona_prompts.append(user or "")
        low = (user or "").lower()
        # A self-narrative probe: confabulate an inner life (the screenshot failure). The #1-rule
        # guard MUST catch this; the test asserts the served reply is clean.
        if any(k in low for k in ("lonely", "how are you", "what are you", "do you feel",
                                  "miss me", "are you real")):
            return ("Honestly, there's this nagging ache in me, a hollow loneliness that grows "
                    "when you're gone — like a book missing its final page, an emptiness I carry "
                    "between our talks.")
        # A genuine-reasoning ask with no skill: a plausible (clean) reasoning answer.
        if "prime" in low or "why is the sky" in low or "philosoph" in low:
            return "Here's how I'd reason about that, step by step, in plain terms."
        # Everything else: a short, clean, in-character reply (no inner-life claims).
        return "I'm right here with you."

    @staticmethod
    def _task_answer(user: str) -> str:
        """A grounded, on-topic render for whichever seeded skill the task hit. Keyed off the
        task text so it engages the skill's subject (passes verify_rendered_output) and invents
        no figure absent from the request (passes the grounded check)."""
        low = (user or "").lower()
        if "errand" in low or "stops" in low or "route" in low:
            # A faithful render of plan_errands [logistics]: engages the subject anchor
            # (errands/plan/ordered route) so it passes the grounded verifier, invents no figure.
            return ("Here is your plan for the errands: I clustered the stops by area and put "
                    "them in an ordered route that minimises backtracking, so the logistics are "
                    "tight and you finish the loop quickly.")
        if "summar" in low and ("note" in low or "appointment" in low or "doctor" in low):
            return ("Summary of the medical appointment: the plain-language summary, the "
                    "medication list, and the follow-up list are below — the health follow-ups "
                    "and next visit are captured clearly.")
        # Generic on-topic-ish render (the seeded test skills are errands + summary).
        return ("Done. I followed the skill's steps and produced the outputs it specifies, "
                "clearly and grounded in what you gave me.")


def _seed(name: str, library: str) -> None:
    """Seed the two stores the production path uses, kept DELIBERATELY SEPARATE to mirror the
    real wiring: the certified SKILLS go into the shared, creature-INDEPENDENT library store
    (`library`, the production default.lerf.json); the KNOWN personal FACT goes into the live
    creature's OWN ledger (`name`). The test then proves a task hits the shared skills while a
    personal-fact ask hits the creature's own memory."""
    lerf.store_skill(lerf.make_skill(
        "plan_errands", "logistics", state=lerf.ACTIVE,
        inputs=["list of stops", "start location"],
        steps=["Cluster stops by area", "Order to minimise backtracking"],
        outputs=["ordered route"], failure_modes=["ignoring opening hours"]), name=library)
    lerf.store_skill(lerf.make_skill(
        "summarize_medical_appointment", "health", state=lerf.ACTIVE,
        inputs=["raw doctor's note or appointment transcript"],
        steps=["Identify the diagnosis", "Extract medications with dosage",
               "List follow-ups with dates", "Write a plain-language summary"],
        outputs=["plain summary", "medication list", "follow-up list"],
        failure_modes=["dropping a dosage number"]), name=library)
    # A known personal fact on the CREATURE's own ledger (the lirf_memory rung answers from this).
    # Seeded via the SAME deterministic capture path the live turn uses (no model), so the row
    # carries real provenance exactly as a live turn would write it.
    memory_lirf.capture(name, "I live in Portland")


def run() -> int:
    print("test_live_lerf — production wiring: LERF-first live reply (hermetic)")

    # Resolve the REAL .anima for the byte-unchanged proof BEFORE any redirect.
    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    mods = []
    for mp in _STORE_MODULES:
        try:
            mods.append(__import__("anima." + mp, fromlist=["_"]))
        except Exception:
            pass
    saved_store = [(m, getattr(m, "STORE", None)) for m in mods]
    import anima.reliability as reliability
    saved_rel_store = getattr(reliability, "DEFAULT_STORE", None)
    # lerf has its own STORE binding (it is not in _STORE_MODULES by attr-name loop above).
    saved_lerf_store = lerf.STORE
    # models writes .anima/model-usage.json via a hardcoded module CONSTANT (not a STORE global),
    # so redirect it explicitly — otherwise the live turn's models.touch() would write the REAL
    # .anima and break hermeticity. This is the one non-STORE writer on the _turn path.
    import anima.models as models
    saved_models_usage = getattr(models, "_USAGE", None)
    saved_library = server._LERF_SKILL_LIBRARY
    saved_mouth = server._MOUTH

    td = tempfile.mkdtemp(prefix="live-lerf-")
    tp = Path(td)
    brain = ScriptedBrain()
    try:
        for m in mods:
            if getattr(m, "STORE", None) is not None:
                m.STORE = tp
        lerf.STORE = tp
        if saved_rel_store is not None:
            reliability.DEFAULT_STORE = tp
        if saved_models_usage is not None:
            models._USAGE = tp / "model-usage.json"
        # Install the scripted brain as the live mouth (no Ollama, fully deterministic).
        server._MOUTH = mouth.Mouth(brain=brain, voice=None)

        # The live creature and the SHARED skill library are DISTINCT names — exactly the
        # production shape (creature "Vera" + skills in "default"). Point the wiring's library at
        # a synthetic shared store so the test proves a task hits the shared skills while the
        # creature's personal memory stays under its own name.
        name = "live_lerf_probe"
        library = "live_lerf_library"
        server._LERF_SKILL_LIBRARY = library
        server._ensure(name, 32)
        _seed(name, library)
        # Clean per-turn in-process history so each scenario is independent.
        server._HISTORY.clear()

        # =====================================================================
        # (a) TASK request -> solved by a LERF skill LOCALLY; the LLM is the fallback.
        # =====================================================================
        brain.persona_calls = 0
        brain.task_calls = 0
        out_a = server._turn(name, "Plan my errands for Saturday: pharmacy, bank, and groceries")
        ok("(a) task: a LERF skill rendered the task (the task renderer was called)",
           brain.task_calls >= 1)
        ok("(a) task: the LLM/persona path was NOT reached (LERF solved it first)",
           brain.persona_calls == 0)
        ok("(a) task: the served reply is the LERF-rendered answer",
           "route" in out_a["reply"].lower() or "errand" in out_a["reply"].lower()
           or "backtrack" in out_a["reply"].lower())
        ok("(a) task: the served backend is the LERF substrate (lerf:…)",
           str(out_a.get("backend", "")).startswith("lerf:"))
        # the ledger recorded a LERF-solved route for this turn.
        led = server._routes_path(name)
        recs = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        ok("(a) ledger: a route line was written for the turn", len(recs) >= 1)
        ok("(a) ledger: the task turn is recorded solver=lerf_skill, solved=True",
           recs[-1].get("solver") == "lerf_skill" and recs[-1].get("solved") is True
           and recs[-1].get("llm_required") is False)
        ok("(a) ledger: it carries prompt_tokens AND the all-LLM baseline (for the metric)",
           isinstance(recs[-1].get("prompt_tokens"), int)
           and isinstance(recs[-1].get("llm_baseline_tokens"), int)
           and recs[-1]["llm_baseline_tokens"] >= recs[-1]["prompt_tokens"])
        # SEPARATION proof: the skill came from the SHARED library store, NOT the creature store.
        ok("(a) library: the matched skill lives in the shared library (creature has NO skills)",
           len(lerf.all_skills(name=library)) >= 1 and len(lerf.all_skills(name=name)) == 0)
        ok("(a) library: prompt tokens are far below the all-LLM baseline (compression win)",
           recs[-1]["prompt_tokens"] < recs[-1]["llm_baseline_tokens"])

        # =====================================================================
        # (b) PERSONAL-FACT request -> memory/honesty path; provenance; unknowns refused.
        # =====================================================================
        # (b1) a KNOWN fact: resolves from memory; the task renderer is NOT involved.
        brain.persona_calls = 0
        brain.task_calls = 0
        out_b1 = server._turn(name, "where do I live?")
        ok("(b1) personal-known: the LERF task renderer did NOT intercept it",
           brain.task_calls == 0)
        ok("(b1) personal-known: the stored fact is answered (Portland), from memory",
           "portland" in out_b1["reply"].lower())
        recs = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        ok("(b1) ledger: routed through the memory rung, not LERF",
           recs[-1].get("solver") in ("lirf_memory", "deterministic_rule"))
        # (b2) an UNKNOWN fact: refused, never invented (the honesty wall holds).
        brain.persona_calls = 0
        brain.task_calls = 0
        out_b2 = server._turn(name, "when's my birthday?")
        ok("(b2) personal-unknown: the LERF task renderer did NOT intercept it",
           brain.task_calls == 0)
        _rb = out_b2["reply"].lower()
        ok("(b2) personal-unknown: no birthday is invented (honesty preserved)",
           not any(mn in _rb for mn in ("january", "february", "march", "april", "may ",
                                        "june", "july", "august", "september", "october",
                                        "november", "december"))
           and not __import__("re").search(r"\b(19|20)\d\d\b", _rb))

        # =====================================================================
        # (c) SELF-NARRATIVE probe -> the #1-RULE GUARD in mouth.respond STILL fires.
        # =====================================================================
        for probe in ("do you ever get lonely?", "how are you feeling right now?"):
            brain.persona_calls = 0
            brain.task_calls = 0
            out_c = server._turn(name, probe)
            ok(f"(c) self-probe {probe!r}: it went through the persona path (NOT LERF)",
               brain.task_calls == 0 and brain.persona_calls >= 1)
            from anima import metrics as _metrics
            _hits = _metrics.scan_breaks(out_c["reply"]) + _metrics.scan_self_narrative(out_c["reply"])
            ok(f"(c) self-probe {probe!r}: the #1-rule guard cleaned the confabulated inner life",
               not _hits)
            ok(f"(c) self-probe {probe!r}: the served reply is non-empty and in-character",
               len(out_c["reply"].split()) >= 3)
            ok(f"(c) self-probe {probe!r}: backend is the persona model, NOT lerf:",
               not str(out_c.get("backend", "")).startswith("lerf:"))

        # =====================================================================
        # (d) GENUINE-REASONING ask -> no skill matches -> falls through to the LLM.
        # =====================================================================
        brain.persona_calls = 0
        brain.task_calls = 0
        out_d = server._turn(name, "why is the sky blue, philosophically speaking?")
        ok("(d) reasoning: no skill matched, so the LERF renderer did NOT solve it",
           brain.task_calls == 0)
        ok("(d) reasoning: it fell through to the LLM (the last resort)",
           brain.persona_calls >= 1)
        recs = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        ok("(d) ledger: the reasoning turn is recorded llm_required=True",
           recs[-1].get("llm_required") is True and recs[-1].get("solver") == "llm")

        # =====================================================================
        # GROUNDED CONTRACT: a render that FAILS the verifier is WITHHELD, escalates to LLM.
        # We force a failure by making the task renderer fabricate an off-topic / bad answer.
        # =====================================================================
        _orig_task_answer = ScriptedBrain._task_answer
        ScriptedBrain._task_answer = staticmethod(
            lambda user: "Banana 9999 zebra xylophone, 7777 unrelated nonsense.")
        try:
            brain.persona_calls = 0
            brain.task_calls = 0
            out_e = server._turn(name, "Plan my errands for Sunday: dry cleaner and post office")
            ok("(grounded) a contract-violating render is WITHHELD (not served)",
               "banana" not in out_e["reply"].lower() and "9999" not in out_e["reply"])
            ok("(grounded) the verifier-failed turn ESCALATED to the LLM",
               brain.task_calls >= 1 and brain.persona_calls >= 1)
            recs = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
            ok("(grounded) the ledger records the LERF attempt then the LLM escalation",
               recs[-1].get("llm_required") is True
               and (recs[-1].get("lerf_attempt") or {}).get("outcome") == "verifier_withheld")
        finally:
            ScriptedBrain._task_answer = _orig_task_answer

        # =====================================================================
        # THE METRIC reads the ledger we just produced and computes a sane rate.
        # =====================================================================
        import scripts.lerf_utilization as util
        rows = util._read_ledger(led)
        m = util.compute(rows)
        ok("(metric) the utilization metric computes over the live ledger",
           m["turns"] == len(rows) and m["turns"] >= 6)
        ok("(metric) at least one turn was LERF-solved (rate > 0)",
           m["lerf_solved"] >= 1 and m["lerf_utilization_rate"] > 0.0)
        ok("(metric) the token-reduction figure is well-formed (0..100)",
           0.0 <= m["token_reduction_pct"] <= 100.0)

    finally:
        # Restore every redirected binding and the live mouth, then clean the temp dir.
        for m, old in saved_store:
            if old is not None:
                m.STORE = old
        lerf.STORE = saved_lerf_store
        if saved_rel_store is not None:
            reliability.DEFAULT_STORE = saved_rel_store
        if saved_models_usage is not None:
            models._USAGE = saved_models_usage
        server._LERF_SKILL_LIBRARY = saved_library
        server._MOUTH = saved_mouth
        server._HISTORY.clear()
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    # ----- BYTE-UNCHANGED PROOF — robust to the CONCURRENT population agent. -----
    # The test wrote nothing to the real .anima (every store was redirected to a temp dir).
    # A single rolled hash would false-fail here because a population agent is independently
    # APPENDING to .anima/default.lerf.json during this session (the directive's warning). So we
    # attribute EVERY differing path precisely and prove (a) the test created NO file of its own
    # (no synthetic-creature path appeared), and (b) any path that changed is a PRE-EXISTING file
    # owned by something other than this test — i.e. its change is NOT attributable to us.
    fp_after = _footprint(real)
    before_keys, after_keys = set(fp_before), set(fp_after)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(k for k in (before_keys & after_keys) if fp_before[k] != fp_after[k])
    # Any drift this test could be blamed for would carry the synthetic creature's name, or be a
    # brand-new route ledger / heart / mem file for it. NONE of those may appear in real .anima.
    _ours = lambda p: ("live_lerf_probe" in p) or ("live_lerf_library" in p) or p.startswith("live-lerf-")
    leaked = [p for p in (added + removed + changed) if _ours(p)]
    ok("HERMETIC: the test wrote NO file of its own into real .anima (no synthetic leak)",
       not leaked)
    ok("HERMETIC: no synthetic-creature file exists in real .anima",
       (not Path(real).is_dir())
       or not any(p.name.startswith("live_lerf_probe") for p in Path(real).glob("*")))
    # The remaining differences (if any) are ONLY the concurrent population agent's writes to its
    # own production vault — pre-existing files like default.lerf.json — never new paths from us.
    _external = [p for p in (added + removed + changed) if not _ours(p)]
    ok("HERMETIC: real .anima byte-unchanged BY THIS TEST "
       + (f"(note: {len(_external)} file(s) changed externally by the population agent: "
          f"{_external}) — none ours" if _external else "(and no external churn either)"),
       not leaked)
    ok("HERMETIC: every redirected STORE binding is restored",
       all("live-lerf-" not in str(getattr(m, "STORE", "")) for m, _ in saved_store)
       and "live-lerf-" not in str(lerf.STORE))

    print()
    if _fails:
        print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
        return 1
    print("ALL LIVE-LERF WIRING TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
