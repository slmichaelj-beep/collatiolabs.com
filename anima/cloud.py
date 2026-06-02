"""cloud — optional cloud brains (opt-in). The default mouth stays LOCAL and private.

The whole project is local-first: nothing leaves the Mac. A cloud brain is a
deliberate, off-by-default choice — when one is active the conversation is sent to
that provider. To keep that honest, two guardrails live alongside this module:

  1. The default is always "local" (Ollama). Cloud is only used if explicitly set.
  2. PRIVACY GUARD: when a cloud brain is active, the capability router (route.py)
     PAUSES message/mail reading, so your private inbox is never pulled into the
     cloud stream. The user's own typed words still go (that's inherent to chatting
     with a cloud model), but their unread texts do not.

The API key is stored under .anima/ like everything else — encrypted at rest if
ANIMA_KEY is set, otherwise plaintext on your own machine.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from .util import load_json, save_json

# --- PII scrub: hash structured PII before anything leaves the Mac for the cloud ----
# Each match becomes a stable, non-reversible token (same value -> same token, so the
# model keeps coreference without ever seeing the real value). Honest limit: regex
# reliably catches STRUCTURED PII (emails, phones, SSNs, cards, IPs). Free-form names
# need an NER model — instead we DON'T send her personal memory (Portrait) to the
# cloud at all, and inbox reading is paused, so the big name sources never go out.
def _tok(kind, s):
    return f"⟨{kind}:{hashlib.sha256(s.encode()).hexdigest()[:6]}⟩"

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\-.\s()]{7,}\d(?![\w.])")


def scrub(text: str) -> str:
    """Replace structured PII with stable hash tokens. Over-redacts rather than leak."""
    if not text:
        return text
    text = _EMAIL.sub(lambda m: _tok("email", m.group(0)), text)
    text = _SSN.sub(lambda m: _tok("ssn", m.group(0)), text)
    text = _CARD.sub(lambda m: _tok("card", m.group(0)) if sum(c.isdigit() for c in m.group(0)) >= 13 else m.group(0), text)
    text = _PHONE.sub(lambda m: _tok("phone", m.group(0)) if sum(c.isdigit() for c in m.group(0)) >= 10 else m.group(0), text)
    text = _IP.sub(lambda m: _tok("ip", m.group(0)), text)
    return text

# Named providers. OpenAI-compatible ones share one request shape; Anthropic differs.
PRESETS = {
    "openai":    {"base": "https://api.openai.com/v1",   "model": "gpt-4o-mini",                "kind": "openai"},
    "deepseek":  {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat",              "kind": "openai"},
    "mistral":   {"base": "https://api.mistral.ai/v1",   "model": "mistral-large-latest",       "kind": "openai"},
    "grok":      {"base": "https://api.x.ai/v1",         "model": "grok-2-latest",              "kind": "openai"},
    "anthropic": {"base": "https://api.anthropic.com",   "model": "claude-3-5-sonnet-latest",   "kind": "anthropic"},
}


def _path() -> Path:
    return Path(".anima") / "brain.json"


def load_cfg() -> dict:
    try:
        c = load_json(_path())
    except Exception:
        c = None
    if not isinstance(c, dict):
        c = {}
    return {"provider": c.get("provider", "local"), "model": c.get("model", ""),
            "key": c.get("key", ""), "base": c.get("base", "")}


def save_cfg(provider: str, model: str, key: str, base: str = "") -> dict:
    if provider not in (("local",) + tuple(PRESETS)):
        provider = "local"
    cur = load_cfg()
    key = (key or "").strip()
    if not key and provider == cur["provider"]:
        key = cur["key"]            # blank key + same provider = keep the existing one (UI never sees it)
    Path(".anima").mkdir(exist_ok=True)
    save_json(_path(), {"provider": provider, "model": (model or "").strip(),
                        "key": key, "base": (base or "").strip()})
    return public()


def public(cfg: dict = None) -> dict:
    """Config safe to send to the UI — the key itself is never exposed."""
    cfg = cfg or load_cfg()
    return {"provider": cfg["provider"], "model": cfg["model"],
            "has_key": bool(cfg["key"]), "is_cloud": cfg["provider"] != "local",
            "providers": list(PRESETS), "presets": {k: {"model": v["model"]} for k, v in PRESETS.items()}}


def is_cloud() -> bool:
    return load_cfg()["provider"] != "local"


class _CloudBrain:
    """Shared bits: length cap, timing field, availability = a key is present."""

    def __init__(self, model, key, name):
        self.model, self.key, self.name = model, key, name
        self.last_tok_s = None
        self.max_tokens = int(os.environ.get("ANIMA_MAX_TOKENS", "160"))

    def available(self) -> bool:
        return bool(self.key)

    def _post(self, url, headers, payload):
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, body, headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())


class OpenAICompatBrain(_CloudBrain):
    """OpenAI-compatible /chat/completions — OpenAI, DeepSeek, Mistral, xAI/Grok, …"""

    def __init__(self, base, model, key, name):
        super().__init__(model, key, name)
        self.base = base.rstrip("/")

    def reply(self, system: str, user: str, history) -> str:
        msgs = [{"role": "system", "content": scrub(system)}]   # scrub at the egress
        for u, a in history:
            msgs += [{"role": "user", "content": scrub(u)}, {"role": "assistant", "content": scrub(a)}]
        msgs.append({"role": "user", "content": scrub(user)})
        d = self._post(self.base + "/chat/completions",
                       {"Content-Type": "application/json", "Authorization": "Bearer " + self.key},
                       {"model": self.model, "messages": msgs,
                        "max_tokens": self.max_tokens, "temperature": 0.8})
        return d["choices"][0]["message"]["content"].strip()


class AnthropicBrain(_CloudBrain):
    """Anthropic Messages API (/v1/messages) — system is a top-level field."""

    def __init__(self, base, model, key):
        super().__init__(model, key, f"anthropic:{model}")
        self.base = base.rstrip("/")

    def reply(self, system: str, user: str, history) -> str:
        msgs = []
        for u, a in history:
            msgs += [{"role": "user", "content": scrub(u)}, {"role": "assistant", "content": scrub(a)}]
        msgs.append({"role": "user", "content": scrub(user)})
        d = self._post(self.base + "/v1/messages",
                       {"Content-Type": "application/json", "x-api-key": self.key,
                        "anthropic-version": "2023-06-01"},
                       {"model": self.model, "system": scrub(system), "messages": msgs,
                        "max_tokens": self.max_tokens})
        return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()


def build_cloud_brain():
    """Return the configured cloud brain, or None to fall back to local Ollama."""
    cfg = load_cfg()
    if cfg["provider"] == "local":
        return None
    preset = PRESETS.get(cfg["provider"])
    if not preset or not cfg["key"]:
        return None
    base = cfg["base"] or preset["base"]
    model = cfg["model"] or preset["model"]
    if preset["kind"] == "anthropic":
        return AnthropicBrain(base, model, cfg["key"])
    return OpenAICompatBrain(base, model, cfg["key"], f"{cfg['provider']}:{model}")
