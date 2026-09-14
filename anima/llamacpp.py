"""
The llama.cpp brain — the V2 "mouth" that can be steered by control vectors.

Why a second backend: Ollama is great for plain chat, but it doesn't expose
llama.cpp's control-vector knob. llama.cpp's server does. A control vector is a
direction in the model's hidden state that embodies one personality axis (warmth,
edge, …); adding it to the residual stream nudges *how* she speaks beneath the
level of words. The vectors are generated per-model by scripts/make_vectors.py and
mapped from the dials by anima/dials.to_vectors().

Honest constraint: llama.cpp applies control vectors at MODEL-LOAD time (they're
passed to llama-server on startup as `--control-vector-scaled FILE SCALE`). So
"moving a slider" re-launches llama-server with new scales — a few-second reload,
not a per-token change. Live, instant feedback still comes from the prompt path
(dials.to_prompt); the vectors are the deeper layer applied when you commit a
setting. The dials are the single source of truth either way.

This brain speaks llama-server's OpenAI-compatible endpoint, so it is a drop-in
for OllamaBrain: same reply(system, user, history) signature.
"""

from __future__ import annotations

import json
import os
import shlex
import urllib.request

DEFAULT_HOST = "http://localhost:8080"
# Where per-model control vectors live (one .gguf per axis). Configurable so the
# big files can sit on an external drive alongside the models.
VECTOR_DIR = os.environ.get("ANIMA_VECTOR_DIR", str(os.path.join(".anima", "vectors")))


class LlamaCppBrain:
    """Local LLM via llama.cpp's server (`llama-server`). Steerable by control
    vectors loaded at server start. Falls back gracefully if the server is down."""

    def __init__(self, host=None, model="local", temperature=0.8):
        self.host = (host or os.environ.get("ANIMA_LLAMACPP_HOST", DEFAULT_HOST)).rstrip("/")
        self.model = model
        self.temperature = temperature
        self.name = f"llamacpp:{self.host}"
        self.max_tokens = int(os.environ.get("ANIMA_MAX_TOKENS", "160"))
        self.last_tok_s = None

    def available(self) -> bool:
        try:
            urllib.request.urlopen(self.host + "/health", timeout=2)
            return True
        except Exception:
            try:
                urllib.request.urlopen(self.host + "/v1/models", timeout=2)
                return True
            except Exception:
                return False

    def warm(self):
        # llama-server holds the model resident already; a 1-token ping avoids any
        # first-call lazy init and confirms reachability.
        try:
            self.reply("", "hi", [])
        except Exception:
            pass

    def reply(self, system: str, user: str, history) -> str:
        import time
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        for u, a in (history or []):
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": user})
        body = json.dumps({"model": self.model, "messages": msgs, "stream": False,
                           "temperature": self.temperature,
                           "max_tokens": self.max_tokens}).encode()
        req = urllib.request.Request(self.host + "/v1/chat/completions", body,
                                     {"Content-Type": "application/json"})
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
        dt = time.perf_counter() - t0
        usage = data.get("usage") or {}
        ct = usage.get("completion_tokens")
        self.last_tok_s = (ct / dt) if (ct and dt > 0) else None
        return data["choices"][0]["message"]["content"].strip()


def launch_command(model_path: str, dials: dict, *, host_port=8080,
                   vector_dir=VECTOR_DIR, extra=()):
    """Build the `llama-server` command line that loads `model_path` with the
    control vectors implied by the current dials. Pure string assembly (no model
    needed) so it is unit-testable; the model manager runs it on the Mac.

    Re-call this and relaunch whenever a dial is committed."""
    from . import dials as _dials
    cmd = ["llama-server", "-m", model_path,
           "--host", "127.0.0.1", "--port", str(host_port),
           "-c", os.environ.get("ANIMA_CTX", "8192")]
    for vp, scale in _dials.to_vectors(dials, vector_dir):
        cmd += ["--control-vector-scaled", vp, f"{scale:.3f}"]
    cmd += list(extra)
    return cmd


def launch_command_str(model_path: str, dials: dict, **kw) -> str:
    return " ".join(shlex.quote(c) for c in launch_command(model_path, dials, **kw))
