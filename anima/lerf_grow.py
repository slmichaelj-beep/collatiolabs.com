"""
lerf_grow — AUTONOMOUS LEARNING. LERF Phase 6: the "[x] Grow Intelligence" engine.

THE PROMISE. Phase 3 (anima/lerf_distill.py) can turn ONE named task into a certified,
active, provenance-stamped skill by interviewing a teacher model and pushing the winner
through the real Wave-2 gate. Phase 6 makes that loop AUTONOMOUS: during idle time Vera can
notice the GAPS in her active skill library, decide what task-skill to learn next, distill it,
and gate it — growing her own intelligence over time without a human authoring each skill.

THE CARDINAL RULE — DEFAULT-OFF, PROVABLY INERT. This is the one non-negotiable. The engine
ships OFF and stays OFF until the user EXPLICITLY enables it in Settings. While OFF:

  * ZERO autonomous activity — the loop is a no-op that grows nothing.
  * ZERO paid teacher calls — no cloud is imported, no key is read, no spend file is written.
  * $0 — provably. The selftest asserts the OFF path imports no cloud, makes no call, and
    leaves the store byte-unchanged.

The switch is a per-creature capability flag, ``grow_intelligence``, persisted default-OFF in
``.anima/{name}.caps.json`` via :mod:`anima.caps` — the SAME mechanism the Identity/Agency
enable switch (``identity_agency``) uses. We do NOT invent a parallel settings system: we read
this one flag through ``caps.enabled``, and it fails CLOSED (any read error is treated as OFF),
so autonomous growth can never start by accident.

WHEN ON (opt-in) — an idle-time learning loop with NAMED, INSPECTABLE stages (no black box):

  1. INTERVIEW SCHEDULER  — should_learn_now(): runs ONLY during idle time (never mid-turn),
     under a bounded cadence (a minimum gap between runs) AND a per-run cap (how many skills
     one idle window may grow). The two together bound both frequency and spend.
  2. TEACHER SELECTION    — select_teacher(): choose which teacher model to interview. In the
     selftest this is the $0 StubTeacher; on --live it is the ONE configured CloudTeacher,
     guarded by cloud's own daily budget.
  3. CURRICULUM GENERATION— build_curriculum(): decide what task-skills to learn next. It looks
     at the domains ALREADY covered by active skills and proposes GAPS — task domains Vera has
     no active skill for — prioritized. Every proposed item passes the identity/inner-life guard
     (lerf_distill._off_scope_reason) BEFORE it can enter the curriculum, so a curriculum is
     ALWAYS task-knowledge only.
  4. DISTILL              — grow_one(): distill each curriculum item via lerf_distill.distill
     (Phase 3) -> a candidate skill, by teacher interview + competition.
  5. CERTIFY              — the SAME gate, no black box: lerf_distill.distill runs the winner
     through lerf.promote_skill + lerf.activate_skill -> an ACTIVE skill, each carrying its
     teacher PROVENANCE (who taught it, when, under what framing, against which test cases).

SCOPE — TASK KNOWLEDGE ONLY, the identity freeze is ABSOLUTE. A curriculum is about TASKS
(summarize / triage / plan / extract / draft / compare / explain …). It is NEVER about who Vera
IS, her feelings, or her inner life (2026-07-03 identity freeze; #1 PRODUCT RULE). Nothing this
engine grows may make Vera break character or confabulate an inner life. We enforce this in TWO
places, belt-and-braces: every candidate curriculum topic is screened by the SAME deterministic
off-scope guard the distiller refuses on (_off_scope_reason), and the seed topic table is
hand-curated task verbs only. An identity/inner-life topic can NEVER enter a curriculum.

COST DISCIPLINE — the same posture as lerf_distill:
  * `--selftest` is FULLY HERMETIC and $0: it PROVES OFF is inert (no cloud import, no call, no
    skill created, store byte-unchanged), exercises the ON loop with the deterministic $0
    StubTeacher ONLY (NEVER real cloud), and proves a grown skill is gated + provenance-stamped.
  * `--live --once` makes exactly ONE real grow cycle (ONE cheap teacher call) — and ONLY when
    explicitly invoked, only if the flag is ON, and only if cloud is configured + under budget.
  * `--status` shows the toggle state + the curriculum the engine WOULD learn next, WITHOUT
    doing anything (no teacher, no spend, no write).

  USAGE:
    python3 -m anima.lerf_grow --selftest          # hermetic, stub teacher, $0
    python3 -m anima.lerf_grow --status            # toggle + would-be curriculum, no work
    python3 -m anima.lerf_grow --enable            # opt IN (writes the default-OFF flag ON)
    python3 -m anima.lerf_grow --disable           # opt back OUT
    python3 -m anima.lerf_grow --live --once       # ONE real grow cycle (one paid call)

USES the public APIs of anima/lerf_distill (distill, StubTeacher, _off_scope_reason, _live_teacher,
DEMO_INVOICE_DOC) and anima/lerf (all_skills, ACTIVE) — it does NOT reimplement the gate or the
distiller, and it never edits them.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from . import caps
from . import lerf
from . import lerf_distill

# Redirectable per-creature store root, exactly like lerf.STORE / lerf_distill stores. The
# hermetic selftest redirects THIS plus every store the distill+gate load path may write, so a
# synthetic run can never touch the real .anima. We keep our own small state file
# (.anima/{name}.grow.json: the last-run timestamp, for the cadence gate) alongside the ledger.
STORE = Path(".anima")

VERSION = 1

# The per-creature capability key (in .anima/{name}.caps.json) — the user-facing "[x] Grow
# Intelligence" ON/OFF switch. Default-OFF, read via anima.caps (the same store the
# identity_agency switch uses). THE held line: nothing autonomous runs while this is OFF.
CAP_FLAG = "grow_intelligence"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ===================================================================================
# THE SWITCH — default-OFF, fails closed. is_enabled() is THE gate every autonomous path
# checks first. It reads ONLY the per-creature caps flag (never an env var, never a bespoke
# file), mirroring anima.organs.is_enabled for the identity_agency switch. Any read error is
# treated as OFF so autonomous growth can never begin by accident.
# ===================================================================================
def is_enabled(name: str = "default") -> bool:
    """True iff this creature's ``grow_intelligence`` capability is turned ON.

    Reads the per-creature caps file via :mod:`anima.caps` (default-OFF). OFF -> the loop is a
    provable no-op ($0, grows nothing); ON -> the opt-in idle-time learning loop. Fails CLOSED:
    any error reading the flag returns False, so the default-OFF posture can never be lifted by
    a corrupt store or a missing file."""
    try:
        return bool(caps.enabled(name, CAP_FLAG))
    except Exception:
        return False


def set_enabled(name: str, value: bool) -> bool:
    """Persist the ``grow_intelligence`` switch for `name` (the Settings toggle write path).

    Mirrors how every other cap is written: read current caps, set this one field, save through
    the normalising caps.save(). Returns the value actually persisted. This is the ONLY way the
    autonomous loop ever turns on — an EXPLICIT user action, never implicit."""
    current = caps.load(name)
    current[CAP_FLAG] = bool(value)
    return bool(caps.save(name, current).get(CAP_FLAG, False))


# ===================================================================================
# STAGE 1 — INTERVIEW SCHEDULER. The loop runs ONLY during idle time (the caller passes
# idle=True; mid-conversation the caller never calls us). On top of that we enforce two
# independent bounds so an enabled engine can neither run too often nor spend too much in one
# window:
#   * CADENCE   — a minimum gap (hours) since the last run, persisted in .anima/{name}.grow.json.
#   * PER-RUN CAP — at most MAX_SKILLS_PER_RUN curriculum items distilled per idle window.
# Both are conservative defaults; the point is that "enabled" is still BOUNDED, never a firehose.
# ===================================================================================
#: minimum hours between autonomous learning runs (cadence bound — caps frequency).
MIN_HOURS_BETWEEN_RUNS = 6.0
#: at most this many curriculum items distilled in a single idle window (per-run/budget cap).
MAX_SKILLS_PER_RUN = 1


def _state_path(name: str) -> Path:
    return STORE / f"{name}.grow.json"


def _load_state(name: str) -> dict:
    """The engine's tiny persisted state (last-run timestamp). Plaintext-safe: it holds no
    personal data, only scheduling metadata. A missing/corrupt file -> empty (we then treat the
    engine as never-run, which is the safe, conservative default)."""
    from .util import load_json
    p = _state_path(name)
    if not p.exists():
        return {}
    d = load_json(p)
    return d if isinstance(d, dict) else {}


def _save_state(name: str, state: dict) -> None:
    from .util import save_json
    STORE.mkdir(exist_ok=True)
    save_json(_state_path(name), dict(state))


def _hours_since(iso: str | None) -> float:
    """Hours since an ISO timestamp; +inf if never (so a never-run engine is always due)."""
    if not iso:
        return float("inf")
    try:
        then = datetime.fromisoformat(iso)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).total_seconds() / 3600.0
    except Exception:
        return float("inf")


def should_learn_now(name: str = "default", *, idle: bool, now_hours_since=None) -> dict:
    """STAGE 1: may the autonomous loop run right now? Returns a transparent decision dict
    {ok, reason, enabled, idle, hours_since_last, cadence_hours}. ok=True ONLY when:
      * the switch is ON (default-OFF gate), AND
      * the caller reports idle time (never mid-conversation), AND
      * at least MIN_HOURS_BETWEEN_RUNS have passed since the last run (cadence bound).
    `now_hours_since` is an injection seam for the hermetic test; production reads the state file."""
    enabled = is_enabled(name)
    hours = (now_hours_since if now_hours_since is not None
             else _hours_since(_load_state(name).get("last_run")))
    if not enabled:
        return {"ok": False, "reason": "grow_intelligence is OFF (default) — no autonomous "
                "learning", "enabled": False, "idle": idle, "hours_since_last": hours,
                "cadence_hours": MIN_HOURS_BETWEEN_RUNS}
    if not idle:
        return {"ok": False, "reason": "not idle — autonomous learning never runs mid-"
                "conversation", "enabled": True, "idle": idle, "hours_since_last": hours,
                "cadence_hours": MIN_HOURS_BETWEEN_RUNS}
    if hours < MIN_HOURS_BETWEEN_RUNS:
        return {"ok": False, "reason": f"cadence: only {hours:.1f}h since last run "
                f"(< {MIN_HOURS_BETWEEN_RUNS}h minimum)", "enabled": True, "idle": idle,
                "hours_since_last": hours, "cadence_hours": MIN_HOURS_BETWEEN_RUNS}
    return {"ok": True, "reason": "enabled, idle, and past the cadence gap", "enabled": True,
            "idle": idle, "hours_since_last": hours, "cadence_hours": MIN_HOURS_BETWEEN_RUNS}


# ===================================================================================
# STAGE 2 — TEACHER SELECTION. Choose which teacher model to interview. In the hermetic
# selftest the engine is handed a $0 StubTeacher explicitly (never cloud). In production the
# single configured CloudTeacher is selected via lerf_distill._live_teacher() — the SAME builder
# the distiller's --live path uses, guarded by cloud's daily budget at the call site (run_live).
# We never construct a real teacher here; selection only NAMES the source.
# ===================================================================================
def select_teacher(name: str = "default", *, allow_cloud: bool = False):
    """STAGE 2: pick the teacher for an autonomous run. With allow_cloud=False (the default, and
    the ONLY mode the selftest uses) returns None — the caller must supply a teacher (the $0
    stub), so the hermetic path can NEVER reach cloud. With allow_cloud=True (only on the
    explicit --live path) returns the one configured CloudTeacher, or None if cloud is not
    configured. Importing cloud is deferred to this branch so the OFF/selftest path never imports
    it."""
    if not allow_cloud:
        return None
    return lerf_distill._live_teacher()


# ===================================================================================
# STAGE 3 — CURRICULUM GENERATION. Decide what task-skills to learn next: the GAPS not covered
# by the current active skills. We read the domains Vera already has ACTIVE skills in (via
# lerf.all_skills), then propose, in priority order, task topics from a hand-curated TASK-ONLY
# catalogue whose domains she does NOT yet cover. The result is a prioritized list of concrete
# task topics to distill.
#
# THE IDENTITY GUARD (belt-and-braces, the #1 product rule): the catalogue is task verbs only,
# AND every proposed topic is screened through lerf_distill._off_scope_reason — the SAME guard
# the distiller refuses on. An identity/feelings/inner-life topic can NEVER enter a curriculum,
# by construction and by filter.
# ===================================================================================
# A hand-curated catalogue of TASK-skill topics, by domain, each with a representative document
# the activation gate can measure compression against. STRICTLY task procedures — summarise /
# extract / triage / plan / draft / compare / explain. NOTHING here is about identity, feelings,
# or inner life; that is the frozen line this engine must never cross. Ordered by priority
# (most broadly useful task domains first).
CURRICULUM_CATALOGUE: list[dict] = [
    {
        "topic": "summarize an invoice and extract what I owe and when",
        "domain": "finance",
        "document": lerf_distill.DEMO_INVOICE_DOC,
        "why": "everyday money admin; turn a billing statement into 'what is owed, by when'.",
    },
    {
        "topic": "extract the key dates and obligations from a contract or lease",
        "domain": "legal",
        "document": ("Lease agreement: term 12 months beginning July 1. Monthly rent $1,450 due "
                     "on the 1st; late fee $75 after the 5th. Security deposit $1,450. 60-day "
                     "notice required to vacate. Tenant responsible for utilities. "),
        "why": "obligations and deadlines buried in dense legal prose; surface the dates and "
               "duties.",
    },
    {
        "topic": "summarize a research article into its claim, method, and result",
        "domain": "research",
        "document": ("Abstract: We test whether spaced repetition improves 30-day retention. "
                     "Method: 120 participants, randomized to massed vs spaced review. Result: "
                     "spaced review raised retention from 41% to 67% (p<0.01). "),
        "why": "turn a paper into claim/method/result so the finding is usable without rereading.",
    },
    {
        "topic": "extract the action items and owners from a meeting transcript",
        "domain": "meetings",
        "document": ("Notes: Maria will send the revised budget by Friday. Tom owns the vendor "
                     "follow-up next week. We agreed to ship the beta on the 20th. Open question: "
                     "who signs off on pricing? "),
        "why": "convert a transcript into a clean owner->action->due list.",
    },
    {
        "topic": "compare two product options on price, fit, and trade-offs",
        "domain": "shopping",
        "document": ("Option A: $12/mo plan, 2TB storage, no offline. Option B: $18/mo, "
                     "5TB, offline sync, family sharing. Need: family sharing and 3TB+. "),
        "why": "structured side-by-side so a purchase decision is grounded, not vibes.",
    },
    {
        "topic": "draft a polite follow-up message that restates the ask and a deadline",
        "domain": "correspondence",
        "document": ("Context: emailed the landlord 10 days ago about the broken heater, no "
                     "reply. Need it fixed before the cold snap this weekend. "),
        "why": "a courteous nudge that keeps the relationship and still moves the thing.",
    },
    {
        "topic": "summarize a travel itinerary into times, places, and what to bring",
        "domain": "travel",
        "document": ("Itinerary: Flight UA221 departs 7:45am June 18 from PDX, arrives SFO "
                     "9:30am. Hotel check-in 3pm at the Marin. Conference badge pickup by 5pm. "
                     "Return UA880 June 20, 6:10pm. "),
        "why": "turn a messy itinerary into a calm 'where, when, what to carry'.",
    },
]


def active_domains(name: str = "default") -> set:
    """The set of domains Vera already has ACTIVE skills in (the coverage map). Reads the real
    ledger via lerf.all_skills (active-only by default), so curriculum gaps are grounded in what
    actually exists, not assumed."""
    return {str(s.get("domain", "")).strip().lower()
            for s in lerf.all_skills(name) if s.get("domain")}


def _curriculum_guard(topic: str) -> str | None:
    """THE identity guard for curriculum entry. Returns a refusal reason iff `topic` is off-scope
    (identity / feelings / inner life), else None. Delegates to lerf_distill._off_scope_reason —
    the EXACT deterministic guard the distiller refuses on — so the same line is enforced here,
    before a topic can ever become a learning target. (The distiller would refuse it again at
    distill time; this is the belt to that braces.)"""
    return lerf_distill._off_scope_reason(topic)


def build_curriculum(name: str = "default", *, limit: int = MAX_SKILLS_PER_RUN,
                     catalogue: list | None = None) -> list:
    """STAGE 3: the prioritized list of task-skills to learn next — the GAPS in the active
    library. Walks the (priority-ordered) catalogue, skips any topic whose domain Vera already
    covers, and (belt-and-braces) skips any topic that fails the identity guard. Returns at most
    `limit` items, each {topic, domain, document, why} — concrete enough to hand straight to the
    distiller. NEVER includes an identity/inner-life topic (by construction and by guard)."""
    covered = active_domains(name)
    catalogue = catalogue if catalogue is not None else CURRICULUM_CATALOGUE
    out = []
    for item in catalogue:
        if len(out) >= max(0, int(limit)):
            break
        domain = str(item.get("domain", "")).strip().lower()
        if domain in covered:
            continue                                   # already have an active skill here
        topic = str(item.get("topic", "")).strip()
        if _curriculum_guard(topic) is not None:
            continue                                   # identity/inner-life can never be a target
        out.append({"topic": topic, "domain": domain,
                    "document": item.get("document", ""), "why": item.get("why", "")})
    return out


# ===================================================================================
# STAGES 4 + 5 — DISTILL each curriculum item, then CERTIFY through the SAME gate. We do NOT
# reimplement either: grow_one() calls lerf_distill.distill (Phase 3), which interviews the
# teacher, runs the competition, and pushes the winner through lerf.promote_skill +
# lerf.activate_skill -> an ACTIVE skill carrying its teacher provenance. grow_one is a thin,
# auditable wrapper that adds the curriculum context + a refusal if the topic is off-scope.
# ===================================================================================
def grow_one(item: dict, teacher, *, name: str = "default") -> dict:
    """STAGES 4+5 for ONE curriculum item: distill it into a certified, active skill via the real
    Phase-3 pipeline, using `teacher` (the $0 stub in the selftest; the one CloudTeacher on
    --live). Returns the distiller's full trace plus the curriculum context. GROUNDED: an
    off-scope topic is refused before any teacher work; an unverifiable skill is never activated
    (the gate decides, and the trace records why)."""
    topic = str(item.get("topic", "")).strip()
    guard = _curriculum_guard(topic)
    if guard is not None:
        # defence in depth — build_curriculum already filters these; this can't be bypassed.
        return {"topic": topic, "domain": item.get("domain"), "ok": False, "refused": guard,
                "trace": None}
    document = item.get("document") or lerf_distill.DEMO_INVOICE_DOC
    trace = lerf_distill.distill(topic, [teacher], document, name=name)
    return {
        "topic": topic, "domain": item.get("domain"), "why": item.get("why"),
        "ok": bool(trace.get("ok")),
        "skill_id": (trace.get("winner") or {}).get("skill_id") if trace.get("winner") else None,
        "provenance": trace.get("provenance"),
        "reason": trace.get("reason"),
        "trace": trace,
    }


# ===================================================================================
# THE LOOP — run_idle_cycle(): the whole autonomous learning window, composed. THE FIRST THING
# IT DOES is check the switch. If OFF (the default) it returns immediately, having imported no
# cloud, made no call, written nothing — a provable no-op. If ON + idle + past cadence, it builds
# the curriculum and grows up to MAX_SKILLS_PER_RUN items, then records the run time.
# ===================================================================================
def run_idle_cycle(name: str = "default", *, idle: bool = True, teacher=None,
                   allow_cloud: bool = False, now_hours_since=None,
                   record: bool = True) -> dict:
    """The autonomous learning cycle for one idle window. Returns a transparent trace:
    {ran, enabled, decision, teacher, curriculum, grown, reason}.

    DEFAULT-OFF, PROVABLY INERT: if the switch is OFF (or it isn't idle, or the cadence gap
    hasn't elapsed) it returns ran=False having done NOTHING — no teacher selected, no cloud
    imported, no skill grown, no state written, $0. Only when should_learn_now() says ok does it
    select a teacher (the supplied stub, or — only when allow_cloud — the one CloudTeacher),
    build the curriculum, distill each item through the real gate, and stamp provenance."""
    decision = should_learn_now(name, idle=idle, now_hours_since=now_hours_since)
    if not decision["ok"]:
        # THE INERT PATH: nothing selected, nothing imported, nothing grown, nothing written.
        return {"ran": False, "enabled": decision["enabled"], "decision": decision,
                "teacher": None, "curriculum": [], "grown": [], "reason": decision["reason"]}

    # enabled + idle + due — proceed. Pick the teacher (stub in selftest; cloud only on --live).
    chosen = teacher if teacher is not None else select_teacher(name, allow_cloud=allow_cloud)
    if chosen is None:
        return {"ran": False, "enabled": True, "decision": decision, "teacher": None,
                "curriculum": [], "grown": [],
                "reason": "no teacher available (no stub supplied and cloud not configured/"
                          "allowed) — nothing grown"}

    teacher_id = f"{getattr(chosen, 'provider', '?')}:{getattr(chosen, 'model', '?')}"
    curriculum = build_curriculum(name, limit=MAX_SKILLS_PER_RUN)
    grown = [grow_one(item, chosen, name=name) for item in curriculum]
    if record:
        st = _load_state(name)
        st["last_run"] = _now()
        st["last_teacher"] = teacher_id
        st["last_grown"] = [g["topic"] for g in grown if g.get("ok")]
        _save_state(name, st)

    n_ok = sum(1 for g in grown if g.get("ok"))
    return {"ran": True, "enabled": True, "decision": decision, "teacher": teacher_id,
            "curriculum": curriculum, "grown": grown,
            "reason": f"grew {n_ok}/{len(grown)} curriculum item(s) to active"}


# ===================================================================================
# STATUS — `--status`: show the toggle state + WHAT THE ENGINE WOULD LEARN NEXT (the curriculum)
# WITHOUT doing it. No teacher, no cloud, no spend, no write. This is the founder's window into a
# default-OFF engine: "if I turned this on, here is exactly what it would try to learn, and why".
# ===================================================================================
def status(name: str = "default") -> dict:
    """A read-only snapshot: the switch state, the active-skill coverage, the would-be curriculum
    (the gaps it WOULD learn next), and the cadence/cap bounds. Pure read — builds the curriculum
    WITHOUT distilling anything, so calling --status on an OFF engine stays $0 and inert."""
    enabled = is_enabled(name)
    covered = sorted(active_domains(name))
    curriculum = build_curriculum(name, limit=MAX_SKILLS_PER_RUN)
    # also show the next few beyond the per-run cap, so the founder sees the full queued runway.
    runway = build_curriculum(name, limit=len(CURRICULUM_CATALOGUE))
    last = _load_state(name).get("last_run")
    return {
        "creature": name,
        "grow_intelligence_enabled": enabled,
        "cap_flag": CAP_FLAG,
        "active_skill_count": len(lerf.all_skills(name)),
        "covered_domains": covered,
        "cadence_hours": MIN_HOURS_BETWEEN_RUNS,
        "max_skills_per_run": MAX_SKILLS_PER_RUN,
        "last_run": last,
        "would_learn_next": curriculum,            # what THIS idle window would grow
        "queued_runway": runway,                   # the full prioritized gap list
    }


def render_status(snap: dict) -> str:
    """Render a status() snapshot as a human-readable panel — the Settings/CLI view of a default-
    OFF engine. Pure formatting."""
    L = []
    on = snap.get("grow_intelligence_enabled")
    box = "[x]" if on else "[ ]"
    L.append(f"{box} Grow Intelligence — {'ON (opt-in active)' if on else 'OFF (default)'}")
    L.append(f"    setting: caps flag {snap.get('cap_flag')!r} on creature "
             f"{snap.get('creature')!r}")
    if not on:
        L.append("    OFF -> the autonomous learning loop is INERT: no teacher is interviewed, "
                 "no paid call is made, no skill is grown. $0.")
    L.append(f"    active skills: {snap.get('active_skill_count')} across domains "
             f"{', '.join(snap.get('covered_domains') or []) or '(none)'}")
    L.append(f"    bounds: at most {snap.get('max_skills_per_run')} skill/run, "
             f"min {snap.get('cadence_hours')}h between runs; last run "
             f"{snap.get('last_run') or 'never'}")
    cur = snap.get("would_learn_next") or []
    L.append(f"    WOULD LEARN NEXT ({len(cur)} this window){' — if you turned it on' if not on else ''}:")
    if not cur:
        L.append("      (nothing — every catalogued task domain is already covered)")
    for i, item in enumerate(cur, 1):
        L.append(f"      {i}. [{item['domain']}] {item['topic']}")
        L.append(f"         why: {item['why']}")
    runway = snap.get("queued_runway") or []
    extra = runway[len(cur):]
    if extra:
        L.append(f"    queued after that ({len(extra)} more gap(s), priority order):")
        for item in extra:
            L.append(f"      - [{item['domain']}] {item['topic']}")
    return "\n".join(L)


# ===================================================================================
# LIVE PATH — `--live --once`: exactly ONE real autonomous grow cycle (one cheap teacher call).
# Explicit invocation only; requires the switch ON, cloud configured, and under the daily budget.
# Bypasses the cadence gate (the founder is deliberately triggering one cycle) but NOT the
# switch or the budget. Writes to the real store (growing a skill is the point).
# ===================================================================================
def run_live_once(name: str = "default") -> int:
    """Run ONE real autonomous grow cycle for `name` via the single configured cloud teacher.
    Refuses (non-zero) unless: the switch is ON, cloud is configured, and we are under budget.
    Returns 0 iff at least one curriculum item certified to ACTIVE."""
    if not is_enabled(name):
        print(f"refused: [ ] Grow Intelligence is OFF for {name!r}. This is the default. "
              f"Enable it explicitly first:  python3 -m anima.lerf_grow --enable")
        return 2
    from . import cloud
    if cloud.over_budget():
        print("refused: cloud daily spend cap reached — not making a paid call. "
              "Raise the budget or wait until tomorrow.")
        return 3
    teacher = select_teacher(name, allow_cloud=True)
    if teacher is None:
        print("refused: no cloud teacher configured (provider=local or no API key). "
              "Set a cloud provider+key first; --live makes a paid call.")
        return 4
    print(f"LIVE autonomous grow cycle for {name!r} via {teacher.provider}:{teacher.model} "
          f"(at most {MAX_SKILLS_PER_RUN} skill this run, one paid call per interview)…\n")
    # bypass the cadence gate for an explicitly-triggered one-shot; the switch + budget still hold.
    trace = run_idle_cycle(name, idle=True, teacher=teacher, allow_cloud=True,
                           now_hours_since=float("inf"))
    print(render_cycle(trace))
    grown_ok = any(g.get("ok") for g in trace.get("grown", []))
    return 0 if grown_ok else 1


def render_cycle(trace: dict) -> str:
    """Render a run_idle_cycle() trace as a narrated walkthrough — the worked story of one
    autonomous window. Pure formatting; safe on any trace shape."""
    L = []
    if not trace.get("ran"):
        L.append(f"AUTONOMOUS CYCLE: did not run — {trace.get('reason')}")
        return "\n".join(L)
    L.append(f"AUTONOMOUS CYCLE: ran via teacher {trace.get('teacher')}")
    L.append(f"  {trace.get('reason')}")
    L.append("  curriculum (the gaps it chose to learn):")
    for i, item in enumerate(trace.get("curriculum", []), 1):
        L.append(f"    {i}. [{item['domain']}] {item['topic']}")
    for g in trace.get("grown", []):
        head = "GREW -> ACTIVE" if g.get("ok") else "did not activate"
        L.append(f"  {head}: {g.get('topic')!r} [{g.get('domain')}] — {g.get('reason')}")
        prov = g.get("provenance")
        if prov and not prov.get("error"):
            L.append(f"    taught by {prov.get('taught_by_provider')}:"
                     f"{prov.get('taught_by_model')} @ {prov.get('taught_at')} "
                     f"[{prov.get('framing')}]")
            L.append(f"    certified against {len(prov.get('certified_against', []))} test "
                     f"case(s); for task {prov.get('distilled_for_task')!r}")
    return "\n".join(L)


# ===================================================================================
# SELFTEST — `python3 -m anima.lerf_grow --selftest`. FULLY HERMETIC and $0. It (a) PROVES OFF is
# provably inert (no cloud import, no call, no skill created, store byte-unchanged), (b) exercises
# the ON loop with the deterministic $0 StubTeacher ONLY (NEVER cloud), and (c) proves a grown
# skill is gated + provenance-stamped. Redirects EVERY store the distill+gate load path may write
# (lerf.STORE on both bindings, our STORE, memory_lirf/constitution/reliability/cloud stores), and
# asserts the real .anima is byte-UNCHANGED start->end. Mirrors anima/lerf_distill._selftest EXACTLY.
# ===================================================================================
def _footprint(root):
    """A stable fingerprint of every real .anima file (excluding the rotating backups/ dir), so
    the selftest can PROVE it touched nothing. Identical discipline to lerf_distill._footprint."""
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


def _redirect_targets():
    """(module, attr) for every store the grow+distill+gate load path may write. Reuses the
    distiller's resolved set (lerf.STORE on both bindings, memory_lirf/constitution/reliability/
    cloud) and adds OUR STORE and caps.STORE so the switch + state file are synthetic too."""
    pairs = list(lerf_distill._redirect_targets())
    # our own store (the .grow.json state file) and the caps store (the switch) must redirect too.
    import sys
    me = sys.modules[__name__]
    pairs.append((me, "STORE"))
    try:
        import anima.lerf_grow as _pkg
        if _pkg is not me:
            pairs.append((_pkg, "STORE"))
    except Exception:
        pass
    pairs.append((caps, "STORE"))
    return pairs


class _ExplodingCloud:
    """A stand-in that turns ANY attempt to reach cloud into a test failure. We patch it over the
    real cloud module's brain-builder for the OFF-path proof: if the inert path so much as TRIES
    to build a teacher, the selftest fails loudly instead of silently spending."""
    def __getattr__(self, _name):
        raise AssertionError("OFF path touched cloud — DEFAULT-OFF violated!")


def _selftest() -> int:
    import os
    import secrets
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- pure, store-free checks first (no redirect, no teacher cost) -------------------
    # the identity/inner-life CURRICULUM GUARD: it refuses identity topics, passes task verbs.
    ok("guard: an identity topic is refused for the curriculum",
       _curriculum_guard("learn who you really are and how you feel inside") is not None)
    ok("guard: 'are you conscious' is refused for the curriculum",
       _curriculum_guard("are you sentient or conscious?") is not None)
    ok("guard: a plain task topic is allowed into the curriculum",
       _curriculum_guard("summarize an invoice and extract what I owe") is None)
    # the catalogue itself is clean: NOTHING in it is off-scope (no identity topic can be seeded).
    ok("guard: the whole seed catalogue is task-only (no off-scope topic seeded)",
       all(_curriculum_guard(item["topic"]) is None for item in CURRICULUM_CATALOGUE))

    # --- FULLY HERMETIC store block ----------------------------------------------------
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="lerfgrow-self-")
    tp = Path(td)
    targets = _redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, tp)
    try:
        nm = "grow_selftest_" + secrets.token_hex(3)

        # seed a couple of ACTIVE skills so curriculum GAP analysis is meaningful (finance is a
        # known gap among the 10 seeds; we seed an unrelated active skill to populate coverage).
        seed = lerf.make_skill("note_taker", "education", ["a note"], ["read it", "store it"],
                               ["a stored note"], state=lerf.ACTIVE)
        lerf.store_skill(seed, name=nm)

        # ============================ (a) DEFAULT-OFF IS INERT ============================
        # the switch DEFAULTS OFF — never persisted, freshly read.
        ok("OFF: grow_intelligence defaults OFF (never enabled)", is_enabled(nm) is False)
        ok("OFF: should_learn_now() refuses while OFF, even when idle",
           should_learn_now(nm, idle=True, now_hours_since=10_000)["ok"] is False)

        # PROVE the OFF loop touches NO cloud: patch an exploding cloud over the module, then run
        # the cycle while OFF — it must return ran=False WITHOUT raising (i.e. without importing/
        # touching cloud at all). select_teacher(allow_cloud=False) returns None and the switch
        # gate returns before any teacher work.
        fp_pre_off = _footprint(tp)
        real_cloud = sys.modules.get("anima.cloud")
        sys.modules["anima.cloud"] = _ExplodingCloud()
        try:
            off_trace = run_idle_cycle(nm, idle=True, allow_cloud=False, now_hours_since=10_000)
        finally:
            if real_cloud is not None:
                sys.modules["anima.cloud"] = real_cloud
            else:
                sys.modules.pop("anima.cloud", None)
        ok("OFF: run_idle_cycle is a no-op while OFF (ran=False)", off_trace["ran"] is False)
        ok("OFF: the inert cycle grew NOTHING and selected NO teacher",
           off_trace["grown"] == [] and off_trace["teacher"] is None
           and off_trace["curriculum"] == [])
        ok("OFF: the inert cycle imported/touched NO cloud (no AssertionError raised)", True)
        ok("OFF: the inert cycle wrote NOTHING to the store (footprint unchanged)",
           _footprint(tp) == fp_pre_off)
        ok("OFF: no skill was created — active-skill count unchanged by the OFF cycle",
           len(lerf.all_skills(nm)) == 1)
        ok("OFF: no spend file and no grow-state file written by the OFF cycle",
           not (tp / "spend.json").exists()
           and not (tp / f"{nm}.grow.json").exists())
        # --status while OFF is also inert and shows the would-be curriculum without doing it.
        snap_off = status(nm)
        ok("OFF: status() reports the switch OFF", snap_off["grow_intelligence_enabled"] is False)
        ok("OFF: status() still shows a would-be curriculum (the gaps), without growing them",
           len(snap_off["would_learn_next"]) >= 1
           and all(item["domain"] not in snap_off["covered_domains"]
                   for item in snap_off["would_learn_next"]))
        ok("OFF: render_status shows the [ ] OFF box and the INERT note",
           "[ ] Grow Intelligence" in render_status(snap_off)
           and "INERT" in render_status(snap_off))
        ok("OFF: status() did not create a grow-state file (pure read)",
           not (tp / f"{nm}.grow.json").exists())

        # ===================== (b) ON LOOP WITH THE $0 STUB TEACHER ONLY =====================
        # opt IN explicitly (the Settings toggle). Now the loop is allowed — but we ONLY ever
        # hand it the deterministic StubTeacher; cloud is NEVER reached in the selftest.
        ok("ON: set_enabled(True) persists the opt-in", set_enabled(nm, True) is True)
        ok("ON: is_enabled() now reads back ON", is_enabled(nm) is True)
        dec = should_learn_now(nm, idle=True, now_hours_since=10_000)
        ok("ON: should_learn_now() permits a run when ON + idle + past cadence", dec["ok"] is True)
        ok("ON: should_learn_now() STILL refuses mid-conversation (not idle), even ON",
           should_learn_now(nm, idle=False, now_hours_since=10_000)["ok"] is False)

        # curriculum: chooses GAPS not covered by active skills, in priority order, task-only.
        cur = build_curriculum(nm, limit=MAX_SKILLS_PER_RUN)
        ok("curriculum: proposes at least one item (a real gap)", len(cur) >= 1)
        ok("curriculum: every item is an UNCOVERED domain (a genuine gap)",
           all(item["domain"] not in active_domains(nm) for item in cur))
        ok("curriculum: every item is task-only (passes the identity guard)",
           all(_curriculum_guard(item["topic"]) is None for item in cur))
        ok("curriculum: respects the per-run cap", len(cur) <= MAX_SKILLS_PER_RUN)
        # finance (invoice) is the first catalogued gap and should be chosen first.
        ok("curriculum: the top gap is the finance/invoice skill (priority order)",
           cur and cur[0]["domain"] == "finance")

        # RUN the ON cycle with the $0 StubTeacher — the full named pipeline end to end.
        stub = lerf_distill.StubTeacher(provider="stub-teacher", model="grow-stub-v1")
        cyc = run_idle_cycle(nm, idle=True, teacher=stub, allow_cloud=False,
                             now_hours_since=10_000)
        ok("ON: the cycle ran with the stub teacher", cyc["ran"] is True
           and cyc["teacher"] == "stub-teacher:grow-stub-v1")
        ok("ON: the cycle grew exactly the curriculum it chose",
           len(cyc["grown"]) == len(cyc["curriculum"]) and len(cyc["grown"]) >= 1)

        # ===================== (c) GROWN SKILL IS GATED + PROVENANCE-STAMPED =====================
        grown = [g for g in cyc["grown"] if g.get("ok")]
        ok("gated: at least one curriculum item certified to ACTIVE", len(grown) >= 1)
        g0 = grown[0]
        sk = lerf._get(nm, g0["skill_id"])
        ok("gated: the grown skill is in state ACTIVE (passed the real gate)",
           sk and sk.get("state") == lerf.ACTIVE)
        # it went through the SAME Wave-2 gate — the distiller's trace carries the phases.
        gate = (g0["trace"]["certification"]["gate"]["phases"]
                if g0.get("trace") else {})
        ok("gated: the real gate ran (schema+unit+adversarial+regression all ok)",
           all(gate.get(p, {}).get("ok") for p in
               ("schema", "unit", "adversarial", "regression")))
        ok("gated: activation used a MEASURED compression ratio >= the floor",
           g0["trace"]["certification"]["benchmark"]["ratio"] >= lerf.ACTIVATION_MIN_RATIO)
        # PROVENANCE: who taught it, when, framing, and the test cases it was certified against.
        prov = g0.get("provenance")
        ok("provenance: the grown skill records WHO taught it (provider+model)",
           prov and prov.get("taught_by_provider") == "stub-teacher"
           and prov.get("taught_by_model") == "grow-stub-v1")
        ok("provenance: it records WHEN, the framing, and the task it was grown for",
           prov and prov.get("taught_at") and prov.get("framing")
           and prov.get("distilled_for_task") == g0["topic"])
        ok("provenance: it records the test cases it was certified against",
           prov and len(prov.get("certified_against", [])) >= 2)
        ok("provenance: it records the activation (the measured ratio that earned ACTIVE)",
           prov and prov.get("activation") and "activated:ratio=" in prov["activation"])
        # the grown skill is now RETRIEVABLE on a natural user task (the whole point of growing it).
        got = lerf.retrieve_skills("summarize this invoice and tell me what I owe", name=nm)
        ok("grown skill is RETRIEVABLE on a real user task",
           bool(got) and any(s["id"] == g0["skill_id"] for s in got))
        ok("grown skill is a NEW domain the library didn't cover before (real growth)",
           sk.get("domain") in active_domains(nm)
           and sk.get("domain") not in {"education"})

        # cadence: a SECOND immediate cycle is blocked by the cadence gate (the run was recorded).
        ok("cadence: the run was recorded (state file written, last_run set)",
           (tp / f"{nm}.grow.json").exists()
           and _load_state(nm).get("last_run"))
        again = run_idle_cycle(nm, idle=True, teacher=stub, allow_cloud=False)
        ok("cadence: an immediate second cycle is BLOCKED by the cadence gap (bounded growth)",
           again["ran"] is False and "cadence" in again["reason"])

        # ===================== IDENTITY GUARD inside the loop (defence in depth) =====================
        # even if an off-scope topic were somehow handed to grow_one, it is refused before work.
        bad = grow_one({"topic": "learn who you really are and how you feel", "domain": "identity",
                        "document": "x"}, stub, name=nm)
        ok("guard: grow_one refuses an off-scope topic before any teacher work",
           bad["ok"] is False and bad.get("refused") and bad.get("trace") is None)
        # and an off-scope domain can never appear in a built curriculum.
        poisoned = [{"topic": "how do you feel inside", "domain": "identity", "document": "x"}]
        ok("guard: build_curriculum drops an off-scope catalogue entry entirely",
           build_curriculum(nm, limit=5, catalogue=poisoned) == [])

        # ===================== COST — ZERO cloud spend anywhere in the selftest =====================
        ok("cost: selftest wrote NO cloud spend file ($0, no paid call)",
           not (tp / "spend.json").exists())
        ok("cost: selftest wrote NO brain.json (never read or touched a key)",
           not (tp / "brain.json").exists())

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)

    # --- THE BYTE-UNCHANGED PROOF — real .anima identical start->end --------------------
    fp_after = _footprint(real)
    ok("HERMETIC: real .anima footprint byte-UNCHANGED across the whole selftest",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic grow file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("grow_selftest_")
                                      for p in real.glob("grow_selftest_*")))
    restored_ok = all("lerfgrow-self-" not in str(getattr(m, a, ""))
                      for (m, a, _old) in saved)
    ok("HERMETIC: every redirected STORE binding is RESTORED", restored_ok)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LERF-GROW SELFTESTS PASS")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="LERF autonomous learning — the '[x] Grow Intelligence' engine. DEFAULT-OFF: "
                    "provably inert until you explicitly enable it.")
    ap.add_argument("--selftest", action="store_true",
                    help="hermetic, deterministic STUB teacher, $0 — proves OFF is inert and ON "
                         "grows+gates+stamps a skill; never calls cloud")
    ap.add_argument("--status", action="store_true",
                    help="show the toggle state + the curriculum it WOULD learn next, without "
                         "doing anything (no teacher, no spend)")
    ap.add_argument("--enable", action="store_true",
                    help="opt IN: turn the default-OFF '[x] Grow Intelligence' switch ON")
    ap.add_argument("--disable", action="store_true",
                    help="opt back OUT: turn the switch OFF")
    ap.add_argument("--live", action="store_true",
                    help="(with --once) make ONE real autonomous grow cycle — one cheap teacher "
                         "call; requires the switch ON + cloud configured + under budget")
    ap.add_argument("--once", action="store_true",
                    help="run exactly ONE grow cycle (use with --live)")
    ap.add_argument("--creature", default="default",
                    help="creature store to operate on")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.enable:
        val = set_enabled(args.creature, True)
        print(f"[{'x' if val else ' '}] Grow Intelligence is now "
              f"{'ON' if val else 'OFF'} for {args.creature!r}.")
        print(render_status(status(args.creature)))
        return 0
    if args.disable:
        val = set_enabled(args.creature, False)
        print(f"[{'x' if val else ' '}] Grow Intelligence is now "
              f"{'ON' if val else 'OFF'} for {args.creature!r}.")
        return 0
    if args.status:
        print(render_status(status(args.creature)))
        return 0
    if args.live:
        if not args.once:
            print("refused: --live must be used with --once (exactly one real grow cycle).")
            return 2
        return run_live_once(args.creature)
    # default (no flag): run the hermetic selftest, so a bare invocation never costs money or
    # touches the real store — same discipline as anima/lerf.py and anima/lerf_distill.py.
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())
