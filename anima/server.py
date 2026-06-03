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
_HISTORY = deque(maxlen=6)           # recent (you, vera) turns — within-session memory


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
        mouth = _mouth()
        _g0 = time.perf_counter()
        u = mouth.respond(heart, text, history=list(_HISTORY),
                          audio_out=audio_out, perception=p, cap_note=cap_note)
        gen_s = time.perf_counter() - _g0      # generation time (no TTS — that's streamed)
        _HISTORY.append((text, u.text))           # within-session memory
        try:                                       # record model use for the cleanup routine
            from . import models, cloud
            if not cloud.is_cloud():
                models.touch(models.active_local())
        except Exception:
            pass
        portrait.log_turn(name, text, u.text)      # logged for the next sleep to distil
        save_json(_path(name), heart.to_dict())    # atomic — never half-written
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
                html = ((WEB / "index.html").read_text()
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
            elif u.path == "/capabilities":
                from . import caps
                self._send(200, "application/json", json.dumps(caps.load(self.name)).encode())
            elif u.path == "/brain":
                from . import cloud
                self._send(200, "application/json", json.dumps(cloud.public()).encode())
            elif u.path == "/models":
                from . import models
                self._send(200, "application/json", json.dumps(models.listing()).encode())
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
            elif path == "/capabilities":
                from . import caps
                data = json.loads(self._read_body() or b"{}")
                self._send(200, "application/json", json.dumps(caps.save(self.name, data)).encode())
            elif path == "/brain":
                from . import cloud
                data = json.loads(self._read_body() or b"{}")
                out = cloud.save_cfg(str(data.get("provider", "local")), str(data.get("model", "")),
                                     str(data.get("key", "")), str(data.get("base", "")),
                                     data.get("budget"))
                _reset_mouth()                          # rebuild the mouth with the new brain
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
