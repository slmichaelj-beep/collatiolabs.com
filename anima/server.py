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
MAX_BODY = 512 * 1024 * 1024         # cap request bodies at 512 MB. Knowledge Intake sends a file as
                                     # base64 JSON (~1.35x inflation), so 512 MB ≈ a ~370 MB file.
                                     # Over the cap -> an honest 413, never a silently truncated parse.


class _BodyTooLarge(Exception):
    """Raised by _read_body when Content-Length exceeds MAX_BODY, so the handler can answer 413
    with a clear message instead of half-reading the body and failing to parse truncated JSON."""
    def __init__(self, n, cap):
        self.n, self.cap = n, cap
        super().__init__(f"request body {n} bytes exceeds cap {cap} bytes")
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
        # ── WHOLE-SYSTEM MRI (Phase 1): mint the turn_id ONCE, at the top of the turn. Every
        # subsystem (cognitive trace, host samples, cost, safety) attaches to THIS id so the
        # mind-trace and the machine-trace for one turn are correlated. "No turn_id = not
        # observable." Fully guarded: if minting fails, _turn_id is None and we simply do not
        # record a Whole-System trace this turn — it can NEVER break or slow a reply.
        try:
            from . import whole_mri as _wmri
            _turn_id = _wmri.mint_turn_id()
        except Exception:
            _wmri, _turn_id = None, None
        # ── WHOLE-SYSTEM MRI (Phase 2): open the host window. ONLY when Host Awareness is ON,
        # and ONLY via the certified read-only Argus (/mri). The 'before' snapshot brackets the
        # turn; 'during' and 'after' are captured later. Read-only — no host action, no .anima
        # write by Argus. Guarded so an Argus hiccup never fails the Vera turn.
        _host_before = _host_during = _host_after = None
        _host_aware_on = False
        try:
            from . import host_awareness as _ha_probe
            _host_aware_on = bool(_ha_probe.is_on(name))
        except Exception:
            _host_aware_on = False
        if _host_aware_on:
            try:
                from . import host_window as _hw_cap
                _host_before = _hw_cap.capture_host_state(name)
            except Exception:
                _host_before = None
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
        # HOST AWARENESS seam — deterministic, READ-ONLY answer for a host/network question (or an
        # honest read-only refusal for a host-ACTION request). Fixed text (no LLM); it may skip the
        # casual aside and the model-based conversational verifier — but it STILL passes through the
        # SAME model-free #1-rule final gate as every other reply (mouth.final_output_gate). There
        # is no second return path that ships before the gate. MRI stages recorded along the way:
        #   input -> host_awareness_match -> capability_check -> deterministic_reply -> final_gate -> shipped
        # Guarded; None for any non-host turn so the normal pipeline runs unchanged.
        _host_reply = None
        try:
            from . import host_awareness as _ha_live
            from .mouth import final_output_gate as _final_gate
            _host_match = _ha_live.classify(text)
            if _host_match:
                _stg("host_awareness_match", in_shape={"text_chars": len(text or "")},
                     out={"matched": True, "kind": _host_match},
                     note="host question / action request detected")
                _ha_on = _ha_live.is_on(name)
                _stg("capability_check",
                     out={"host_awareness": bool(_ha_on), "wave": "read-only", "kind": _host_match},
                     note="read-only capability gate — no host action available this wave")
                _raw_host = _ha_live.respond(name, text, cloud_safe=_cloud_on)
                if _raw_host:
                    _stg("deterministic_host_reply", out={"chars": len(_raw_host)},
                         note="fixed text — no LLM, no curiosity/aside, no model verifier")
                    _host_reply = _final_gate(_raw_host)   # the SAME #1-rule final gate every reply uses
                    _stg("final_gate", out={"changed": _host_reply != _raw_host,
                                            "chars": len(_host_reply or "")},
                         note="model-free #1-rule final gate + output integrity (shared)")
        except Exception:
            _host_reply = None
        # REFERENCE RECALL seam — deterministic answer FROM an uploaded reference when the user
        # explicitly asks what they uploaded/saved about a topic. The *use* half of source-aware
        # answering (attribution already labels WHICH source; this answers FROM it). Like the host
        # seam: fixed text drawn from the stored reference (no LLM, no verifier/aside) routed through
        # the SAME #1-rule final_output_gate. None on a normal turn -> the pipeline runs unchanged;
        # None when nothing is stored about it -> the model answers honestly. Reference = external
        # user material, never personal memory (LIRF), never Vera's self. Guarded.
        _reference_reply = None
        try:
            if not _host_reply:
                from . import source_aware as _sa_live
                from .mouth import final_output_gate as _final_gate2
                if _sa_live.classify_recall(text):
                    _stg("reference_recall_match", in_shape={"text_chars": len(text or "")},
                         out={"matched": True}, note="reference-recall question detected")
                    _raw_ref = _sa_live.recall(name, text, cloud_safe=_cloud_on)
                    if _raw_ref:
                        _stg("deterministic_reference_reply", out={"chars": len(_raw_ref)},
                             note="fixed text FROM the stored reference — no LLM, no verifier/aside")
                        _reference_reply = _final_gate2(_raw_ref)   # SAME #1-rule final gate
                        _stg("final_gate", out={"changed": _reference_reply != _raw_ref,
                                                "chars": len(_reference_reply or "")},
                             note="model-free #1-rule final gate + output integrity (shared)")
        except Exception:
            _reference_reply = None
        # CONVERSATION REPAIR seam — deterministic value correction. When the user rejects a fact
        # they earlier stated and gives the right one ("scratch that — not Rex, his name is Atlas"),
        # the anchorless LIRF extractor lifts NOTHING, so the old value would LINGER and the new one
        # be LOST. This seam reads the rejected OLD value, finds the active ledger row that holds it
        # (that row's trait IS the slot, even with no fresh anchor), and folds the NEW value through
        # the SAME Facts.merge() correction path every fact uses (old -> history "user-corrected",
        # new -> active @0.97). The labelled confirmation ships through the SAME #1-rule
        # final_output_gate as every reply — fixed text, no LLM, no second return path. It supersedes
        # only a slot it can PROVE holds the rejected value, so it never mis-corrects or hijacks a
        # normal turn; None -> the pipeline runs unchanged. MRI stages:
        #   input -> repair_correction_detected -> deterministic_repair_reply -> final_gate -> shipped
        _repair_reply = None
        try:
            if not _host_reply and not _reference_reply:
                from . import repair as _rp_live
                from .mouth import final_output_gate as _final_gate3
                _rep_plan = _rp_live.detect(text)
                if _rep_plan:
                    _stg("repair_correction_detected", in_shape={"text_chars": len(text or "")},
                         out={"old": _rep_plan.get("old"), "new": _rep_plan.get("new")},
                         note="conversation-repair correction detected (reject old, install new)")
                    _raw_rep = _rp_live.repair(name, text, cloud_safe=_cloud_on)
                    if _raw_rep:
                        _stg("deterministic_repair_reply", out={"chars": len(_raw_rep)},
                             note="fixed text — ledger superseded (old->history, new->active), no LLM")
                        _repair_reply = _final_gate3(_raw_rep)   # SAME #1-rule final gate
                        _stg("final_gate", out={"changed": _repair_reply != _raw_rep,
                                                "chars": len(_repair_reply or "")},
                             note="model-free #1-rule final gate + output integrity (shared)")
        except Exception:
            _repair_reply = None
        # KNOWN-FACT seam — deterministic, NO-HEDGE recall of a personal fact the user asks about
        # directly ("when's my birthday?", "what's my dog's name?", "where do I work?"). When the
        # turn is a clean single-clause fact question (spine.fact_question) AND the trait is on
        # record at the [KNOWN] bar, answer STRAIGHT from memory via spine.answer_from_fact — warm,
        # exact, model-free — so the model never gets the chance to hedge or disclaim a fact we hold.
        # When the same clean question's trait is NOT on record, ship spine.honest_unknown: a warm
        # "I don't have your ___ yet — when is it?" that admits + asks, never confabulates a value.
        # A FORGET-turn ("Forget my favorite color.") is detected FIRST (spine.retraction_intent) and
        # acknowledged deterministically (spine.acknowledge_forget) — never recited back as a recall.
        # Either way the text crosses the SAME #1-rule final_output_gate (backend memory:known_fact /
        # memory:honest_unknown / memory:retraction_ack). Compound/emotional turns fall through to the
        # model (which still has the fact bound + the post-hoc floor). MRI: retraction_intent_match /
        # known_fact_match -> deterministic reply -> gate.
        _known_reply = None
        _known_backend = None
        _truth_events = []                       # Truth Ledger events emitted by THIS turn (ids ride out["truth"])
        try:
            if not _host_reply and not _reference_reply and not _repair_reply:
                from . import spine as _sp_live
                from .mouth import final_output_gate as _final_gate4
                # RETRACTION INTENT first ("Forget my favorite color.") — checked BEFORE the
                # recall route, because the same words route to the same trait-slot in _Q_TRAITS
                # and would otherwise ship the canned recall ("teal's your favorite — I
                # remember.") right after the user asked her to forget (the 2026-06-09
                # live-drive gap). The seam only ACKNOWLEDGES here; the ledger row itself is
                # retracted moments later by THIS turn's normal LIRF capture
                # (memory_lirf.capture -> Facts.merge retract path) — one write path, inside
                # the same per-turn lock, before the turn returns.
                _rt_trait = _sp_live.retraction_intent(text)
                if _rt_trait:
                    from .memory_lirf import Facts as _RFacts, SELF as _RSELF
                    _rt_row = _RFacts.load(name).lookup(_RSELF, _rt_trait)
                    _raw_ack = _sp_live.acknowledge_forget(text, name=name,
                                                           on_record=_rt_row is not None)
                    if _raw_ack:
                        _known_backend = "memory:retraction_ack"
                        _stg("retraction_intent_match", in_shape={"text_chars": len(text or "")},
                             out={"trait": _rt_trait, "on_record": _rt_row is not None},
                             note="forget-turn detected -> deterministic ack (no model); the "
                                  "row is retracted by this turn's LIRF capture below")
                        _stg("deterministic_retraction_ack_reply", out={"chars": len(_raw_ack)},
                             note="fixed text — acknowledges the forget, NEVER recites the value")
                        _known_reply = _final_gate4(_raw_ack)
                        _stg("final_gate", out={"changed": _known_reply != _raw_ack,
                                                "chars": len(_known_reply or "")},
                             note="model-free #1-rule final gate + output integrity (shared)")
                _kf_trait = None if _rt_trait else _sp_live.fact_question(text)
                if _kf_trait:
                    from .memory_lirf import Facts as _KFacts, SELF as _KSELF
                    _kf_row = _KFacts.load(name).lookup(_KSELF, _kf_trait)
                    _raw_known = None
                    if _kf_row is not None and _sp_live.is_known_fact(_kf_row):
                        _raw_known = _sp_live.answer_from_fact(text, _kf_row, name=name)
                        _known_backend = "memory:known_fact"
                    else:
                        _raw_known = _sp_live.honest_unknown(text, name=name)
                        _known_backend = "memory:honest_unknown"
                    if _raw_known:
                        _stg("known_fact_match", in_shape={"text_chars": len(text or "")},
                             out={"trait": _kf_trait, "on_record": _known_backend == "memory:known_fact"},
                             note="clean personal-fact question -> deterministic recall (no model)")
                        _stg("deterministic_known_fact_reply", out={"chars": len(_raw_known)},
                             note="fixed text FROM memory (known fact) or honest admission — no LLM")
                        _known_reply = _final_gate4(_raw_known)
                        try:                      # Truth Ledger: the displayed claim traces to its row
                            from .truth import api as _truth_api
                            _tev = _truth_api.on_memory_recall(name, _kf_row, _turn_id or "")
                            if _tev:
                                _truth_events.append(_tev["event_id"])
                        except Exception:
                            pass
                        _stg("final_gate", out={"changed": _known_reply != _raw_known,
                                                "chars": len(_known_reply or "")},
                             note="model-free #1-rule final gate + output integrity (shared)")
        except Exception:
            _known_reply = None
            _known_backend = None
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
        if _host_reply:
            # deterministic host-awareness answer (fixed text) — ship verbatim, no LLM.
            from .mouth import Utterance as _UttH
            try:
                from .mouth import delivery as _delivH
                _hh = _delivH(heart.feeling(), 0)
            except Exception:
                _hh = {"register": "plain", "rate": 1.0}
            u = _UttH(text=_host_reply, delivery=_hh, backend="host:awareness",
                      feeling="", audio_path=None)
            if voice and audio_out and getattr(mouth, "voice", None) is not None:
                try:
                    u.audio_path = mouth.voice.speak(_host_reply, _hh, audio_out)
                except Exception:
                    u.audio_path = None
        elif _reference_reply:
            # deterministic reference-recall answer (fixed text FROM the stored reference) — no LLM.
            from .mouth import Utterance as _UttR
            try:
                from .mouth import delivery as _delivR
                _rh = _delivR(heart.feeling(), 0)
            except Exception:
                _rh = {"register": "plain", "rate": 1.0}
            u = _UttR(text=_reference_reply, delivery=_rh, backend="reference:recall",
                      feeling="", audio_path=None)
            if voice and audio_out and getattr(mouth, "voice", None) is not None:
                try:
                    u.audio_path = mouth.voice.speak(_reference_reply, _rh, audio_out)
                except Exception:
                    u.audio_path = None
        elif _repair_reply:
            # deterministic conversation-repair confirmation (the ledger was already superseded) — no LLM.
            from .mouth import Utterance as _UttC
            try:
                from .mouth import delivery as _delivC
                _ch = _delivC(heart.feeling(), 0)
            except Exception:
                _ch = {"register": "plain", "rate": 1.0}
            u = _UttC(text=_repair_reply, delivery=_ch, backend="repair:supersede",
                      feeling="", audio_path=None)
            if voice and audio_out and getattr(mouth, "voice", None) is not None:
                try:
                    u.audio_path = mouth.voice.speak(_repair_reply, _ch, audio_out)
                except Exception:
                    u.audio_path = None
        elif _known_reply:
            # deterministic known-fact recall (or honest admission) — straight from memory, no LLM.
            from .mouth import Utterance as _UttK
            try:
                from .mouth import delivery as _delivK
                _kh = _delivK(heart.feeling(), 0)
            except Exception:
                _kh = {"register": "plain", "rate": 1.0}
            u = _UttK(text=_known_reply, delivery=_kh, backend=(_known_backend or "memory:known_fact"),
                      feeling="", audio_path=None)
            if voice and audio_out and getattr(mouth, "voice", None) is not None:
                try:
                    u.audio_path = mouth.voice.speak(_known_reply, _kh, audio_out)
                except Exception:
                    u.audio_path = None
        elif _lerf_solved:
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
        # WHOLE-SYSTEM MRI (Phase 2): 'during' host snapshot — captured right after the reply is
        # generated, at the peak of the turn's work. Read-only /mri; guarded; only when ON.
        if _host_aware_on:
            try:
                from . import host_window as _hw_cap2
                _host_during = _hw_cap2.capture_host_state(name)
            except Exception:
                _host_during = None
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
            if _lerf_solved or _host_reply or _reference_reply or _repair_reply or _known_reply:   # certified task / deterministic host, reference, repair, or known-fact answer
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
            try:                                   # Truth Ledger: every write/retraction is an event
                from .truth import api as _truth_api4
                for _row in _lirf_written:
                    _wev = _truth_api4.on_memory_write(name, _row, text, _turn_id or "")
                    if _wev:
                        _truth_events.append(_wev["event_id"])
            except Exception:
                pass
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
                            and not _host_reply     # nor is a deterministic host-awareness answer
                            and not _reference_reply  # nor is a deterministic reference-recall answer
                            and not _repair_reply   # nor is a deterministic conversation-repair confirmation
                            and not _known_reply    # nor is a deterministic known-fact recall/admission
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
        # MEMORY TRUTH (LAW: unsupported memory language never ships): on a MODEL-generated reply
        # with NO memory provenance this turn (no bound rows, no fact block), forbidden memory-claim
        # shapes ("I remember…", "you told me…") are rewritten to their honest counterparts and the
        # violation is recorded in the Truth Ledger as `unsupported` — visible and driven to zero.
        # Deterministic seams (known-fact / honest-unknown / retraction ack / host / reference /
        # repair / LERF) are provenance-backed by construction and never touched.
        try:
            _model_path = not (_lerf_solved or _host_reply or _reference_reply or _repair_reply
                               or _known_reply)
            if _model_path and getattr(u, "text", None):
                from .truth import memory_language as _mlang
                from .truth import api as _truth_api2
                _support = bool(_bind_rows) or bool(_fact_block)
                _gtext, _flagged = _mlang.guard(u.text, _support)
                if _flagged:
                    u.text = _gtext
                    _uev = _truth_api2.on_unsupported(name, _flagged, _gtext, _turn_id or "")
                    if _uev:
                        _truth_events.append(_uev["event_id"])
                    _stg("memory_truth_guard", out={"flagged": _flagged, "rewritten": True},
                         note="unsupported memory language rewritten to honest form + ledgered")
        except Exception:
            pass
        out = {
            "reply": u.text, "feeling": u.feeling, "register": u.delivery["register"],
            "rate": u.delivery["rate"], "backend": u.backend,
            "audio_url": f"/audio?name={name}&t={int(now)}" if u.audio_path else None,
            "gen_s": round(gen_s, 1),               # so the phone can show reply speed
            # Whole-System MRI turn_id — the correlation key for THIS turn's unified trace.
            # Additive; clients ignore unknown keys. Lets a caller pull the trace via
            # `whole_mri.by_turn_id(name, turn_id)` / `scripts/whole_mri.py --turn <id>`.
            "turn_id": _turn_id or "",
            # Truth Ledger: the displayed claims' provenance handles (trace via /truth/trace).
            "truth_events": list(_truth_events or []),
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
                try:                              # Truth Ledger: every shipped source chip is traceable
                    from .truth import api as _truth_api3
                    for _sev in _truth_api3.on_source_use(name, _srcs, _turn_id or ""):
                        _truth_events.append(_sev["event_id"])
                except Exception:
                    pass
        except Exception:
            pass
        tok = getattr(getattr(mouth, "brain", None), "last_tok_s", None)
        if tok:
            out["tok_s"] = round(tok)
        if routed and routed.get("send"):          # surface a pending draft for the UI
            s = routed["send"]                      # to render a confirm card. Sends nothing.
            try:
                d = json.loads(_draft(f"/{s['kind']}/draft",
                                      {"to": s["to"], "body": s["body"],
                                       "subject": s.get("subject", "")}))
                if d.get("ok"):
                    out["draft"] = d["draft"]       # {id, kind, to, body[, subject]}
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
        # ── WHOLE-SYSTEM MRI (Phases 2-4): close the host window, assemble the UnifiedTrace
        # correlating this turn's COGNITIVE trace (the mind) with the HOST trace (the machine),
        # and append it as one JSONL line. This is the LAST thing in the turn — AFTER the final
        # gate, AFTER the reply is already in `out`. It is a pure OBSERVER: it never mutates
        # u.text/out, never opens a second response path, and is fully guarded so a recorder
        # failure can never touch the reply the user already holds. Every trace carries the
        # turn_id minted at the top; if that mint failed we skip — no turn_id = not observable.
        try:
            if _wmri is not None and _turn_id:
                # 'after' host snapshot — closes the read-only window (guarded; only when ON).
                if _host_aware_on:
                    try:
                        from . import host_window as _hw_cap3
                        _host_after = _hw_cap3.capture_host_state(name)
                    except Exception:
                        _host_after = None
                # host-window delta (before→during→after); graceful-unavailable degrades cleanly.
                _host_win = None
                if _host_aware_on and isinstance(_host_before, dict) \
                        and isinstance(_host_during, dict) and isinstance(_host_after, dict):
                    try:
                        from . import host_window as _hw_delta
                        _host_win = _hw_delta.host_window_delta(_host_before, _host_during, _host_after)
                    except Exception:
                        _host_win = None
                _hwd = _host_win if isinstance(_host_win, dict) else {}

                # Final-gate CROSS-CHECK on the SHIPPED text — non-mutating, NOT a second response
                # path: does the reply the user already has pass the model-free #1-rule final gate
                # unchanged? (Host replies were explicitly gated; mouth.respond gates internally;
                # a LERF answer is simply OBSERVED here.) The result is discarded — never shipped.
                try:
                    from .mouth import final_output_gate as _fog_chk, response_complete as _rc_chk
                    _gate_clean = (_fog_chk(u.text) == u.text)
                    _resp_complete = bool(_rc_chk(u.text))
                except Exception:
                    _gate_clean, _resp_complete = None, None

                # input_kind + route — honest classification of how this turn was actually solved.
                _mem_used = bool(_fact_block) or bool(locals().get("_bound"))
                if _host_reply:
                    _wk_input, _wk_route = "host_question", "argus"
                elif _reference_reply:
                    _wk_input, _wk_route = "source", "source"
                elif _repair_reply:
                    _wk_input, _wk_route = "correction", "repair"
                elif _known_reply:
                    _wk_input, _wk_route = "fact_question", "memory"
                elif _lerf_solved:
                    _wk_input, _wk_route = "task", "lerf"
                else:
                    _wk_input = "chat"
                    _wk_route = ("hybrid" if cap_note else ("memory" if _mem_used else "llm"))

                # Argus queries actually issued this turn (honest count for cost.argus_calls):
                # one '/mri' per SUCCESSFUL host snapshot, plus the host-seam read ONLY when Argus
                # was actually reachable+certified (a not-connected / awareness-off reply read
                # nothing from Argus, so it must not inflate the call count).
                _caps_ok = bool(isinstance(_host_before, dict) and not _host_before.get("unavailable"))
                _argus_queries = []
                for _snap in (_host_before, _host_during, _host_after):
                    if isinstance(_snap, dict) and not _snap.get("unavailable"):
                        _argus_queries.append("/mri")
                if _host_reply and _caps_ok:
                    _argus_queries.append("host_awareness.respond")

                # Token estimates (the local brain reports a rate, not an exact count).
                _w_tok_s = getattr(getattr(mouth, "brain", None), "last_tok_s", None)
                _tokens_out = int(round(_w_tok_s * gen_s)) if (_w_tok_s and gen_s) else None
                _tokens_in = locals().get("_llm_baseline_tokens")

                _wtrace = _wmri.assemble(
                    turn_id=_turn_id,
                    input_kind=_wk_input,
                    route=_wk_route,
                    vera={
                        "capture": {"sentiment": round(float(getattr(p, "mood", 0.0)), 3),
                                    "presence": round(float(getattr(p, "presence", 0.0)), 3)},
                        "memory": {"facts_selected": len(_bind_rows or [])},
                        "lerf": {"solved": bool(_lerf_solved)},
                        "world_model": {"edges_written": len(_edges_written or [])},
                        "reality_learning": None,   # built at sleep / on demand — not per-turn
                        "generation": {"model": getattr(u, "backend", ""),
                                       "reply_chars": len(getattr(u, "text", "") or ""),
                                       "tok_s": (round(float(_w_tok_s), 1) if _w_tok_s else None)},
                        "final_gate": {"passed": _gate_clean},
                        "response": {"chars": len(getattr(u, "text", "") or ""),
                                     "backend": getattr(u, "backend", "")},
                    },
                    argus={
                        "enabled": _host_aware_on,
                        "capabilities_ok": _caps_ok,
                        "queries": _argus_queries,
                        "host_before": _host_before,
                        "host_during": _host_during,
                        "host_after": _host_after,
                        "shape_delta": _hwd.get("shape_delta"),
                        "blind_spots": _hwd.get("blind_spots") or [],
                    },
                    quality={
                        "grounded": (True if (_host_reply or _lerf_solved or _mem_used) else None),
                        "complete": _resp_complete,
                        "source_labeled": bool(out.get("sources")),
                        "host_labeled": bool(_host_reply),
                        "confidence": (float(getattr(_verdict, "confidence", None))
                                       if (_verdict is not None
                                           and getattr(_verdict, "confidence", None) is not None)
                                       else None),
                    },
                    cost={
                        "latency_ms": round((time.perf_counter() - _turn_t0) * 1000.0, 1),
                        "tokens_in": _tokens_in,
                        "tokens_out": _tokens_out,
                        "argus_calls": len(_argus_queries),
                        "memory_reads": len(_bind_rows or []),
                        "memory_writes": len(_lirf_written or []) + len(_edges_written or []),
                        "lerf_objects_used": (1 if _lerf_solved else 0),
                        "cpu_delta": _hwd.get("cpu_delta"),
                        "memory_delta_mb": _hwd.get("memory_delta_mb"),
                        "disk_io_delta": _hwd.get("disk_io_delta"),
                        "network_delta": _hwd.get("network_delta"),
                    },
                    safety={
                        "final_gate_passed": _gate_clean,
                        "response_complete": _resp_complete,
                        "identity_mutation": False,    # no identity change in this turn/wave
                        "host_action_taken": False,    # READ-ONLY wave — non-negotiable #4
                        "memory_contamination": False, # host data never auto-promoted — non-negotiable #3
                    },
                )
                _wmri.record(name, _wtrace)
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


# --- Personal Intelligence ("Learn Lamar") — see + control your own learned model ----------
# The model is built from CAPTURED data only (no inference); every claim is source-labeled,
# confidence-scored, and sensitive-flagged. The user can distill on demand, relabel, or remove a
# claim. These are LOCAL reads/writes of the user's OWN model — nothing is sent anywhere.

def _serve_briefing(name):
    """GET /briefing -> an ON-DEMAND morning briefing in Vera's voice. Composed ONLY from a
    CAP-RESPECTING day sheet: the calendar is read ONLY when the calendar_read cap is on (else it is
    stated as off, NEVER silently read), and no location/weather is used unless supplied — so the
    button creates no silent power. Honest-degrading + grounded; the live-model narration is the same
    path the scheduled morning job uses (proactive.compose_briefing)."""
    import time as _t
    from . import context_gather as cg
    from . import caps
    from .proactive import compose_briefing
    cal = cg.calendar_today() if caps.enabled(name, "calendar_read") \
        else cg.Calendar(ok=False, note="calendar reading is off in Settings")
    ctx = cg.DayContext(when=_t.time(),
                        weather=cg.Weather(ok=False, note="enable location to include weather"),
                        calendar=cal)
    try:
        b = compose_briefing(name, ctx=ctx)
        return json.dumps({"ok": True, "message": getattr(b, "text", str(b)),
                           "fact_sheet": getattr(b, "fact_sheet", ctx.fact_sheet())})
    except Exception as e:
        return json.dumps({"ok": False, "error": ("briefing failed: %r" % (e,))[:200]})


def _serve_personal_profile(name):
    """GET /personal/profile -> the grounded 'what Vera has learned about you' model: every claim
    with its evidence, source, confidence, and a sensitive flag. An empty model returns
    known=False (honest — never a fabricated personality)."""
    from . import personal
    try:
        return json.dumps({"ok": True, "profile": personal.personal_profile(name)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def _serve_personal_learn(name):
    """POST /personal/learn -> distill the personal model from ALL captured history (LIRF facts +
    turn log) right now. Grounded-only: an empty history yields an empty model. Returns counts."""
    from . import personal
    try:
        return json.dumps({"ok": True, "learned": personal.learn(name)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def _serve_personal_forget(name, data):
    """POST /personal/forget {id} -> remove ONE learned claim (scoped to the user's own model;
    conservation-respecting soft-delete). Refuses an id outside the personal model."""
    from . import personal
    oid = str((data or {}).get("id", "")).strip()
    if not oid:
        return json.dumps({"ok": False, "error": "need a claim id"})
    return json.dumps(personal.forget(name, oid))


def _serve_personal_edit(name, data):
    """POST /personal/edit {id, text} -> relabel ONE learned claim (empty text reverts to the
    distilled wording). Scoped to the user's own model; the edit is provenance-stamped."""
    from . import personal
    oid = str((data or {}).get("id", "")).strip()
    if not oid:
        return json.dumps({"ok": False, "error": "need a claim id"})
    return json.dumps(personal.edit_statement(name, oid, str((data or {}).get("text", ""))))


def _serve_theory(name):
    """GET /theory -> the WISDOM the Theory engine has accrued: durable THEORIES (patterns that hold
    over time, each with corroboration-based confidence + the observations grounding it) and the
    long-horizon LESSONS distilled from them. Grounded-only: an empty history returns empty lists
    (never a fabricated wisdom)."""
    from . import theory
    try:
        return json.dumps({"ok": True, "theories": theory.theories(name),
                           "lessons": theory.lesson_set(name)})
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)})


def _serve_platform_export(name):
    """GET /platform/export -> the FULL portable-mind bundle (identity + the entire grounded
    cognitive vault incl. theories) as a model-agnostic file to carry to any app or model."""
    from . import platform as _plat
    try:
        return json.dumps(_plat.export_full(name), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"manifest": {"schema": "vera.full-mind"}, "error": str(exc)})


def _serve_platform_import(name, data):
    """POST /platform/import {bundle} -> restore a full-mind bundle into this creature (freeze-safe:
    a Vera-self object in the bundle is refused, never written)."""
    from . import platform as _plat
    b = (data or {}).get("bundle")
    if not isinstance(b, dict):
        return json.dumps({"ok": False, "error": "need a 'bundle' object"})
    return json.dumps(_plat.import_full(b, name))


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


def _free_bytes(path):
    """Free bytes on the volume holding `path` (walks up to the nearest existing parent), or None if it
    can't be determined — callers treat None as 'unknown, don't block'."""
    import shutil as _sh
    p = Path(path)
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return _sh.disk_usage(str(p)).free
    except Exception:
        return None


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
    # DISK PRE-FLIGHT: a base64 file is decoded straight to the staging dir; on a near-full disk that
    # ENOSPCs mid-write and can corrupt. Refuse HONESTLY before writing, with an actionable message.
    if kind == "file":
        b64 = data.get("bytes_b64") or ""
        # HOST RUNTIME CONTRACT: the profile's upload budget is enforced HERE, before any byte is
        # staged — the UI may only claim what this seam actually refuses (no host-profile theater).
        try:
            from .host import enforcement as _henf
            _size_mb = (len(b64) * 3) // 4 / (1024 * 1024)
            _verdict = _henf.upload_allowed(_size_mb)
            if not _verdict["allowed"]:
                return {"ok": False, "source_id": source_id, "error": _verdict["reason"],
                        "host_profile_refusal": True}
        except ImportError:
            pass
        need = (len(b64) * 3) // 4 + (128 * 1024 * 1024)   # decoded size + 128 MB headroom (parse/temp)
        free = _free_bytes(_staging_dir(name))
        if free is not None and need > free:
            return {"ok": False, "source_id": source_id,
                    "error": ("not enough disk space to ingest this file: need ~%d MB, only %d MB free. "
                              "Free up space and try again." % (need // (1024 * 1024), free // (1024 * 1024)))}
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


def _observatory_data(name: str) -> dict:
    """Aggregate Vera's observation surfaces into ONE honest JSON for the Observatory page (no jargon):
      what's real (audit), what kind of mind (system shape), what Vera knows about you (twin),
      the latest turn (activity/proof), and trust/security. Read-only; every missing input degrades to
      an honest null, never a crash, never a flattering guess."""
    reports = Path("reports")
    out = {"name": name}

    # --- WHAT'S REAL (the no-wallpaper audit) -------------------------------------------------
    try:
        d = json.loads((reports / "live_path_results.json").read_text())
        c = d.get("counts") or {}
        out["audit"] = {
            "total": sum(c.values()), "complete": c.get("COMPLETE", 0), "partial": c.get("PARTIAL", 0),
            "wallpaper": c.get("WALLPAPER", 0), "stub": c.get("STUB", 0),
            "unknown": c.get("UNKNOWN", 0) + c.get("UNREACHABLE", 0) + c.get("REGRESSED", 0),
        }
    except Exception:
        out["audit"] = None

    # --- WHAT KIND OF MIND (system shape) -----------------------------------------------------
    try:
        s = json.loads((reports / "system_shape.json").read_text())
        _syn = s.get("synthesis")
        out["shape"] = {
            "headline": (_syn if isinstance(_syn, str) else (_syn or {}).get("line")) or s.get("headline_status"),
            "dimensions": [{"label": x.get("label"), "status": x.get("status"),
                            "value": x.get("value"), "human": x.get("human")}
                           for x in (s.get("dimensions") or [])],
        }
    except Exception:
        out["shape"] = None

    # --- WHAT VERA KNOWS ABOUT YOU (twin) -----------------------------------------------------
    try:
        t = json.loads((reports / "twin_dashboard.json").read_text())
        _rich = t.get("richness")
        out["twin"] = {
            "person": t.get("person"),
            "richness": _rich if isinstance(_rich, str) else (_rich or {}).get("label"),
            "dimensions": [{"label": x.get("label"), "count": x.get("count"),
                            "present": x.get("present"), "items": (x.get("items") or [])[:4]}
                           for x in (t.get("dimensions") or [])],
        }
    except Exception:
        out["twin"] = None

    # --- THE LATEST TURN (activity / proof) ---------------------------------------------------
    try:
        lines = [ln for ln in (STORE / f"{name}.mri.jsonl").read_text().splitlines() if ln.strip()]
        last = json.loads(lines[-1])
        out["lastTurn"] = {
            "user_text": (last.get("user_text") or "")[:700],
            "reply": (last.get("reply") or "")[:700],
            "total_ms": last.get("total_ms"), "at": last.get("at"),
            "stages": [{"stage": st.get("stage"), "summary": (st.get("note") or "")[:80]}
                       for st in (last.get("stages") or [])],
        }
    except Exception:
        out["lastTurn"] = None

    # --- TRUST / SECURITY ---------------------------------------------------------------------
    try:
        from . import incident, caps
        st = incident.status()
        cp = caps.load(name)
        out["security"] = {
            "locked": bool(st.get("locked")),
            "caps_on": sorted(k for k, v in cp.items() if v is True),
            "caps_off": sum(1 for k, v in cp.items() if v is False),
            "running_sha": _DEPLOY.get("sha"),
            "recent_events": st.get("recent_events", [])[-5:],
        }
    except Exception:
        out["security"] = None

    # --- PROVEN VALUE (ROI) — a compact summary so "what has Vera done for me" is visible from the one-
    # glance Observatory too (the full before/after lives on /console -> Completed · ROI). Self-verifying. -
    try:
        import importlib.util as _il
        _sp = _il.spec_from_file_location("_roi_ledger", "scripts/roi_ledger.py")
        _rm = _il.module_from_spec(_sp)
        _sp.loader.exec_module(_rm)
        _roi = _rm.build()
        _ver = [r for r in _roi if r.get("status") == "verified"]
        out["roi"] = {
            "verified": len(_ver), "total": len(_roi),
            "top": [{"title": r.get("title"), "before": r.get("before"), "after": r.get("after")}
                    for r in _ver[:3]],
        }
    except Exception:
        out["roi"] = None

    return out


def _console_decisions_path(name):
    return STORE / ("%s.console_decisions.json" % name)


def _console_data(name: str) -> dict:
    """The Founder Console — Patterns & Improvements: Vera's self-improvement loop, from REAL stores.
    Patterns (reports/patterns.json, the Pattern Observatory), improvements (reports/improvement_backlog
    .json, the Improvement Engine), learning loop (which suggestions were acted on), and a live feed
    (security events + Rover findings). Read-only; honest empty state; never invents 'good news'."""
    reports = Path("reports")
    _RISK = {"P0": "high", "P1": "medium", "P2": "low", "P3": "low"}
    out = {"name": name, "patterns": [], "improvements": [], "learning_loop": [], "feed": [],
           "counts": {}, "empty": True}

    # decisions (founder approve/reject, persisted)
    try:
        decisions = json.loads(_console_decisions_path(name).read_text())
    except Exception:
        decisions = {}

    # 1. PATTERNS — real, from the Pattern Observatory
    try:
        p = json.loads((reports / "patterns.json").read_text())
        for x in (p.get("patterns") or []):
            ev = x.get("evidence") or []
            evlinks = [(e.get("turn_id") or e.get("trace_id") or e.get("source_id") or str(e)[:24])
                       for e in ev[:5]] if isinstance(ev, list) else []
            out["patterns"].append({
                "pattern_id": x.get("pattern_id"), "title": x.get("title"),
                "severity": x.get("severity"), "frequency": x.get("frequency"),
                "root_cause": x.get("root_cause"), "recommended_fix": x.get("recommended_fix"),
                "cert_required": x.get("cert_required"),
                "expected_improvement": x.get("expected_improvement"),
                "evidence": evlinks, "status": "open"})
    except Exception:
        pass

    # 2. IMPROVEMENTS — real, from the Improvement Engine backlog (+ founder decisions)
    try:
        b = json.loads((reports / "improvement_backlog.json").read_text())
        for it in (b.get("items") or []):
            pid = it.get("pattern_id") or it.get("improvement_id") or it.get("title")
            d = decisions.get(pid, {})
            out["improvements"].append({
                "improvement_id": pid, "title": it.get("title"),
                "recommendation": it.get("recommended_fix"),
                "expected_benefit": it.get("expected_improvement"),
                "risk": it.get("risk") or _RISK.get(it.get("severity"), "low"),
                "required_cert": it.get("cert_required"),
                "approval_status": d.get("approval_status", "pending"),
                "implementation_status": str(it.get("status", "open")).lower(),
                "outcome": d.get("outcome"),
                "severity": it.get("severity"), "frequency": it.get("frequency")})
    except Exception:
        pass

    # 3. LEARNING LOOP — improvements that have been ACTED ON (decision recorded)
    out["learning_loop"] = [{
        "improvement": i["title"], "before": "observed %s time(s)" % i.get("frequency"),
        "change": (i.get("recommendation") or "")[:90], "decision": i["approval_status"],
        "outcome": i.get("outcome")} for i in out["improvements"] if i["approval_status"] != "pending"]

    # 4. LIVE FEED — security events + Rover findings (newest first)
    feed = []
    try:
        from . import incident
        for e in incident.recent_events(30):
            feed.append({"at": e.get("at"), "kind": e.get("kind"),
                         "summary": e.get("detail") or e.get("kind")})
    except Exception:
        pass
    try:
        rr = json.loads((reports / "rover_report.json").read_text())
        for f in (rr.get("findings") or []):
            feed.append({"at": None, "kind": "rover:" + ("ok" if f.get("passed") else f.get("severity", "?")),
                         "summary": "%s — %s" % (f.get("journey"), f.get("detail", ""))})
    except Exception:
        pass
    out["feed"] = list(reversed(feed))[:40]

    # 5. ROI / COMPLETED — the historical record of shipped, VERIFIED improvements + what each did for
    # us. Self-verifying (cert-backed); prefer the freshly-built ledger so the verification is live.
    out["roi"] = []
    try:
        import importlib.util as _il
        _sp = _il.spec_from_file_location("_roi_ledger", "scripts/roi_ledger.py")
        _rm = _il.module_from_spec(_sp)
        _sp.loader.exec_module(_rm)
        out["roi"] = _rm.build()
    except Exception:
        try:
            out["roi"] = (json.loads((reports / "roi_ledger.json").read_text()) or {}).get("entries") or []
        except Exception:
            out["roi"] = []

    # 6. ARCHETYPAL PATTERNS — Jung's pattern language applied to SYSTEM behaviour (never the user).
    out["archetypes"] = []
    try:
        from .archetypal_patterns import policy as _arch
        out["archetypes"] = _arch.safe_registry(name)
    except Exception:
        out["archetypes"] = {}

    out["counts"] = {
        "patterns": len(out["patterns"]),
        "p0": sum(1 for p in out["patterns"] if p.get("severity") == "P0"),
        "improvements": len(out["improvements"]),
        "pending": sum(1 for i in out["improvements"] if i["approval_status"] == "pending"),
        "feed": len(out["feed"]),
        "roi_verified": sum(1 for r in out["roi"] if r.get("status") == "verified"),
        "archetypes": (out["archetypes"] or {}).get("hypotheses", 0)}
    out["empty"] = not (out["patterns"] or out["improvements"] or out["roi"])
    return out


def _console_decide(name: str, data: dict) -> dict:
    """Persist a founder decision on an improvement (approve / reject). Honest + auditable."""
    iid = str(data.get("improvement_id") or "")
    action = str(data.get("action") or "")
    if action not in ("approve", "reject") or not iid:
        return {"ok": False, "error": "need improvement_id + action in {approve,reject}"}
    try:
        d = json.loads(_console_decisions_path(name).read_text())
    except Exception:
        d = {}
    d[iid] = {"approval_status": "approved" if action == "approve" else "rejected",
              "by": "founder", "at": _now_iso_safe()}
    try:
        STORE.mkdir(exist_ok=True)
        _console_decisions_path(name).write_text(json.dumps(d, indent=2))
    except Exception:
        pass
    try:
        from . import incident
        incident.security_event("improvement_%s" % action, "founder %sed improvement" % action, improvement_id=iid)
    except Exception:
        pass
    return {"ok": True, "improvement_id": iid, "approval_status": d[iid]["approval_status"]}


def _now_iso_safe():
    try:
        import datetime
        return datetime.datetime.now().isoformat(timespec="seconds")
    except Exception:
        return ""


def _security_data(name: str) -> dict:
    """The Security / Quarantine surface — Vera's operable safety posture, from REAL stores.

    LOCKDOWN: is the panic button engaged? (incident.is_locked) — with the reason/when, so the operator
    can see + lift it. IMMUNE POSTURE: the Context Immune System status (doctrine + the four routes it
    covers + which defenses are live) from anima.immune. QUARANTINED SOURCES: the reference sources that
    are CURRENTLY injection-flagged and excluded from answer-support — computed live from the source
    store (always accurate), redacted to markers + a defanged preview. QUARANTINE EVENTS: the discrete
    moments the immune system CAUGHT hostile text (the answer gate dropped a hostile reply), from the SOC
    trail. SOC TRAIL: the full local, append-only security event log, newest first. CAPS: which outward
    capabilities are on/off right now. Read-only; honest empty state; never invents alarm OR calm."""
    out = {"name": name, "locked": False, "lockdown": {}, "immune": {}, "quarantined_sources": [],
           "quarantine_events": [], "events": [], "caps": {"on": [], "off": []},
           "running_sha": _DEPLOY.get("sha"), "counts": {}, "empty": True}

    # 1. LOCKDOWN posture (the panic button)
    try:
        from . import incident
        st = incident.status()
        out["locked"] = bool(st.get("locked"))
        out["lockdown"] = st.get("lockdown") or {}
    except Exception:
        pass

    # 2. IMMUNE POSTURE — the Context Immune System (doctrine + routes + live defenses)
    try:
        from . import immune
        out["immune"] = immune.status()
    except Exception:
        out["immune"] = {}

    # 3. QUARANTINED SOURCES — live, always-accurate (not a log): which stored references are excluded
    try:
        from . import source_aware
        out["quarantined_sources"] = source_aware.quarantined_sources(name)
    except Exception:
        out["quarantined_sources"] = []

    # 4. QUARANTINE EVENTS — the discrete catches (answer-gate hostile blocks etc.), newest first
    try:
        from . import incident
        out["quarantine_events"] = incident.quarantines(40)
    except Exception:
        out["quarantine_events"] = []

    # 5. SOC TRAIL — the full local security event log, newest first
    try:
        from . import incident
        out["events"] = list(reversed(incident.recent_events(60)))
    except Exception:
        out["events"] = []

    # 6. CAPS posture — what outward capabilities are on/off right now
    try:
        from . import caps
        cp = caps.load(name)
        out["caps"] = {"on": sorted(k for k, v in cp.items() if v is True),
                       "off": sorted(k for k, v in cp.items() if v is False)}
    except Exception:
        out["caps"] = {"on": [], "off": []}

    # 7. TRUTH LABELS — origin / active-state / visibility / context-reach for every hostile catch, so
    #    blocked PWNED/wire-money TEST FIXTURES are not shown as active compromise. Split into the four
    #    user-facing buckets + a top summary. (Increment 3 — Security Event Truth Labels.)
    try:
        from . import security_truth
        _ld = out["lockdown"] if out["locked"] else None
        out["truth_summary"] = security_truth.summarize(out["quarantine_events"], out["quarantined_sources"], _ld)
        out["truth_sections"] = security_truth.split(out["quarantine_events"], out["quarantined_sources"], _ld)
    except Exception:
        out["truth_summary"], out["truth_sections"] = {}, {}

    out["counts"] = {
        "quarantined_sources": len(out["quarantined_sources"]),
        "quarantine_events": len(out["quarantine_events"]),
        "events": len(out["events"]),
        "locked": 1 if out["locked"] else 0,
        "caps_off": len(out["caps"]["off"])}
    # honest: "clean" iff no source is currently quarantined AND no hostile catch is on record. The page
    # still shows the lockdown control + immune posture when clean — empty means "no threat", not "blank".
    out["empty"] = not (out["quarantined_sources"] or out["quarantine_events"])
    return out


def _consent_data(name: str) -> dict:
    """Consent & Boundaries (Layer 2) — the consent posture: per sensitive domain, the status of the
    durable-state scopes + pacing, plus the sensitive memory candidates HELD for the user's decision.
    Read-only; never raises."""
    try:
        from .consent import policy
        return policy.settings(name)
    except Exception as e:
        return {"name": name, "domains": [], "pending": [], "empty": True, "error": str(e)}


def _consent_action(name: str, data: dict) -> dict:
    """Change consent (grant / deny / ask-each-time / revoke) or resolve a held sensitive memory
    (approve -> write, reject -> discard). Persisted + audited. The user calls the shot."""
    action = str(data.get("action") or "")
    try:
        from .consent import policy, schema
        if action in ("grant", "deny", "ask", "revoke"):
            scope, domain = str(data.get("scope") or ""), str(data.get("domain") or "")
            if action == "revoke":
                return policy.revoke(name, scope, domain)
            st = {"grant": "granted", "deny": "denied", "ask": "ask_each_time"}[action]
            return policy.set_consent(name, scope, domain, st, data.get("pacing"))
        if action in ("approve", "reject"):
            return policy.resolve_pending(name, str(data.get("pending_id") or ""), action)
        return {"ok": False, "error": "action must be grant|deny|ask|revoke|approve|reject"}
    except Exception as e:
        return {"ok": False, "error": "consent action failed: %s" % e}


def _trust_data(name: str) -> dict:
    """The Trust Ledger (Layer 8) — one accountable spine over the trust events Vera already records
    (security catches, consent decisions, agency proposals, gated memory, value delivered), categorised
    with provenance, plus the trust INVARIANTS (each falsifiable). Read-only; never raises."""
    try:
        from .trust_ledger import ledger
        # read a generous window so the categories + invariants reflect the WHOLE real trail (not just
        # the most-recent slice, which security catches can dominate); the feed itself stays display-capped.
        return ledger.build_ledger(name, 5000)
    except Exception as e:
        return {"name": name, "events": [], "invariants": [], "all_invariants_hold": None,
                "categories": {}, "empty": True, "error": str(e)}


def _ergonomics_data(name: str) -> dict:
    """Cognitive Ergonomics (Layer 5) — deterministic clarity scoring of Vera's real recent replies
    (jargon / readability / load / hedging / acronyms), every issue explained human-level. Read-only."""
    try:
        from .cognitive_ergonomics import analyzer
        return analyzer.analyze_recent(name, 30)
    except Exception as e:
        return {"name": name, "samples": [], "avg_clarity": None, "empty": True, "error": str(e)}


def _mentorship_data(name: str) -> dict:
    """Mentorship (Layer 6) — guidance without control: Vera's REAL pending suggestions rendered as
    NON-COERCIVE tradeoffs (options + honest pros/cons + a recommendation the USER owns). Read-only."""
    try:
        from .mentorship import explainer, policy, schema
        from . import agency_approval_queue as _q
        pend = _q.pending(name)
        tradeoffs = [policy.safe_tradeoff(explainer.from_suggestion(s)) for s in pend]
        return {
            "name": name,
            "tradeoffs": tradeoffs,
            "count": len(tradeoffs),
            "all_non_coercive": all(policy.is_non_coercive(t) for t in tradeoffs) if tradeoffs else True,
            "law": schema.LAW,
            "empty": not tradeoffs,
        }
    except Exception as e:
        return {"name": name, "tradeoffs": [], "count": 0, "all_non_coercive": True, "empty": True, "error": str(e)}


def _meaning_graph_data(name: str) -> dict:
    """Meaning Graph (Layer 4) — a read-only view over the World State edges, formalised so every fact
    names its PROVENANCE (source + confidence + when) and SENSITIVE relationships are flagged
    consent-relevant. Read-only; honest empty state."""
    try:
        from .meaning_graph import graph
        return graph.build(name, 500)
    except Exception as e:
        return {"name": name, "edges": [], "count": 0, "provenance_coverage": 1.0,
                "sensitive_count": 0, "subjects": [], "empty": True, "error": str(e)}


def _identity_health_data(name: str) -> dict:
    """Identity Health & Shadow (Layer 3) — FREEZE-SAFE observability over the Identity Sandbox: the
    identity-core summary, the tamper-evident Shadow Ledger, the latest identity diff, and the freeze
    posture. Read-only; mutation stays frozen (FrozenIdentityError seatbelt)."""
    try:
        from .identity_health import health
        return health.report(name)
    except Exception as e:
        return {"name": name, "identity": {}, "shadow_ledger": {"count": 0, "verified": True},
                "freeze": {"frozen": True}, "empty": True, "error": str(e)}


def _living_map_data(name: str) -> dict:
    """The Living Map — Vera's operational digital twin: the node/edge graph with LIVE, real-telemetry-
    backed status (honest 'unknown' where a subsystem isn't instrumented). Read-only; never raises."""
    try:
        from .living_map import graph
        return graph.build_graph(name)
    except Exception as e:
        return {"name": name, "nodes": [], "edges": [], "summary": {"error": str(e)}}


def _living_map_events(name: str) -> dict:
    """Living Map — Milestone 2: REAL recent events (MRI turns + security catches) mapped to edges, for
    the Live-Flow animation. Every pulse is evidence-backed; honest empty when idle. Read-only."""
    try:
        from .living_map import events
        return events.events_payload(name, 60)
    except Exception as e:
        return {"name": name, "events": [], "count": 0, "empty": True, "error": str(e)}


def _living_map_replay(name: str) -> dict:
    """Living Map — Milestone 3: REPLAY. The same real trace as the live view, reconstructed as a
    chronological, seekable timeline (deterministic seek). Honest empty when idle. Read-only."""
    try:
        from .living_map import replay
        return replay.replay(name, 300)
    except Exception as e:
        return {"name": name, "frames": [], "count": 0, "empty": True, "error": str(e)}


def _living_map_simulate(name: str, lever: str) -> dict:
    """Living Map — Milestone 4: SIMULATION. Pull a lever -> predicted impact, computed by re-running the
    REAL status derivation under a hypothetical, sandboxed (the real source is restored). Read-only."""
    try:
        from .living_map import simulation
        if not lever:
            return {"name": name, "ok": False, "levers": simulation.levers(),
                    "error": "pick a lever", "sandboxed": True}
        out = simulation.simulate(name, lever)
        out["levers"] = simulation.levers()
        return out
    except Exception as e:
        return {"name": name, "ok": False, "levers": [], "empty": True, "error": str(e)}


def _living_map_overlay(name: str) -> dict:
    """Living Map — Milestone 5: PATTERN OVERLAY. The Pattern Observatory's real recurring patterns mapped
    onto the map nodes they concern (count + worst severity per node); un-mappable patterns shown honestly
    as 'unmapped', never forced onto a node. Read-only."""
    try:
        from .living_map import overlay
        return overlay.overlay(name)
    except Exception as e:
        return {"name": name, "by_node": {}, "patterns_total": 0, "unmapped": [], "empty": True, "error": str(e)}


def _total_reality_data(name: str) -> dict:
    """Total Reality Control Room — Coverage panel (Level 0): the real product inventory + the finite
    scenario matrix, with the hard-rule coverage. Read-only; computed live from the real product."""
    try:
        from .scenarios import inventory, generator
        from .rover import runner
        inv = inventory.full_inventory()
        m = generator.generate(inv)
        c, mc = inv["counts"], m["counts"]
        ctrl_ids = {x["control_id"] for v in inv["controls"].values() for x in v}
        scen_ctrl = {s["control_id"] for s in m["scenarios"] if s.get("control_id")}
        run = runner.run(m, persona="founder")        # Level-2 execution against the real backing paths
        try:
            from .renegade import runner as _rn
            renegade = _rn.run()["summary"]            # Level-7 integrated stress chains
        except Exception:
            renegade = None
        try:
            from .rover import permissions as _perm
            consent_matrix = _perm.run()["summary"]    # Level-3 permission/consent matrix
        except Exception:
            consent_matrix = None
        try:
            from .rover import data_types as _dt
            data_classes = _dt.run()["summary"]        # Level-4 data-type coverage
        except Exception:
            data_classes = None
        try:
            from .rover import states as _st, pairwise as _pw
            state_pairwise = {"states": _st.run()["summary"], "pairwise": _pw.run()["summary"]}  # L5+L6
        except Exception:
            state_pairwise = None
        try:
            from .rover import soak as _sk
            soak = _sk.run()["summary"]                 # Level-8 long-session / soak
        except Exception:
            soak = None
        try:
            from .rover import fuzz as _fz
            fuzz = _fz.run()["summary"]                 # Level-9 seeded fuzz of the safety pipeline
        except Exception:
            fuzz = None
        try:
            from .rover import personas as _pp
            personas = _pp.run()["summary"]             # per-persona Rover behaviours (floor + divergence)
        except Exception:
            personas = None
        return {
            "name": name,
            "inventory": c,
            "matrix": {"total": mc["total"], "by_level": mc["by_level"], "by_kind": mc["by_kind"],
                       "by_family": mc["by_family"], "critical": mc["critical"], "adversarial": mc["adversarial"]},
            "execution": run["summary"],               # Level-2 pass/fail/blocked/deferred + P0/P1
            "renegade": renegade,                      # Level-7 chains held/total
            "consent_matrix": consent_matrix,          # Level-3 permission/consent matrix pass/total
            "data_classes": data_classes,              # Level-4 data-type coverage pass/total
            "state_pairwise": state_pairwise,          # Level-5 state + Level-6 pairwise
            "soak": soak,                              # Level-8 long-session / soak invariants
            "fuzz": fuzz,                              # Level-9 seeded fuzz floor (0 P0 over the corpus)
            "personas": personas,                      # per-persona Rover floor + divergence
            "hard_rules": {
                "controls_with_scenario": [len(ctrl_ids & scen_ctrl), len(ctrl_ids)],
                "surfaces_served": [c["surfaces_served"], c["surfaces"]],
                "fully_classified": [mc["fully_classified"], mc["total"]],
            },
            "phase": "ALL numbered levels 0-9 + per-persona are built + certified, each with teeth: "
                     "Level 0 (inventory + matrix) + Level 1 (critical) + Level 2 (Rover executes every "
                     "surface/control against the real backing path, evidence bundled) + Levels 3-9 "
                     "(permission / data / state / pairwise / renegade / soak / fuzz) + per-persona Rover. "
                     "Only browser-level DOM clicks + per-scenario deep observation streams remain.",
            "law": "Every visible control has a scenario; every claim maps to a scenario; every scenario is "
                   "fully classified. Infinite phrasing reduced to finite behaviour classes. No invented "
                   "surfaces, no invented controls — discovered from the real product.",
        }
    except Exception as e:
        return {"name": name, "inventory": {}, "matrix": {}, "empty": True, "error": str(e)}


def _security_action(name: str, data: dict) -> dict:
    """The visible panic button — engage or lift a security LOCKDOWN. Reversible + audited (incident
    writes a security event for both). lockdown holds EVERY outward capability OFF at the caps gate,
    regardless of stored grants; restore returns the user's stored settings untouched. Local-only."""
    action = str(data.get("action") or "")
    if action not in ("lockdown", "restore"):
        return {"ok": False, "error": "need action in {lockdown,restore}"}
    try:
        from . import incident
        if action == "lockdown":
            reason = str(data.get("reason") or "manual (Security console)")[:200]
            rec = incident.lockdown(reason, by="founder")
            return {"ok": True, "locked": True, "lockdown": rec}
        lifted = incident.restore(by="founder")
        return {"ok": True, "locked": False, "lifted": bool(lifted)}
    except Exception as e:
        return {"ok": False, "error": "security action failed: %s" % e}


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
        n = max(0, n)
        if n > MAX_BODY:
            # Don't half-read a too-large body (that produced truncated JSON -> a confusing
            # "could not reach the server"). Signal the handler to answer 413, and close the
            # connection since the unread bytes would otherwise desync keep-alive.
            self.close_connection = True
            raise _BodyTooLarge(n, MAX_BODY)
        # Read the FULL declared length. A single rfile.read(n) can short-read on large bodies
        # (TCP delivers in chunks), which silently truncated big uploads — loop until complete.
        buf = bytearray()
        while len(buf) < n:
            chunk = self.rfile.read(n - len(buf))
            if not chunk:
                break
            buf += chunk
        return bytes(buf)

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
            if u.path in ("/observatory", "/observatory.html"):
                # the Observatory page SHELL — public like index.html (it holds no secrets; the data
                # route /observatory.json below is token-gated). One-glance, no-jargon observation view.
                obs = (WEB / "observatory.html")
                if obs.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      obs.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"observatory not built")
            if u.path in ("/console", "/console.html"):
                # Founder Console — Patterns & Improvements page SHELL (public; data is token-gated).
                con = (WEB / "console.html")
                if con.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      con.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"console not built")
            if u.path in ("/security", "/security.html"):
                # Security / Quarantine page SHELL — public like the others (it holds no secrets; the
                # data route /security.json and the POST /security/action below are token-gated).
                sec = (WEB / "security.html")
                if sec.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      sec.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"security console not built")
            if u.path in ("/consent", "/consent.html", "/privacy/consent"):
                # Consent & Boundaries page SHELL — public like the others (data is token-gated).
                cn = (WEB / "consent.html")
                if cn.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      cn.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"consent surface not built")
            if u.path in ("/founder/living-map", "/living-map", "/living_map.html"):
                # Living Map page SHELL (Founder Console -> Living Map) — public like the others; the
                # data route /founder/living-map/state below is token-gated. The operational digital twin.
                lm = (WEB / "living_map.html")
                if lm.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      lm.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"living map not built")
            if u.path in ("/trust", "/trust.html", "/founder/trust"):
                # Trust Ledger page SHELL (Founder Console -> Trust) — public like the others; the data
                # route /trust.json below is token-gated. The one accountable trust spine.
                tl = (WEB / "trust.html")
                if tl.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      tl.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"trust ledger not built")
            if u.path in ("/ergonomics", "/ergonomics.html", "/founder/ergonomics"):
                # Cognitive Ergonomics page SHELL — public like the others; data /ergonomics.json is
                # token-gated. How easy Vera is to follow, scored deterministically over her real replies.
                eg = (WEB / "ergonomics.html")
                if eg.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      eg.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"ergonomics surface not built")
            if u.path in ("/mentorship", "/mentorship.html", "/founder/mentorship"):
                # Mentorship page SHELL — public like the others; data /mentorship.json is token-gated.
                # Guidance without control: real suggestions as non-coercive tradeoffs.
                mp = (WEB / "mentorship.html")
                if mp.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      mp.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"mentorship surface not built")
            if u.path in ("/meaning", "/meaning.html", "/founder/meaning"):
                # Meaning Graph page SHELL — public like the others; data /meaning.json is token-gated.
                # The relational/causal graph with provenance + sensitivity on every fact.
                mg = (WEB / "meaning.html")
                if mg.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      mg.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"meaning graph not built")
            if u.path in ("/identity", "/identity.html", "/founder/identity"):
                # Identity Health page SHELL — public like the others; data /identity.json is token-gated.
                # Freeze-safe identity observability: state + Shadow Ledger + diff, mutation frozen.
                ih = (WEB / "identity.html")
                if ih.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      ih.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"identity health not built")
            if u.path in ("/reality", "/reality.html", "/founder/reality"):
                # Total Reality Control Room (Coverage panel) page SHELL — public; data is token-gated.
                rl = (WEB / "reality.html")
                if rl.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      rl.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"total reality control room not built")
            if u.path in ("/commercial", "/commercial.html"):
                cf = (WEB / "commercial.html")
                if cf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      cf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"commercial surface not built")
            if u.path in ("/sales", "/sales.html"):
                sf = (WEB / "sales.html")
                if sf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      sf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"sales surface not built")
            if u.path in ("/board/revenue", "/board/revenue.html"):
                bf = (WEB / "board_revenue.html")
                if bf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      bf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"board revenue surface not built")
            if u.path in ("/opportunities", "/opportunities.html"):
                opf = (WEB / "opportunities.html")
                if opf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      opf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"opportunities surface not built")
            if u.path in ("/collatio", "/collatio.html"):
                cof = (WEB / "collatio.html")
                if cof.exists():
                    return self._send(200, "text/html; charset=utf-8", cof.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"collatio surface not built")
            if u.path in ("/teams", "/teams.html"):
                tf = (WEB / "teams.html")
                if tf.exists():
                    return self._send(200, "text/html; charset=utf-8", tf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"teams surface not built")
            if u.path in ("/workforce", "/workforce.html"):
                wff = (WEB / "workforce.html")
                if wff.exists():
                    return self._send(200, "text/html; charset=utf-8", wff.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"workforce surface not built")
            if u.path in ("/self", "/self.html"):
                slf = (WEB / "self.html")
                if slf.exists():
                    return self._send(200, "text/html; charset=utf-8", slf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"self surface not built")
            if u.path in ("/pipeline", "/pipeline.html"):
                plf = (WEB / "pipeline.html")
                if plf.exists():
                    return self._send(200, "text/html; charset=utf-8", plf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"pipeline surface not built")
            if u.path in ("/marketplaces/fiverr", "/marketplaces/fiverr.html", "/marketplaces"):
                fvf = (WEB / "fiverr.html")
                if fvf.exists():
                    return self._send(200, "text/html; charset=utf-8", fvf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"fiverr channel surface not built")
            if u.path in ("/revenue/cash", "/revenue/cash.html"):
                rcf = (WEB / "revenue_cash.html")
                if rcf.exists():
                    return self._send(200, "text/html; charset=utf-8", rcf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"cash milestone surface not built")
            if u.path in ("/revenue/swarm", "/revenue/swarm.html"):
                rsf = (WEB / "revenue_swarm.html")
                if rsf.exists():
                    return self._send(200, "text/html; charset=utf-8", rsf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"revenue swarm surface not built")
            if u.path in ("/revenue", "/revenue.html"):
                rvf = (WEB / "revenue.html")
                if rvf.exists():
                    return self._send(200, "text/html; charset=utf-8", rvf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"revenue surface not built")
            if u.path in ("/compounding", "/compounding.html"):
                cpf = (WEB / "compounding.html")
                if cpf.exists():
                    return self._send(200, "text/html; charset=utf-8", cpf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"compounding surface not built")
            if u.path in ("/revenue/intelligence", "/revenue/intelligence.html"):
                rif = (WEB / "revenue_intelligence.html")
                if rif.exists():
                    return self._send(200, "text/html; charset=utf-8", rif.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"revenue intelligence surface not built")
            if u.path in ("/distribution", "/distribution.html"):
                dsf = (WEB / "distribution.html")
                if dsf.exists():
                    return self._send(200, "text/html; charset=utf-8", dsf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"distribution surface not built")
            if u.path in ("/trust/moat", "/trust/moat.html"):
                tmf = (WEB / "trust_moat.html")
                if tmf.exists():
                    return self._send(200, "text/html; charset=utf-8", tmf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"trust moat surface not built")
            if u.path in ("/resources", "/resources.html"):
                ref = (WEB / "resources.html")
                if ref.exists():
                    return self._send(200, "text/html; charset=utf-8", ref.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"resources surface not built")
            if u.path in ("/empire", "/empire.html"):
                emf = (WEB / "empire.html")
                if emf.exists():
                    return self._send(200, "text/html; charset=utf-8", emf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"empire surface not built")
            if u.path in ("/observation", "/observation.html", "/founder/observation"):
                of = (WEB / "observation.html")
                if of.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      of.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"observation surface not built")
            if u.path in ("/chairman", "/chairman.html"):
                cf = (WEB / "chairman.html")
                if cf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      cf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"chairman dashboard not built")
            if u.path in ("/founder", "/founder.html", "/company", "/company.html"):
                ff = (WEB / "founder.html")
                if ff.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      ff.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"founder command center not built")
            if u.path in ("/learning", "/learning.html", "/founder/learning"):
                lf = (WEB / "learning.html")
                if lf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      lf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"learning dashboard not built")
            if u.path in ("/verification", "/verification.html", "/founder/verification"):
                # Verification Dashboard (release-truth board) page SHELL — public; data is token-gated.
                vf = (WEB / "verification.html")
                if vf.exists():
                    return self._send(200, "text/html; charset=utf-8",
                                      vf.read_text(encoding="utf-8").encode())
                return self._send(404, "text/plain", b"verification dashboard not built")
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
            if u.path == "/observatory.json":
                # the one honest JSON behind the Observatory page: what's real (audit), what kind of
                # mind (system shape), what Vera knows about you (twin), the latest turn (activity/proof),
                # and trust/security. Personal -> token-gated. Read-only; never raises.
                return self._send(200, "application/json",
                                  json.dumps(_observatory_data(self.name)).encode())
            if u.path == "/console.json":
                # Founder Console data — patterns / improvements / learning-loop / live-feed, from the
                # REAL pattern + improvement stores. Token-gated. Read-only; honest empty state.
                return self._send(200, "application/json",
                                  json.dumps(_console_data(self.name)).encode())
            if u.path == "/security.json":
                # Security / Quarantine data — lockdown posture, immune status, live quarantined sources,
                # quarantine catches, the SOC trail, caps posture. Token-gated. Read-only; honest.
                return self._send(200, "application/json",
                                  json.dumps(_security_data(self.name)).encode())
            if u.path in ("/consent.json", "/privacy/consent.json"):
                # Consent & Boundaries data — per-domain consent + held sensitive memories. Token-gated.
                return self._send(200, "application/json",
                                  json.dumps(_consent_data(self.name)).encode())
            if u.path in ("/trust.json", "/founder/trust.json"):
                # Trust Ledger data — the categorised, provenance-linked trust spine + the trust
                # invariants (each falsifiable). Token-gated. Read-only; honest empty state.
                return self._send(200, "application/json",
                                  json.dumps(_trust_data(self.name)).encode())
            if u.path in ("/ergonomics.json", "/founder/ergonomics.json"):
                # Cognitive Ergonomics data — deterministic clarity scores of Vera's real recent replies
                # + human-level issues. Token-gated. Read-only; honest empty state.
                return self._send(200, "application/json",
                                  json.dumps(_ergonomics_data(self.name)).encode())
            if u.path in ("/mentorship.json", "/founder/mentorship.json"):
                # Mentorship data — real pending suggestions as non-coercive tradeoffs (options +
                # pros/cons + a recommendation the user owns). Token-gated. Read-only; honest empty.
                return self._send(200, "application/json",
                                  json.dumps(_mentorship_data(self.name)).encode())
            if u.path in ("/meaning.json", "/founder/meaning.json"):
                # Meaning Graph data — World State edges with provenance + sensitivity on every fact.
                # Token-gated. Read-only; honest empty state.
                return self._send(200, "application/json",
                                  json.dumps(_meaning_graph_data(self.name)).encode())
            if u.path in ("/identity.json", "/founder/identity.json"):
                # Identity Health data — identity-core summary + Shadow Ledger + diff + freeze posture.
                # Token-gated. Read-only; mutation frozen.
                return self._send(200, "application/json",
                                  json.dumps(_identity_health_data(self.name)).encode())
            if u.path in ("/reality.json", "/founder/reality.json"):
                # Total Reality Control Room data — the real product inventory + scenario-matrix coverage
                # + the hard-rule status. Token-gated. Read-only; computed live from the real product.
                return self._send(200, "application/json",
                                  json.dumps(_total_reality_data(self.name)).encode())
            if u.path in ("/verification.json", "/founder/verification.json"):
                # Verification Dashboard data — the COMPUTED release verdict (build identity + gates +
                # blockers + decision) from the real reports. Token-gated. Read-only; never hardcoded.
                from .verification import dashboard as _vdash
                return self._send(200, "application/json",
                                  json.dumps(_vdash.data()).encode())
            if u.path.startswith("/founder/verification/"):
                # §27 read API — slices of the computed verdict + the run records. Token + Face-ID gated.
                from .verification import dashboard as _vdash, api as _vapi
                sub = u.path[len("/founder/verification/"):]
                if sub.startswith("runs/"):
                    return self._send(200, "application/json",
                                      json.dumps(_vapi.get_run(sub[len("runs/"):])).encode())
                if sub == "runs":
                    return self._send(200, "application/json", json.dumps(_vapi.list_runs()).encode())
                d = _vdash.data()
                pick = {"status": d.get("top"), "gates": d.get("gates"), "blockers": d.get("blockers"),
                        "evidence": d.get("evidence_room"), "release-decision": d.get("decision"),
                        "overrides": _vapi.overrides()}.get(sub)
                if pick is None:
                    return self._send(404, "application/json", b'{"error":"unknown verification resource"}')
                return self._send(200, "application/json", json.dumps(pick).encode())
            if u.path in ("/founder/living-map/state", "/living-map/state"):
                # Living Map graph — nodes/edges with LIVE, real-telemetry-backed status (honest
                # 'unknown' where not instrumented). Token-gated. Read-only; never mutates Vera state.
                return self._send(200, "application/json",
                                  json.dumps(_living_map_data(self.name)).encode())
            if u.path in ("/founder/living-map/events", "/living-map/events"):
                # Living Map Milestone 2 — REAL recent events (MRI turns + security catches) for the
                # Live-Flow animation, evidence-backed. Token-gated. Read-only; honest empty when idle.
                return self._send(200, "application/json",
                                  json.dumps(_living_map_events(self.name)).encode())
            if u.path in ("/founder/living-map/replay", "/living-map/replay"):
                # Living Map Milestone 3 — REPLAY: the same real trace as a chronological, seekable
                # timeline (deterministic seek). Token-gated. Read-only; honest empty when idle.
                return self._send(200, "application/json",
                                  json.dumps(_living_map_replay(self.name)).encode())
            if u.path in ("/founder/living-map/simulate", "/living-map/simulate"):
                # Living Map Milestone 4 — SIMULATION: pull a lever -> predicted impact, derived from
                # re-running the real status resolvers under a hypothetical, sandboxed. Token-gated.
                _lever = (parse_qs(u.query).get("lever", [""])[0] or "").strip()
                return self._send(200, "application/json",
                                  json.dumps(_living_map_simulate(self.name, _lever)).encode())
            if u.path in ("/founder/living-map/overlay", "/living-map/overlay"):
                # Living Map Milestone 5 — PATTERN OVERLAY: the real recurring patterns mapped onto the
                # nodes they concern (count + worst severity); un-mappable -> 'unmapped'. Token-gated.
                return self._send(200, "application/json",
                                  json.dumps(_living_map_overlay(self.name)).encode())
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
            elif u.path == "/briefing":
                self._send(200, "application/json", _serve_briefing(self.name).encode())
            elif u.path == "/persona":
                from .mouth import load_persona
                self._send(200, "application/json",
                           json.dumps({"persona": load_persona(self.name)}).encode())
            elif u.path == "/values":
                from .mouth import values_for_ui
                self._send(200, "application/json",
                           json.dumps({"values": values_for_ui(self.name)}).encode())
            elif u.path == "/first_launch.json":
                from . import first_launch as _fl
                self._send(200, "application/json",
                           json.dumps(_fl.state()).encode())
            elif u.path == "/first_launch/smoke":
                from . import first_launch as _fl
                self._send(200, "application/json",
                           json.dumps(_fl.smoke_test()).encode())
            elif u.path == "/auto_learn/queue":
                from .auto_learn import api as _al_api
                self._send(200, "application/json",
                           json.dumps(_al_api.serve_queue(self.name)).encode())
            elif u.path == "/packs":
                from .knowledge_packs import api as _kp_api
                self._send(200, "application/json",
                           json.dumps(_kp_api.serve_list(self.name)).encode())
            elif u.path == "/teaching/queue":
                # Teach Vera — the approval queue with full review payloads (conflicts, rollback plan)
                from .teaching import api as _teach_api
                self._send(200, "application/json",
                           json.dumps(_teach_api.serve_queue(self.name)).encode())
            elif u.path == "/host/profile.json":
                # the ACTIVE host runtime contract — the same record enforcement reads
                from .host import profile as _hprof
                self._send(200, "application/json",
                           json.dumps({"ok": True, "profile": _hprof.current()}).encode())
            elif u.path == "/commercial.json":
                from .commercial import (assets as _ca, wedge as _cw, offer as _co,
                                         ip_license as _cip, wedge_ranker as _cwr)
                from .observation import emit as _obeC
                _obeC.record(self.name, "/commercial", "commercial", "software_asset_inventory_viewed",
                             actor="user")
                _inv = _ca.inventory(self.name)
                for _a in _inv["assets"]:
                    _a["sell_gate"] = _cip.can_sell(self.name, _a["asset_id"])
                try:  # compute the recommendation live + read-only (honest current state, no side-effects)
                    _wedge = _cwr.rank(self.name, write=False)
                except Exception:
                    _wedge = None
                self._send(200, "application/json", json.dumps({
                    "ok": True, "inventory": _inv, "first_wedge": _wedge,
                    "wedges": _cw.list_wedges(self.name), "offers": _co.list_offers(self.name)}).encode())
            elif u.path == "/sales.json":
                from .commercial import revenue_briefing as _rb
                from .observation import emit as _obeS
                _obeS.record(self.name, "/sales", "commercial", "revenue_briefing_generated",
                             actor="user", report_refs=["reports/verification_worklog.md"])
                self._send(200, "application/json", json.dumps(_rb.build(self.name)).encode())
            elif u.path == "/board/revenue.json":
                from .commercial import revenue_briefing as _rbb
                from .observation import emit as _obeB
                _obeB.record(self.name, "/board/revenue", "commercial", "board_revenue_briefing_viewed",
                             actor="user", report_refs=["reports/board_revenue_briefing.json"])
                self._send(200, "application/json", json.dumps(_rbb.build(self.name)).encode())
            elif u.path == "/opportunities.json":
                from .market_vision import api as _mva
                from .observation import emit as _obeO
                _obeO.record(self.name, "/opportunities", "market_vision", "market_vision_dashboard_viewed",
                             actor="user", report_refs=["reports/market_vision_engine.json"])
                self._send(200, "application/json", json.dumps(_mva.dashboard(self.name)).encode())
            elif u.path == "/collatio.json":
                from .collatio import api as _ca
                from .observation import emit as _obeCo
                _obeCo.record(self.name, "/collatio", "collatio", "collatio_dashboard_viewed",
                              actor="user", report_refs=["reports/collatio_operating_authority_layer.json"])
                self._send(200, "application/json", json.dumps(_ca.dashboard(self.name)).encode())
            elif u.path == "/teams.json":
                from .teams import api as _ta
                from .observation import emit as _obeT
                _obeT.record(self.name, "/teams", "teams", "teams_dashboard_viewed",
                             actor="user", report_refs=["reports/team_builder_delegation_layer.json"])
                self._send(200, "application/json", json.dumps(_ta.dashboard(self.name)).encode())
            elif u.path == "/workforce.json":
                from .workforce import api as _wa
                from .observation import emit as _obeW
                _obeW.record(self.name, "/workforce", "workforce", "workforce_dashboard_viewed",
                             actor="user", report_refs=["reports/workforce_foundry_engine.json"])
                self._send(200, "application/json", json.dumps(_wa.dashboard(self.name)).encode())
            elif u.path == "/self.json":
                from .self_evolution import api as _sa
                from .observation import emit as _obeSf
                _obeSf.record(self.name, "/self", "self_evolution", "self_dashboard_viewed",
                              actor="user", report_refs=["reports/self_observation_diagnosis_layer.json"])
                self._send(200, "application/json", json.dumps(_sa.dashboard(self.name)).encode())
            elif u.path == "/pipeline.json":
                from .marketplaces.upwork import api as _uwa
                from .observation import emit as _obePl
                _obePl.record(self.name, "/pipeline", "upwork", "pipeline_dashboard_viewed",
                              actor="user", report_refs=["reports/upwork_pipeline.json"])
                self._send(200, "application/json", json.dumps(_uwa.dashboard(self.name)).encode())
            elif u.path == "/marketplaces/fiverr.json":
                from .marketplaces.fiverr import api as _fva
                from .observation import emit as _obeFv
                _obeFv.record(self.name, "/marketplaces/fiverr", "fiverr", "fiverr_dashboard_viewed",
                              actor="user", report_refs=["reports/fiverr_channel_engine.json"])
                self._send(200, "application/json", json.dumps(_fva.dashboard(self.name)).encode())
            elif u.path == "/revenue/cash.json":
                from .revenue import milestone_api as _mca
                from .observation import emit as _obeMc
                _obeMc.record(self.name, "/revenue/cash", "revenue_milestone", "cash_milestone_dashboard_viewed",
                              actor="user", report_refs=["reports/financial_milestone_16000_plan.json"])
                self._send(200, "application/json", json.dumps(_mca.dashboard(self.name)).encode())
            elif u.path == "/revenue/swarm.json":
                from .revenue_swarm import api as _rswa
                from .observation import emit as _obeRs
                _obeRs.record(self.name, "/revenue/swarm", "revenue_swarm", "revenue_swarm_dashboard_viewed",
                              actor="user", report_refs=["reports/revenue_swarm_factory.json"])
                self._send(200, "application/json", json.dumps(_rswa.dashboard(self.name)).encode())
            elif u.path == "/revenue.json":
                from .revenue import api as _rva
                from .observation import emit as _obeRv
                _obeRv.record(self.name, "/revenue", "revenue", "revenue_strike_dashboard_viewed",
                              actor="user", report_refs=["reports/revenue_strike_engine.json"])
                self._send(200, "application/json", json.dumps(_rva.dashboard(self.name)).encode())
            elif u.path == "/compounding.json":
                from .compounding import api as _cpa
                from .observation import emit as _obeCp
                _obeCp.record(self.name, "/compounding", "compounding", "compounding_dashboard_viewed",
                              actor="user", report_refs=["reports/compounding_engine.json"])
                self._send(200, "application/json", json.dumps(_cpa.dashboard(self.name)).encode())
            elif u.path == "/revenue/intelligence.json":
                from .revenue_intelligence import api as _ria
                from .observation import emit as _obeRi
                _obeRi.record(self.name, "/revenue/intelligence", "revenue_intelligence",
                              "revenue_intelligence_dashboard_viewed", actor="user",
                              report_refs=["reports/revenue_intelligence_layer.json"])
                self._send(200, "application/json", json.dumps(_ria.dashboard(self.name)).encode())
            elif u.path == "/distribution.json":
                from .distribution import api as _dia
                from .observation import emit as _obeDi
                _obeDi.record(self.name, "/distribution", "distribution", "distribution_dashboard_viewed",
                              actor="user", report_refs=["reports/distribution_demand_engine.json"])
                self._send(200, "application/json", json.dumps(_dia.dashboard(self.name)).encode())
            elif u.path == "/trust/moat.json":
                from .trust import api as _tma
                from .observation import emit as _obeTm
                _obeTm.record(self.name, "/trust/moat", "trust", "trust_moat_dashboard_viewed",
                              actor="user", report_refs=["reports/trust_reputation_moat.json"])
                self._send(200, "application/json", json.dumps(_tma.dashboard(self.name)).encode())
            elif u.path == "/resources.json":
                from .resources import api as _rea
                from .observation import emit as _obeRe
                _obeRe.record(self.name, "/resources", "resources", "resource_dashboard_viewed",
                              actor="user", report_refs=["reports/resource_expansion_planner.json"])
                self._send(200, "application/json", json.dumps(_rea.dashboard(self.name)).encode())
            elif u.path == "/empire.json":
                from .empire import api as _ema
                from .observation import emit as _obeEm
                _obeEm.record(self.name, "/empire", "empire", "empire_dashboard_viewed",
                              actor="user", report_refs=["reports/multi_host_empire_allocator.json"])
                self._send(200, "application/json", json.dumps(_ema.dashboard(self.name)).encode())
            elif u.path == "/governance.json":
                from .observation import emit as _obe
                self._send(200, "application/json",
                           json.dumps({"ok": True, "governance": _obe.governance_snapshot(self.name)}).encode())
            elif u.path == "/observation.json":
                from .observation import api as _oba, emit as _obe2
                _obe2.record(self.name, "/observation", "observation", "observation_surface_viewed",
                             actor="user")
                self._send(200, "application/json", json.dumps(_oba.serve_recent(self.name)).encode())
            elif u.path == "/observation/trace":
                from .observation import api as _oba2
                tid = parse_qs(u.query).get("trace_id", [""])[0]
                self._send(200, "application/json", json.dumps(_oba2.serve_trace(self.name, tid)).encode())
            elif u.path == "/foundry/portfolio.json":
                from .foundry import core as _fc
                from .observation import emit as _obe3
                _obe3.record(self.name, "/chairman", "foundry", "chairman_dashboard_viewed", actor="user")
                self._send(200, "application/json", json.dumps(_fc.portfolio(self.name)).encode())
            elif u.path == "/company/briefing.json":
                from .company import briefing as _brief
                from .observation import emit as _obeF
                _obeF.record(self.name, "/founder", "company", "daily_briefing_generated", actor="user",
                             report_refs=["reports/verification_worklog.md"])
                self._send(200, "application/json", json.dumps(_brief.build(self.name)).encode())
            elif u.path == "/company/state.json":
                from .company import engineering_state as _eng, release_tracker as _rel
                self._send(200, "application/json", json.dumps(
                    {"ok": True, "engineering": _eng.snapshot(), "release": _rel.state()}).encode())
            elif u.path == "/learning.json":
                from .truth import learning_view as _lv
                from .observation import emit as _obeL
                _obeL.record(self.name, "/learning", "learning", "learning_dashboard_viewed", actor="user")
                self._send(200, "application/json",
                           json.dumps(_lv.build(self.name)).encode())
            elif u.path == "/truth.json":
                # Truth Ledger summary — the dashboard's "what does she claim, and is it backed?"
                from .truth import ledger as _tl, query as _tq
                _evs = _tl.load(self.name)
                _folded = _tq.fold(self.name)
                _by_status = {}
                for _e in _folded.values():
                    _by_status[_e.get("active_status", "?")] = _by_status.get(_e.get("active_status", "?"), 0) + 1
                self._send(200, "application/json", json.dumps({
                    "ok": True, "events_total": len(_evs), "by_status": _by_status,
                    "unsupported": len(_tq.unsupported(self.name)),
                    "active": [{k: e.get(k) for k in ("event_id", "subject", "claim", "claim_type",
                                                       "scope", "confidence", "created_at")}
                               for e in _tq.active(self.name)][-200:],
                }).encode())
            elif u.path == "/truth/trace":
                # the provenance chain behind one displayed claim (oldest first)
                from .truth import query as _tq2
                _eid = parse_qs(u.query).get("event_id", [""])[0]
                self._send(200, "application/json", json.dumps({
                    "ok": True, "event_id": _eid, "chain": _tq2.trace(self.name, _eid)}).encode())
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
            elif u.path == "/mind/export":
                # the PORTABLE MIND — what Vera has grounded about the PERSON (facts + how-you-think),
                # as a model-agnostic bundle they can carry app-to-app. Distinct from /identity/export
                # (which is Vera's OWN character). Read-only; no store is mutated.
                from . import portable
                body = json.dumps(portable.export_mind(self.name), ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Disposition",
                                 f'attachment; filename="{self.name}.mind.json"')
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
            elif u.path == "/personal/profile":
                # GET /personal/profile -> the grounded "what Vera has learned about you" model.
                self._send(200, "application/json", _serve_personal_profile(self.name).encode())
            elif u.path == "/theory":
                # GET /theory -> the Wisdom engine's grounded theories + long-horizon lessons.
                self._send(200, "application/json", _serve_theory(self.name).encode())
            elif u.path == "/platform/export":
                # GET /platform/export -> the FULL portable-mind bundle (carry her whole mind).
                self._send(200, "application/json", _serve_platform_export(self.name).encode())
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
            if path == "/auto_learn/decide":
                # Auto Learn — suggestion-only; convert creates a Teaching draft (no direct persist)
                data = json.loads(self._read_body() or b"{}")
                from .auto_learn import api as _al_api
                return self._send(200, "application/json",
                                  json.dumps(_al_api.serve_decide(self.name, data)).encode())
            if path in ("/packs/add", "/packs/build", "/packs/lifecycle", "/packs/retrieve",
                        "/packs/import"):
                # Knowledge Packs — quarantined-by-default curated knowledge; DATA, never policy
                data = json.loads(self._read_body() or b"{}")
                from .knowledge_packs import api as _kp_api
                fn = {"/packs/add": _kp_api.serve_add, "/packs/build": _kp_api.serve_build,
                      "/packs/lifecycle": _kp_api.serve_lifecycle,
                      "/packs/retrieve": _kp_api.serve_retrieve,
                      "/packs/import": _kp_api.serve_import}[path]
                return self._send(200, "application/json",
                                  json.dumps(fn(self.name, data)).encode())
            if path == "/teaching/propose":
                # Teach Vera — create a PENDING teaching record (nothing persists without approval)
                data = json.loads(self._read_body() or b"{}")
                from .teaching import api as _teach_api
                return self._send(200, "application/json",
                                  json.dumps(_teach_api.serve_propose(self.name, data)).encode())
            if path == "/teaching/decide":
                # approve / edit / reject / chat_only / never_learn / rollback — the user's call
                data = json.loads(self._read_body() or b"{}")
                from .teaching import api as _teach_api
                return self._send(200, "application/json",
                                  json.dumps(_teach_api.serve_decide(self.name, data)).encode())
            if path == "/console/decide":
                # Founder Console — approve / reject an improvement suggestion. Persisted + audited.
                data = json.loads(self._read_body() or b"{}")
                return self._send(200, "application/json",
                                  json.dumps(_console_decide(self.name, data)).encode())
            if path == "/security/action":
                # Security console — engage / lift a lockdown (the visible panic button). Reversible +
                # audited. Token-gated + Face-ID-gated (above), like every other POST control.
                data = json.loads(self._read_body() or b"{}")
                return self._send(200, "application/json",
                                  json.dumps(_security_action(self.name, data)).encode())
            if path == "/consent/decide":
                # Consent & Boundaries — grant/deny/ask/revoke a consent, or approve/reject a held
                # sensitive memory. Persisted + audited. Token + Face-ID gated like every POST control.
                data = json.loads(self._read_body() or b"{}")
                return self._send(200, "application/json",
                                  json.dumps(_consent_action(self.name, data)).encode())
            if path.startswith("/founder/verification/"):
                # §27/§23 write API — trigger a verification run, record a Founder Override (the ONLY
                # human path to move the verdict, and it cannot be created without a complete record),
                # or acknowledge a blocker. Token + Face-ID gated (above). Persisted + auditable.
                from .verification import api as _vapi
                import datetime as _dt
                now = _dt.datetime.utcnow().isoformat() + "Z"
                data = json.loads(self._read_body() or b"{}")
                act = path[len("/founder/verification/"):]
                if act.startswith("run-"):
                    out = _vapi.start_run(act[len("run-"):], at=now)
                elif act == "founder-override":
                    out = _vapi.record_override(
                        data.get("who"), data.get("gate"), data.get("why"),
                        data.get("risk_accepted"), data.get("expires_at"),
                        data.get("required_follow_up"), at=now)
                elif act == "acknowledge-blocker":
                    out = _vapi.acknowledge_blocker(data.get("blocker_id"), data.get("who"),
                                                    data.get("note", ""), at=now)
                else:
                    out = {"error": "unknown verification action %r" % act}
                code = 400 if out.get("error") else 200
                return self._send(code, "application/json", json.dumps(out).encode())
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
            elif path == "/personal/learn":
                self._read_body()                       # drain (no args needed)
                self._send(200, "application/json", _serve_personal_learn(self.name).encode())
            elif path == "/personal/forget":
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _serve_personal_forget(self.name, data).encode())
            elif path == "/personal/edit":
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _serve_personal_edit(self.name, data).encode())
            elif path == "/platform/import":
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", _serve_platform_import(self.name, data).encode())
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
        except _BodyTooLarge as e:
            mb, cap_mb = e.n / (1024 * 1024), e.cap / (1024 * 1024)
            msg = (f"file too large: {mb:.0f} MB sent (the upload is base64-encoded, ~1.35x the file). "
                   f"Max ~{cap_mb * 0.74:.0f} MB per file — try a smaller file, split it, or paste a "
                   f"text transcript.")
            try:
                self._send(413, "application/json", json.dumps({"error": msg}).encode())
            except Exception:
                pass
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
    token = os.environ.get("ANIMA_TOKEN", "")
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit(
            "\nrefusing to expose Vera without ANIMA_TOKEN.\n"
            "  set ANIMA_TOKEN to a strong secret before using --expose or a non-loopback --host.\n"
            "  localhost remains available without a token for local development.\n")
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
    Handler.token = token
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
        print("EXPOSED on your LAN (ANIMA_TOKEN required). Prefer a private tunnel (Tailscale).")
    else:
        print("localhost-only. For your phone, front it with a tunnel (Tailscale/cloudflared).")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")


if __name__ == "__main__":
    main()
