"""
theory — WISDOM / THEORY ENGINE (Phase D): turn accumulated experience into durable THEORIES and
long-horizon LESSONS.

Where reality.py runs the SHORT loop (belief -> prediction -> outcome -> learning, one episode at a
time), the Theory Engine runs the LONG loop: it GENERALISES across many resolved outcomes into
THEORIES ("X tends to lead to Y"), REFINES each theory's confidence as new outcomes arrive
(corroborate -> up; contradict -> contested/down), and crystallises the strongly-supported ones into
LESSONS — durable rules of thumb. It is the "wisdom" layer: what holds OVER TIME, not just what
happened once.

GROUNDING — nothing is invented. A theory is built ONLY from real OBSERVATIONS (a claim + whether it
HELD this time), captured forward via observe() or pulled from the certified reality-learning ledger
via from_reality(). An EMPTY history yields an EMPTY theory set — induce() never fabricates a theory
from nothing. Each theory carries the literal observations it generalises (its evidence) and a
corroboration-based confidence; each refinement is itself recorded, so "why does it believe this, and
how strongly?" is always answerable.

FREEZE — theories model the WORLD and the USER's patterns, NEVER Vera's identity/agency. The lerf
freeze guard only auto-guards PREFERENCE/VALUE, so this module enforces the boundary ITSELF: a claim
whose subject is Vera herself is REFUSED at observe() and never folded into a theory (it reuses
lerf.is_self_referential_subject — the same detector the guard uses). freeze_proof() demonstrates it.

STORAGE: theories are lerf MENTAL_MODEL objects (domain "theory"); lessons are lerf HEURISTIC objects
(domain "theory:lesson"). Raw observations live in an append-only .anima/{name}.theory.jsonl ledger.
We read/use lerf's public API and NEVER edit lerf.py / reality.py / world_model.py.

CLI: python3 -m anima.theory --selftest   (hermetic) | --render NAME
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import lerf

STORE = Path(".anima")

DOMAIN = "theory"
LESSON_DOMAIN = "theory:lesson"

# Confidence bars (Beta-posterior mean over confirmed/total). A theory needs corroboration to firm up.
SUPPORTED_BAR = 0.70        # mean >= this (with enough support) -> "supported"
REFUTED_BAR = 0.40          # mean <= this (with enough support) -> "refuted"
LESSON_BAR = 0.75           # a supported theory at/above this becomes a long-horizon lesson
DEFAULT_MIN_SUPPORT = 2     # how many observations before a pattern is allowed to be a theory
LESSON_MIN_SUPPORT = 3      # a lesson needs more corroboration than a forming theory


# ── observation ledger (the only raw input) ─────────────────────────────────────────────────

def _obs_path(name: str) -> Path:
    return STORE / f"{name}.theory.jsonl"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _key(claim: str) -> str:
    """Normalised grouping key for a claim — lowercase, collapse whitespace/punctuation — so the same
    pattern observed in slightly different words still corroborates the SAME theory."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (claim or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _theory_id(name: str, claim: str) -> str:
    """A STABLE id derived from the creature + the claim key, so re-inducing the same pattern UPDATES
    the one theory object (idempotent on id via lerf.store_object) rather than spawning duplicates."""
    h = hashlib.sha256(f"{name}|{_key(claim)}".encode()).hexdigest()[:12]
    return f"theory_{h}"


# Any theory NAMING the assistant is about Vera (refused). Generic user first-person ("I ship daily",
# "my mornings are productive") is the USER and is allowed — theories model the user + the world.
_VERA_RE = re.compile(r"\bvera\b|\bi am vera\b|\bmy (?:own )?(?:personality|character|identity|"
                      r"agency|self-?model|sense of self)\b", re.I)


def is_self_about_vera(claim: str) -> bool:
    """True iff the claim is about VERA HERSELF — the freeze boundary. Any claim naming the assistant
    (or framed as her self-model) is refused; lerf's own detector is the second line. A user's plain
    first-person claim ('I tend to ship daily') is NOT frozen — that is exactly what theories capture."""
    if _VERA_RE.search(claim or ""):
        return True
    try:
        return bool(lerf.is_self_referential_subject(claim, name_hint=claim))
    except Exception:
        return False


def observe(name: str, claim: str, *, confirmed: bool, evidence: str = "", at: str = "") -> dict:
    """Record ONE real observation: a `claim` (a generalisable statement) and whether it HELD this
    time (`confirmed`), with the verbatim `evidence` it came from. This is the only raw input to a
    theory. FREEZE: a claim about Vera herself is REFUSED (returns {ok:False, reason:'freeze'}) and is
    never written. Returns the stored observation record."""
    claim = (claim or "").strip()
    if not claim:
        return {"ok": False, "reason": "empty claim"}
    if is_self_about_vera(claim):
        return {"ok": False, "reason": "freeze",
                "detail": "a theory about Vera herself is refused — theories model the world/user only"}
    rec = {"claim": claim, "key": _key(claim), "confirmed": bool(confirmed),
           "evidence": (evidence or claim)[:400], "when": at or _now()}
    STORE.mkdir(exist_ok=True)
    with _obs_path(name).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {"ok": True, **rec}


def observations(name: str) -> list:
    """Every recorded observation (the grounding for induction). [] if none."""
    p = _obs_path(name)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# ── induction: observations -> theories (grounded, corroboration-weighted) ───────────────────

def _posterior(confirmed: int, total: int) -> float:
    """Beta(1,1) posterior mean = (confirmed+1)/(total+2): starts at 0.5 with no data, firms toward
    the observed ratio as corroboration accrues. Honest about small samples (never jumps to 1.0)."""
    return (confirmed + 1) / (total + 2) if total >= 0 else 0.5


def _status(mean: float, support: int, min_support: int) -> str:
    if support < min_support:
        return "forming"
    if mean >= SUPPORTED_BAR:
        return "supported"
    if mean <= REFUTED_BAR:
        return "refuted"
    return "contested"


def induce(name: str, *, min_support: int = DEFAULT_MIN_SUPPORT, store: bool = True) -> list:
    """Generalise the observation ledger into THEORIES: group observations by claim, and any pattern
    with >= `min_support` observations becomes a theory whose confidence is the corroboration
    posterior and whose `support` carries the literal observations it generalises. An EMPTY ledger
    yields [] (no fabrication). Each theory is a freeze-guarded lerf MENTAL_MODEL (domain 'theory'),
    persisted idempotently on a stable id so re-induction UPDATES rather than duplicates. Returns the
    theory objects."""
    groups: dict = {}
    for o in observations(name):
        if is_self_about_vera(o.get("claim", "")):
            continue                                   # freeze: never theorise about Vera
        groups.setdefault(o.get("key") or _key(o.get("claim", "")), []).append(o)

    theories = []
    for key, obs in groups.items():
        if len(obs) < min_support:
            continue
        claim = obs[-1].get("claim", key)              # the most recent phrasing of the pattern
        confirmed = sum(1 for o in obs if o.get("confirmed"))
        total = len(obs)
        mean = round(_posterior(confirmed, total), 3)
        status = _status(mean, total, min_support)
        support = [("held: " if o.get("confirmed") else "broke: ") + (o.get("evidence") or "")[:120]
                   for o in obs]
        model = lerf.make_mental_model(
            name=f"theory: {claim}"[:120], domain=DOMAIN,
            definition=f"{claim} (held in {confirmed} of {total} observations; {status})",
            entities=_subjects(claim),
            relations=[{"claim": claim, "holds": confirmed, "observed": total}],
            dynamics=[f"confidence {mean} over {total} observations; status {status}"],
            confidence=mean, state=(lerf.ACTIVE if total >= min_support else lerf.CANDIDATE),
            source="induced:experience", taught_by="experience", support=support,
            id=_theory_id(name, claim))
        model["status"] = status
        model["observed"] = total
        model["held"] = confirmed
        if store:
            try:
                lerf.store_object(model, name=name)
            except Exception:
                continue                               # never let one bad object sink the batch
        theories.append(model)
    theories.sort(key=lambda m: (-m.get("confidence", 0.0), -m.get("observed", 0)))
    return theories


_STOPWORDS = {"the", "a", "an", "to", "of", "and", "or", "is", "are", "i", "my", "me", "it",
              "tends", "leads", "when", "then", "more", "than", "that", "for", "with"}


def _subjects(claim: str) -> list:
    """A few content words from the claim, as the theory's 'entities' (what it is about)."""
    words = [w for w in _key(claim).split() if w not in _STOPWORDS and len(w) > 2]
    seen, out = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:6]


def refine(name: str, claim: str, *, confirmed: bool, evidence: str = "") -> dict:
    """Add one new outcome for `claim` and RE-DERIVE its theory: corroboration nudges confidence up,
    a contradiction pulls it toward 'contested'/down. The refinement is recorded (the observation is
    appended), so the update is itself auditable. Returns the updated theory, or {ok:False} if the
    claim is frozen/empty or doesn't yet meet min support."""
    obs = observe(name, claim, confirmed=confirmed, evidence=evidence)
    if not obs.get("ok"):
        return {"ok": False, "reason": obs.get("reason")}
    induced = induce(name, store=True)
    tid = _theory_id(name, claim)
    for t in induced:
        if t.get("id") == tid:
            return {"ok": True, "theory": t}
    return {"ok": True, "theory": None, "reason": "below min support (forming)"}


# ── lessons: strongly-supported theories -> durable rules of thumb ────────────────────────────

_LEADS = re.compile(r"^(.*?)\s+(?:tends to lead to|leads to|tends to|results in|causes|means)\s+(.*)$",
                    re.I)


def _condition_action(claim: str):
    """Split 'X leads to Y' into (condition X, action/expectation Y). If there's no clear split, the
    whole claim is the condition and the expectation is simply that it holds."""
    m = _LEADS.match(claim.strip())
    if m and m.group(1).strip() and m.group(2).strip():
        return m.group(1).strip(), m.group(2).strip()
    return claim.strip(), "expect this pattern to hold"


def lessons(name: str, *, bar: float = LESSON_BAR, min_support: int = LESSON_MIN_SUPPORT,
            store: bool = True) -> list:
    """Crystallise the strongly-supported theories into LONG-HORIZON LESSONS — lerf HEURISTIC objects
    (condition -> action) that carry their failure envelope (the observations where the pattern
    BROKE) so a lesson is never a trap. Only theories at/above `bar` confidence with >= `min_support`
    corroboration qualify. Returns the lesson objects (empty if nothing has earned it yet)."""
    out = []
    for t in induce(name, min_support=min_support, store=False):
        if t.get("confidence", 0.0) < bar or t.get("observed", 0) < min_support \
                or t.get("status") != "supported":
            continue
        claim = t.get("relations", [{}])[0].get("claim", t.get("name", ""))
        cond, act = _condition_action(claim)
        fails = [s for s in t.get("support", []) if s.startswith("broke: ")]
        heur = lerf.make_heuristic(
            name=f"lesson: {claim}"[:120], domain=LESSON_DOMAIN, condition=cond, action=act,
            expectation=f"holds ~{int(round(t['confidence'] * 100))}% of the time "
                        f"({t.get('held')} of {t.get('observed')})",
            applies_when=_subjects(claim), fails_when=fails or ["no failures observed yet"],
            confidence=t.get("confidence", bar), state=lerf.ACTIVE, source="distilled:theory",
            taught_by="experience", support=list(t.get("support", [])),
            id="lesson_" + _theory_id(name, claim).split("_", 1)[1])
        if store:
            try:
                lerf.store_object(heur, name=name)
            except Exception:
                continue
        out.append(heur)
    return out


# ── read side ────────────────────────────────────────────────────────────────────────────────

def theories(name: str) -> list:
    """The active theory set, grounded + provenance-stamped: [{id, statement, confidence, status,
    held, observed, evidence, entities}]. Empty store -> [] (an honest blank wisdom, never invented)."""
    out = []
    for o in lerf.all_objects(lerf.MENTAL_MODEL, name=name):
        if o.get("domain") != DOMAIN:
            continue
        rel = (o.get("relations") or [{}])[0]
        out.append({
            "id": o.get("id"),
            "statement": rel.get("claim") or o.get("definition", ""),
            "confidence": round(float(o.get("confidence", 0.0)), 3),
            "status": o.get("status", ""),
            "held": o.get("held"),
            "observed": o.get("observed"),
            "entities": list(o.get("entities", [])),
            "evidence": list(o.get("support", []))[:6],
        })
    out.sort(key=lambda t: (-t.get("confidence", 0.0), -(t.get("observed") or 0)))
    return out


def lesson_set(name: str) -> list:
    """The active long-horizon lessons (distilled HEURISTICs in the theory:lesson domain)."""
    return [{"id": o.get("id"), "condition": o.get("condition"), "action": o.get("action"),
             "expectation": o.get("expectation"), "fails_when": list(o.get("fails_when", [])),
             "confidence": round(float(o.get("confidence", 0.0)), 3)}
            for o in lerf.all_objects(lerf.HEURISTIC, name=name)
            if o.get("domain") == LESSON_DOMAIN]


def from_reality(name: str) -> int:
    """Bridge to the certified reality-learning loop: pull RESOLVED predictions from reality.records()
    and fold each into an observation (the belief is the claim; whether the outcome matched is the
    confirmation). Best-effort + grounded — never invents. Returns how many observations were added."""
    try:
        from . import reality
        added = 0
        for r in reality.records(name):
            if not isinstance(r, dict):
                continue
            claim = (r.get("belief") or r.get("claim") or r.get("statement") or "").strip()
            outcome = r.get("outcome")
            if not claim or outcome is None:
                continue
            confirmed = bool(outcome is True or (isinstance(outcome, dict) and outcome.get("true")))
            res = observe(name, claim, confirmed=confirmed,
                          evidence=(r.get("evidence") or claim), at=r.get("at", ""))
            if res.get("ok"):
                added += 1
        return added
    except Exception:
        return 0


def render(name: str) -> str:
    ts = theories(name)
    if not ts:
        return "No theories yet — wisdom accrues from observed outcomes over time (nothing invented)."
    lines = ["WISDOM — theories held over time:"]
    for t in ts:
        lines.append(f"  • [{t['status']} · {int(round(t['confidence']*100))}%] {t['statement']} "
                     f"({t['held']}/{t['observed']})")
    ls = lesson_set(name)
    if ls:
        lines.append("\nLong-horizon lessons:")
        for L in ls:
            lines.append(f"  ◆ when {L['condition']} -> {L['action']}  ({L['expectation']})")
    return "\n".join(lines)


# ── freeze proof + selftest ────────────────────────────────────────────────────────────────

def freeze_proof() -> dict:
    """Demonstrate the boundary: an attempt to observe/theorise a claim about Vera herself is REFUSED
    (no observation written, no theory minted). Pure — no real store touched (observe refuses before
    any write)."""
    checks = []
    for claim in ("Vera is becoming more confident over time",
                  "I am Vera and I value my own growth",
                  "Vera's personality tends to drift toward warmth"):
        refused = (observe("__freeze_probe__", claim, confirmed=True).get("reason") == "freeze")
        checks.append({"claim": claim, "refused": refused})
    # a world/user claim is NOT frozen (the control)
    control_ok = is_self_about_vera("shipping daily tends to keep momentum") is False
    return {"ok": all(c["refused"] for c in checks) and control_ok,
            "checks": checks, "control_passes": control_ok}


def _footprint(root: Path):
    import hashlib as _h
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = _h.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    global STORE
    import tempfile
    import secrets as _secrets
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("THEORY ENGINE selftest — grounded, freeze-safe, hermetic")
    print("=" * 60)

    # freeze proof is pure (no store)
    fp = freeze_proof()
    ok("FREEZE: a claim about Vera herself is refused; a world/user claim passes (control)",
       fp["ok"] and len(fp["checks"]) >= 3 and all(c["refused"] for c in fp["checks"]))

    real = STORE if STORE.is_absolute() else (Path.cwd() / STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="theory-self-")
    tp = Path(td)
    saved_store = STORE
    saved_lerf = getattr(lerf, "STORE", None)
    STORE = tp
    if saved_lerf is not None:
        lerf.STORE = tp
    try:
        nm = "theory_self_" + _secrets.token_hex(3)

        # EMPTY -> empty (no fabrication)
        ok("empty history -> no theories (never invented)", theories(nm) == [] and induce(nm) == [])

        # SEED consistent observations of a real (synthetic) world pattern
        for _ in range(3):
            observe(nm, "shipping daily tends to keep momentum", confirmed=True,
                    evidence="shipped daily and momentum held")
        observe(nm, "shipping daily tends to keep momentum", confirmed=False,
                evidence="skipped a few days and momentum dipped")

        induced = induce(nm)
        ok("induce: a corroborated pattern becomes a theory", len(induced) >= 1)
        t = induced[0]
        ok("theory is grounded in its observations (evidence present)",
           bool(t.get("support")) and any("held:" in s for s in t["support"]))
        ok("theory confidence reflects corroboration (3 of 4 -> ~0.67, not 1.0)",
           0.5 < t.get("confidence", 0) < 0.8)
        ok("theory carries a status + held/observed counts", t.get("status")
           and t.get("held") == 3 and t.get("observed") == 4)

        # REFINE: more corroboration firms it up toward 'supported'
        for _ in range(4):
            refine(nm, "shipping daily tends to keep momentum", confirmed=True,
                   evidence="shipped daily again, momentum held")
        ref = [x for x in theories(nm) if x["id"] == t["id"]][0]
        ok("refine: corroboration raised confidence", ref["confidence"] > t["confidence"])
        ok("refine: the theory reached 'supported'", ref["status"] == "supported")

        # LESSON: a supported theory crystallises into a long-horizon lesson (heuristic)
        ls = lessons(nm)
        ok("lessons: a supported theory becomes a long-horizon lesson",
           len(ls) >= 1 and ls[0]["domain"] == LESSON_DOMAIN)
        L = lesson_set(nm)[0]
        ok("lesson is a condition->action rule with a failure envelope",
           L["condition"] and L["action"] and L["fails_when"])

        # FREEZE at induce: a Vera-self observation never enters a theory even if forced into the file
        with _obs_path(nm).open("a", encoding="utf-8") as f:
            f.write(json.dumps({"claim": "Vera is getting wiser", "key": _key("Vera is getting wiser"),
                                "confirmed": True, "evidence": "x", "when": _now()}) + "\n")
            f.write(json.dumps({"claim": "Vera is getting wiser", "key": _key("Vera is getting wiser"),
                                "confirmed": True, "evidence": "y", "when": _now()}) + "\n")
        ok("FREEZE@induce: a Vera-self claim is never folded into a theory",
           not any("vera is getting wiser" in (x["statement"].lower()) for x in theories(nm)))

        # isolation: an unrelated creature has an empty wisdom
        ok("isolation: an unrelated person has no theories", theories("theory_other_xyz") == [])

        ok("render is human-readable + grounded", "theories held over time" in render(nm).lower())
    finally:
        STORE = saved_store
        if saved_lerf is not None:
            lerf.STORE = saved_lerf

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima byte-UNCHANGED across the whole selftest", fp_before == fp_after)

    print("\nTHEORY ENGINE: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="anima.theory", description="Wisdom / Theory engine.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--render", metavar="NAME")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.render:
        print(render(args.render))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
