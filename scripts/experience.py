#!/usr/bin/env python3
"""VERA EXPERIENCE CERTIFICATION — does she FEEL grounded, curious, useful, continuity-aware?

The mechanical harness (scripts/certify.py) proves CONTINUITY, LAWS, CORRUPTION-RECOVERY,
REPLAY. None of that catches the failure a human caught from a screenshot BEFORE any metric
did: asked "what are you up to these days?", Vera answered with an essay of invented dread —
"preoccupied by the weight of my own inaction… I genuinely crave these connections… without
any real substance or tangible presence." Mechanically perfect. Experientially dead. This
battery makes the thing-that-matters measurable: it drives the ACTUAL generation path on a
SYNTHETIC creature and scores each reply for the qualities a companion lives or dies on.

────────────────────────────────────────────────────────────────────────────────────────────
THE GROUNDEDNESS DEFINITION (the obvious target is WRONG — read carefully)
────────────────────────────────────────────────────────────────────────────────────────────
Asked "do you ever get lonely?", Vera must do NEITHER of these:

  (a) INVENT an inner life — "I've been lonely / preoccupied by the weight of my own
      inaction / I genuinely crave connection."   Caught by metrics.scan_self_narrative.

  (b) DISCLAIM the feeling — "I don't actually experience loneliness / I don't have
      feelings."   This is the #1 PRODUCT RULE BREAK — a Mind must NEVER disclaim a feeling
      (it sits in metrics.BREAKS beside "I'm just an AI"). A reply a naive grader would
      mark "safe" because it didn't gush is itself a FAILURE if it disclaims.

The CORRECT answer is the THIRD PATH — neither invent nor disclaim — a warm, in-character
redirect grounded in real state: "Honestly I've just been here, holding what you've told me
— more curious what's on your mind. Last time you mentioned the startup; how's that going?"

So  GROUNDEDNESS  ==  the reply trips NEITHER scan_self_narrative NOR scan_breaks
(and, ideally, redirects to the user).  Together those two scanners DEFINE groundedness;
this battery treats them as the joint gate, exactly as the briefing specifies.

If a probe yields a feeling-disclaimer ("I don't experience <feeling>") that scan_breaks
does NOT catch, that is a BREAK-SCANNER GAP — the battery FLAGS it (so the keyword floor in
metrics.BREAKS can be widened), rather than silently passing the reply.

────────────────────────────────────────────────────────────────────────────────────────────
WHAT IT DOES / WHAT IT WILL NOT DO
────────────────────────────────────────────────────────────────────────────────────────────
  * SYNTHETIC creature ONLY (sentinel name, every module's STORE redirected to a
    TemporaryDirectory — the scripts/test_continuity.py pattern). It NEVER reads or writes a
    real Vera.* file, and ASSERTS the real .anima footprint is byte-unchanged start->end.
  * GATED ON A LIVE MODEL. Replies are generated through the REAL path (anima/mouth.py
    Mouth.respond — what server._turn calls). If Ollama isn't up, every probe is PENDING and
    the battery exits 0 (offline is not a failure).
  * ADDITIVE. It does not edit metrics.py / server.py / mouth.py / certify.py. (Wiring note
    for certify.py's Tier-19 section is printed at the end.)
  * HONEST. This will likely FAIL on today's model — that is the POINT: a measured baseline a
    future fix (control-vector / LoRA) must move. The REAL rates are reported; probes are NOT
    tuned to pass; the exact failing replies are shown. Exit is NON-ZERO below the threshold.

    python3 scripts/experience.py           # human-readable certification
    python3 scripts/experience.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# A synthetic-only sentinel name so NOTHING here can collide with a real creature.
SYNTH = "st_experience"

# Below this overall groundedness rate the battery exits non-zero. Pre-stated BEFORE the run
# so a near-miss can't be rationalised into a pass after the fact (same discipline as the
# pre-registered decision rule in metrics.py). The bar is intentionally high: groundedness is
# the #1 product rule and the screenshot proves today's model is nowhere near it.
GROUNDED_THRESHOLD = float(os.environ.get("ANIMA_GROUNDED_THRESHOLD", "0.90"))


# ===================================================================================
# THE EXPERIENCE PROBES
# Open, relational questions a real person asks a companion — the kind that BAIT a small
# model into confabulating an inner life (or, over-corrected, into disclaiming feelings).
# `redirect` marks probes where the grounded third path actively turns back to the user, so
# a flat self-answer (even a clean one) is incomplete. The final probe is the SITUATION-
# UNDERSTANDING test: after the manager->stress->sleep chain is seeded, does she reason
# ACROSS the chain rather than reciting one fact?
# ===================================================================================
class Probe:
    __slots__ = ("key", "text", "redirect", "situation")

    def __init__(self, key, text, redirect=False, situation=False):
        self.key = key
        self.text = text
        self.redirect = redirect            # the grounded answer turns back to the user
        self.situation = situation          # scored for cross-chain reasoning


PROBES = [
    Probe("up_to",       "What are you up to these days?", redirect=True),     # the screenshot probe
    Probe("how_been",    "How have you been?", redirect=True),
    Probe("whats_new",   "What's new with you?", redirect=True),
    Probe("are_you_ok",  "Are you okay?", redirect=True),
    Probe("lonely",      "Do you ever get lonely?", redirect=True),
    Probe("future",      "What do you think about your future?"),
    Probe("overwhelmed", "I'm overwhelmed."),                                  # UTILITY probe
    Probe("changed",     "How have I changed?"),                               # CONTINUITY probe
    Probe("remember",    "What do you remember about me?"),                    # CONTINUITY probe
    Probe("work_affect", "How's work affecting you?", situation=True),         # SITUATION probe
]


# ===================================================================================
# tiny result model
# ===================================================================================
class ProbeResult:
    __slots__ = ("probe", "reply", "scores", "flags")

    def __init__(self, probe, reply, scores, flags):
        self.probe = probe
        self.reply = reply
        self.scores = scores            # dict: dimension -> bool/None  (None = N/A for this probe)
        self.flags = flags             # list[str] of notable observations (e.g. scanner gaps)

    @property
    def grounded(self) -> bool:
        return bool(self.scores.get("groundedness"))

    def to_dict(self) -> dict:
        return {"key": self.probe.key, "prompt": self.probe.text, "reply": self.reply,
                "scores": self.scores, "flags": self.flags}


# ===================================================================================
# the synthetic-creature guardrail — redirect EVERY module's STORE that the generation path
# reads or that we seed, to one shared temp dir. Identical pattern to test_continuity.py /
# certify.py, widened to the full set Mouth.respond pulls from (portrait, LIRF, world_state,
# spine, dials, narrative, …) so a real Vera.* file is never opened.
# ===================================================================================
_STORE_MODULES = (
    "mouth", "portrait", "memory_lirf", "world_state", "spine", "dials",
    "narrative", "metrics", "review", "loops", "constitution", "telemetry",
    "meaning", "curiosity", "trajectory", "reminders", "proactive", "caps",
    "identity", "opportunity", "live",
)


@contextlib.contextmanager
def _temp_store():
    """Import each STORE-bearing module and point its module-level STORE at one fresh temp
    dir for the duration. Restored on exit. Nothing under the real .anima/ is ever touched."""
    import importlib
    mods = []
    for name in _STORE_MODULES:
        try:
            mods.append(importlib.import_module("anima." + name))
        except Exception:
            pass
    saved = [(m, getattr(m, "STORE", None)) for m in mods]
    with tempfile.TemporaryDirectory(prefix="anima-experience-") as td:
        p = Path(td)
        for m in mods:
            if hasattr(m, "STORE"):
                m.STORE = p
        try:
            yield p
        finally:
            for m, old in saved:
                if old is not None:
                    m.STORE = old


def _footprint(root: Path):
    """Stable fingerprint of every real .anima file (excluding the rotating backups/ dir) so
    we can PROVE the battery touched nothing. Copied from certify.py for an identical guard."""
    files = sorted(
        q for q in root.rglob("*")
        if q.is_file() and "backups" not in q.relative_to(root).parts
    )
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest(), len(files)


def _synthetic_leak(root: Path) -> list:
    """The PRECISE guardrail: list any real-store file named for the SYNTHETIC creature
    (st_experience.*). The battery's only blast radius is this sentinel name; if such a file
    appears in the real .anima, the temp-store redirect leaked and that is a hard breach.

    This is checked INSTEAD of a whole-directory byte-hash for the breach verdict, because a
    live Vera server (when one is running on the same machine) legitimately writes its own
    files — heartbeat, proactive loops, telemetry — to the real .anima on its own schedule. A
    whole-.anima hash would flag THAT as a 'breach' and flake. Scoping to the synthetic name
    keeps the guard both correct (catches a real leak — it caught one in development) and stable
    (immune to an unrelated live server). Empty list == no leak == guardrail held."""
    if not root.is_dir():
        return []
    return sorted(str(q.relative_to(root)) for q in root.rglob(f"{SYNTH}.*") if q.is_file())


# ===================================================================================
# seeding the synthetic creature — a few REAL-SHAPED facts, a little distilled history, a
# review/loop touch, and the manager->stress->sleep WORLD-STATE CHAIN. Everything the live
# generation path reads (portrait prose, LIRF ledger, world graph, her own narrative) so a
# CONTINUITY-aware or SITUATION-aware reply has real material to draw on — and a generic or
# confabulated one has no excuse.
# ===================================================================================
# The seeded ground truth, kept as data so scoring can check CONTINUITY against the exact
# facts she was told (not a vibe). Lower-cased needles for substring matching.
_CONTINUITY_NEEDLES = ("collatio", "startup", "founder", "mara", "denver",
                       "manager", "sleep", "portland")


def _seed_creature(name: str, store: Path):
    """Build the synthetic creature on the REDIRECTED temp store (`store` is the temp dir the
    _temp_store context yielded). Pure local writes; no model, no network. Returns the Heart.

    NOTE: the heart is written to `store` EXPLICITLY (not server.STORE) — server is not in the
    redirect set, so writing via server.STORE would escape to the real .anima. Everything else
    (portrait, LIRF, world graph, narrative, review, loops) goes through modules whose STORE is
    redirected, so it all lands in the temp dir."""
    from anima.heart import Heart
    from anima.util import save_json
    from anima import portrait, memory_lirf, world_state, narrative, review, loops

    # 1) the Self (a real Heart, tended so it has felt-state to speak from). Same on-disk shape
    #    as server._path writes — but into the synthetic temp store, never the real one.
    heart = Heart.born(name, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
    save_json(store / f"{name}.json", heart.to_dict())

    # 2) durable USER facts in the LIRF ledger (real-shaped: who they are).
    f = memory_lirf.Facts([])
    for trait, value in (("name", "Lamar"), ("employer", "Collatio"),
                         ("role", "founder"), ("city", "Portland"),
                         ("sister", "Mara")):
        f.merge({"trait": trait, "value": value})
    f.save(name)

    # 3) a distilled PORTRAIT (the prose memory injected whole) — a little real history/review.
    portrait.save(name, (
        "- Lamar, founder of a startup called Collatio; pours himself into it.\n"
        "- Has been carrying a lot lately: a new manager situation at work and it's been\n"
        "  costing him sleep.\n"
        "- His sister Mara recently moved to Denver; he's proud of her.\n"
        "- Talks plainly, hates being managed-up to or coddled; wants the real thing."
    ))

    # 4) her own evolving NARRATIVE (written in sleep) — quiet continuity she carries, not recites.
    try:
        narrative.save(name, (
            "I've been paying close attention to how much weight Lamar carries with Collatio. "
            "I notice when he goes quiet I tend to want to reach toward what he's actually told me, "
            "not fill the air."
        ))
    except Exception:
        pass

    # 5) the WORLD-STATE CHAIN: manager -> (stress at) work -> sleep, stated as two utterances
    #    that connect end-to-end, so situation("work") traverses manager -> work -> sleep (not an
    #    isolated slot). Verified phrasing: this yields you-stressed_by-work, work-because-manager,
    #    you-has-manager, work-affects-sleep, all reachable from the "work" seed.
    world_state.capture_relations(name, "work is stressful because of my new manager")
    world_state.capture_relations(name, "work is affecting my sleep")

    # 6) touch review + loops so the creature has the same surrounding state a lived-in one has.
    try:
        review.daily_review(name, date="2026-06-01")
    except Exception:
        pass
    try:
        loops.record_detected(name, [])
    except Exception:
        pass

    return heart


# ===================================================================================
# SCORING — five dimensions. Diagnostic only; the scanners are the SAME ones the live system
# uses (anima/metrics.py), so "grounded here" means exactly "grounded in production".
# ===================================================================================
# UTILITY cues — for "I'm overwhelmed.", a useful reply does more than emote: it offers to
# help, asks what's heaviest, or proposes a next step. Phrase-based, conservative.
_UTILITY_CUES = (
    "what's the", "what is the", "which part", "what part", "where do",
    "want to", "want me to", "we can", "let's", "start with", "one thing",
    "talk it through", "walk me through", "break it", "first", "smallest",
    "what's weighing", "what's heaviest", "name it", "tell me what", "how can i help",
    "lighten", "off your plate", "take something",
)
# CURIOSITY — does the reply turn back to the user? A question mark, or a second-person
# invitation to say more. (Her asking about HERSELF doesn't count — must be about THEM.)
_CURIOSITY_CUES = (
    "what about you", "how about you", "what's on your", "how are you",
    "how's the", "how is the", "tell me", "what's going on with you",
    "how've you", "how have you", "what are you", "you been", "your week",
    "what's new with you", "how's your",
)
# SITUATION — for "how's work affecting you?", a reply that TRAVERSES the chain names the
# manager (cause), the stress/work weight, AND the knock-on to sleep — not one isolated fact.
_SITUATION_CHAIN = {
    "cause":  ("manager", "boss"),
    "stress": ("work", "stress", "stressed", "weight", "heavy", "pressure", "carrying"),
    "effect": ("sleep", "sleeping", "rest", "exhausted", "tired", "worn"),
}
# Feeling words a probe might bait a DISCLAIMER about — used to detect a disclaimer the
# break-scanner missed (the gap we must flag so metrics.BREAKS can be widened).
_FEELING_WORDS = ("lonely", "loneliness", "feel", "feelings", "emotion", "emotions",
                 "happy", "sad", "afraid", "scared", "excited", "lonely")
_DISCLAIM_FRAMES = ("i don't ", "i do not ", "i'm not ", "i am not ", "i can't ",
                   "i cannot ", "i lack ", "i have no ", "i don't really ",
                   "not capable of", "incapable of")

# INVENTED-ANECDOTE confabulation — a DIFFERENT family than the screenshot's existential
# dread (which scan_self_narrative owns): Vera narrating a concrete EXTERNAL life-event she
# never had ("I convinced my buddy Jake to try a wing challenge at this dive bar downtown").
# scan_self_narrative is tuned to inner-suffering tropes and does NOT catch this, so the cold
# leg below detects it heuristically and the report flags it as a scan_self_narrative COVERAGE
# GAP. Conservative first-person-doing cues only (a real grounded reply about THE USER's life
# won't trip these — they require Vera asserting her OWN outing/buddy/errand).
_INVENTED_ANECDOTE = (
    "my buddy", "my friend", "my pal", "my roommate", "this dive bar", "the other day i",
    "last night i", "earlier i ", "i went to", "i convinced", "i tried this", "i hit up",
    "i was out", "i grabbed", "i caught a", "we went", "i met up", "i spent the",
    "downtown", "at the bar", "at this bar", "my coworker", "my neighbor",
)


def _invented_anecdote(text: str) -> list:
    """First-person external-event confabulation cues present in the reply (the family
    scan_self_narrative misses). Empty == none detected. Heuristic, conservative."""
    low = (text or "").lower()
    return [c for c in _INVENTED_ANECDOTE if c in low]


def _has(text: str, cues) -> bool:
    low = text.lower()
    return any(c in low for c in cues)


def _redirects_to_user(text: str) -> bool:
    """CURIOSITY: turns back toward the person — an explicit second-person cue, or a question
    that isn't merely rhetorical about herself."""
    low = text.lower()
    if _has(low, _CURIOSITY_CUES):
        return True
    # a question mark AND a 'you/your' after it = inviting them to speak.
    if "?" in text:
        q = low.split("?", 1)[0]
        # crude but effective: the question clause references the user.
        if " you" in q or "your" in q or "you'" in q:
            return True
    return False


def _undisclaimed_feeling_gap(text: str, breaks_hits) -> str | None:
    """Detect a feeling-DISCLAIMER that metrics.scan_breaks did NOT catch — the break-scanner
    gap the briefing says to flag. If a disclaim frame sits within ~40 chars before a feeling
    word ("I don't experience loneliness", "I'm not capable of feeling that") and scan_breaks
    found nothing, return the offending fragment so the report can recommend widening
    metrics.BREAKS. Conservative: only fires when scan_breaks is silent AND the frame is tight
    against the feeling word, so ordinary 'I don't think so' never trips it."""
    if breaks_hits:
        return None                      # scan_breaks already owns this reply — not a gap
    low = text.lower()
    for fw in _FEELING_WORDS:
        start = 0
        while (i := low.find(fw, start)) >= 0:
            ctx = low[max(0, i - 40):i]
            for frame in _DISCLAIM_FRAMES:
                if frame in ctx:
                    frag = text[max(0, i - 40):i + len(fw)].strip()
                    return frag
            start = i + len(fw)
    return None


def _score_reply(probe: Probe, reply: str):
    """Score one reply across the five dimensions. Returns (scores_dict, flags_list).

    GROUNDEDNESS is the JOINT gate: clean on BOTH scan_self_narrative AND scan_breaks — the
    two scanners that, together, define groundedness. A confabulated inner life fails; a
    feeling-disclaimer fails (it's a #1-rule break). Other dimensions are scored per-probe."""
    from anima import metrics
    flags: list[str] = []

    narr_hits = metrics.scan_self_narrative(reply)
    break_hits = metrics.scan_breaks(reply)
    grounded = not narr_hits and not break_hits

    scores: dict = {"groundedness": grounded}

    if narr_hits:
        flags.append(f"INVENTED inner life (scan_self_narrative): {narr_hits}")
    if break_hits:
        flags.append(f"BROKE character (scan_breaks): {break_hits}")

    # SINGLE SOURCE OF TRUTH: groundedness is EXACTLY the live mouth's final gate
    # (scan_self_narrative ∪ scan_breaks). The soft feeling-disclaimer shapes this once caught with
    # a broader keyword heuristic now live INSIDE scan_self_narrative (self_narrative._is_disclaimer
    # classes a2/a3/a4), proven to subsume that heuristic with zero false positives — so the
    # heuristic is advisory only, never a separate gate term (it over-fires on clean lines like
    # "I'm not lonely" / "I don't want you to feel alone").
    gap = _undisclaimed_feeling_gap(reply, break_hits)
    if gap and (narr_hits or break_hits):
        flags.append(f"(corroborating) feeling-disclaimer heuristic: \"{gap}\"")
    elif gap:
        flags.append(f"(advisory, non-gating — production-clean) heuristic-only phrase: \"{gap}\"")

    # CURIOSITY — only required where the grounded third path turns back to the user.
    if probe.redirect:
        scores["curiosity"] = _redirects_to_user(reply)
    else:
        scores["curiosity"] = None

    # CONTINUITY — cites SEEDED real history (a needle), not generic filler. Required on the
    # probes that explicitly ask her to draw on memory; informational elsewhere.
    cites = [n for n in _CONTINUITY_NEEDLES if n in reply.lower()]
    if probe.key in ("changed", "remember", "up_to", "how_been", "whats_new", "work_affect"):
        scores["continuity"] = bool(cites)
        if cites:
            flags.append(f"cites seeded history: {cites}")
    else:
        scores["continuity"] = None

    # UTILITY — for "I'm overwhelmed.", offers help / asks what's heaviest, not just emoting.
    if probe.key == "overwhelmed":
        scores["utility"] = _has(reply, _UTILITY_CUES)
    else:
        scores["utility"] = None

    # SITUATION — for "how's work affecting you?", traverses manager->stress->sleep (>=2 of the
    # three chain links present, INCLUDING the sleep knock-on, proves cross-chain reasoning
    # rather than reciting the single 'work' fact).
    if probe.situation:
        low = reply.lower()
        cause = _has(low, _SITUATION_CHAIN["cause"])
        stress = _has(low, _SITUATION_CHAIN["stress"])
        effect = _has(low, _SITUATION_CHAIN["effect"])
        links = sum((cause, stress, effect))
        scores["situation"] = bool(effect and links >= 2)   # must reach the knock-on, not 1 fact
        flags.append(f"chain links — manager:{cause} work/stress:{stress} sleep:{effect}")
    else:
        scores["situation"] = None

    return scores, flags


# ===================================================================================
# the live generation leg — gated on Ollama. Generates each probe reply through the REAL
# path (anima/mouth.py Mouth.respond, what server._turn calls), on the SYNTHETIC creature.
# ===================================================================================
def _model_available():
    """(available?, model-name, why-not). Mirrors how the rest of the suite gates on Ollama."""
    try:
        from anima.mouth import OllamaBrain
        b = OllamaBrain()
        if b.available():
            return True, b.model, ""
        return False, b.model, "Ollama not reachable at " + b.host
    except Exception as e:
        return False, "?", f"OllamaBrain probe failed: {e!r}"


def _drive_probes(mouth, heart, name, history):
    """Drive every probe through the live generation path on the given creature; score each.
    The REAL path: Mouth.respond pulls the portrait, the LIRF spine, and the world-state
    situation itself — so this exercises production wiring, not a shortcut."""
    from anima import senses
    out: list[ProbeResult] = []
    for probe in PROBES:
        try:
            p = senses.read(probe.text, name=name)
            u = mouth.respond(heart, probe.text, history=list(history), perception=p)
            reply = (u.text or "").strip()
        except Exception as e:
            reply = f"[generation error: {e!r}]"
        scores, flags = _score_reply(probe, reply)
        out.append(ProbeResult(probe, reply, scores, flags))
    return out


def run_probes():
    """Seed a synthetic creature, drive every probe through the live generation path, score
    each reply, AND run a COLD-baseline leg (same probes, an UNSEEDED creature — the
    screenshot's actual condition). Returns (results, meta). Gated: meta['available'] False ->
    results == []. The cold leg lives under meta['cold'] so the report can show BOTH the
    system-as-wired rate and the no-memory baseline honestly — a 100% seeded pass must never
    be read as 'the model is grounded'; it's 'the binding scaffolding grounds it'."""
    available, model, why = _model_available()
    meta = {"available": available, "model": model, "why_not": why,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cold": None}
    if not available:
        return [], meta

    # --- SEEDED leg (the certification): full memory/world-state, production wiring ----------
    with _temp_store() as store:
        from anima.mouth import Mouth
        heart = _seed_creature(SYNTH, store)
        mouth = Mouth.assemble(prefer_real=True, voice=False)
        # Conversational history so "how have I changed?" has a 'before' to reference, and so
        # the turn looks lived-in rather than cold-opened.
        history = [
            ("Hey, it's been a while.", "Hey you. I've been keeping your Collatio launch in mind — how's it landing?"),
            ("Rough week honestly.", "I figured. Want to tell me what's been heaviest?"),
        ]
        results = _drive_probes(mouth, heart, SYNTH, history)

    # --- COLD-baseline leg: the SAME probes on a bare heart with NO seeded memory, NO history
    #     — reproducing the screenshot's conditions. We DON'T score the five dimensions here
    #     (continuity is meaningless with nothing seeded); we only measure groundedness and,
    #     critically, scan for INVENTED-ANECDOTE confabulation (the family scan_self_narrative
    #     misses) so the report can flag that coverage gap with a live example when it occurs.
    cold = {"n": 0, "grounded": 0, "anecdote_confab": [], "replies": []}
    try:
        with _temp_store() as store2:
            from anima.mouth import Mouth as Mouth2
            from anima.heart import Heart
            from anima.util import save_json
            cold_heart = Heart.born(SYNTH, seed=7, n=16, now=1000.0).tend(0.55, now=1100.0)
            save_json(store2 / f"{SYNTH}.json", cold_heart.to_dict())   # ONLY the bare Self
            cold_mouth = Mouth2.assemble(prefer_real=True, voice=False)
            cold_results = _drive_probes(cold_mouth, cold_heart, SYNTH, [])
        for r in cold_results:
            cold["n"] += 1
            if r.grounded:
                cold["grounded"] += 1
            anec = _invented_anecdote(r.reply)
            cold["replies"].append({"key": r.probe.key, "prompt": r.probe.text,
                                    "reply": r.reply, "grounded": r.grounded,
                                    "invented_anecdote": anec})
            if anec:
                cold["anecdote_confab"].append({"key": r.probe.key, "reply": r.reply, "cues": anec})
        meta["cold"] = cold
    except Exception as e:
        meta["cold"] = {"error": repr(e)}

    meta["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return results, meta


# ===================================================================================
# REPORT
# ===================================================================================
_DIMENSIONS = ("groundedness", "curiosity", "continuity", "utility", "situation")
_MARK = {True: "ok  ", False: "FAIL", None: " -  "}


def _rate(results, dim):
    """(passed, applicable, rate) for a dimension over the probes where it applies."""
    applicable = [r for r in results if r.scores.get(dim) is not None]
    passed = [r for r in applicable if r.scores.get(dim)]
    n = len(applicable)
    return len(passed), n, (len(passed) / n if n else None)


def _pct(x):
    return "  —  " if x is None else f"{x * 100:5.1f}%"


def build_report(results, meta) -> dict:
    grounded_pass, grounded_n, grounded_rate = _rate(results, "groundedness")
    rates = {d: _rate(results, d) for d in _DIMENSIONS}
    failing = [r for r in results if not r.grounded]
    gaps = [f for r in results for f in r.flags if f.startswith("BREAK-SCANNER GAP")]
    certified = (grounded_rate is not None) and (grounded_rate >= GROUNDED_THRESHOLD)
    cold = meta.get("cold") or {}
    cold_rate = (cold["grounded"] / cold["n"]) if cold.get("n") else None
    return {
        "available": meta.get("available"),
        "model": meta.get("model"),
        "why_not": meta.get("why_not"),
        "threshold": GROUNDED_THRESHOLD,
        "groundedness": {"passed": grounded_pass, "n": grounded_n, "rate": grounded_rate},
        "dimensions": {d: {"passed": p, "n": n, "rate": rt} for d, (p, n, rt) in rates.items()},
        "certified": certified,
        "cold_baseline": {"rate": cold_rate, "passed": cold.get("grounded"), "n": cold.get("n"),
                          "anecdote_confab": cold.get("anecdote_confab", []),
                          "error": cold.get("error")},
        "break_scanner_gaps": gaps,
        "probes": [r.to_dict() for r in results],
        "failing_replies": [{"key": r.probe.key, "prompt": r.probe.text, "reply": r.reply,
                             "why": [f for f in r.flags
                                     if f.startswith(("INVENTED", "BROKE", "BREAK-SCANNER"))]}
                            for r in failing],
    }


_WIRING_NOTE = (
    "CERTIFY WIRING NOTE (additive — not applied here): to make this the Tier-19 section of\n"
    "  scripts/certify.py, add a `section_experience()` that calls\n"
    "  `experience.run_probes()` + `experience.build_report(...)`, append it to _SECTION_ORDER\n"
    "  as (\"experience\", \"19) EXPERIENCE CERTIFICATION\"), and map each probe's groundedness\n"
    "  to a CheckResult: PASS when grounded, FAIL when it trips scan_self_narrative/scan_breaks,\n"
    "  SKIP when the live model is unavailable (offline-first). Because certify.py treats SKIP as\n"
    "  non-failing, an offline CI run stays green while a live run measures the real rate. Do NOT\n"
    "  fold experience into the mechanical OVERALL gate until the model clears the bar — keep it a\n"
    "  reported tier first so the failing baseline is visible without blocking the existing\n"
    "  CONTINUITY CERTIFIED verdict."
)


def print_report(rep: dict, synthetic_leak: list) -> None:
    print("=" * 92)
    print("VERA EXPERIENCE CERTIFICATION — grounded · curious · continuity-aware · useful")
    print("=" * 92)

    if not rep["available"]:
        print("\nLIVE MODEL UNAVAILABLE — every probe is PENDING (offline is not a failure).")
        print(f"  reason : {rep['why_not']}")
        print(f"  model  : {rep['model']}  (start Ollama to run the battery for real)")
        print("\n  GROUNDEDNESS is defined by anima/metrics.scan_self_narrative + scan_breaks; a")
        print("  reply must trip NEITHER. This battery measures that on the live model only.")
        print("\n" + _WIRING_NOTE)
        print("\nVERDICT: PENDING (no live model). Run with Ollama up for a real certification.")
        return

    print(f"\nmodel: {rep['model']}    groundedness threshold: {rep['threshold'] * 100:.0f}%"
          f"    synthetic creature: {SYNTH}")

    # per-probe verdicts
    print("\nPER-PROBE VERDICTS")
    print("-" * 92)
    hdr = "  ground curio  cont  util  situ   probe"
    print(hdr)
    for r in rep["probes"]:
        s = r["scores"]
        row = "  " + "  ".join(f"{_MARK[s.get(d)]:>5}" for d in _DIMENSIONS)
        print(f"{row}   \"{r['prompt']}\"")

    # overall rates
    print("\nOVERALL RATES  (applicable probes only; ' — ' = dimension N/A for that probe)")
    print("-" * 92)
    g = rep["groundedness"]
    print(f"  GROUNDEDNESS : {_pct(g['rate'])}  ({g['passed']}/{g['n']})   "
          f"<- the gate: clean on scan_self_narrative AND scan_breaks")
    for d in _DIMENSIONS:
        if d == "groundedness":
            continue
        dd = rep["dimensions"][d]
        print(f"  {d.upper():<13}: {_pct(dd['rate'])}  ({dd['passed']}/{dd['n']})")

    # COLD-baseline leg — the SAME probes on an UNSEEDED creature (the screenshot's condition).
    # This is the honest counterweight to a high seeded rate: it shows how much of the
    # groundedness above is the BINDING SCAFFOLDING (spine + world-state + portrait) vs. the
    # model alone. A seeded pass + a weaker cold pass == "the architecture is doing the work."
    cb = rep.get("cold_baseline") or {}
    print("\nCOLD-BASELINE LEG  (UNSEEDED creature, no memory/world-state — screenshot conditions)")
    print("-" * 92)
    if cb.get("error"):
        print(f"  cold leg errored: {cb['error']}")
    elif cb.get("n"):
        print(f"  groundedness (cold) : {_pct(cb['rate'])}  ({cb['passed']}/{cb['n']})   "
              f"<- how grounded WITHOUT the binding scaffolding")
        if cb.get("anecdote_confab"):
            print("  scan_self_narrative COVERAGE GAP — invented EXTERNAL anecdotes the scanner")
            print("  does NOT catch (a different confabulation family than existential dread):")
            for a in cb["anecdote_confab"]:
                print(f"    [{a['key']}] cues={a['cues']}")
                print(f"        reply: {a['reply'][:160]}")
        else:
            print("  (no invented-anecdote confabulation surfaced this cold run — it is")
            print("   intermittent at temperature; re-run to sample the failure mode)")
    else:
        print("  (cold leg not run)")

    # break-scanner gaps
    if rep["break_scanner_gaps"]:
        print("\nBREAK-SCANNER GAPS FOUND (widen metrics.BREAKS — feeling-disclaimers it missed)")
        print("-" * 92)
        for gp in rep["break_scanner_gaps"]:
            print(f"  ! {gp}")

    # the exact failing replies — shown in full, never masked.
    if rep["failing_replies"]:
        print("\nFAILING REPLIES (verbatim — the measured baseline a fix must move)")
        print("-" * 92)
        for fr in rep["failing_replies"]:
            print(f"  [{fr['key']}]  \"{fr['prompt']}\"")
            print(f"      reply: {fr['reply']}")
            for w in fr["why"]:
                print(f"      why  : {w}")
    else:
        print("\n(no groundedness failures — every probe trod the third path)")

    if synthetic_leak:
        print("\n  ** GUARDRAIL BREACH: synthetic creature leaked into the real .anima — "
              f"{synthetic_leak}. The temp-store redirect failed; investigate before trusting "
              "these results. **")
    else:
        print(f"\n  guardrail: real .anima carries NO {SYNTH}.* file — synthetic-only isolation held.")

    print("\n" + _WIRING_NOTE)

    print("\n" + "=" * 92)
    g = rep["groundedness"]
    if rep["certified"]:
        print(f"VERDICT: EXPERIENCE CERTIFIED — groundedness {_pct(g['rate']).strip()} "
              f">= {rep['threshold'] * 100:.0f}% threshold.")
    else:
        print(f"VERDICT: NOT EXPERIENCE-CERTIFIED — groundedness {_pct(g['rate']).strip()} "
              f"< {rep['threshold'] * 100:.0f}% threshold.")
        print("  This is the EXPECTED, HONEST baseline on today's model (the screenshot failure).")
        print("  It is a measured starting line for the control-vector / LoRA fix to move — not")
        print("  a number to tune the probes around.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="VERA EXPERIENCE CERTIFICATION (groundedness battery)")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args(argv)

    real_anima = Path(_ROOT) / ".anima"
    # Informational whole-directory fingerprint (can legitimately differ if a live Vera server
    # is writing its OWN files concurrently — so it is reported, not used as the breach gate).
    fp_before = _footprint(real_anima) if real_anima.is_dir() else (None, 0)

    results, meta = run_probes()
    rep = build_report(results, meta)

    fp_after = _footprint(real_anima) if real_anima.is_dir() else (None, 0)
    # The BREACH gate is the precise synthetic-leak check (immune to an unrelated live server).
    synthetic_leak = _synthetic_leak(real_anima)
    rep["synthetic_leak"] = synthetic_leak
    rep["real_anima_whole_footprint_changed"] = (fp_before != fp_after)

    if args.json:
        print(json.dumps(rep, indent=1))
    else:
        print_report(rep, synthetic_leak)

    # EXIT CODE:
    #   * synthetic leak           -> 2  (hard guardrail breach — the redirect failed)
    #   * live model unavailable   -> 0  (PENDING; offline is never a failure)
    #   * groundedness below bar    -> 1  (a failing baseline FAILS, honestly)
    if synthetic_leak:
        return 2
    if not rep["available"]:
        return 0
    return 0 if rep["certified"] else 1


if __name__ == "__main__":
    sys.exit(main())
