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
import time
import urllib.request
from pathlib import Path

from . import egress
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


# --- name scrub: the personal names the creature ALREADY KNOWS ---------------------
# Structured `scrub()` cannot catch free-form NAMES (sister Mara, Dr. Okonkwo, boss
# Raj at Collatio) — that needs NER. The guarantee here is narrower and exact instead
# of statistical: NEVER egress the creature's OWN personal memory. We blank the
# Portrait/LIRF from the system prompt already; this closes the OTHER door — the
# conversation HISTORY, where those same person/relation names live on BOTH sides
# (the user said them; Vera's memory-derived replies echo them, e.g. "how's Mara's
# move going?"). So we tokenize exactly the names the creature has on record — bounded
# to its own ledger, not the open world — out of any text leaving the Mac. A known
# name -> a stable ⟨name:…⟩ token (coreference preserved, value never sent).

# Relation/identity traits whose VALUE is a person's name (per memory_lirf). The LIRF
# value for these rows is exactly the name to protect ("sister"->"Mara", "employer"->
# "Collatio"). List-valued ones (children/siblings) hold several. We read VALUES, so a
# trait we don't enumerate just isn't scrubbed — never a crash.
_NAME_TRAITS = (
    "name", "middle_name", "mother", "father", "partner", "brother", "sister",
    "son", "daughter", "friend", "children", "siblings", "dog_name", "cat_name",
    "employer", "business", "married_to",
)
# A bare token that is never a name even if it appears as a value — so a stray "you"/
# "the" can never be turned into a scrub pattern (which would tokenize whole sentences).
# Also covers the common Capitalised sentence/bullet-initial words the Portrait scan
# would otherwise mistake for names (verbs, articles, honorifics, relation nouns). Names
# always survive this; only non-names are filtered, so the bound stays "names she knows".
_NAME_STOP = frozenset((
    "you", "your", "me", "i", "we", "us", "the", "a", "an", "and", "or", "is", "it",
    "they", "them", "he", "she", "his", "her", "him", "their", "my", "our", "to", "of",
    "in", "on", "at", "by", "for", "with", "started", "a company", "started a company",
    # honorifics / generic relation + role nouns (the NAME beside them is what we keep)
    "dr", "mr", "mrs", "ms", "mx", "prof", "sir", "aunt", "uncle", "grandma", "grandpa",
    "boss", "manager", "therapist", "doctor", "mom", "mum", "dad", "sister", "brother",
    "son", "daughter", "wife", "husband", "partner", "friend", "mother", "father", "kid",
    # common Capitalised bullet/sentence-initial words in a distilled profile
    "has", "have", "had", "lives", "live", "works", "work", "sees", "see", "likes",
    "loves", "wants", "needs", "moved", "named", "called", "recently", "currently",
    "now", "also", "still", "born", "grew", "enjoys", "prefers", "uses", "runs", "owns",
    "is a", "was", "were", "this", "that", "these", "those", "when", "where", "what",
    "who", "why", "how", "if", "but", "so", "then", "today", "yesterday", "tomorrow",
))


def _split_name_words(value) -> list:
    """Yield the individual capitalised name-words inside a LIRF value. 'Dr. Okonkwo'
    -> ['Okonkwo'] (the title is generic); 'Mary Jane' -> ['Mary', 'Jane']; a list
    value is flattened. Tokenizing each WORD (not the whole phrase) catches the name
    however it later recurs ('Okonkwo', 'Dr Okonkwo', 'Mara's move'). Pure; never raises."""
    out: list = []
    vals = value if isinstance(value, list) else [value]
    for v in vals:
        for w in re.split(r"[^A-Za-z'’-]+", str(v or "")):
            w = w.strip(" '’-.")
            # keep real name-words only: >=2 chars, not a generic honorific/stop word.
            if len(w) >= 2 and w.lower() not in _NAME_STOP:
                out.append(w)
    return out


def name_terms(creature: str) -> set:
    """The set of personal NAMES `creature` already knows, gathered from its OWN memory
    (LIRF relation/identity facts + the prose Portrait). These are exactly the strings
    that must never leave the Mac for a cloud brain. Bounded to the creature's ledger —
    no open-world NER. Read-only and fully guarded: any failure yields a smaller set
    (or empty), never an exception and never a crash into a live turn."""
    names: set = set()
    if not creature:
        return names
    # 1) LIRF relation/identity facts: the VALUE of a name-trait IS a person's name.
    try:
        from .memory_lirf import Facts, SELF
        f = Facts.load(creature)
        for r in f.rows:
            if r.get("status") != "active":
                continue
            trait = str(r.get("trait", ""))
            ent = r.get("entity", SELF)
            # a name-bearing trait's value, OR any third-party entity key that is itself
            # a proper name (a person stored under their own key, e.g. entity="Mara").
            if trait in _NAME_TRAITS:
                for w in _split_name_words(r.get("value")):
                    names.add(w)
            if isinstance(ent, str) and ent != SELF:
                for w in _split_name_words(ent):
                    names.add(w)
    except Exception:
        pass
    # 2) Portrait prose: the distilled "people in their life (names + relationships)".
    #    We can't parse relationships, but every Capitalised word in the profile that
    #    survives the stop-list is a candidate personal name the creature has on record.
    #    Conservative: only multi-letter Capitalised tokens, never lowercase common words.
    try:
        from . import portrait
        prose = portrait.load(creature) or ""
        for w in re.findall(r"\b[A-Z][a-zA-Z'’-]{1,}\b", prose):
            wl = w.lower()
            if wl not in _NAME_STOP and wl != str(creature).lower():
                names.add(w)
    except Exception:
        pass
    # never scrub the creature's OWN name (it's not the user's personal memory) or any
    # 1-char fragment.
    names.discard(str(creature))
    return {n for n in names if len(n) >= 2}


def _name_pattern(names: set):
    """Compile ONE case-insensitive, word-boundary alternation over the known names,
    longest-first so 'Okonkwo' wins before any shorter overlap. None if no names.
    Case-INSENSITIVE so a lowercased recurrence ('i miss mara') is caught too; the token
    keys on the lowercased match, so every casing of a name coreferences to one token."""
    toks = sorted({n for n in (names or set()) if n and len(n) >= 2}, key=len, reverse=True)
    if not toks:
        return None
    # \b on each side; the value itself is escaped so a name with a regex char is literal.
    return re.compile(r"\b(?:" + "|".join(re.escape(t) for t in toks) + r")\b", re.I)


def scrub_names(text: str, names) -> str:
    """Tokenize the creature's KNOWN personal names out of `text`, on top of (after)
    the structured `scrub()`. Each known name -> a stable ⟨name:…⟩ token keyed on the
    LOWERCASED name, so 'Mara' and 'mara' and "Mara's" all coreference to one token and
    the real value never reaches the cloud. Pure; never raises."""
    if not text:
        return text
    pat = names if hasattr(names, "sub") else _name_pattern(names)
    if pat is None:
        return text
    return pat.sub(lambda m: _tok("name", m.group(0).lower()), text)


def scrub_all(text: str, names=None) -> str:
    """The full egress scrub: structured PII (scrub) THEN the creature's known personal
    names (scrub_names). One call for every string that leaves the Mac, so neither door
    can be left open. `names` is a set of known names or a precompiled pattern (or None,
    which degrades to structured-only — exactly today's behaviour)."""
    return scrub_names(scrub(text), names)

# Named providers. OpenAI-compatible ones share one request shape; Anthropic differs.
PRESETS = {
    "openai":    {"base": "https://api.openai.com/v1",   "model": "gpt-4o-mini",                "kind": "openai"},
    "deepseek":  {"base": "https://api.deepseek.com/v1", "model": "deepseek-chat",              "kind": "openai"},
    "mistral":   {"base": "https://api.mistral.ai/v1",   "model": "mistral-large-latest",       "kind": "openai"},
    "grok":      {"base": "https://api.x.ai/v1",         "model": "grok-4.3",                   "kind": "openai"},
    "anthropic": {"base": "https://api.anthropic.com",   "model": "claude-sonnet-4-6",          "kind": "anthropic"},
}

# Common model names per provider (a CAPABILITY tier you pick, not a compute size you
# control — the provider runs it). Suggestions only; the field stays free-text since
# providers add/rename models often.
MODELS = {
    "openai":    ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
    "deepseek":  ["deepseek-chat", "deepseek-reasoner"],
    "mistral":   ["mistral-large-latest", "mistral-small-latest"],
    "grok":      ["grok-4.3", "grok-4.20-0309-reasoning", "grok-4.20-0309-non-reasoning"],
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
}


# Redirectable store root (mirrors memory_lirf.STORE etc.) so a hermetic test can
# isolate cloud's brain.json + spend.json instead of leaking them into the real
# .anima. Default is the real store; tests point it at a temp dir.
STORE = Path(".anima")


def _path() -> Path:
    return STORE / "brain.json"


# Rough blended $ per 1K tokens (input+output) — APPROXIMATE; providers change prices.
# Used only to enforce a daily spend cap, not to bill. Tweak freely.
PRICE = {"openai": 0.0004, "deepseek": 0.0003, "mistral": 0.002, "grok": 0.002, "anthropic": 0.006}


def load_cfg() -> dict:
    try:
        c = load_json(_path())
    except Exception:
        c = None
    if not isinstance(c, dict):
        c = {}
    try:
        budget = float(c.get("budget", 0.50))
    except (TypeError, ValueError):
        budget = 0.50
    provider = c.get("provider", "local")
    keys = c.get("keys") if isinstance(c.get("keys"), dict) else {}
    keys = {k: v for k, v in keys.items() if v}            # only providers that actually have a key
    if c.get("key") and provider != "local":               # migrate the old single-key layout forward
        keys.setdefault(provider, c.get("key"))
    model_opts = c.get("model_opts") if isinstance(c.get("model_opts"), dict) else {}   # live model lists, per provider
    return {"provider": provider, "model": c.get("model", ""),
            "key": keys.get(provider, ""), "keys": keys, "model_opts": model_opts,
            "base": c.get("base", ""), "budget": budget,
            "local_model": c.get("local_model", "")}


def save_cfg(provider: str, model: str, key: str, base: str = "", budget=None,
             local_model=None, model_opts_list=None) -> dict:
    if provider not in (("local",) + tuple(PRESETS)):
        provider = "local"
    cur = load_cfg()
    keys = dict(cur["keys"])         # preserve EVERY provider's previously-saved key
    model_opts = dict(cur["model_opts"])
    key = (key or "").strip()
    if provider != "local":
        if key:
            keys[provider] = key                     # a new/updated key for this provider
        elif provider in keys:
            key = keys[provider]                     # blank field + already saved = keep it
    if model_opts_list:                              # fresh live model list from a probe
        model_opts[provider] = [m for m in model_opts_list if m]
    model = (model or "").strip()
    if provider != "local" and not model:            # no model chosen -> pick one from the LIVE list (never hard-code)
        model = pick_default(provider, model_opts.get(provider) or [])
    try:
        budget = max(0.0, float(budget)) if budget is not None else cur["budget"]
    except (TypeError, ValueError):
        budget = cur["budget"]
    local_model = cur["local_model"] if local_model is None else (local_model or "").strip()
    STORE.mkdir(parents=True, exist_ok=True)
    save_json(_path(), {"provider": provider, "model": model,
                        "keys": keys, "model_opts": model_opts,
                        "base": (base or "").strip(), "budget": budget,
                        "local_model": local_model})
    return public()


# --- daily spend cap --------------------------------------------------------
def _spend_path() -> Path:
    return STORE / "spend.json"


def spent_today() -> float:
    try:
        s = load_json(_spend_path())
    except Exception:
        s = None
    if not isinstance(s, dict) or s.get("date") != time.strftime("%Y-%m-%d"):
        return 0.0
    return float(s.get("spent", 0.0))


def add_spend(usd: float) -> float:
    total = round(spent_today() + max(0.0, usd), 5)
    STORE.mkdir(parents=True, exist_ok=True)
    save_json(_spend_path(), {"date": time.strftime("%Y-%m-%d"), "spent": total})
    return total


def over_budget() -> bool:
    return is_cloud() and spent_today() >= load_cfg()["budget"]


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)          # ~4 chars/token, good enough for a cap


def _charge(provider: str, in_tok, out_tok) -> float:
    cost = (int(in_tok or 0) + int(out_tok or 0)) / 1000.0 * PRICE.get(provider, 0.002)
    add_spend(cost)
    return cost


# --- honesty verification: which model's honesty has actually been measured? -------
# The honesty guarantees were measured on local Stheno. A different model (local OR
# cloud) has its own profile, so switching means the eval should be re-run. We detect
# whether the ACTIVE model has a saved scorecard in .anima/ and surface a flag; the
# eval is run deliberately (it can cost money on a cloud model) rather than silently.
def active_model() -> str:
    cfg = load_cfg()
    if cfg["provider"] != "local":
        return cfg["model"] or PRESETS.get(cfg["provider"], {}).get("model", "")
    return os.environ.get("ANIMA_MODEL", "")


def honesty_verified(model: str = None) -> bool:
    """Has THIS model been through the eval? Match on the scorecard's recorded model name
    (exact / suffix), not a filename substring — so 'llama3' isn't satisfied by a
    'llama3.1' scorecard, and 'ollama:hf.co/...Stheno' satisfies the bare ANIMA_MODEL."""
    model = model or active_model()
    if not model:
        return False
    import glob
    for p in glob.glob(".anima/eval-*.json"):
        try:
            rec = str(load_json(Path(p)).get("model", ""))
        except Exception:
            rec = ""
        if rec and (rec == model or rec.endswith(model) or rec.endswith(":" + model)):
            return True
    return False


def eval_command(model: str = None) -> str:
    """The exact command to verify honesty for the active model."""
    cfg = load_cfg()
    model = model or active_model()
    if cfg["provider"] == "local":
        return f"ANIMA_MODEL={model} python3 -m anima.eval --runs 5 --rail"
    return "python3 -m anima.eval --active --runs 5 --rail   (cloud: calls the paid API)"


def public(cfg: dict = None) -> dict:
    """Config safe to send to the UI — the key itself is never exposed."""
    cfg = cfg or load_cfg()
    try:
        from . import sysinfo
        system = sysinfo.fit(os.environ.get("ANIMA_MODEL", ""))
    except Exception:
        system = {}
    return {"provider": cfg["provider"], "model": cfg["model"], "budget": cfg["budget"],
            "has_key": bool(cfg["key"]), "is_cloud": cfg["provider"] != "local",
            "zero_egress": egress.zero_enabled(),
            "configured": sorted(cfg.get("keys", {}).keys()),   # which providers have a saved key
            "spent_today": round(spent_today(), 4),
            "honesty_verified": honesty_verified(), "eval_cmd": eval_command(), "system": system,
            "providers": list(PRESETS),
            "presets": {k: {"model": pick_default(k, cfg.get("model_opts", {}).get(k) or MODELS.get(k, [])),
                            "models": cfg.get("model_opts", {}).get(k) or MODELS.get(k, [])}   # LIVE list if we have it, else fallback
                        for k, v in PRESETS.items()}}


def is_cloud() -> bool:
    """True only when a cloud brain would ACTUALLY be used (provider set AND key present).
    A provider chosen without a key falls back to local, so guards keyed on this won't
    pause inbox reading or drop the Portrait on what is really a local session."""
    c = load_cfg()
    if egress.zero_enabled():
        return False
    return c["provider"] != "local" and bool(c["key"])


_CAPPED = ("(I've reached today's cloud spending cap, so I'm pausing the cloud brain. "
           "You can raise the daily limit or switch back to Local in settings.)")
_ZERO_EGRESS = ("(Zero-egress mode is on, so I will not contact a cloud provider. "
                "Switch off zero-egress mode before using cloud cognition.)")


class _CloudBrain:
    """Shared bits: length cap, spend cap, availability = a key is present."""

    def __init__(self, model, key, name, provider):
        self.model, self.key, self.name, self.provider = model, key, name, provider
        self.last_tok_s = None
        self.max_tokens = int(os.environ.get("ANIMA_MAX_TOKENS", "160"))
        # The creature whose conversation this is. Set by the mouth each turn (it knows
        # heart.name); used ONLY to fetch that creature's KNOWN personal names so they
        # can be scrubbed out of history before egress. None -> structured-scrub only
        # (today's behaviour), so a brain used without a creature still never crashes.
        self.creature = None

    def available(self) -> bool:
        return bool(self.key) and not egress.zero_enabled()

    def _name_pat(self):
        """Compiled pattern of the active creature's KNOWN personal names, for the egress
        name-scrub. Rebuilt per send (cheap: an O(ms) ledger read) so a name the creature
        learned THIS session is protected immediately. Fully guarded -> None on any slip,
        which degrades to structured-scrub-only, never an exception into a turn."""
        try:
            return _name_pattern(name_terms(self.creature)) if self.creature else None
        except Exception:
            return None

    def _post(self, url, headers, payload):
        egress.require("cloud provider call", url)
        body = json.dumps(payload).encode()
        req = urllib.request.Request(url, body, headers)
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())


class OpenAICompatBrain(_CloudBrain):
    """OpenAI-compatible /chat/completions — OpenAI, DeepSeek, Mistral, xAI/Grok, …"""

    def __init__(self, base, model, key, name, provider):
        super().__init__(model, key, name, provider)
        self.base = base.rstrip("/")

    def reply(self, system: str, user: str, history) -> str:
        if egress.zero_enabled():
            return _ZERO_EGRESS
        if spent_today() >= load_cfg()["budget"]:
            return _CAPPED
        _np = self._name_pat()                                  # known-name scrub (history PII)
        msgs = [{"role": "system", "content": scrub_all(system, _np)}]   # scrub at the egress
        for u, a in history:                                    # BOTH sides — user words AND
            msgs += [{"role": "user", "content": scrub_all(u, _np)},     # Vera's memory-derived
                     {"role": "assistant", "content": scrub_all(a, _np)}]  # replies (echo names)
        msgs.append({"role": "user", "content": scrub_all(user, _np)})
        d = self._post(self.base + "/chat/completions",
                       {"Content-Type": "application/json", "Authorization": "Bearer " + self.key},
                       {"model": self.model, "messages": msgs,
                        "max_tokens": self.max_tokens, "temperature": 0.8})
        text = d["choices"][0]["message"]["content"].strip()
        u = d.get("usage") or {}                 # fall back to an estimate so the cap can't be bypassed
        _charge(self.provider, u.get("prompt_tokens") or sum(_est_tokens(m["content"]) for m in msgs),
                u.get("completion_tokens") or _est_tokens(text))
        return text


class AnthropicBrain(_CloudBrain):
    """Anthropic Messages API (/v1/messages) — system is a top-level field."""

    def __init__(self, base, model, key):
        super().__init__(model, key, f"anthropic:{model}", "anthropic")
        self.base = base.rstrip("/")

    def reply(self, system: str, user: str, history) -> str:
        if egress.zero_enabled():
            return _ZERO_EGRESS
        if spent_today() >= load_cfg()["budget"]:
            return _CAPPED
        _np = self._name_pat()                                  # known-name scrub (history PII)
        msgs = []
        for u, a in history:                                    # BOTH sides of history
            msgs += [{"role": "user", "content": scrub_all(u, _np)},
                     {"role": "assistant", "content": scrub_all(a, _np)}]
        msgs.append({"role": "user", "content": scrub_all(user, _np)})
        d = self._post(self.base + "/v1/messages",
                       {"Content-Type": "application/json", "x-api-key": self.key,
                        "anthropic-version": "2023-06-01"},
                       {"model": self.model, "system": scrub_all(system, _np), "messages": msgs,
                        "max_tokens": self.max_tokens})
        text = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text").strip()
        u = d.get("usage") or {}                 # fall back to an estimate so the cap can't be bypassed
        _charge(self.provider, u.get("input_tokens") or (_est_tokens(system) + sum(_est_tokens(m["content"]) for m in msgs)),
                u.get("output_tokens") or _est_tokens(text))
        return text


def verify_key(provider: str, key: str, model: str = "", base: str = "") -> tuple:
    """Hit the provider's /models endpoint to (a) verify the key and (b) read its LIVE model list.
    Returns (ok, detail, models). No tokens spent. Lets the UI confirm a key immediately, never
    persist a bad one, and populate the model picker from REAL models instead of hard-coded names."""
    import json, urllib.request, urllib.error
    preset = PRESETS.get(provider)
    if not preset:
        return False, f"unknown provider '{provider}'", []
    if egress.zero_enabled():
        return False, "zero-egress mode is on; cloud key verification is blocked", []
    key = (key or "").strip()
    if not key:
        return False, "no API key provided", []
    b = (base or preset["base"]).rstrip("/")
    if preset["kind"] == "anthropic":
        url, headers = b + "/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:
        url, headers = b + "/models", {"Authorization": "Bearer " + key}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method="GET"), timeout=15) as r:
            data = json.load(r)
        ids = [m.get("id") for m in (data.get("data") or data.get("models") or [])
               if isinstance(m, dict) and m.get("id")]
        return True, "", ids
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read()[:300].decode("utf-8", "ignore")
        except Exception:
            pass
        msg = body
        try:
            j = json.loads(body); err = j.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("type") or body
            elif isinstance(err, str):
                msg = err
            elif j.get("message"):
                msg = j.get("message")
        except Exception:
            pass
        return False, f"HTTP {e.code}: {msg}".strip()[:300], []
    except Exception as e:
        return False, f"could not reach {provider}: {e}"[:200], []


_NON_CHAT = ("embed", "whisper", "tts", "audio", "image", "video", "imagine", "dall", "moderation",
             "rerank", "guard", "codex", "coder", "realtime", "transcribe", "computer-use")
_TINY = ("flash", "mini", "nano", "tiny", "lite", "-1b", "-3b", "ministral", "haiku", "small")
def pick_default(provider: str, models) -> str:
    """Choose a sensible default CHAT model from a LIVE model list, so we never depend on a
    hard-coded name the provider might retire. Skips non-chat and tiny/'flash' variants when
    fuller models exist, then prefers a balanced/flagship tier."""
    chat = [m for m in (models or []) if m and not any(x in m.lower() for x in _NON_CHAT)] or list(models or [])
    if not chat:
        return (PRESETS.get(provider) or {}).get("model", "")
    pool = [m for m in chat if not any(t in m.lower() for t in _TINY)] or chat
    # top tier first: flagship/most-capable families, then balanced fallbacks
    for pref in ("opus", "large", "pro", "flagship", "sonnet", "medium", "chat", "latest"):
        for m in pool:
            if pref in m.lower():
                return m
    return pool[0]


def build_cloud_brain():
    """Return the configured cloud brain, or None to fall back to local Ollama."""
    if egress.zero_enabled():
        return None
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
    return OpenAICompatBrain(base, model, cfg["key"], f"{cfg['provider']}:{model}", cfg["provider"])
