"""
server — the home host. Run it on your Mac; open it on your phone.

The creature and its (optional) voice live here on the laptop. The phone is just
a browser window: it sends what you say and plays back what the creature says.

    python3 -m anima.server --name Nova --neurons 256          # text
    python3 -m anima.server --name Nova --voice                # + Kokoro voice

On your home WiFi, open http://<laptop-ip>:8765 on the phone. From anywhere, put
a tunnel in front of it (Tailscale, or `cloudflared tunnel`) — no app to install.
"""

from __future__ import annotations

import argparse
import hmac
import json
import logging
import os
import secrets
import threading
import time
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")                       # quiet torch/HF startup noise
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .heart import Heart
from .memory import Memory
from .mouth import Mouth
from .util import label, save_json, load_json
from . import senses, portrait

STORE = Path(".anima")
WEB = Path(__file__).parent / "web"
MAX_BODY = 25 * 1024 * 1024          # cap request bodies (audio uploads) at 25 MB
_lock = threading.Lock()             # serialises a turn (state read-modify-write)
_model_lock = threading.Lock()       # guards one-time model loads
_MOUTH = None
_EARS = None
_VOICE = False                       # server voice mode (set at startup); the single mouth
                                     # always loads Kokoro when True, regardless of caller
_HISTMAX = int(os.environ.get("ANIMA_HISTORY", "24"))   # how many recent turns she keeps
_HISTORY = deque(maxlen=_HISTMAX)    # recent (you, her) turns — persisted so a restart
                                     # doesn't wipe her short-term memory
_CURIOSITY_ASKED = set()             # names that surfaced a curiosity question this process-
                                     # session — pace Law 002's gap-asking to one gentle aside
                                     # per session (conservative default; budget-tunable)

# ANIMA LAW 005 — DEPLOYED OVER BUILT. The deploy-fingerprint of THIS running process,
# captured ONCE at startup (see _capture_deploy / main). The /version endpoint serves it
# so a deploy check can confirm the RUNNING process executes the certified commit — git ==
# running. Defaults are the never-broke-startup fallbacks; never recomputed per request.
_DEPLOY = {"sha": "unknown", "branch": "unknown", "started": None}


def _git(*args) -> str:
    """Run a read-only git command in the repo dir and return its stripped stdout, or ""
    on ANY failure. GUARDED so a missing git / not-a-repo / timeout can NEVER raise — this
    feeds startup, and LAW 005 must add deploy-proof without ever risking the server boot."""
    import subprocess
    try:
        repo = Path(__file__).resolve().parent.parent      # anima/.. == repo root
        out = subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                             text=True, timeout=5)
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except Exception:
        pass
    return ""


def _capture_deploy() -> dict:
    """Fingerprint the commit THIS process is running, ONCE at startup. Short HEAD sha +
    branch via guarded subprocess (falls back to 'unknown'), plus an ISO start timestamp.
    Fully guarded: any failure yields the 'unknown' fallback rather than breaking boot."""
    try:
        sha = _git("rev-parse", "--short", "HEAD") or "unknown"
        branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    except Exception:
        sha, branch = "unknown", "unknown"
    return {"sha": sha, "branch": branch,
            "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def _hist_path(name):
    return STORE / f"{name}.history.json"


def _load_history(name):
    """Restore the recent conversation so a server restart doesn't erase her memory."""
    try:
        rows = load_json(_hist_path(name))
        if isinstance(rows, list):
            _HISTORY.extend((u, a) for u, a in rows[-_HISTMAX:])
    except Exception:
        pass


def _save_history(name):
    try:
        save_json(_hist_path(name), [[u, a] for u, a in _HISTORY])
    except Exception:
        pass


def _mouth():
    global _MOUTH
    if _MOUTH is None:
        with _model_lock:
            if _MOUTH is None:
                _MOUTH = Mouth.assemble(voice=_VOICE)   # built once with the server's voice mode
    return _MOUTH


def _reset_mouth():
    """Drop the cached mouth so the next turn rebuilds it (after a brain change)."""
    global _MOUTH
    with _model_lock:
        _MOUTH = None


def _ears():
    global _EARS
    if _EARS is None:
        with _model_lock:
            if _EARS is None:
                from .mouth import WhisperEars
                _EARS = WhisperEars()              # Whisper large-v3-turbo, loaded once
    return _EARS


def _transcribe(audio_bytes):
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        import sys
        t0 = time.perf_counter()
        text = _ears().listen(tmp)
        print(f"[timing] stt {time.perf_counter() - t0:.1f}s · {len(text.split())} words",
              file=sys.stderr)
        return {"text": text}
    except Exception as e:
        import sys
        print(f"[anima ears] transcription failed: {e}", file=sys.stderr)
        return {"text": ""}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _tts(data):
    """Synthesise ONE chunk of text to a WAV with Kokoro and return the bytes. The
    phone calls this per sentence and plays them in order, so speech starts after the
    first sentence instead of waiting for the whole reply to be voiced."""
    import os as _os
    import sys
    import tempfile
    import time as _time
    text = str(data.get("text", ""))[:2000].strip()
    if not text:
        return (400, "text/plain", b"empty")
    v = getattr(_mouth(), "voice", None)
    if v is None:
        return (503, "text/plain", b"voice unavailable")
    try:
        rate = float(data.get("rate", 1.0))
    except (TypeError, ValueError):
        rate = 1.0
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    try:
        t0 = _time.perf_counter()
        out = v.speak(text, {"rate": rate}, tmp)
        print(f"[timing] tts {(_time.perf_counter() - t0):.1f}s · {len(text.split())} words",
              file=sys.stderr)
        if not out:
            return (503, "text/plain", b"synth failed")
        with open(tmp, "rb") as fh:
            return (200, "audio/wav", fh.read())
    except Exception as e:
        print(f"[anima tts] {e}", file=sys.stderr)
        return (503, "text/plain", b"synth error")
    finally:
        try:
            _os.unlink(tmp)
        except OSError:
            pass


def _path(name):
    return STORE / f"{name}.json"


def _mem(name):
    return STORE / f"{name}.mem.json"


def _ensure(name, neurons):
    if not _path(name).exists():
        STORE.mkdir(exist_ok=True)
        save_json(_path(name), Heart.born(name, n=neurons).to_dict())


# ===================================================================================
# LERF-FIRST — the live wiring of the cognitive substrate into the reply path.
#
# THE SHIFT. Before this seam the live mouth was "LLM + LERF": every turn went to the
# language model, and LERF was a library tried nowhere on the hot path. This block makes
# the runtime LERF-FIRST for TASK-shaped requests: a matching ACTIVE skill is retrieved
# as compact context, rendered by the SMALL local model, and GROUNDED-verified — the full
# LLM/cloud is reached ONLY on verifier-failure or no-match. The LLM becomes the LAST
# resort, not the default.
#
# WHAT IT NEVER TOUCHES (non-negotiable). This path fires for TASK requests ONLY. Self-
# narrative / conversational / "how are you" / personal-feeling / personal-fact / device-
# capability turns are EXCLUDED here and flow through the EXISTING pipeline unchanged
# (rail -> honesty -> spine/memory -> mouth.respond's #1-rule guard). The #1 product rule
# (never break character, never confabulate an inner life) lives in mouth.respond and is
# the gate for every self turn; LERF routing must not, and does not, intercept those.
# This is TASK-EXECUTION routing — orthogonal to Vera's identity/agency (FROZEN until
# 2026-07-03). Nothing here asserts, denies, or shapes any self-model.
# ===================================================================================

# Per-turn route ledger — a lightweight JSONL append, one line per turn, NOT a heavy
# observatory. scripts/lerf_utilization.py reads it to compute the LERF Utilization Rate
# and the token/latency/cost deltas vs the all-LLM baseline.
class _SkipConvVerifier(Exception):
    """Internal sentinel: a LERF-solved task answer skips the conversational ignored-known-
    fact / confabulation backstop (that backstop is for self/personal replies). Raised inside
    the verifier try-block and swallowed by its existing `except Exception`, so the skip is a
    clean no-op with zero behaviour change for non-LERF turns."""


# The creature whose LERF skill library the live mouth retrieves from. SKILLS ARE A SHARED,
# creature-INDEPENDENT capability vault ("summarize a medical note", "plan errands") — the
# production library is .anima/default.lerf.json, which a population run keeps filling. This is
# DISTINCT from per-creature PERSONAL memory (facts/portrait/world-state), which always stays
# under the live creature's own name. So: task SKILLS come from this shared store; the memory/
# honesty/#1-rule path is untouched and remains per-creature. Env-overridable for a creature
# that grows its own private skill set later.
_LERF_SKILL_LIBRARY = os.environ.get("ANIMA_LERF_LIBRARY", "default")


def _routes_path(name):
    return STORE / f"{name}.lerf_routes.jsonl"


def _record_route(name, record):
    """Append ONE structured route decision for THIS turn. Fully guarded: a ledger hiccup
    can NEVER change a reply or break a turn (it runs after the reply is in hand)."""
    try:
        STORE.mkdir(exist_ok=True)
        record = dict(record or {})
        record.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with open(_routes_path(name), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


# The system prompt that drives the small local model when LERF EXECUTES a task. It is a
# TASK-EXECUTION instruction handed the retrieved skill as its whole context — deliberately
# NOT the persona/self system prompt. It carries no identity content and asks for no inner
# life: it is the language organ rendering a certified procedure, nothing more. The grounded
# verifier (lerf.verify_rendered_output) adjudicates the output before it is ever served.
_LERF_TASK_SYS = (
    "You are completing a concrete task. You have been given a verified skill describing "
    "exactly how to do it: its inputs, its steps, and the outputs it must produce. Follow "
    "that skill. Use ONLY the information in the user's request and the skill — do NOT invent "
    "facts, numbers, names, or dates that were not given. If a required detail is missing, "
    "say plainly what you need rather than guessing. Produce the outputs the skill specifies, "
    "clearly and concisely."
)


# ── LERF eligibility lexicons: a turn reaches the skill substrate ONLY if it is a directive ──
# TASK. The rail separates personal-fact / capability / generative, but a feeling-disclosure or a
# self-reflective ask lands in the SAME "generative" bucket as a real task. The #1 rule is that
# Vera answers a feeling as a COMPANION, never with a task skill — so the gate also requires the
# turn to be TASK-SHAPED and excludes first-person distress + self-reflection. Bias is toward
# EXCLUSION: a missed task only costs compression (the LLM still answers); a captured feeling is
# a companion failure. This is a POSITIVE allowlist of the bounded operations skills perform —
# not a blocklist of "bad" phrasings.
_LERF_TASK_VERBS = (
    r"summari[sz]e|recap|digest|draft|compose|reword|rewrite|reply to|respond to|plan|schedule|"
    r"organi[sz]e|arrange|extract|pull|list|enumerate|find|compare|contrast|triage|sort|"
    r"prioriti[sz]e|rank|prep|prepare|outline|translate|format|proofread|turn .* into|"
    r"break .* down|explain|brief me|walk me through|what are the|what'?s the|give me the"
)
_LERF_AFFECT = (
    r"overwhelm|anxious|anxiety|stress|\bsad\b|lonely|exhaust|tired|\blost\b|depress|worried|"
    r"\bworry\b|scared|afraid|angry|upset|burned out|burnt out|hopeless|numb|\bempty\b|miserable|"
    r"struggling|can'?t cope|falling apart|on edge|frustrated|defeated|overwhelmed"
)


def _lerf_companion_turn(t):
    """A feeling/state disclosure or a self-reflective/advice ask — owned by the companion, never
    LERF. (first-person + distress affect) OR a 'what should I / why do I / do you think I'
    reflection about the user's own life, behaviour, or decisions."""
    import re
    return bool(
        # first-person COPULA close to a distress word: "I'm overwhelmed", "I've been anxious",
        # "I feel lost" — the user describing THEIR OWN state (not an adjective on the material,
        # e.g. "summarize this stressful report" has no first-person copula -> not companion).
        re.search(r"\bi(?:'?m| am| feel| feeling| have been|'?ve been| was| get| keep|"
                  r" can'?t stop| cannot stop)\b[^.?!]{0,30}(" + _LERF_AFFECT + r")", t) or
        re.search(r"\b(what should i|why (do|am|did|does|is) i|should i|what do you think i|"
                  r"do you think i|help me (decide|figure|think|process)|how (do|am) i feel)\b", t)
    )


def _lerf_task_shaped(text):
    """True ONLY for a directive task request. A companion turn is excluded even if it mentions a
    task word ('I'm overwhelmed planning the move'); an otherwise non-companion turn is admitted on
    a task verb or an explicit this/these/attached reference to PROVIDED material to operate on."""
    import re
    t = (text or "").strip().lower()
    if not t or _lerf_companion_turn(t):
        return False
    if re.search(r"\b(" + _LERF_TASK_VERBS + r")\b", t):
        return True
    if re.search(r"\b(this|these|the following|attached|the above)\b", t):
        return True
    return False


def _lerf_eligible(name, text, cap_note, cloud_on):
    """Is THIS turn a TASK the LERF substrate should try FIRST? Returns the matched
    :class:`Route` (rung 3, lerf_skill) when eligible, else None.

    The gate is deliberately NARROW — four independent exclusions must ALL pass before
    a single skill is even considered, so a self/personal/conversational turn can never be
    captured by an incidental keyword match:

      1. A deterministic capability (route.py / cap_note) already owns the turn -> never LERF.
      2. The honesty rail classes this as PERSONAL or CAPABILITY (a personal-fact ask or a
         device-data ask) -> the EXISTING memory/honesty pipeline owns it -> never LERF.
      2b. The turn is not TASK-SHAPED — a first-person feeling/state disclosure or a self-
         reflective/advice ask (which the rail still calls "generative") -> the COMPANION path
         owns it -> never LERF. A feeling must never be answered with a task skill (#1 rule).
      3. The router's own decision must be exactly `lerf_skill` (rung 3): a real ACTIVE skill
         scored above the match floor. Any other route (deterministic_rule, lirf_memory,
         cloud, no_local_faculty) means "not a LERF-skill turn" -> fall through unchanged.

    Pure + guarded: any hiccup returns None (fall through to the existing pipeline), so the
    LERF path can only ever ADD a fast local answer, never remove the safe default."""
    if cap_note:                                    # (1) code already owns this turn
        return None
    try:
        from . import rail
        kind = rail.classify(text or "")
    except Exception:
        kind = "generative"
    if kind in ("personal", "capability"):          # (2) memory/honesty/device path owns it
        return None
    if not _lerf_task_shaped(text):                 # (2b) a feeling/reflection/companion turn is
        return None                                 #      never a task -> the companion path owns it
    try:
        from . import lerf_router
        # Route over the SHARED skill library (_LERF_SKILL_LIBRARY), not the creature's personal
        # store — the certified skills are a creature-independent vault. (We already excluded the
        # personal/capability turns above, so the router's memory/rule rungs are not in play here;
        # we only ever ACCEPT a rung-3 lerf_skill match below.)
        r = lerf_router.route_task(text or "", name=_LERF_SKILL_LIBRARY,
                                   caps_state={"cloud_on": bool(cloud_on)})
    except Exception:
        return None
    # (3) ONLY a genuine rung-3 skill match proceeds. Everything else is the existing path.
    if r.route == "lerf_skill" and r.skill_id:
        return r
    return None


def _lerf_task_first(name, text, route, mouth, cloud_on):
    """Execute a TASK with the LERF substrate: render the matched skill with the SMALL local
    model, then GROUNDED-verify. Returns (reply_text, ledger_record) on a verified solve, or
    (None, ledger_record) when it could not solve locally (no usable model output, or the
    verifier WITHHELD a contract-violating render) so the caller escalates to the LLM.

    GROUNDED CONTRACT: a render that fails lerf.verify_rendered_output is NEVER served — it is
    withheld and the turn escalates. The verifier is the gate, exactly as the router specifies.
    Fully guarded: any exception returns (None, record) -> the caller falls through to the LLM."""
    from . import lerf, lerf_router
    import time as _time
    t0 = _time.perf_counter()
    lib = _LERF_SKILL_LIBRARY                        # the shared certified-skill vault
    # Compact context: just the retrieved skill, explained — hundreds of tokens, not a stuffed
    # transcript. This is the prompt the small local model renders the task from.
    try:
        skill_ctx = lerf.assemble_skill_context(text, name=lib, limit=1)
    except Exception:
        skill_ctx = ""
    if not skill_ctx.strip():
        rec = {"route": "lerf_skill", "rung": route.rung, "solved": False,
               "outcome": "no_context", "skill_id": route.skill_id,
               "skill_name": route.skill_name, "score": route.score,
               "latency_ms": round((_time.perf_counter() - t0) * 1000.0, 1)}
        return None, rec
    user_msg = f"{skill_ctx}\n\nTASK:\n{text}"
    prompt_tokens = lerf.count_tokens(_LERF_TASK_SYS) + lerf.count_tokens(user_msg)
    # Render with the SAME local brain the mouth uses — but with the TASK-EXECUTION prompt,
    # never the persona/self prompt. No history is fed (a task render is self-contained on the
    # skill), which also keeps it off the conversational/self surface entirely.
    rendered = ""
    try:
        rendered = mouth.brain.reply(_LERF_TASK_SYS, user_msg, []) or ""
    except Exception as e:
        import sys
        print(f"[anima lerf] task render failed: {e}", file=sys.stderr)
        rendered = ""
    gen_ms = round((_time.perf_counter() - t0) * 1000.0, 1)
    if not rendered.strip():
        rec = {"route": "lerf_skill", "rung": route.rung, "solved": False,
               "outcome": "empty_render", "skill_id": route.skill_id,
               "skill_name": route.skill_name, "score": route.score,
               "prompt_tokens": prompt_tokens, "latency_ms": gen_ms}
        return None, rec
    # GROUNDED VERIFY — adjudicate the render against the skill CONTRACT via the router's rung
    # 5, over the SAME shared library the skill came from. The task text is the only grounded
    # input we have, so a fabricated figure not present in the request fails the check and the
    # render is WITHHELD.
    verdict = lerf_router.route_task(text, name=lib, rendered=rendered,
                                     inputs={"request": text},
                                     caps_state={"cloud_on": bool(cloud_on)})
    if verdict.route == "small_local_verified" and verdict.grounded:
        rec = {"route": "lerf_skill", "rung": 5, "solved": True, "outcome": "verified_local",
               "skill_id": route.skill_id, "skill_name": route.skill_name, "score": route.score,
               "grounded": True, "prompt_tokens": prompt_tokens, "latency_ms": gen_ms}
        return rendered.strip(), rec
    # Verifier FAILED -> withhold the render, escalate to the LLM. (GROUNDED: never serve it.)
    rec = {"route": "lerf_skill_then_llm", "rung": verdict.rung, "solved": False,
           "outcome": "verifier_withheld", "skill_id": route.skill_id,
           "skill_name": route.skill_name, "score": route.score, "grounded": False,
           "verifier_reasons": (verdict.why or "")[:300],
           "prompt_tokens": prompt_tokens, "latency_ms": gen_ms}
    return None, rec


def _turn(name, text, voice=False):
    """One exchange: feel it, record it, reply from state. Serialised for safety."""
    with _lock:
        _turn_t0 = time.perf_counter()             # MRI: wall-clock for the whole turn
        heart = Heart.from_dict(load_json(_path(name)))
        # ---- perception (MRI frame) ----
        _ps0 = time.perf_counter()
        p = senses.read(text, name=name)
        _perc_ms = (time.perf_counter() - _ps0) * 1000.0
        now = time.time()
        mem = Memory.load(_mem(name))
        last = mem.rows[-1]["clock"] if mem.rows else heart.last_tick
        mem.record(heart.input_vector(p.vector(), now), (now - last) / 60.0, now)
        mem.save(_mem(name))
        # ---- heart (MRI frame — the NEURAL layer) ----
        _hs0 = time.perf_counter()
        heart.perceive(p.vector(), now=now)
        _heart_ms = (time.perf_counter() - _hs0) * 1000.0
        audio_out = str(STORE / f"{name}.last.wav") if voice else None
        _tid = "t-%d" % int(now * 1000)            # telemetry: open a flight-recorder trace for this
        # MRI RECORDER (rich per-turn trace). One trace per turn, PASSIVE + GUARDED: every
        # record below is wrapped so a recorder failure can NEVER change a reply, break a
        # turn, or add meaningful latency. ``_mri`` is the open trace; ``_stg`` is a tiny
        # swallow-everything stage recorder so a call site never has to try/except inline.
        try:
            from . import telemetry as _telem
            _telem.get(name).begin(_tid)           # legacy lean bus-style trace (unchanged)
        except Exception:
            pass
        try:
            from . import telemetry as _telem2
            _mri = _telem2.open_trace(name, _tid, text)
        except Exception:
            _mri = None

        def _stg(*a, **k):
            try:
                if _mri is not None:
                    _mri.stage(*a, **k)
            except Exception:
                pass

        # perception frame: entities/sentiment + a SUMMARY of the 9-field percept vector.
        try:
            _pv = p.vector()
            _stg("perception", t_ms=_perc_ms,
                 in_shape={"text_chars": len(text or "")},
                 out={"sentiment": round(float(getattr(p, "mood", 0.0)), 3),
                      "presence": round(float(getattr(p, "presence", 0.0)), 3),
                      "attention": round(float(getattr(p, "attention", 0.0)), 3),
                      "distress": round(float(getattr(p, "distress", 0.0)), 3),
                      "seeking": round(float(getattr(p, "seeking", 0.0)), 3),
                      "vector": {f: round(float(v), 3)
                                 for f, v in zip(senses.PERCEPT_FIELDS, _pv.tolist())}},
                 dropped=["raw_text", "token_stream"],   # text is felt as 9 floats; the words drop here
                 confidence=round(float(getattr(p, "openness", 0.0)), 3),
                 note="text -> 9-field affect percept")
        except Exception:
            pass
        # heart frame: feeling vector + neuron-state summary + unrest (the NEURAL layer).
        try:
            import numpy as _np_h
            _feel = heart.feeling()
            _hvec = heart.h
            _stg("heart", t_ms=_heart_ms,
                 in_shape={"percept_dims": len(senses.PERCEPT_FIELDS), "neurons": int(heart.genome.n)},
                 out={"feeling": {k: round(float(v), 4) for k, v in _feel.items()},
                      "neurons": {"n": int(heart.genome.n),
                                  "mean": round(float(_np_h.mean(_hvec)), 4),
                                  "l2": round(float(_np_h.linalg.norm(_hvec)), 4),
                                  "max_abs": round(float(_np_h.max(_np_h.abs(_hvec))), 4)},
                      "unrest": round(float(heart.unrest), 4)},
                 dropped=[],                              # the heart loses nothing — it integrates all of it
                 confidence=None, note="LTC continuous-time state read")
            # shape: how the perception crosses into the heart.
            if _mri is not None:
                _mri.shape("perception->heart",
                           received={"type": "Perception", "fields": len(senses.PERCEPT_FIELDS)},
                           expected={"type": f"ndarray({len(senses.PERCEPT_FIELDS)},)+internal(4)"},
                           transformation="Perception.vector() then input_vector(): 9 affect floats "
                                          "+ 4 body-internal (bias,unrest,tod_sin,tod_cos)",
                           loss=["entities", "sentiment_label", "word_order"])
        except Exception:
            pass

        # deterministic capability router: fetch REAL live data (read) or prepare a
        # confirm-gated draft (send) in code, so the mouth narrates only what's proven
        # and NOTHING sends without an explicit confirm.
        from . import route
        _rt0 = time.perf_counter()
        routed = route.route(name, text)
        _route_cap_ms = (time.perf_counter() - _rt0) * 1000.0
        cap_note = routed.get("note") if routed else None
        # Organ 3 (Router): query-aware memory selection — inject ONLY the facts relevant
        # to THIS turn (not the blanket top-N), and decide the cheapest-sufficient path.
        # PII guard: blank the fact block on a cloud brain so private facts never leave.
        _route_dec, _fact_block, _cloud_on = None, None, False
        try:
            from .organs import router
            from . import cloud as _cl
            _cloud_on = _cl.is_cloud()
            _rs0 = time.perf_counter()
            _route_dec = router.route(name, text, {"cloud_on": _cloud_on})
            _route_sel_ms = (time.perf_counter() - _rs0) * 1000.0
            if not _cloud_on:
                _fact_block = _route_dec.selected_block
        except Exception:
            _route_sel_ms = 0.0

        # MRI: route frame — facts selected (ids+values) + the routing decision. The rows
        # themselves aren't kept on RouteDecision, so re-derive them via the SAME
        # deterministic O(ms) selection the router just ran (pure dict-scan over the
        # personal store — sub-ms, fully guarded). PII guard: values are redacted under a
        # cloud brain, exactly as the real fact block is blanked.
        _bind_rows = []
        try:
            from .organs import router as _router_mri
            _sel_rows, _ = _router_mri.select_facts(name, text)
            _bind_rows = list(_sel_rows or [])
        except Exception:
            _bind_rows = []
        try:
            _sel = [{"id": r.get("id"), "trait": r.get("trait"),
                     "value": ("<cloud:redacted>" if _cloud_on else str(r.get("value"))[:80])}
                    for r in _bind_rows if isinstance(r, dict)][:40]
            _mids = list(getattr(_route_dec, "memory_ids", []) or [])
            _dropped_route = []
            if _cloud_on and getattr(_route_dec, "selected_block", ""):
                _dropped_route.append("fact_block(PII: blanked for cloud brain)")
            _stg("route", t_ms=_route_cap_ms + _route_sel_ms,
                 in_shape={"text_chars": len(text or ""), "cloud_on": _cloud_on},
                 out={"capability": (cap_note[:200] if cap_note else None),
                      "selected_ids": _mids[:40],
                      "selected": _sel,
                      "model": getattr(_route_dec, "model", "local"),
                      "escalation": getattr(_route_dec, "escalation", ""),
                      "reason": getattr(_route_dec, "reason", "")},
                 dropped=_dropped_route,
                 confidence=None, note="capability route + query-aware memory selection")
            # the brain-choice alternative (the road not taken).
            if _mri is not None:
                _sel_model = getattr(_route_dec, "model", "local") or "local"
                _is_local = not str(_sel_model).startswith("cloud")
                _mri.alternative("route:brain",
                                 selected=_sel_model,
                                 rejected=[{"option": ("cloud" if _is_local else "local"),
                                            "reason": ("cloud paused for privacy / not configured"
                                                       if _is_local else
                                                       "local sufficient — no escalation")}])
        except Exception:
            pass

        # MRI: bind frame — the bound spine block + per-fact truth-classes. spine.bind is
        # pure + model-free (sub-ms); it renders the SAME binding contract the mouth uses,
        # so the trace shows exactly what was bound for this turn and at what truth-class.
        try:
            from . import spine as _spine_mri
            _bs0 = time.perf_counter()
            _bound = _spine_mri.bind(_bind_rows, text)
            _tc = {}
            for r in _bind_rows:
                if isinstance(r, dict):
                    _cls = _spine_mri.truth_class(r)
                    if _cls:
                        _tc[str(r.get("trait", "?"))] = _cls
            _bind_ms = (time.perf_counter() - _bs0) * 1000.0
            _stg("bind", t_ms=_bind_ms,
                 in_shape={"selected_facts": len(_bind_rows)},
                 out={"block_len": len(_bound or ""), "truth_classes": _tc,
                      "bound": bool(_bound)},
                 dropped=[],
                 confidence=(1.0 if "KNOWN" in _tc.values() else None),
                 note="spine.bind: binding-evidence contract")
        except Exception:
            pass

        # MRI: situation + meaning — these do NOT run in the live turn path (the Life Graph
        # cluster and Meaning Objects are built at sleep / read on demand, never per-turn).
        # Recorded as explicit skip frames with a note so the Viewer shows them as black
        # boxes for the live turn rather than silently missing. (No latency added.)
        _stg("situation", t_ms=0.0, in_shape=None, out=None, dropped=[], confidence=None,
             note="N/A in live turn: world_state.situation() is on-demand/background, not per-turn")
        _stg("meaning", t_ms=0.0, in_shape=None, out=None, dropped=[], confidence=None,
             note="N/A in live turn: meaning.meaning() is built at sleep / read on demand, not per-turn")

        # MRI: prompt frame — the memory block fed to the mouth + history depth. NOTE: the
        # FULL system prompt is assembled INSIDE mouth.respond (mouth.system_prompt) and is
        # not returned to _turn, so its exact length is a black box here; we record the mem
        # block (what _turn controls) and flag the rest.
        try:
            _memblock = _fact_block if _fact_block else _bound
            _stg("prompt", t_ms=0.0,
                 in_shape={"history_turns": len(_HISTORY), "cloud_on": _cloud_on},
                 out={"mem_block_len": len(_memblock or ""),
                      "mem_block_present": bool(_memblock),
                      "cap_note_present": bool(cap_note),
                      "system_prompt_len": None},   # built inside the mouth — see note
                 dropped=[], confidence=None,
                 note="mem block + history; full system prompt assembled inside mouth.respond")
        except Exception:
            pass

        mouth = _mouth()
        # ── LERF-FIRST SEAM (ATTACHES: Wave 3) ────────────────────────────────────────────
        # Before the LLM speaks, ask the cognitive substrate to solve this turn. For a TASK-
        # shaped request with a matching ACTIVE skill, LERF retrieves the skill as compact
        # context, the SMALL local model renders it, and the GROUNDED verifier adjudicates the
        # output. On a verified solve we serve THAT and the LLM is never reached for this turn.
        # On a self/personal/conversational turn, or no skill match, or a verifier-withheld
        # render, this is a no-op and the EXISTING pipeline below runs UNCHANGED (the #1-rule
        # guard in mouth.respond remains the gate for every self turn). Fully guarded.
        _lerf_solved = False
        _lerf_reply = None
        _lerf_rec = None
        try:
            _lroute = _lerf_eligible(name, text, cap_note, _cloud_on)
            if _lroute is not None:
                _lerf_reply, _lerf_rec = _lerf_task_first(name, text, _lroute, mouth, _cloud_on)
                _lerf_solved = bool(_lerf_reply)
        except Exception:
            _lerf_solved, _lerf_reply, _lerf_rec = False, None, None
        _g0 = time.perf_counter()
        if _lerf_solved:
            # The task was solved LOCALLY by a certified skill, grounded-verified. Wrap it in an
            # Utterance so the SAME downstream bookkeeping (history, durable-fact capture, save,
            # telemetry) runs — but the conversational #1-rule/confabulation backstop and the
            # casual-turn aside are SKIPPED below (this is task output, not a self/feeling turn).
            from .mouth import Utterance as _Utt
            _hints = {"register": "plain", "rate": 1.0}
            try:
                _f_now = heart.feeling()
                from .mouth import delivery as _deliv
                _hints = _deliv(_f_now, 0)
            except Exception:
                pass
            _backend = getattr(getattr(mouth, "brain", None), "name", "local")
            u = _Utt(text=_lerf_reply, delivery=_hints,
                     backend=f"lerf:{_backend}", feeling="", audio_path=None)
            # Optional voice: synth the served task answer so the phone still gets audio.
            if voice and audio_out and getattr(mouth, "voice", None) is not None:
                try:
                    u.audio_path = mouth.voice.speak(_lerf_reply, _hints, audio_out)
                except Exception:
                    u.audio_path = None
        else:
            u = mouth.respond(heart, text, history=list(_HISTORY),
                              audio_out=audio_out, perception=p, cap_note=cap_note,
                              fact_block=_fact_block)
        gen_s = time.perf_counter() - _g0      # generation time (no TTS — that's streamed)
        # MRI: generate frame — model + reply + token count + tok/s. tok/s is the brain's
        # real measured rate; token count is estimated from rate*seconds (the brain doesn't
        # hand back an exact count here). Recorded immediately so the trace pins the FIRST
        # draft even if the verifier later regenerates/overrides (captured in 'verify').
        try:
            _tok_s = getattr(getattr(mouth, "brain", None), "last_tok_s", None)
            _ntok = int(round(_tok_s * gen_s)) if (_tok_s and gen_s) else None
            _stg("generate", t_ms=gen_s * 1000.0,
                 in_shape={"mem_block_len": len((_fact_block if _fact_block else _bound) or "")},
                 out={"model": getattr(u, "backend", ""),
                      "reply": (getattr(u, "text", "") or "")[:2000],
                      "reply_chars": len(getattr(u, "text", "") or ""),
                      "tokens_est": _ntok,
                      "tok_s": (round(float(_tok_s), 1) if _tok_s else None),
                      "feeling": getattr(u, "feeling", "")},
                 dropped=[], confidence=None,
                 note="first draft (verifier may regenerate — see verify frame)")
        except Exception:
            pass
        # Organ 4 (Verifier) + Knowledge Spine ENFORCEMENT: check the draft against its
        # evidence (facts in play + the capability result) BEFORE it ships, and when it
        # overrides for an IGNORED KNOWN FACT (a fact on disk AND asked-for, yet disclaimed
        # or omitted — the exact failure the Spine exists to kill), ACT:
        #   1) REGENERATE once with the HARD binding contract (hard_bind=True);
        #   2) if it STILL disclaims, ship the deterministic floor (spine.answer_from_fact)
        #      so the KNOWN fact ALWAYS appears — never on model luck.
        # Strictly gated on a KNOWN fact existing, so an honest "I don't have that yet" on a
        # genuinely-unknown trait is NEVER touched (honesty preserved). Fully guarded: any
        # spine/verifier hiccup degrades to shipping the original draft — never breaks a turn.
        # A LERF-solved task answer was ALREADY grounded-verified against the skill contract
        # (lerf.verify_rendered_output) before it was served. The conversational ignored-known-
        # fact / confabulation backstop below is for self/personal replies and has no role on
        # certified task output, so the whole block is skipped for a LERF-solved turn.
        _verdict = None
        try:
            if _lerf_solved:
                raise _SkipConvVerifier()
            from .organs.verifier import verify
            from .memory_lirf import Facts as _VF, SELF as _VSELF
            from . import spine as _spine
            _evidence = _VF.load(name).about(_VSELF)
            _verdict = verify(text, u.text, _evidence, cap_note=cap_note)

            def _ignored_trait(v):
                """The trait slug from an ignored_known_fact override, or None."""
                if not v or not getattr(v, "override", False):
                    return None
                for iss in getattr(v, "issues", []) or []:
                    if str(iss).startswith("ignored_known_fact:"):
                        # issue shape: "ignored_known_fact:<trait>: ..."
                        return str(iss).split(":", 2)[1].strip()
                return None

            _bad_trait = _ignored_trait(_verdict)
            if _bad_trait:
                # (1) REGENERATE once with the hard binding contract.
                try:
                    _u2 = mouth.respond(heart, text, history=list(_HISTORY),
                                        audio_out=None, perception=p, cap_note=cap_note,
                                        fact_block=_fact_block, hard_bind=True)
                except Exception:
                    _u2 = None
                if _u2 is not None and getattr(_u2, "text", "").strip():
                    _v2 = verify(text, _u2.text, _evidence, cap_note=cap_note)
                    if _ignored_trait(_v2) is None:
                        u, _verdict = _u2, _v2     # the retry stated the fact — ship it
                    else:
                        # (2) STILL disclaiming after the hard contract — ship the
                        # deterministic floor so the known value appears no matter what.
                        _row = _VF.load(name).lookup(_VSELF, _bad_trait)
                        _floor = _spine.answer_from_fact(text, _row, name=name)
                        if _floor and _floor.strip():
                            u.text = _floor
                            _verdict = verify(text, u.text, _evidence, cap_note=cap_note)
                        else:
                            u, _verdict = _u2, _v2  # floor declined (not KNOWN) — keep retry
                else:
                    # regenerate failed outright — go straight to the deterministic floor.
                    _row = _VF.load(name).lookup(_VSELF, _bad_trait)
                    _floor = _spine.answer_from_fact(text, _row, name=name)
                    if _floor and _floor.strip():
                        u.text = _floor
                        _verdict = verify(text, u.text, _evidence, cap_note=cap_note)
            else:
                # HONESTY GUARD (the inverse of ignored-known): the draft CONFABULATED a hard
                # personal specific the evidence can't back (e.g. invents a birthday that was
                # never stored). The #1 rule forbids shipping a fabricated personal fact, so
                # regenerate ONCE under the binding contract (whose [UNKNOWN] line steers her
                # to admit + ask); if she STILL invents, ship the spine's honest UNKNOWN
                # phrasing so she NEVER asserts a fact she doesn't have. No floor here — there
                # is no KNOWN value to assemble, and inventing one is the very failure we block.
                def _confab_trait(v):
                    if not v or not getattr(v, "override", False):
                        return None
                    for iss in getattr(v, "issues", []) or []:
                        s = str(iss)
                        if s.startswith("unsupported_personal_claim:") and "confabulation" in s:
                            # issue shape: "unsupported_personal_claim: reply asserts <trait> = ..."
                            m = _re_confab.search(s)
                            return m.group(1) if m else None
                    return None
                import re as _re
                _re_confab = _re.compile(r"reply asserts (\w+) =")
                _fab_trait = _confab_trait(_verdict)
                if _fab_trait and _VF.load(name).lookup(_VSELF, _fab_trait) is None:
                    try:
                        _u2 = mouth.respond(heart, text, history=list(_HISTORY),
                                            audio_out=None, perception=p, cap_note=cap_note,
                                            fact_block=_fact_block, hard_bind=False)
                    except Exception:
                        _u2 = None
                    if _u2 is not None and _confab_trait(
                            verify(text, _u2.text, _evidence, cap_note=cap_note)) is None:
                        u = _u2                         # the retry stopped inventing — ship it
                    else:
                        # still confabulating — emit the spine's honest UNKNOWN phrasing.
                        _hon = _spine.honest_unknown(text, name=name)
                        if _hon and _hon.strip():
                            u.text = _hon
                    _verdict = verify(text, u.text, _evidence, cap_note=cap_note)
        except Exception:
            pass
        # MRI: verify frame — verdict + issues + whether it overrode (regenerated/floored).
        try:
            _ov = bool(getattr(_verdict, "override", False)) if _verdict is not None else False
            _issues = [str(i) for i in (getattr(_verdict, "issues", []) or [])] if _verdict is not None else []
            try:
                _vconf = float(getattr(_verdict, "confidence", None)) if _verdict is not None else None
            except (TypeError, ValueError):
                _vconf = None
            _stg("verify", t_ms=0.0,
                 in_shape={"reply_chars": len(getattr(u, "text", "") or ""),
                           "evidence_facts": (len(_evidence) if "_evidence" in dir() else None)},
                 out={"verdict": ("override" if _ov else ("ok" if _verdict is not None else "skipped")),
                      "issues": _issues[:20],
                      "override": _ov},
                 dropped=[], confidence=_vconf,
                 note=("verifier enforced the spine (regenerate/floor)" if _ov else "draft passed"))
        except Exception:
            pass
        _HISTORY.append((text, u.text))           # within-session memory
        _save_history(name)                        # survive a restart
        try:                                       # record model use for the cleanup routine
            from . import models, cloud
            if not cloud.is_cloud():
                models.touch(models.active_local())
        except Exception:
            pass
        portrait.log_turn(name, text, u.text)      # logged for the next sleep to distil
        _lirf_written, _edges_written = [], []
        _cap_ms = 0.0
        try:                                       # capture durable user-facts NOW (birthday, dog…)
            from . import memory_lirf               # into the LIRF ledger — immediate, not just at
            _cs0 = time.perf_counter()
            _lirf_written = memory_lirf.capture(name, text) or []   # sleep → a fact told today is known tomorrow.
            _cap_ms += (time.perf_counter() - _cs0) * 1000.0
        except Exception:
            pass
        try:                                       # Personal World State: capture relational/causal
            from . import world_state               # edges from THIS turn (additive, union-safe save,
            _ws0 = time.perf_counter()
            _edges_written = world_state.capture_relations(name, text) or []  # race-free under _lock.
            _cap_ms += (time.perf_counter() - _ws0) * 1000.0
        except Exception:
            pass
        # MRI: capture frame — the CONSERVATION ledger of this turn. What durable structure
        # the turn extracted from the utterance (LIRF facts + world edges WRITTEN) vs. what
        # it let go: the utterance text itself is NOT stored as a fact unless it names a
        # durable trait/relation, so everything not lifted is the 'dropped' salient mass.
        try:
            def _fact_brief(r):
                if not isinstance(r, dict):
                    return {"raw": str(r)[:80]}
                return {"id": r.get("id"), "trait": r.get("trait"),
                        "value": str(r.get("value"))[:80], "status": r.get("status")}

            def _edge_brief(e):
                if not isinstance(e, dict):
                    return {"raw": str(e)[:80]}
                return {"subject": e.get("subject"), "predicate": e.get("predicate"),
                        "object": e.get("object")}
            _kept = len(_lirf_written) + len(_edges_written)
            _stg("capture", t_ms=_cap_ms,
                 in_shape={"utterance_chars": len(text or "")},
                 out={"lirf_facts_written": [_fact_brief(r) for r in _lirf_written][:40],
                      "world_edges_written": [_edge_brief(e) for e in _edges_written][:40],
                      "facts_kept": len(_lirf_written),
                      "edges_kept": len(_edges_written),
                      "salient_kept": _kept},
                 dropped=([] if _kept else ["utterance carried no durable fact/edge to store"]),
                 confidence=None,
                 note="conservation: durable structure lifted from this utterance (rest is transient)")
        except Exception:
            pass
        _aside_kind, _aside_gated, _aside_line = None, False, None   # MRI: curiosity-stage tracking
        try:                                       # PROACTIVE ASIDE — at most ONE gentle, optional aside
            from . import curiosity, loops, cloud as _cc  # per session, only on a CASUAL turn (no fact
            _aside_gated = (not _cc.is_cloud()      # remember WHY the aside was/ wasn't even attempted
                            and name not in _CURIOSITY_ASKED
                            and not _fact_block and not cap_note
                            and not _lerf_solved    # a certified task answer is not a casual turn
                            and not (_verdict is not None and getattr(_verdict, "override", False)))
            if _aside_gated:                        # answered, no capability, no verifier override; cloud-off (PII)
                _aside = None
                try:                                # 1) Opportunity Engine: a grounded, optional OFFER
                    from . import opportunity        # "want me to…?" — paced; an OFFER, never an action
                    _op = opportunity.next_opportunity(name)
                    if _op and _op.strip():
                        _oc = opportunity.last_opportunity_choice()
                        if _oc:
                            opportunity.mark_offered(name, _oc, line=_op)
                        _aside, _aside_kind = _op.strip(), "opportunity"
                except Exception:
                    _aside = None
                if not _aside:
                    try:                            # 2) Dream Engine: resurface a stalled open loop —
                        _rl = loops.resurface(name)  # "you wanted X — still?" (paced + 21-day cooldown)
                        if _rl and _rl.strip():
                            _ch = loops.last_resurface_choice()
                            if _ch:
                                loops.mark_resurfaced(name, _ch, line=_rl)  # never re-nag (Law 001)
                            _aside, _aside_kind = _rl.strip(), "loop"
                    except Exception:
                        _aside = None
                if not _aside:                      # 3) else a contextual curiosity question (Law 002)
                    try:
                        _q = curiosity.next_question(name, recent_text=text)
                        if _q and _q.strip():
                            _cands = curiosity.candidate_gaps(name)
                            if _cands:
                                curiosity.mark_asked(name, _cands[0])   # never re-ask this gap (Law 002)
                            _aside, _aside_kind = _q.strip(), "curiosity"
                    except Exception:
                        _aside = None
                if _aside:                          # surface exactly one, persist, mark the session
                    _aside_line = _aside
                    u.text = u.text.rstrip() + "\n\n" + _aside
                    _HISTORY[-1] = (text, u.text)                       # within-session coherence
                    _save_history(name)                                 # persist it (Law 001)
                    _CURIOSITY_ASKED.add(name)
        except Exception:
            pass
        # MRI: curiosity frame — the gaps it sees, the candidate questions, which aside (if
        # any) it SELECTED, and the REJECTED candidates with the reason. Read-only + guarded;
        # candidate_gaps is the same O(ms) detection the aside used. The 'rejected' list is
        # the runner-up gaps that lost to the top one this turn (Law 002 pacing).
        try:
            from . import curiosity as _cur_mri
            _gaps, _cands_mri = [], []
            try:
                _gaps = _cur_mri.detect_gaps(name) or []
                _cands_mri = _cur_mri.candidate_gaps(name) or []
            except Exception:
                pass

            def _gap_label(g):
                if not isinstance(g, dict):
                    return str(g)[:60]
                return (g.get("entity") or "you") + ":" + (g.get("slot") or g.get("trait") or "?")
            _cand_labels = [_gap_label(g) for g in _cands_mri][:20]
            _selected = (_aside_kind + ":" + (_aside_line[:80] if _aside_line else "")) if _aside_kind else None
            # reasons why the aside stayed silent (the common, important case to SEE).
            if not _aside_kind:
                if not _aside_gated:
                    _why_silent = "gated off: cloud brain / fact answered / capability / override / already asked this session"
                elif not _cands_mri:
                    _why_silent = "no un-asked gaps available"
                else:
                    _why_silent = "budget/pacing held it silent this turn"
            else:
                _why_silent = ""
            _rejected = []
            for g in _cands_mri[1:6]:               # runners-up that lost to the top candidate
                _rejected.append({"option": _gap_label(g),
                                  "reason": "lower priority than the selected gap this turn"})
            _stg("curiosity", t_ms=0.0,
                 in_shape={"gaps_detected": len(_gaps)},
                 out={"candidates": _cand_labels,
                      "selected": _selected,
                      "aside_kind": _aside_kind,
                      "silent_reason": _why_silent},
                 dropped=[g["option"] for g in _rejected],
                 confidence=None,
                 note=("asked one gentle aside" if _aside_kind else ("silent: " + _why_silent)))
            if _mri is not None and (_selected or _rejected):
                _mri.alternative("curiosity:which gap to surface",
                                 selected=(_cand_labels[0] if (_aside_kind == "curiosity" and _cand_labels) else _selected),
                                 rejected=_rejected)
        except Exception:
            pass
        save_json(_path(name), heart.to_dict())    # atomic — never half-written
        try:                                       # telemetry: record what crossed each edge this turn —
            import types as _t                     # the model, the memory facts in play, the routing
            from . import telemetry as _telem      # decision, and the verifier's verdict. "See the edge,
            if _route_dec is not None:             # don't guess it." Read back via telemetry.last/replay.
                _telem.get(name).note_decision(_tid, _route_dec.as_decision())   # the REAL routing verdict
            else:
                _fids = []
                try:
                    from .memory_lirf import Facts as _Facts
                    _fids = [f.get("id") for f in (_Facts.load(name).about() or []) if isinstance(f, dict)][:40]
                except Exception:
                    pass
                _telem.get(name).note_decision(_tid, _t.SimpleNamespace(
                    model=getattr(u, "backend", ""), memory_ids=_fids,
                    contributing_organs=(["capability"] if cap_note else []) + (["memory"] if _fids else []),
                    escalation=("capability" if cap_note else ""), answer_plan=""))
            if _verdict is not None:               # the verifier's verdict, as its own observation
                _ov = getattr(_verdict, "override", False)
                _telem.get(name).note_observation(_tid, _t.SimpleNamespace(
                    organ="verifier", weight=1.0,
                    memory={"id": None, "confidence": getattr(_verdict, "confidence", None)},
                    note=("override: " + "; ".join(getattr(_verdict, "issues", []))) if _ov else "ok"))
            _telem.get(name).commit(_tid)
        except Exception:
            pass
        out = {
            "reply": u.text, "feeling": u.feeling, "register": u.delivery["register"],
            "rate": u.delivery["rate"], "backend": u.backend,
            "audio_url": f"/audio?name={name}&t={int(now)}" if u.audio_path else None,
            "gen_s": round(gen_s, 1),               # so the phone can show reply speed
        }
        # SOURCE-AWARE ATTRIBUTION (Intake Wave 3, Q — safe layer): surface which uploaded
        # REFERENCE sources are relevant to this question, labeled and distinct from personal
        # memory. This NEVER touches u.text (the reply is byte-for-byte unchanged) — it only adds
        # an attribution channel the UI can show as "based on: <your uploaded doc>". Fully guarded
        # so it can never change or break a turn. (Reference-GROUNDED generation — the model
        # answering FROM the source — is a separate step that must clear the #1-rule battery first.)
        try:
            from . import source_aware as _srcaware
            _srcs = _srcaware.relevant_sources(name, text)
            if _srcs:
                out["sources"] = _srcs
        except Exception:
            pass
        tok = getattr(getattr(mouth, "brain", None), "last_tok_s", None)
        if tok:
            out["tok_s"] = round(tok)
        if routed and routed.get("send"):          # surface a pending draft for the UI
            s = routed["send"]                      # to render a confirm card. Sends nothing.
            try:
                d = json.loads(_draft(f"/{s['kind']}/draft", {"to": s["to"], "body": s["body"]}))
                if d.get("ok"):
                    out["draft"] = d["draft"]       # {id, kind, to, body}
            except Exception:
                pass
        # LERF ROUTE LEDGER — one structured line per turn (which rung solved it, full-solve
        # vs partial vs LLM-required, prompt tokens used vs the all-LLM baseline, latency). This
        # is what makes the LERF Utilization Rate measurable. Lightweight + guarded — appended
        # after the reply is already in `out`, so it can never change or slow the served answer.
        try:
            _total_ms = round((time.perf_counter() - _turn_t0) * 1000.0, 1)
            # The all-LLM baseline: what an LLM-only turn pays in prompt tokens — the full system
            # prompt + the injected memory/fact block + the conversation history. Estimated with
            # lerf.count_tokens so it is comparable to the LERF prompt-token figure.
            from . import lerf as _lerf_tok
            _baseline_src = " ".join(str(x) for x in (
                (_fact_block or _bound or ""),
                str(text or ""),
                " ".join((a or "") + " " + (b or "") for a, b in list(_HISTORY)[-6:]),
            ))
            _llm_baseline_tokens = _lerf_tok.count_tokens(_baseline_src) + 220  # +persona floor
            if _lerf_solved and _lerf_rec is not None:
                _rec = dict(_lerf_rec)
                _rec["solver"] = "lerf_skill"
                _rec["llm_required"] = False
                _rec["llm_baseline_tokens"] = _llm_baseline_tokens
                _rec["total_ms"] = _total_ms
            else:
                # The turn went to the existing pipeline. Name the rung that actually carried it:
                # a deterministic capability (route.py), the LIRF memory/fact path (a fact block
                # was bound), or the LLM as the genuine last resort. If LERF was ATTEMPTED but
                # withheld by the verifier, carry that provenance through.
                if cap_note:
                    _solver, _rt = "deterministic_rule", "deterministic_rule"
                elif _fact_block or _bound:
                    _solver, _rt = "lirf_memory", "lirf_memory"
                else:
                    _solver, _rt = "llm", "llm"
                _rec = {"route": _rt, "solver": _solver, "solved": _solver != "llm",
                        "llm_required": _solver == "llm",
                        "prompt_tokens": _llm_baseline_tokens,
                        "llm_baseline_tokens": _llm_baseline_tokens,
                        "latency_ms": round(gen_s * 1000.0, 1), "total_ms": _total_ms}
                if _lerf_rec is not None:        # LERF was tried first but did not solve locally
                    _rec["lerf_attempt"] = {k: _lerf_rec.get(k) for k in
                                            ("outcome", "skill_name", "score", "grounded")}
            _record_route(name, _rec)
        except Exception:
            pass
        # MRI: close + flush the full per-turn trace (ONE jsonl line). total_ms is the real
        # wall-clock for the whole turn. Last thing before returning; fully guarded so a
        # recorder failure can never touch the reply the user already has in `out`.
        try:
            if _mri is not None:
                _mri.commit(reply=u.text, total_ms=(time.perf_counter() - _turn_t0) * 1000.0)
        except Exception:
            pass
        return out


# --- outward-facing actions: draft → confirm → send (NEVER auto-send) -------
# A message/email is only sent by /…/send, and only if a matching draft exists and
# the capability is toggled on. The mouth can never send on its own.
_DRAFTS = {}                         # id -> {kind, to, subject, body, ts}


def _draft(path, data):
    """Create a pending draft and return it for review. Sends nothing."""
    kind = "imessage" if "imessage" in path else "mail"
    to = str(data.get("to", ""))[:200].strip()
    body = str(data.get("body", ""))[:4000]
    subject = str(data.get("subject", ""))[:300]
    if not to or not body:
        return json.dumps({"ok": False, "error": "a draft needs both 'to' and 'body'"})
    now = time.time()
    for k, v in list(_DRAFTS.items()):          # prune drafts older than an hour
        if now - v["ts"] > 3600:
            _DRAFTS.pop(k, None)
    did = secrets.token_hex(8)
    _DRAFTS[did] = {"kind": kind, "to": to, "subject": subject, "body": body, "ts": now}
    preview = {"id": did, "kind": kind, "to": to, "body": body}
    if kind == "mail":
        preview["subject"] = subject
    return json.dumps({"ok": True, "draft": preview})


def _confirm_send(name, path, data):
    """Send a previously-drafted message — the only path that actually sends."""
    from . import caps, applemac
    kind = "imessage" if "imessage" in path else "mail"
    if not caps.enabled(name, kind):
        return json.dumps({"ok": False, "error": f"{kind} is turned off in settings"})
    d = _DRAFTS.pop(str(data.get("id", "")), None)
    if not d or d["kind"] != kind:
        return json.dumps({"ok": False, "error": "no matching draft — draft and review it first"})
    if kind == "imessage":
        ok, detail = applemac.imessage_send(d["to"], d["body"])
    else:
        ok, detail = applemac.mail_send(d["to"], d["subject"], d["body"])
    return json.dumps({"ok": ok, "sent": ok, "to": d["to"], "detail": detail})


def _read_msgs(name, path, data):
    from . import caps, applemac
    kind = "imessage" if "imessage" in path else "mail"
    if not (caps.enabled(name, kind) and caps.enabled(name, f"{kind}_read")):
        return json.dumps({"ok": False, "error": f"{kind} reading is off in settings"})
    limit = int(data.get("limit", 10) or 10)
    res = applemac.imessage_recent(limit) if kind == "imessage" else applemac.mail_recent(limit)
    return json.dumps(res)


def _web_fetch(name, data):
    from . import caps, webget
    if not caps.enabled(name, "web"):
        return json.dumps({"ok": False, "error": "web access is off in settings"})
    c = caps.load(name)
    return json.dumps(webget.fetch(str(data.get("url", ""))[:2000], c["allowlist"]))


# --- proactive: serve a rendered briefing/reminder audio file ---------------
# proactive.render_audio writes .anima/<Name>.briefing.wav (Kokoro) or .aiff (`say`);
# a reminder escalation renders similarly. Caddy fronts vera.guruu.ai -> :8765, so a
# push payload can carry an https://vera.guruu.ai/audio/<name> URL the phone fetches
# (with the token) and plays. Serving is BASENAME-ONLY (no path traversal) and only
# from the .anima audio dir, gated behind _authed() like everything else.
_AUDIO_TYPES = {".wav": "audio/wav", ".aiff": "audio/aiff", ".aif": "audio/aiff",
                ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".caf": "audio/x-caf"}


def _serve_audio_file(fname: str):
    """Resolve a rendered audio file by BASENAME inside .anima/ and return
    (code, ctype, body). Path-traversal-safe: Path(...).name strips any dir, and we
    re-check the resolved parent is exactly the audio store before reading."""
    base = Path(str(fname)).name                       # drop any path components
    ext = Path(base).suffix.lower()
    if not base or ext not in _AUDIO_TYPES:
        return (404, "text/plain", b"no audio")
    f = (STORE / base)
    try:
        store_real = STORE.resolve()
        f_real = f.resolve()
    except OSError:
        return (404, "text/plain", b"no audio")
    # belt-and-suspenders: the resolved file MUST live directly in the audio store
    if f_real.parent != store_real or not f_real.is_file():
        return (404, "text/plain", b"no audio")
    return (200, _AUDIO_TYPES[ext], f_real.read_bytes())


# --- proactive: where the phone POSTs its location + push token -------------
# SECURITY: these are gated behind _authed() (see do_POST). With ANIMA_TOKEN UNSET,
# auth is OPEN — anything on the tailnet could spoof your location or hijack the push
# target — so this whole proactive subsystem REQUIRES ANIMA_TOKEN to be set. The
# stored values feed the morning briefing's weather (location) and the reminder/call
# push delivery (device token). Both persist via save_json (atomic + encrypted at
# rest iff ANIMA_KEY is set), same as the rest of .anima.
def _loc_path(name):
    return STORE / f"{name}.loc.json"


def _device_path(name):
    return STORE / f"{name}.device.json"


def _store_location(name, data):
    """Persist the phone's latest {lat, lon, ts} under .anima/. Validates the numbers;
    rejects junk so a bad post can't poison the weather lookup."""
    try:
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "lat and lon must be numbers"})
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return json.dumps({"ok": False, "error": "lat/lon out of range"})
    try:
        ts = float(data.get("ts"))
    except (TypeError, ValueError):
        ts = time.time()
    STORE.mkdir(exist_ok=True)
    save_json(_loc_path(name), {"lat": lat, "lon": lon, "ts": ts, "stored": time.time()})
    return json.dumps({"ok": True, "lat": lat, "lon": lon, "ts": ts})


def _store_device(name, data):
    """Persist the iPhone's push token(s) under .anima/, so the reminder subsystem can
    target APNs/PushKit. Accepts an APNs alert token and/or a VoIP (PushKit) token."""
    token = str(data.get("token", "")).strip()
    voip = str(data.get("voip_token", "")).strip()
    if not token and not voip:
        return json.dumps({"ok": False, "error": "need a 'token' (and/or 'voip_token')"})
    STORE.mkdir(exist_ok=True)
    rec = load_json(_device_path(name), default={}) or {}
    if token:
        rec["token"] = token[:512]
    if voip:
        rec["voip_token"] = voip[:512]
    rec["platform"] = str(data.get("platform", "ios"))[:32]
    rec["bundle_id"] = str(data.get("bundle_id", rec.get("bundle_id", "")))[:200]
    rec["updated"] = time.time()
    save_json(_device_path(name), rec)
    return json.dumps({"ok": True, "have_token": bool(rec.get("token")),
                       "have_voip": bool(rec.get("voip_token"))})


# ===========================================================================
# INTAKE HTTP HELPERS — pure functions called by the Handler dispatch. All real
# logic lives in intake / intake_queue / intake_search; these are thin adapters
# that handle staging I/O, wire the engine calls, and normalise the HTTP response.
# Each is importable/testable WITHOUT starting the HTTP server or the LLM brain.
# ===========================================================================

def _staging_dir(name: str) -> Path:
    """The staging directory for raw files awaiting approval."""
    return STORE / f"{name}.intake_staging"


def _write_staging(name: str, source_id: str, kind: str, data: dict) -> Path:
    """Write raw bytes/text to the staging path and return the path. The staging path
    is .anima/{name}.intake_staging/{source_id}.* — one file per ingest attempt."""
    import base64
    sd = _staging_dir(name)
    sd.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        fname = str(data.get("filename") or "upload.bin")
        ext = Path(fname).suffix or ".bin"
        p = sd / f"{source_id}{ext}"
        raw_b64 = data.get("bytes_b64") or ""
        if raw_b64:
            p.write_bytes(base64.b64decode(raw_b64))
        else:
            p.write_bytes(b"")
    elif kind == "url":
        p = sd / f"{source_id}.url"
        p.write_text(str(data.get("input") or ""), encoding="utf-8")
    else:
        # text or code
        p = sd / f"{source_id}.txt"
        p.write_text(str(data.get("text") or data.get("input") or ""), encoding="utf-8")
    return p


def _read_staging(name: str, source_id: str) -> tuple:
    """Find a staging file by source_id prefix. Returns (path, exists)."""
    sd = _staging_dir(name)
    if not sd.is_dir():
        return None, False
    for f in sd.iterdir():
        if f.suffix == ".meta":
            continue                       # the sidecar is not the raw content — skip it
        if f.stem == source_id or f.name.startswith(source_id + "."):
            return f, True
    return None, False


def _intake_plan(name: str, data: dict) -> dict:
    """POST /intake/plan handler. Stages raw, runs Wave-1 (no durable write), returns plan.

    The staging source_id is the stable round-trip key for /intake/approve.
    The trace_id in the response is the REAL id ingest() committed to the MRI trace file
    so /intake/trace?trace_id=... works. A tiny .meta sidecar persists the mapping.
    """
    from . import intake as _int
    kind = str(data.get("kind") or "text")
    source_id = _int._new_id("src")
    try:
        stage_path = _write_staging(name, source_id, kind, data)
    except Exception as e:
        return {"ok": False, "error": f"staging failed: {e!r}", "source_id": source_id}
    # run Wave-1 ingest on the staged path (or the URL directly for url kind)
    try:
        if kind == "url":
            ingest_input = str(data.get("input") or "")
        else:
            ingest_input = str(stage_path)
        result = _int.ingest(ingest_input, name=name)
        # capture the real trace_id (the id ingest() used when committing to the MRI trace)
        # BEFORE overriding source_id so /intake/trace lookups work.
        real_trace_id = str(result.trace_id or result.source.source_id)
        # override source_id so the staging round-trip key matches the staging filename
        result.source.source_id = source_id
        result.trace_id = real_trace_id  # preserve the real trace id (not the staging id)
        # persist a tiny sidecar so approve() can re-locate the real trace_id if needed
        try:
            meta_path = stage_path.parent / f"{source_id}.meta"
            import json as _json2
            meta_path.write_text(_json2.dumps({"staging_id": source_id,
                                               "real_trace_id": real_trace_id}),
                                 encoding="utf-8")
        except Exception:
            pass
    except Exception as e:
        return {"ok": False, "error": f"ingest failed: {e!r}", "source_id": source_id,
                "committed": False}
    d = result.to_dict()
    src = d.get("source") or {}
    return {
        "ok": True,
        "source_id": source_id,
        "trace_id": real_trace_id,
        "detected_type": d.get("detected_type"),
        "suggested_use": d.get("suggested_use"),
        "routing": d.get("routing"),
        "confidence": d.get("confidence"),
        "reason": d.get("reason"),
        "requires_user_confirmation": d.get("requires_user_confirmation"),
        "parse_status": d.get("parse_status"),
        "chunk_count": d.get("chunk_count"),
        "chunks_sample": d.get("chunks_sample"),
        "safety": d.get("safety"),
        "candidates": d.get("candidates"),
        "provenance": d.get("provenance"),
        "committed": False,
    }


def _intake_approve(name: str, data: dict) -> dict:
    """POST /intake/approve handler. Re-parses from staging, commits on the user's control."""
    from . import intake as _int
    from . import intake_queue as _iq
    from . import intake_parsers as _ip
    source_id = str(data.get("source_id") or "")
    control = str(data.get("control") or _iq.DEFAULT_CONTROL)
    delete_raw = bool(data.get("delete_raw") or control == _iq.CTL_DELETE_RAW)
    session = str(data.get("session") or "default")
    if not source_id:
        return {"ok": False, "error": "source_id required"}
    stage_path, found = _read_staging(name, source_id)
    if not found or stage_path is None:
        return {"ok": False, "error": f"staging file for source_id {source_id!r} not found"}
    # re-parse from staging
    try:
        if stage_path.suffix == ".url":
            ingest_input = stage_path.read_text(encoding="utf-8").strip()
        else:
            ingest_input = str(stage_path)
        result = _int.ingest(ingest_input, name=name)
        result.source.source_id = source_id
        result.trace_id = source_id
        parsed = _ip.parse(ingest_input)
    except Exception as e:
        return {"ok": False, "error": f"re-parse failed: {e!r}"}
    # commit
    try:
        receipt = _iq.commit_on_approval(result, parsed, control=control, name=name,
                                         session=session, delete_raw=delete_raw)
    except Exception as e:
        return {"ok": False, "error": f"commit failed: {e!r}"}
    # clean up staging once the source has been PROCESSED to any disposition — committed to a
    # durable store, added as reference, archived, or loaded as temporary — not only durable
    # commits. The single case we KEEP the staged raw is an explicit "review later" (CTL_REVIEW)
    # that committed nothing, so the user can still approve it later. delete_raw always purges.
    # Remove the staging directory too once it empties (so nothing lingers in the store).
    try:
        processed = bool(receipt.get("ok", True)) and control != _iq.CTL_REVIEW
        if receipt.get("committed") or delete_raw or processed:
            sd = stage_path.parent
            for f in list(sd.glob(f"{source_id}*")):   # the content file AND its .meta sidecar
                try:
                    f.unlink()
                except Exception:
                    pass
            if sd.is_dir() and not any(sd.iterdir()):   # drop the staging dir once it empties
                sd.rmdir()
    except Exception:
        pass
    receipt["ok"] = receipt.get("ok", True)
    return receipt


def _serve_library(name: str, query_string: str) -> dict:
    """GET /library handler. Returns normalised library items with optional section filter."""
    from . import intake_queue as _iq
    from urllib.parse import parse_qs
    qs = parse_qs(query_string)
    nm = qs.get("name", [name])[0]
    section = (qs.get("section", [""])[0] or "").lower()
    items = []
    # Reference Library items
    for ref in _iq.references(nm):
        if not isinstance(ref, dict):
            continue
        prov = ref.get("provenance") or {}
        rights = prov.get("rights_category") or "unknown"
        rtype = "reference"
        title = ref.get("title") or ""
        if "archive" in title.lower():
            rtype = "archive"
        elif rights == "public-web":
            rtype = "web_page"
        item = {
            "id": ref.get("id") or "",
            "title": title,
            "type": rtype,
            "source": prov.get("source") or prov.get("url_or_file") or "",
            "status": "active" if not ref.get("deleted") else "deleted",
            "destination": "Reference Library",
            "last_used": ref.get("stored_at") or "",
            "confidence": float(prov.get("confidence") or 0.0),
            "objects_extracted": 0,
            "rights": rights,
        }
        if not _section_matches(item, section):
            continue
        items.append(item)
    # Queue records (pending / in-progress / classified)
    for rec in _iq.queue(nm):
        if not isinstance(rec, dict):
            continue
        state = rec.get("state") or ""
        # skip if already represented in reference library
        rid = rec.get("source_id") or ""
        if any(it["id"] == rid for it in items):
            continue
        item = {
            "id": rid,
            "title": rec.get("title") or "",
            "type": rec.get("detected_type") or "reference",
            "source": (rec.get("provenance") or {}).get("url_or_file") or "",
            "status": state,
            "destination": (rec.get("routing") or [{"destination": ""}])[0].get("destination") or "",
            "last_used": rec.get("updated_at") or rec.get("created_at") or "",
            "confidence": float((rec.get("provenance") or {}).get("confidence") or 0.0),
            "objects_extracted": len(rec.get("candidate_ids") or []),
            "rights": rec.get("rights_category") or "unknown",
        }
        if not _section_matches(item, section):
            continue
        items.append(item)
    return {"ok": True, "items": items}


def _section_matches(item: dict, section: str) -> bool:
    """True if the item matches the requested library section filter (or no filter)."""
    if not section:
        return True
    itype = (item.get("type") or "").lower()
    dest = (item.get("destination") or "").lower()
    status = (item.get("status") or "").lower()
    if section == "references":
        return itype in ("reference", "book", "article", "web_page", "uploaded_pdf")
    if section == "your writing":
        return itype in ("personal_memory", "writing_sample", "project_document", "codebase")
    if section == "authoritative sources":
        return itype in ("book", "article", "authoritative")
    if section == "discussion topics":
        return itype in ("conversation_transcript", "temporary_context")
    if section == "training material":
        return "training" in dest
    if section == "personal documents":
        return itype in ("personal_memory", "legal_financial_medical")
    if section == "archived files":
        return status == "archived" or itype == "archive"
    if section == "extracted cognitive objects":
        return "lerf" in dest.lower()
    return True


def _serve_search(name: str, data: dict) -> dict:
    """POST /search handler. Cross-store labeled search via intake_search."""
    from . import intake_search as _is
    q = str(data.get("q") or "")
    nm = str(data.get("name") or name)
    scopes = data.get("scopes") or None
    if not q.strip():
        return {"ok": False, "error": "q (query) is required", "results": []}
    try:
        results = _is.search(q, name=nm, scopes=scopes)
    except Exception as e:
        return {"ok": False, "error": f"search failed: {e!r}", "results": []}
    return {"ok": True, "results": results}


def _serve_library_edit(name: str, data: dict) -> dict:
    """POST /library/edit handler. Dispatches to intake_queue.edit_item."""
    from . import intake_queue as _iq
    nm = str(data.get("name") or name)
    item_id = str(data.get("id") or "")
    action = str(data.get("action") or "")
    new_destination = data.get("new_destination")
    new_rights = data.get("new_rights")
    if not item_id:
        return {"ok": False, "error": "id is required"}
    if action not in _iq._VALID_EDIT_ACTIONS:
        return {"ok": False, "error": f"action must be one of {_iq._VALID_EDIT_ACTIONS}"}
    try:
        item, audit = _iq.edit_item(nm, item_id, action=action,
                                    new_destination=new_destination,
                                    new_rights=new_rights,
                                    reason=str(data.get("reason") or ""))
    except KeyError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"edit failed: {e!r}"}
    audit_out = {
        "from": audit.get("from"),
        "to": audit.get("to"),
        "when": audit.get("when"),
        "reason": audit.get("reason"),
    }
    return {"ok": True, "item": item, "audit": audit_out}


# --------------------------------------------------------------------------------------------
# HOST AWARENESS (Argus integration — FIRST WAVE: READ-ONLY). Reading the host picture is gated
# on the host_awareness capability (default OFF). There is deliberately NO host-action path in
# this wave (no pause/block endpoint exists), and the client integrates ONLY with a CERTIFIED,
# frozen, read-only Argus (the /capabilities handshake). Under a cloud brain specifics are redacted.
# --------------------------------------------------------------------------------------------
def _serve_host_awareness(name: str, cloud_on: bool) -> dict:
    """GET /host/awareness -> the human-level host picture, or {on:False} when not opted in.
    Under a cloud brain the specifics are redacted (host/process/IP are private)."""
    from . import caps, host_awareness
    if not caps.enabled(name, "host_awareness"):
        return {"on": False}
    try:
        return host_awareness.summary(name, cloud_safe=bool(cloud_on))
    except Exception:
        return {"on": True, "available": False,
                "headline": "Host awareness is on, but the monitor couldn't be reached."}


def _serve_host_timeline(name: str, hours: int) -> dict:
    """GET /host/timeline -> Argus's narrated recent history (read-only)."""
    from . import caps
    if not caps.enabled(name, "host_awareness"):
        return {"on": False}
    from .tools.argus_client import client
    c = client()
    if not c.available():
        return {"on": True, "available": False}
    return {"on": True, "available": True, "timeline": c.timeline(hours)}


def _serve_host_action_log(name: str) -> dict:
    """GET /host/action_log -> Argus's audit log of actions IT has taken (read-only)."""
    from . import caps
    if not caps.enabled(name, "host_awareness"):
        return {"on": False}
    from .tools.argus_client import client
    c = client()
    if not c.available():
        return {"on": True, "available": False}
    return {"on": True, "available": True, "action_log": c.action_log()}


def _serve_host_certification(name: str) -> dict:
    """GET /host/certification -> the Argus handshake result Vera verified BEFORE integrating
    (frozen release, ARGUS PRIME pass, loopback-only, read-only, 0 third-party deps)."""
    from . import caps
    if not caps.enabled(name, "host_awareness"):
        return {"on": False}
    from .tools.argus_client import client
    return {"on": True, **client().certification()}


class Handler(BaseHTTPRequestHandler):
    name = "Vera"
    voice = False
    token = ""        # set from ANIMA_TOKEN; "" disables auth

    def _authed(self) -> bool:
        if not self.token:
            return True
        q = parse_qs(urlparse(self.path).query)
        given = q.get("k", [""])[0] or self.headers.get("X-Anima-Key", "")
        auth = self.headers.get("Authorization", "")
        if not given and auth.startswith("Bearer "):
            given = auth[7:]
        return hmac.compare_digest(given, self.token)   # constant-time

    def _origin(self):
        host = self.headers.get("Host", "")
        return host.split(":")[0], f"https://{host}"     # (rp_id, origin) for WebAuthn

    def _passed(self) -> bool:
        """Second layer: when a passkey (Face ID) is required, a valid Face-ID session is
        needed on top of the token. Inert/opt-in — returns True unless required."""
        from . import passkey
        if not passkey.required():
            return True
        return passkey.valid_session(self.headers.get("X-Anima-Sess", ""))

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            n = 0
        return self.rfile.read(max(0, min(n, MAX_BODY)))

    def _fail(self, verb):
        import sys, traceback
        print(f"[anima server] {verb} {urlparse(self.path).path} failed: "
              f"{traceback.format_exc().strip().splitlines()[-1]}", file=sys.stderr)
        try:
            self._send(500, "text/plain", b"error")
        except Exception:
            pass

    def do_GET(self):
        try:
            u = urlparse(self.path)
            # the app SHELL is public (it holds no secrets); every DATA route below
            # still requires the token. The page remembers the token in localStorage,
            # so a saved/home-screen app keeps working without ?k= on every launch.
            if u.path in ("/", "/index.html"):
                html = ((WEB / "index.html").read_text(encoding="utf-8")
                        .replace("__NAME__", self.name).replace("__TOKEN__", ""))
                return self._send(200, "text/html; charset=utf-8", html.encode())
            if u.path == "/version":
                # ANIMA LAW 005 — DEPLOYED OVER BUILT. The deploy fingerprint of THIS
                # running process: the commit it is actually executing, captured ONCE at
                # startup. UNAUTHENTICATED by design — it is non-sensitive deploy metadata
                # (a short sha + branch + start time, no secrets, no personal data), and a
                # deploy check MUST be able to read it without a session to prove git ==
                # running. Served straight from the module-level stash; computes nothing here.
                return self._send(200, "application/json",
                                  json.dumps(_DEPLOY).encode())
            if not self._authed():
                return self._send(401, "text/plain", b"unauthorized")
            if u.path == "/auth/status":
                from . import passkey
                return self._send(200, "application/json", json.dumps(passkey.status()).encode())
            if not self._passed():               # Face ID required but not unlocked this session
                return self._send(401, "application/json", b'{"need_face_id":true}')
            if u.path == "/audio":
                nm = Path(parse_qs(u.query).get("name", [self.name])[0]).name  # no traversal
                f = STORE / f"{nm}.last.wav"
                if f.exists():
                    self._send(200, "audio/wav", f.read_bytes())
                else:
                    self._send(404, "text/plain", b"no audio")
            elif u.path.startswith("/audio/"):
                # serve a rendered briefing/reminder file by name so Caddy can deliver
                # it (a push payload carries this URL). Basename-only, .anima-only.
                self._send(*_serve_audio_file(u.path[len("/audio/"):]))
            elif u.path == "/state":
                heart = Heart.from_dict(load_json(_path(self.name)))
                self._send(200, "application/json", json.dumps(heart.feeling()).encode())
            elif u.path == "/persona":
                from .mouth import load_persona
                self._send(200, "application/json",
                           json.dumps({"persona": load_persona(self.name)}).encode())
            elif u.path == "/values":
                from .mouth import values_for_ui
                self._send(200, "application/json",
                           json.dumps({"values": values_for_ui(self.name)}).encode())
            elif u.path == "/dials":
                from . import dials
                self._send(200, "application/json",
                           json.dumps({"dials": dials.ui(self.name)}).encode())
            elif u.path == "/identity/export":
                from . import identity
                body = json.dumps(identity.export(self.name), ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{self.name}.identity.json"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif u.path == "/capabilities":
                from . import caps
                self._send(200, "application/json", json.dumps(caps.load(self.name)).encode())
            elif u.path == "/brain":
                from . import cloud
                self._send(200, "application/json", json.dumps(cloud.public()).encode())
            elif u.path == "/models":
                from . import models
                self._send(200, "application/json", json.dumps(models.listing()).encode())
            elif u.path == "/metrics":
                if os.environ.get("ANIMA_METRICS") != "1":   # operator diagnostics — opt-in, OFF by default
                    self._send(404, "text/plain", b"not found")
                else:
                    from . import metrics
                    self._send(200, "application/json",
                               json.dumps({**metrics.summary(self.name), "verdict": metrics.verdict(self.name)}).encode())
            elif u.path == "/intake/queue":
                # GET /intake/queue?name=...  -> {ok, records:[QueueRecord dicts]}
                from . import intake_queue as _iq
                _nm = parse_qs(u.query).get("name", [self.name])[0]
                recs = _iq.queue(_nm)
                self._send(200, "application/json",
                           json.dumps({"ok": True, "records": recs}).encode())
            elif u.path == "/intake/trace":
                # GET /intake/trace?name=...&trace_id=...  -> {ok, trace, render}
                from . import intake as _int
                qs = parse_qs(u.query)
                _nm = qs.get("name", [self.name])[0]
                _tid = qs.get("trace_id", [""])[0]
                tr = _int.trace(_nm, _tid) if _tid else _int.last_trace(_nm)
                if tr is None:
                    self._send(200, "application/json",
                               json.dumps({"ok": False, "error": "trace not found"}).encode())
                else:
                    self._send(200, "application/json",
                               json.dumps({"ok": True, "trace": tr,
                                           "render": _int.render_trace(tr)}).encode())
            elif u.path == "/library":
                # GET /library?name=...&section=...  -> {ok, items:[...]}
                _out = _serve_library(self.name, u.query)
                self._send(200, "application/json", json.dumps(_out).encode())
            elif u.path == "/host/awareness":
                # GET /host/awareness -> the human-level host picture (Argus). Cloud-redacted.
                try:
                    from . import cloud as _cl_host
                    _cloud_host = _cl_host.is_cloud()
                except Exception:
                    _cloud_host = False
                _out = _serve_host_awareness(self.name, _cloud_host)
                self._send(200, "application/json", json.dumps(_out).encode())
            elif u.path == "/host/timeline":
                try:
                    _hrs = int(parse_qs(u.query).get("hours", ["12"])[0])
                except Exception:
                    _hrs = 12
                self._send(200, "application/json",
                           json.dumps(_serve_host_timeline(self.name, _hrs)).encode())
            elif u.path == "/host/action_log":
                self._send(200, "application/json",
                           json.dumps(_serve_host_action_log(self.name)).encode())
            elif u.path == "/host/certification":
                self._send(200, "application/json",
                           json.dumps(_serve_host_certification(self.name)).encode())
            else:
                self._send(404, "text/plain", b"not found")
        except Exception:
            self._fail("GET")

    def do_POST(self):
        try:
            if not self._authed():
                return self._send(401, "text/plain", b"unauthorized")
            path = urlparse(self.path).path
            if path.startswith("/auth/"):
                from . import passkey
                rp_id, origin = self._origin()
                data = json.loads(self._read_body() or b"{}")
                if path == "/auth/register/begin":
                    out = passkey.register_begin(rp_id)
                elif path == "/auth/register/finish":
                    out = json.dumps(passkey.register_finish(data.get("cred") or {}, rp_id, origin))
                elif path == "/auth/login/begin":
                    out = passkey.auth_begin(rp_id) or '{"error":"not enrolled"}'
                elif path == "/auth/login/finish":
                    out = json.dumps(passkey.auth_finish(data.get("cred") or {}, rp_id, origin))
                elif path == "/auth/disable" and self._passed():
                    out = json.dumps(passkey.disable())
                else:
                    out = '{"ok":false,"error":"bad auth request"}'
                return self._send(200, "application/json", out.encode())
            if not self._passed():
                return self._send(401, "application/json", b'{"need_face_id":true}')
            if path == "/talk":
                data = json.loads(self._read_body() or b"{}")
                text = str(data.get("text", ""))[:4000]          # cap absurd input
                # text only — the phone streams the voice sentence-by-sentence via /tts,
                # so she starts speaking after the first sentence, not the whole reply
                self._send(200, "application/json",
                           json.dumps(_turn(self.name, text, voice=False)).encode())
            elif path == "/tts":
                data = json.loads(self._read_body() or b"{}")
                self._send(*_tts(data))
            elif path == "/say":
                # text-only turn (no server-side voice synth) — for the Action Button
                # shortcut, which speaks her reply with the phone's own voice
                data = json.loads(self._read_body() or b"{}")
                text = str(data.get("text", ""))[:4000]
                self._send(200, "application/json",
                           json.dumps(_turn(self.name, text, voice=False)).encode())
            elif path == "/stt":
                self._send(200, "application/json",
                           json.dumps(_transcribe(self._read_body())).encode())
            elif path == "/persona":
                from .mouth import save_persona
                data = json.loads(self._read_body() or b"{}")
                save_persona(self.name, str(data.get("persona", ""))[:8000])
                self._send(200, "application/json", b'{"ok":true}')
            elif path == "/values":
                from .mouth import save_values, VALUES
                data = json.loads(self._read_body() or b"{}")
                vals = [{"key": v.get("key"), "on": bool(v.get("on")),
                         "level": v.get("level") if v.get("level") in ("less", "balanced", "more") else "balanced"}
                        for v in data.get("values", []) if v.get("key") in VALUES][:20]
                save_values(self.name, vals)
                self._send(200, "application/json", b'{"ok":true}')
            elif path == "/dials":
                from . import dials
                data = json.loads(self._read_body() or b"{}")
                saved = dials.save(self.name, data.get("dials") or {})
                _reset_mouth()                       # so the new manner takes effect at once
                self._send(200, "application/json",
                           json.dumps({"ok": True, "dials": saved}).encode())
            elif path == "/identity/import":
                from . import identity
                data = json.loads(self._read_body() or b"{}")
                out = identity.import_bundle(data.get("bundle") or data, self.name)
                _reset_mouth()                       # adopt the imported character at once
                self._send(200, "application/json", json.dumps(out).encode())
            elif path == "/capabilities":
                from . import caps
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", json.dumps(caps.save(self.name, data)).encode())
            elif path == "/brain":
                from . import cloud
                data = json.loads(self._read_body() or b"{}")
                provider = str(data.get("provider", "local"))
                key = str(data.get("key", "")).strip()
                ok, detail, opts = True, "", None
                if provider != "local" and key:         # verify the new key AND fetch its live model list
                    ok, detail, opts = cloud.verify_key(provider, key, str(data.get("model", "")),
                                                        str(data.get("base", "")))
                if not ok:                               # bad key: report it, do NOT persist
                    self._send(200, "application/json",
                               json.dumps({"ok": False, "error": detail}).encode())
                else:
                    out = cloud.save_cfg(provider, str(data.get("model", "")), key,
                                         str(data.get("base", "")), data.get("budget"),
                                         model_opts_list=opts)
                    _reset_mouth()                       # rebuild the mouth with the new brain
                    out["ok"] = True
                    if provider != "local" and key:
                        out["verified"] = True
                    self._send(200, "application/json", json.dumps(out).encode())
            elif path in ("/models/select", "/models/pull", "/models/remove", "/models/cleanup"):
                from . import models
                data = json.loads(self._read_body() or b"{}")
                ref = str(data.get("ref", ""))
                if path == "/models/select":
                    out = models.select(ref)
                    if out.get("ok"):
                        _reset_mouth()                  # switch to the chosen local model
                elif path == "/models/pull":
                    out = models.start_pull(ref)
                elif path == "/models/remove":
                    out = models.remove(ref)
                else:
                    out = models.cleanup_unused()
                self._send(200, "application/json", json.dumps(out).encode())
            elif path in ("/imessage/draft", "/mail/draft"):
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _draft(path, data).encode())
            elif path in ("/imessage/send", "/mail/send"):
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _confirm_send(self.name, path, data).encode())
            elif path in ("/imessage/read", "/mail/read"):
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _read_msgs(self.name, path, data).encode())
            elif path == "/web/fetch":
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _web_fetch(self.name, data).encode())
            elif path == "/loc":
                # iPhone posts {lat, lon, ts}; stored for the proactive briefing's weather.
                # AUTHED (above) — must be, or the tailnet could spoof your location.
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _store_location(self.name, data).encode())
            elif path == "/device":
                # iPhone posts its push token(s); stored so reminders can reach APNs/PushKit.
                # AUTHED (above) — must be, or anything could hijack the push target.
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _store_device(self.name, data).encode())
            elif path == "/acknowledge":
                # the 👍 "Got it" action (or the app) confirms a reminder so it won't
                # escalate to a call. AUTHED (above). {reminder_id} -> reminders.acknowledge
                from . import reminders
                data = json.loads(self._read_body() or b"{}")
                ok = reminders.acknowledge(str(data.get("reminder_id", "")))
                self._send(200, "application/json", json.dumps({"ok": ok}).encode())
            elif path == "/intake/plan":
                # POST /intake/plan — stage raw + run Wave-1 (no durable write)
                data = json.loads(self._read_body() or b"{}")
                out = _intake_plan(self.name, data)
                self._send(200, "application/json", json.dumps(out).encode())
            elif path == "/intake/approve":
                # POST /intake/approve — re-parse from staging + commit on approval
                data = json.loads(self._read_body() or b"{}")
                out = _intake_approve(self.name, data)
                self._send(200, "application/json", json.dumps(out).encode())
            elif path == "/search":
                # POST /search — cross-store labeled search
                data = json.loads(self._read_body() or b"{}")
                out = _serve_search(self.name, data)
                self._send(200, "application/json", json.dumps(out).encode())
            elif path == "/library/edit":
                # POST /library/edit — memory-type editor (K)
                data = json.loads(self._read_body() or b"{}")
                out = _serve_library_edit(self.name, data)
                self._send(200, "application/json", json.dumps(out).encode())
            else:
                self._send(404, "text/plain", b"not found")
        except Exception:
            self._fail("POST")

    def log_message(self, *a):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="anima.server")
    ap.add_argument("--name", default="Vera")
    ap.add_argument("--neurons", type=int, default=64)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="default localhost-only (safe). Use --expose to allow the LAN.")
    ap.add_argument("--expose", action="store_true",
                    help="bind 0.0.0.0 so other devices on your WiFi can reach it")
    ap.add_argument("--voice", action="store_true", help="synthesize speech with Kokoro")
    args = ap.parse_args(argv)

    host = "0.0.0.0" if args.expose else args.host
    _ensure(args.name, args.neurons)
    _load_history(args.name)              # bring back her recent conversation across restarts
    try:                                  # verify the key fits before serving
        load_json(_path(args.name))
    except RuntimeError as e:
        raise SystemExit(f"\ncannot open {args.name}: {e}\n"
                         "  set the same ANIMA_KEY you used before (or unset it if plaintext).\n")
    label(f"{args.name} server :{args.port}")
    global _DEPLOY                       # LAW 005: pin the running commit ONCE, before serving
    _DEPLOY = _capture_deploy()          # guarded — never breaks startup; serves /version
    print(f"deploy: running {_DEPLOY['sha']} ({_DEPLOY['branch']}) — "
          f"`python3 scripts/deploy_check.py` confirms git == running (LAW 005)")
    Handler.token = os.environ.get("ANIMA_TOKEN", "")
    from . import crypto
    from .mouth import DEFAULT_MODEL
    print(f"brain: {os.environ.get('ANIMA_MODEL', DEFAULT_MODEL)} (Ollama) — "
          f"make sure `ollama list` shows it")
    print(f"security: auth {'ON (token required)' if Handler.token else 'OFF (no token)'} · "
          f"files {'ENCRYPTED' if crypto.enabled() else 'plaintext'}")
    from . import passkey
    if os.environ.get("ANIMA_NO_PASSKEY") == "1":
        print("face id: BYPASSED (ANIMA_NO_PASSKEY=1)")
    elif passkey.required():
        print("face id: ON (unlock required) — bypass with ANIMA_NO_PASSKEY=1 if locked out")
    elif passkey.enrolled():
        print("face id: enrolled but not required")
    if args.voice:
        from .mouth import KokoroVoice
        if KokoroVoice().available():
            print("voice: Kokoro (natural)")
        else:
            print("voice: Kokoro NOT available — phone will use the robotic browser voice.\n"
                  "  fix: pip install kokoro soundfile  &&  brew install espeak-ng")
    from .mouth import WhisperEars
    if WhisperEars().available():
        print(f"ears: Whisper {WhisperEars().model_name} (mic dictation ready)")
    else:
        print("ears: faster-whisper not installed — mic off (pip install faster-whisper)")
    Handler.name, Handler.voice = args.name, args.voice
    global _VOICE
    _VOICE = args.voice                  # the single mouth loads Kokoro iff started with --voice
    # warm the model in the background so the FIRST turn is fast (and keep_alive holds
    # it resident after). Doesn't block listening; silent if Ollama isn't up yet.
    def _warm():
        try:
            brain = getattr(_mouth(), "brain", None)
            if brain is not None and hasattr(brain, "warm") and brain.available():
                brain.warm()
            if args.voice:                       # warm Kokoro so the first sentence is instant
                v = getattr(_mouth(), "voice", None)
                if v is not None:
                    import tempfile as _tf, os as _os2
                    with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as _f:
                        _tw = _f.name
                    try:
                        v.speak("ready", {"rate": 1.0}, _tw)
                    finally:
                        try: _os2.unlink(_tw)
                        except OSError: pass
            try:
                _ears().warm()                   # load Whisper now, not on the first utterance
            except Exception:
                pass
            print("brain: warmed (model + voice + ears resident — first turn won't pay a cold load)")
        except Exception:
            pass
    threading.Thread(target=_warm, daemon=True).start()
    try:
        srv = ThreadingHTTPServer((host, args.port), Handler)
    except OSError:
        raise SystemExit(
            f"\nport {args.port} is busy — another {args.name} is already running.\n"
            f"  free it:  lsof -ti:{args.port} | xargs kill -9   (then start again)\n")
    print(f"{args.name} is listening at http://{host}:{args.port}")
    if host == "0.0.0.0":
        print("EXPOSED on your LAN (no password). Prefer a private tunnel (Tailscale) for the phone.")
    else:
        print("localhost-only. For your phone, front it with a tunnel (Tailscale/cloudflared).")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")


if __name__ == "__main__":
    main()
