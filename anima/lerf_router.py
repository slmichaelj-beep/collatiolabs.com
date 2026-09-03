"""lerf_router — Wave 2. The RUNTIME ROUTING LADDER for the LERF substrate.

THE QUESTION this answers. Wave 1 (anima/lerf.py) proved a skill can be moved OUT of the
weights into an inspectable, retrievable object, and that retrieving it beats stuffing the
prompt by 4-25x. But a runtime still has to DECIDE, per task, *which* of its escalating
faculties to spend — and the rule that makes the whole stack cheap is: **use the cheapest
faculty that is actually SUFFICIENT, and stop.** A deterministic rule is ~free; a LIRF lookup
is microseconds; a LERF skill is a few hundred tokens of local context; a small local model is
seconds and watts; a cloud call is dollars and your data leaving the Mac. You do not pay for a
rung you didn't need.

This module is that ladder. For a task it walks six rungs and returns the FIRST that suffices,
with an explanation you can read:

    1. DETERMINISTIC RULE   — does route.py already own this turn (a message read, a send, a
                              known-fact question)? Then code answers with ground truth; no
                              model is involved at all. (cost: ~0)
    2. LIRF MEMORY          — is the answer a fact already on the ledger ("when's my birthday")?
                              Then memory answers it, with provenance. (cost: a lookup)
    3. LERF SKILL           — does a verified/active skill/procedure cover this task
                              ("summarize this doctor's note")? Then retrieve that one object as
                              compact context. (cost: ~hundreds of tokens)
    4. SMALL LOCAL + SKILL  — render the answer with a SMALL local model, handed the retrieved
                              skill as its whole context (not a stuffed transcript). (cost: a
                              local generation)
    5. VERIFIER             — check the small model's render against the skill's CONTRACT
                              (lerf.verify_rendered_output — GROUNDED, never a rubber stamp). If
                              it passes, we are DONE locally. (cost: a deterministic check)
    6. ESCALATE TO CLOUD    — ONLY if the verifier fails (or nothing above had standing AND a
                              cloud brain is available) do we spend a larger/cloud model.
                              (cost: $$ + data egress — the last resort, never the default.)

Every rung the router returns carries the SAME three fields, because a routing decision you
cannot explain is just a different black box:

    {
      "route":    "lerf_skill",                                   # which rung answered
      "why":      "matched active skill summarize_medical_appointment @ 0.92",
      "fallback": "small local model renders with the skill; cloud critic if verifier fails",
    }

(plus diagnostics: the rung index, the cheaper rungs it ruled out, the selected object id, the
cost tier, and — at the verifier rung — the grounded verdict.)

DECIDES + EXPLAINS ONLY THIS WAVE. The router does not call a model, does not touch
mouth.respond, does not write to the server. It is a pure planner over lerf.py + the existing
organs.router / memory_lirf / route seams, fully unit-testable offline. The single seam where
Wave 3 wires the chosen route into the live reply is marked exactly once below — search
"ATTACHES: Wave 3". Until then the live reply is UNCHANGED.

Built to the seams, like organs/router.py: the live modules are imported when present and fall
back to contract-faithful shims when this file is exercised standalone, so `_selftest()` runs
with zero unbuilt dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# --- LERF seam: the Wave-1 substrate this router plans over. This is a hard, in-package
#     dependency (the router has no reason to exist without it), imported directly. ----------
from . import lerf


# --- route.py seam (rung 1): the existing deterministic capability/known-fact router. We DEFER
#     to it rather than re-implement its regexes. Best-effort: absent in isolation -> no rule. -
try:  # pragma: no cover - import wiring
    from . import route as _route
except Exception:  # pragma: no cover - isolation fallback
    _route = None


# --- memory_lirf seam (rung 2): the fact ledger. We ask it whether the task is a known-fact
#     question it can answer from a stored row with provenance. ---------------------------------
try:  # pragma: no cover - import wiring
    from . import memory_lirf as _lirf
except Exception:  # pragma: no cover - isolation fallback
    _lirf = None


# --- cloud seam (rung 6): only to learn whether a cloud brain is even available; this module
#     never CALLS it. Absent -> treated as "no cloud", which simply keeps everything local. ----
try:  # pragma: no cover - import wiring
    from . import cloud as _cloud
except Exception:  # pragma: no cover - isolation fallback
    _cloud = None


# ---------------------------------------------------------------------------
# Cost tiers — the ordering the ladder enforces. Lower is cheaper; the router always
# returns the cheapest SUFFICIENT rung, so these double as the rung's price tag in the
# explanation. (Indicative, not calibrated currency — the point is the strict ordering
# free < lookup < tokens < local-gen < cloud that makes "cheapest sufficient" meaningful.)
# ---------------------------------------------------------------------------
COST = {
    "deterministic_rule": 0,    # code answers; no model, no tokens
    "lirf_memory": 1,           # a ledger lookup
    "lerf_skill": 2,            # retrieve one compact object (~hundreds of tokens)
    "small_local": 3,           # a local generation
    "verifier": 3,             # a deterministic check riding on the local render
    "cloud": 9,                 # a larger/cloud model — $$ + data egress
}

# The retrieval score at/above which a LERF skill is considered a confident match for the task
# (below this, the rung abstains and the ladder falls through to the local/cloud render). Tuned
# so the seed skills' on-topic tasks clear it and an unrelated task does not.
SKILL_MATCH_FLOOR = 0.30


@dataclass(frozen=True)
class Route:
    """One routing decision: the cheapest sufficient rung for a task, fully explained.

    The three contract fields (`route`, `why`, `fallback`) are what every caller reads; the
    rest are diagnostics for the trace. Frozen + value-equal so `_selftest` can assert
    determinism (same task -> identical Route)."""

    route: str                                  # the rung that answered ("lerf_skill", …)
    why: str                                    # human-readable justification
    fallback: str                               # what happens if this rung proves insufficient
    rung: int = 0                               # 1..6, the ladder position that answered
    cost_tier: int = 0                          # COST[route] — the price tag
    considered: list = field(default_factory=list)   # cheaper rungs ruled out, with reasons
    skill_id: Optional[str] = None              # the chosen LERF object id, when one was used
    skill_name: Optional[str] = None
    score: Optional[float] = None               # the retrieval score, when a skill matched
    escalated: bool = False                     # True iff this route spends the cloud
    grounded: Optional[bool] = None             # verifier verdict, when the verifier ran

    def as_dict(self) -> dict:
        """The {route, why, fallback, …} dict — the shape the directive specifies and the form
        a trace/log records. Pure data; no live objects."""
        return {
            "route": self.route,
            "why": self.why,
            "fallback": self.fallback,
            "rung": self.rung,
            "cost_tier": self.cost_tier,
            "considered": list(self.considered),
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "score": self.score,
            "escalated": self.escalated,
            "grounded": self.grounded,
        }


# ---------------------------------------------------------------------------
# Rung probes — each is PURE and returns its evidence (or None), never a side effect. The
# ladder (`route_task`) calls them in cost order and stops at the first that suffices.
# ---------------------------------------------------------------------------

def _rule_hit(name: str, task: str) -> Optional[dict]:
    """RUNG 1 — does a DETERMINISTIC rule own this turn? Defer to route.py: if it claims the
    turn (a capability like a message read / send, or a known-fact question it answers with
    provenance), return its ground-truth note dict. None otherwise. Best-effort; never raises."""
    if _route is None:
        return None
    try:
        note = _route.route(name, task)
    except Exception:
        return None
    return note if isinstance(note, dict) and note.get("note") else None


# The cheap, deterministic test for "is this task even a known-fact QUESTION?" — reused from the
# same question->trait table memory_lirf/route answer from, so rung 2 routes precisely (a "when's
# my birthday" hits, "summarize this note" does not). Falls back to a tiny built-in in isolation.
_FACT_QUESTION_TABLE = (
    list(getattr(_lirf, "_Q_TRAITS", []) or []) if _lirf is not None else []
) or [
    (re.compile(r"\bbirthday|\bbday|\bborn\b|date of birth\b", re.I), "birthday"),
    (re.compile(r"\bwhere (?:do|am) i (?:live|living)|where i live\b", re.I), "lives"),
    (re.compile(r"\bmy name\b|what'?s my name|who am i\b", re.I), "name"),
]


def _asks_known_fact(task: str) -> Optional[str]:
    """The trait slug a task asks about, if it is a known-fact question (else None). Pure regex
    over the shared table — no store, no model. This gates rung 2 cheaply before any load."""
    for rx, trait in _FACT_QUESTION_TABLE:
        try:
            if rx.search(task or ""):
                return trait
        except Exception:
            continue
    return None


def _lirf_hit(name: str, task: str) -> Optional[dict]:
    """RUNG 2 — does LIRF MEMORY answer this? Only if the task is a known-fact question AND the
    creature actually has that fact on the active ledger. Returns {trait, value, source} or None.
    Never confabulates: a fact-question with NO stored row falls through (the honesty wall lives
    in route.py/mouth; the router just declines to claim memory answered)."""
    trait = _asks_known_fact(task)
    if trait is None or _lirf is None:
        return None
    try:
        f = _lirf.Facts.load(name)
        row = f.lookup(getattr(_lirf, "SELF", "you"), trait)
    except Exception:
        return None
    if not row:
        return None
    return {"trait": row.get("trait", trait), "value": row.get("value"),
            "source": row.get("source", "lirf"), "confidence": row.get("confidence")}


def _skill_hit(task: str, name: str) -> Optional[tuple]:
    """RUNGS 3-5 trigger — the best ACTIVE LERF skill for the task and its retrieval score, iff
    that score clears SKILL_MATCH_FLOOR. Returns (skill, score) or None. Pure: lerf.retrieve is
    deterministic keyword matching, no model."""
    skills = lerf.retrieve_skills(task, limit=1, name=name)
    if not skills:
        return None
    sk = skills[0]
    score = lerf._score(sk, lerf._kw(task), task)
    if score < SKILL_MATCH_FLOOR:
        return None
    return sk, round(float(score), 2)


def _cloud_available(caps_state: dict) -> bool:
    """Is a larger/cloud brain usable for rung 6? Reads the per-turn caps the live turn carries
    (cloud_on / cloud_available), and — best-effort — the cloud module's own view. Never calls
    the cloud; only asks whether it COULD be spent."""
    if caps_state.get("cloud_on") or caps_state.get("cloud_available"):
        return True
    if _cloud is not None:
        for probe in ("available", "is_available", "is_cloud"):
            fn = getattr(_cloud, probe, None)
            if callable(fn):
                try:
                    if bool(fn()):
                        return True
                except Exception:
                    pass
    return False


# ---------------------------------------------------------------------------
# THE LADDER.
# ---------------------------------------------------------------------------

def route_task(task: str, *, name: str = "default", caps_state: Optional[dict] = None,
               rendered: Optional[str] = None, inputs: Optional[dict] = None) -> Route:
    """Pick the CHEAPEST SUFFICIENT rung for `task` and explain it. Deterministic; no model.

    Walks the six rungs in cost order and returns the first that suffices:

      1 deterministic_rule  · route.py owns the turn (capability / known-fact-with-provenance)
      2 lirf_memory         · a stored fact answers a known-fact question
      3 lerf_skill          · a verified/active skill covers the task -> retrieve it as context
      4 small_local         · render with a SMALL local model, handed that skill (Wave 3 wires
                              the live generation; this wave plans + names the rung)
      5 verifier            · grounded-check the render against the skill CONTRACT
      6 cloud               · escalate to a larger/cloud model — only on verifier failure, or no
                              local standing with a cloud available

    Optional `rendered` (+ `inputs`) lets a caller that ALREADY produced a small-model answer
    have the router adjudicate rung 5 for real: if the render violates the skill's contract
    (fabricated figure, off-topic, empty), the router escalates to the cloud critic; if it
    passes, the route is the verified local render. Without `rendered`, the router plans up to
    rung 4 and names the verifier/cloud as the fallback (the live wiring is Wave 3).

    `caps_state` recognises cloud_on / cloud_available / cloud_model / needs_cloud (the same
    dict shape organs.router.route reads). Returns a :class:`Route`."""
    caps_state = dict(caps_state or {})
    considered: list[dict] = []

    # ── RUNG 1: deterministic rule ────────────────────────────────────────────────────────
    rule = _rule_hit(name, task)
    if rule is not None:
        kind = "send" if rule.get("send") else "ground-truth note"
        return Route(
            route="deterministic_rule",
            why=f"route.py owns this turn ({kind}) — code answers with ground truth, no model",
            fallback="if the rule had not matched: try LIRF memory, then a LERF skill",
            rung=1, cost_tier=COST["deterministic_rule"], considered=considered)
    considered.append({"rung": "deterministic_rule", "ruled_out": "no route.py rule matched"})

    # ── RUNG 2: LIRF memory ───────────────────────────────────────────────────────────────
    mem = _lirf_hit(name, task)
    if mem is not None:
        val = lerf._obj_to_text(mem["value"]) if not isinstance(mem["value"], str) else mem["value"]
        return Route(
            route="lirf_memory",
            why=(f"known-fact question answered from the ledger: {mem['trait']} = {val!r} "
                 f"(provenance: {mem.get('source')}) — a lookup, no model"),
            fallback="if the fact were not on record: ask the user honestly (never confabulate)",
            rung=2, cost_tier=COST["lirf_memory"], considered=considered)
    if _asks_known_fact(task) is not None:
        considered.append({"rung": "lirf_memory",
                           "ruled_out": "fact-question but value not on the ledger"})
    else:
        considered.append({"rung": "lirf_memory", "ruled_out": "not a known-fact question"})

    # ── RUNG 3: LERF skill ────────────────────────────────────────────────────────────────
    hit = _skill_hit(task, name)
    if hit is None:
        # Nothing above had standing AND no skill covers the task. The honest move is to
        # escalate to the cloud IF one is available; otherwise say so plainly (no local faculty
        # is sufficient, and we will not pretend one is).
        considered.append({"rung": "lerf_skill",
                           "ruled_out": f"no active skill scored >= {SKILL_MATCH_FLOOR}"})
        if _cloud_available(caps_state):
            return Route(
                route="cloud",
                why="no deterministic rule, no stored fact, and no LERF skill covers this task "
                    "— nothing local is sufficient, so escalate to the cloud",
                fallback="if cloud were unavailable: tell the user this is out of scope locally",
                rung=6, cost_tier=COST["cloud"], considered=considered, escalated=True)
        return Route(
            route="no_local_faculty",
            why="no deterministic rule, no stored fact, no LERF skill — and no cloud available",
            fallback="author a skill for this task, or answer directly and capture the result",
            rung=6, cost_tier=COST["cloud"], considered=considered)

    sk, score = hit
    skill_line = f"{sk['name']} @ {score}"
    # The skill matched. The cheapest sufficient *use* of it depends on whether the caller asked
    # us only to PLAN (no render handed in) or to ADJUDICATE a render it already produced.

    # ── RUNGS 4-5: small local render + grounded verifier (adjudicated when a render is given) ─
    if rendered is not None:
        verdict = lerf.verify_rendered_output(sk, rendered, inputs=inputs)
        considered.append({"rung": "lerf_skill",
                           "used": f"retrieved {skill_line} as the small model's context"})
        if verdict["ok"]:
            # rung 5 PASSED: the small local model + retrieved skill produced a contract-faithful
            # answer. We are DONE locally — the cloud is never spent.
            return Route(
                route="small_local_verified",
                why=(f"small local model rendered with skill {skill_line}; the verifier confirms "
                     f"the output meets the skill contract (coverage {verdict.get('coverage')}) "
                     f"— done locally, cloud not needed"),
                fallback="had the verifier failed: escalate to a cloud critic to re-render",
                rung=5, cost_tier=COST["small_local"], considered=considered,
                skill_id=sk["id"], skill_name=sk["name"], score=score, grounded=True)
        # rung 5 FAILED: the render violates the contract (fabrication / off-topic / empty). THIS
        # is the one case the directive escalates for — the verifier is the gate that decides the
        # cloud is warranted, not a blanket default.
        if _cloud_available(caps_state):
            return Route(
                route="cloud",
                why=(f"small local render with skill {skill_line} FAILED the grounded verifier "
                     f"({'; '.join(verdict['reasons'])}) — escalate to a cloud critic"),
                fallback="if cloud were unavailable: return the failure, never the bad render",
                rung=6, cost_tier=COST["cloud"], considered=considered,
                skill_id=sk["id"], skill_name=sk["name"], score=score,
                escalated=True, grounded=False)
        return Route(
            route="verifier_failed_no_cloud",
            why=(f"render FAILED the verifier ({'; '.join(verdict['reasons'])}) and no cloud is "
                 f"available — the bad render is withheld (GROUNDED: never serve it)"),
            fallback="re-render locally, or surface the contract violation to the user",
            rung=5, cost_tier=COST["verifier"], considered=considered,
            skill_id=sk["id"], skill_name=sk["name"], score=score, grounded=False)

    # No render handed in: PLAN up to rung 4 and name the verifier/cloud as the fallback. This is
    # the steady-state route for "a skill covers this; render it locally with the compact context".
    #
    # ATTACHES: Wave 3 — HERE is the single live-wiring seam. A runtime (server._turn / the Mouth)
    # takes this Route, calls lerf.compile_procedure(task)+run_procedure to assemble the plan, and
    # drives a SMALL local model with `assemble_skill_context(task)` as its whole prompt — then
    # passes the model's output back through `route_task(..., rendered=output, inputs=...)` so rung
    # 5 (verify_rendered_output) adjudicates it and escalates to the cloud ONLY on failure. This
    # wave stops at the plan; the live reply is unchanged.
    return Route(
        route="lerf_skill",
        why=f"matched active skill {skill_line} — retrieve it as compact context for a small "
            f"local model (vs stuffing the prompt)",
        fallback="small local model renders with the skill; if the verifier (contract check) "
                 "fails, escalate to a cloud critic",
        rung=3, cost_tier=COST["lerf_skill"], considered=considered,
        skill_id=sk["id"], skill_name=sk["name"], score=score)


def explain_route(task: str, *, name: str = "default", caps_state: Optional[dict] = None,
                  rendered: Optional[str] = None, inputs: Optional[dict] = None) -> str:
    """Render a routing decision as inspectable prose — the human-readable companion to the
    {route, why, fallback} dict. Shows the chosen rung, its reason and fallback, and the cheaper
    rungs it ruled out (so you can SEE the ladder skip free faculties for cause)."""
    r = route_task(task, name=name, caps_state=caps_state, rendered=rendered, inputs=inputs)
    L = [f"TASK: {task}",
         f"  ROUTE:    {r.route}  (rung {r.rung}, cost tier {r.cost_tier}"
         + (", ESCALATED to cloud" if r.escalated else "") + ")",
         f"  WHY:      {r.why}",
         f"  FALLBACK: {r.fallback}"]
    if r.skill_name:
        L.append(f"  SKILL:    {r.skill_name}  (id={r.skill_id}, score={r.score})")
    if r.grounded is not None:
        L.append(f"  VERIFIER: {'PASSED' if r.grounded else 'FAILED'} (grounded contract check)")
    if r.considered:
        L.append("  RULED OUT (cheaper rungs that did not suffice):")
        for c in r.considered:
            tag = c.get("ruled_out") or c.get("used") or ""
            L.append(f"    - {c.get('rung')}: {tag}")
    return "\n".join(L)


# ===================================================================================
# SELFTEST — `python3 -m anima.lerf_router --selftest`. FULLY HERMETIC: a synthetic creature
# in a throwaway temp store, with EVERY store the LERF/LIRF load path may write redirected for
# the whole block (lerf.STORE on both bindings + memory_lirf.STORE + constitution.STORE +
# reliability.DEFAULT_STORE), and the real .anima asserted byte-UNCHANGED around it. Same
# gold-standard discipline as lerf._selftest / memory_lirf._selftest / experience.py.
# ===================================================================================

def _footprint(root):
    from pathlib import Path
    import hashlib
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
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    import tempfile
    import secrets
    from pathlib import Path
    fails: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("lerf_router self-test")

    # --- pure, store-free checks first --------------------------------------------------
    ok("cost tiers are strictly ordered free < lookup < tokens < local < cloud",
       COST["deterministic_rule"] < COST["lirf_memory"] < COST["lerf_skill"]
       < COST["small_local"] <= COST["verifier"] < COST["cloud"])
    ok("a known-fact question is detected by the cheap gate",
       _asks_known_fact("when's my birthday?") is not None)
    ok("a skill task is NOT mistaken for a known-fact question",
       _asks_known_fact("summarize this doctor's note into reminders") is None)

    # --- FULLY HERMETIC store block -----------------------------------------------------
    real = lerf.STORE if Path(lerf.STORE).is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="lerfrouter-self-")
    tp = Path(td)
    # Redirect EVERY store the LERF/LIRF load path may write (both lerf bindings — under
    # `-m anima.lerf_router` this is __main__'s import, distinct from the package's — plus the
    # LIRF ledger, the constitution continuity ledger, and the reliability backup root).
    targets = [(lerf, "STORE")]
    try:
        import anima.lerf as _pkglerf
        if _pkglerf is not lerf:
            targets.append((_pkglerf, "STORE"))
    except Exception:
        pass
    for modpath, attr in (("anima.memory_lirf", "STORE"),
                          ("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            targets.append((__import__(modpath, fromlist=["_"]), attr))
        except Exception:
            pass
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "lerfrouter_selftest_" + secrets.token_hex(3)

        # Seed two ACTIVE skills the router can match on.
        lerf.store_skill(lerf.make_skill(
            "summarize_medical_appointment", "health", state=lerf.ACTIVE,
            inputs=["raw doctor's note or appointment transcript"],
            steps=["Identify the diagnosis", "Extract medications with dosage",
                   "List follow-ups with dates", "Write a plain-language summary"],
            outputs=["plain summary", "medication list", "follow-up list"],
            failure_modes=["dropping a dosage number"]), name=nm)
        lerf.store_skill(lerf.make_skill(
            "plan_errands", "logistics", state=lerf.ACTIVE,
            inputs=["list of stops", "start location"],
            steps=["Cluster stops by area", "Order to minimise backtracking"],
            outputs=["ordered route"], failure_modes=["ignoring opening hours"]), name=nm)

        # ── RUNG 3: a skill task routes to lerf_skill, names the right skill + fallback ──
        r = route_task("Summarize this doctor's note and turn it into reminders", name=nm)
        ok("rung3: a skill task routes to lerf_skill", r.route == "lerf_skill")
        ok("rung3: it names the correct matched skill",
           r.skill_name == "summarize_medical_appointment")
        ok("rung3: the {route,why,fallback} contract is fully populated",
           bool(r.as_dict()["route"]) and bool(r.as_dict()["why"]) and bool(r.as_dict()["fallback"]))
        ok("rung3: the why explains the match with a score",
           "summarize_medical_appointment" in r.why and "@" in r.why)
        ok("rung3: the fallback names the verifier->cloud path",
           "verifier" in r.fallback and "cloud" in r.fallback)
        ok("rung3: it ruled out the two cheaper rungs (rule, memory)",
           any(c["rung"] == "deterministic_rule" for c in r.considered)
           and any(c["rung"] == "lirf_memory" for c in r.considered))
        ok("rung3: it did NOT escalate (a local skill is sufficient)", r.escalated is False)

        # determinism
        ok("router is deterministic (same task -> identical Route)",
           route_task("plan my errands for saturday", name=nm)
           == route_task("plan my errands for saturday", name=nm))

        # ── RUNG 5 PASS: a faithful render is verified locally; cloud NOT spent ──────────
        good = ("Summary: your blood pressure is stage 1. Medication: lisinopril 10 mg once "
                "daily in the morning. Follow-up: book labs before the next visit.")
        rv = route_task("Summarize this doctor's note into reminders", name=nm,
                        rendered=good,
                        inputs={"note": "stage 1 hypertension; lisinopril 10 mg once daily "
                                        "in the morning; get labs before next visit"})
        ok("rung5: a contract-faithful local render verifies -> small_local_verified",
           rv.route == "small_local_verified" and rv.grounded is True)
        ok("rung5: a verified local render does NOT escalate to cloud", rv.escalated is False)

        # ── RUNG 5 FAIL -> RUNG 6: a fabricated-figure render escalates to the cloud ─────
        bad = ("Take lisinopril 999 mg twice daily; your reading was 250 over 190; "
               "follow up on the 47th.")
        rb = route_task("Summarize this doctor's note into reminders", name=nm,
                        rendered=bad,
                        inputs={"note": "stage 1 hypertension discussed; no doses or figures given"},
                        caps_state={"cloud_on": True, "cloud_model": "claude"})
        ok("rung6: a render that FAILS the grounded verifier escalates to cloud",
           rb.route == "cloud" and rb.escalated is True and rb.grounded is False)
        ok("rung6: the why cites the verifier failure as the escalation reason",
           "verifier" in rb.why.lower() or "fabricated" in rb.why.lower())
        # GROUNDED proof: the SAME bad render with NO cloud is WITHHELD, never served.
        rb2 = route_task("Summarize this doctor's note into reminders", name=nm,
                         rendered=bad,
                         inputs={"note": "stage 1 hypertension discussed; no figures given"},
                         caps_state={})
        ok("grounded: a failed render with no cloud is WITHHELD (never the bad output)",
           rb2.route == "verifier_failed_no_cloud" and rb2.grounded is False)

        # ── no-skill task: escalate to cloud iff available, else say so honestly ────────
        rno = route_task("compose a symphony in the style of Mahler", name=nm,
                         caps_state={"cloud_on": True})
        ok("no-skill + cloud: escalates to cloud (nothing local suffices)",
           rno.route == "cloud" and rno.escalated is True)
        rno2 = route_task("compose a symphony in the style of Mahler", name=nm, caps_state={})
        ok("no-skill + no cloud: honestly reports no local faculty (no confabulation)",
           rno2.route == "no_local_faculty")
        ok("no-skill: the cheaper rungs are all recorded as ruled out",
           {"deterministic_rule", "lirf_memory", "lerf_skill"}
           <= {c["rung"] for c in rno2.considered})

        # ── explain_route renders the ladder inspectably ────────────────────────────────
        prose = explain_route("Summarize this doctor's note into reminders", name=nm)
        ok("explain_route: shows the chosen route + why + fallback",
           "ROUTE:" in prose and "WHY:" in prose and "FALLBACK:" in prose)
        ok("explain_route: shows the ruled-out cheaper rungs",
           "RULED OUT" in prose and "lirf_memory" in prose)

        # ── the LIRF-memory rung: with no fact on the (synthetic) ledger, a fact-question
        #    correctly does NOT claim memory answered — it falls through honestly. ────────
        rfact = route_task("when's my birthday?", name=nm, caps_state={})
        ok("rung2: a fact-question with no stored value does NOT claim lirf_memory",
           rfact.route != "lirf_memory")
        ok("rung2: it recorded WHY memory was ruled out (fact not on ledger)",
           any(c["rung"] == "lirf_memory" and "ledger" in c.get("ruled_out", "")
               for c in rfact.considered))

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    # --- BYTE-UNCHANGED PROOF ------------------------------------------------------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic router file leaked into real .anima",
       (not Path(real).is_dir())
       or not any(p.name.startswith("lerfrouter_selftest_") for p in Path(real).glob("lerf*")))
    restored_ok = all("lerfrouter-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE/DEFAULT_STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LERF_ROUTER SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
