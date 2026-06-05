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


def _turn(name, text, voice=False):
    """One exchange: feel it, record it, reply from state. Serialised for safety."""
    with _lock:
        heart = Heart.from_dict(load_json(_path(name)))
        p = senses.read(text, name=name)
        now = time.time()
        mem = Memory.load(_mem(name))
        last = mem.rows[-1]["clock"] if mem.rows else heart.last_tick
        mem.record(heart.input_vector(p.vector(), now), (now - last) / 60.0, now)
        mem.save(_mem(name))
        heart.perceive(p.vector(), now=now)
        audio_out = str(STORE / f"{name}.last.wav") if voice else None
        # deterministic capability router: fetch REAL live data (read) or prepare a
        # confirm-gated draft (send) in code, so the mouth narrates only what's proven
        # and NOTHING sends without an explicit confirm.
        from . import route
        routed = route.route(name, text)
        cap_note = routed.get("note") if routed else None
        _tid = "t-%d" % int(now * 1000)            # telemetry: open a flight-recorder trace for this
        try:                                       # turn (direct/off-bus path — no organs on the bus
            from . import telemetry as _telem      # yet). Passive: only appends; a recorder failure
            _telem.get(name).begin(_tid)           # can never break a turn.
        except Exception:
            pass
        # Organ 3 (Router): query-aware memory selection — inject ONLY the facts relevant
        # to THIS turn (not the blanket top-N), and decide the cheapest-sufficient path.
        # PII guard: blank the fact block on a cloud brain so private facts never leave.
        _route_dec, _fact_block = None, None
        try:
            from .organs import router
            from . import cloud as _cl
            _route_dec = router.route(name, text, {"cloud_on": _cl.is_cloud()})
            if not _cl.is_cloud():
                _fact_block = _route_dec.selected_block
        except Exception:
            pass
        mouth = _mouth()
        _g0 = time.perf_counter()
        u = mouth.respond(heart, text, history=list(_HISTORY),
                          audio_out=audio_out, perception=p, cap_note=cap_note,
                          fact_block=_fact_block)
        gen_s = time.perf_counter() - _g0      # generation time (no TTS — that's streamed)
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
        _verdict = None
        try:
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
        _HISTORY.append((text, u.text))           # within-session memory
        _save_history(name)                        # survive a restart
        try:                                       # record model use for the cleanup routine
            from . import models, cloud
            if not cloud.is_cloud():
                models.touch(models.active_local())
        except Exception:
            pass
        portrait.log_turn(name, text, u.text)      # logged for the next sleep to distil
        try:                                       # capture durable user-facts NOW (birthday, dog…)
            from . import memory_lirf               # into the LIRF ledger — immediate, not just at
            memory_lirf.capture(name, text)         # sleep — so a fact told today is known tomorrow.
        except Exception:
            pass
        try:                                       # Personal World State: capture relational/causal
            from . import world_state               # edges from THIS turn (additive, union-safe save,
            world_state.capture_relations(name, text)  # race-free under _lock) — situations build over time.
        except Exception:
            pass
        try:                                       # PROACTIVE ASIDE — at most ONE gentle, optional aside
            from . import curiosity, loops, cloud as _cc  # per session, only on a CASUAL turn (no fact
            if (not _cc.is_cloud()                  # answered, no capability, no verifier override),
                    and name not in _CURIOSITY_ASKED   # cloud-off (PII). AFTER capture, so a fact/goal
                    and not _fact_block and not cap_note   # stated THIS turn is never asked back about.
                    and not (_verdict is not None and getattr(_verdict, "override", False))):
                _aside = None
                try:                                # 1) Dream Engine: resurface a stalled open loop —
                    _rl = loops.resurface(name)     # "you wanted X — still?" (paced + 21-day cooldown)
                    if _rl and _rl.strip():
                        _ch = loops.last_resurface_choice()
                        if _ch:
                            loops.mark_resurfaced(name, _ch, line=_rl)  # never re-nag (Law 001 ledger)
                        _aside = _rl.strip()
                except Exception:
                    _aside = None
                if not _aside:                      # 2) else a contextual curiosity question (Law 002)
                    try:
                        _q = curiosity.next_question(name, recent_text=text)
                        if _q and _q.strip():
                            _cands = curiosity.candidate_gaps(name)
                            if _cands:
                                curiosity.mark_asked(name, _cands[0])   # never re-ask this gap (Law 002)
                            _aside = _q.strip()
                    except Exception:
                        _aside = None
                if _aside:                          # surface exactly one, persist, mark the session
                    u.text = u.text.rstrip() + "\n\n" + _aside
                    _HISTORY[-1] = (text, u.text)                       # within-session coherence
                    _save_history(name)                                 # persist it (Law 001)
                    _CURIOSITY_ASKED.add(name)
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
