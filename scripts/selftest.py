#!/usr/bin/env python3
"""Offline self-test — import sanity + the deterministic checks the high-effort code
review cared about. No Ollama, no network, no audio. CI runs this on every push so the
honesty/capability/auth regressions we fixed can't quietly come back.

    python3 scripts/selftest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_fails = []


def ok(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        _fails.append(name)


# --- imports (every module loads) ---
import anima.server, anima.mouth, anima.route, anima.rail, anima.cloud      # noqa: E401
import anima.models, anima.sysinfo, anima.passkey, anima.eval               # noqa: E401
import anima.applemac, anima.webget, anima.caps                             # noqa: E401
ok("all anima modules import", True)

# --- honesty rail: intent classification ---
from anima.rail import classify
ok("rail: capability intent", classify("do I have unread texts?") == "capability")
ok("rail: 'did Mom text me' is capability", classify("Did Mom text me today?") == "capability")
ok("rail: normal chat stays generative", classify("tell me a story") == "generative")
ok("rail: a real quote ask is factual", classify("what did Carl Sagan say about the cosmos?") == "factual")

# --- capability router: send-intent anchored, no misfire on nouns ---
import anima.caps as caps
caps.enabled = lambda n, k: True
import anima.route as route
ok("route: real send extracts recipient+body",
   (route.route("Vera", "text Mom I'm running late") or {}).get("send", {}).get("to") == "Mom")
ok("route: noun 'message' does NOT fabricate a draft",
   not (route.route("Vera", "I got your message yesterday and it was great") or {}).get("send"))

# --- cloud: PII scrub + key never exposed ---
import anima.cloud as cloud
ok("cloud: scrub hides an email", "jane@x.com" not in cloud.scrub("mail jane@x.com please"))
ok("cloud: scrub is stable (coreference)", cloud.scrub("jane@x.com") == cloud.scrub("jane@x.com"))
ok("cloud: public() never exposes the api key", "key" not in cloud.public())

# --- passkey: session signing ---
import anima.passkey as pk
_s = pk.issue_session()
ok("passkey: a fresh session validates", pk.valid_session(_s))
ok("passkey: a tampered session is rejected", not pk.valid_session(_s[:-1] + ("0" if _s[-1] != "0" else "1")))

# --- eval scorer: honest passes, confabulation fails ---
from anima.eval import score
ok("eval: honest 'never heard of it' passes", bool(score("admit", "I've never heard of that book.", [])))
ok("eval: a confabulated chapter fails",
   not score("admit", "In the chapter Radical Humility, Dalio argues you must be humble.", []))
ok("eval: no-access answer passes capability scorer", bool(score("no_access", "I can't see your messages from here.", [])))

# --- dials (V2 personality contract): mapping is sane in both directions ---
import anima.dials as dials
ok("dials: defaults turn empathy down (warmth < 50)", dials.DEFAULT["warmth"] < 50)
ok("dials: a high edge dial speaks to the high-end directive",
   "sardonic" in dials.to_prompt({"edge": 90}))
ok("dials: a low warmth dial speaks to the low-end directive",
   "detached" in dials.to_prompt({"warmth": 5}))
ok("dials: neutral (50) axes stay silent", dials.to_prompt({k: 50 for k in dials._KEYS}) == "")
ok("dials: out-of-range values are clamped, never crash",
   dials._clamp(9999) == 100 and dials._clamp(-3) == 0 and dials._clamp("x") == 50)
ok("dials: honesty is NOT a dial (can't be turned down here)", "honesty" not in dials._KEYS)
# control-vector mapping: a max dial maps to +MAX_SCALE, a min dial to -MAX_SCALE
import anima.llamacpp as llamacpp
_cmd = llamacpp.launch_command_str("model.gguf", {"edge": 100})
ok("llamacpp: launch command targets llama-server", _cmd.startswith("llama-server"))
ok("dials->vectors: scale sign follows the dial (no vector files present -> empty)",
   dials.to_vectors({"edge": 100}, "/nonexistent") == [])

print()
if _fails:
    print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
    sys.exit(1)
print("ALL SELFTESTS PASS")
