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
import json
import logging
import threading
import time
import warnings

warnings.filterwarnings("ignore")                       # quiet torch/HF startup noise
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .heart import Heart
from .memory import Memory
from .mouth import Mouth
from .util import label
from . import senses

STORE = Path(".anima")
WEB = Path(__file__).parent / "web"
_lock = threading.Lock()
_MOUTH = None
_EARS = None


def _mouth(voice):
    global _MOUTH
    if _MOUTH is None:
        _MOUTH = Mouth.assemble(voice=voice)   # built once, not per request
    return _MOUTH


def _ears():
    global _EARS
    if _EARS is None:
        from .mouth import WhisperEars
        _EARS = WhisperEars()                  # Whisper large-v3-turbo, loaded once
    return _EARS


def _transcribe(audio_bytes):
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        return {"text": _ears().listen(tmp)}
    except Exception as e:
        import sys
        print(f"[anima ears] transcription failed: {e}", file=sys.stderr)
        return {"text": ""}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _path(name):
    return STORE / f"{name}.json"


def _mem(name):
    return STORE / f"{name}.mem.json"


def _ensure(name, neurons):
    if not _path(name).exists():
        STORE.mkdir(exist_ok=True)
        _path(name).write_text(json.dumps(Heart.born(name, n=neurons).to_dict()))


def _turn(name, text, voice=False):
    """One exchange: feel it, record it, reply from state. Serialised for safety."""
    with _lock:
        heart = Heart.from_dict(json.loads(_path(name).read_text()))
        p = senses.read(text, name=name)
        now = time.time()
        mem = Memory.load(_mem(name))
        last = mem.rows[-1]["clock"] if mem.rows else heart.last_tick
        mem.record(heart.input_vector(p.vector(), now), (now - last) / 60.0, now)
        mem.save(_mem(name))
        heart.perceive(p.vector(), now=now)
        audio_out = str(STORE / f"{name}.last.wav") if voice else None
        u = _mouth(voice).respond(heart, text, audio_out=audio_out, perception=p)
        _path(name).write_text(json.dumps(heart.to_dict()))
        return {
            "reply": u.text, "feeling": u.feeling, "register": u.delivery["register"],
            "rate": u.delivery["rate"], "backend": u.backend,
            "audio_url": f"/audio?name={name}&t={int(now)}" if u.audio_path else None,
        }


class Handler(BaseHTTPRequestHandler):
    name = "Vera"
    voice = False

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            html = (WEB / "index.html").read_text().replace("__NAME__", self.name)
            self._send(200, "text/html; charset=utf-8", html.encode())
        elif u.path == "/audio":
            nm = parse_qs(u.query).get("name", [self.name])[0]
            f = STORE / f"{nm}.last.wav"
            if f.exists():
                self._send(200, "audio/wav", f.read_bytes())
            else:
                self._send(404, "text/plain", b"no audio")
        elif u.path == "/state":
            heart = Heart.from_dict(json.loads(_path(self.name).read_text()))
            self._send(200, "application/json", json.dumps(heart.feeling()).encode())
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/talk":
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, "application/json",
                       json.dumps(_turn(self.name, data.get("text", ""), self.voice)).encode())
        elif path == "/stt":
            n = int(self.headers.get("Content-Length", 0))
            audio = self.rfile.read(n)
            self._send(200, "application/json", json.dumps(_transcribe(audio)).encode())
        else:
            self._send(404, "text/plain", b"not found")

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
    label(f"{args.name} server :{args.port}")
    import os
    print(f"brain: {os.environ.get('ANIMA_MODEL', 'qwen2.5:7b-instruct')} (Ollama) — "
          f"make sure `ollama list` shows it")
    if args.voice:
        from .mouth import KokoroVoice
        if KokoroVoice().available():
            print("voice: Kokoro (natural)")
        else:
            print("voice: Kokoro NOT available — phone will use the robotic browser voice.\n"
                  "  fix: pip install kokoro soundfile  &&  brew install espeak-ng")
    from .mouth import WhisperEars
    if WhisperEars().available():
        print("ears: Whisper large-v3-turbo (mic dictation ready)")
    else:
        print("ears: faster-whisper not installed — mic off (pip install faster-whisper)")
    Handler.name, Handler.voice = args.name, args.voice
    srv = ThreadingHTTPServer((host, args.port), Handler)
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
