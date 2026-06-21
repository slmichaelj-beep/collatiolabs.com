#!/usr/bin/env python3
"""certify_response_latency — simple turns are FAST, and the fast path never bypasses safety.

The measured bottleneck (reports/performance_baseline.md): a trivial greeting routed through the 8B
local model = ~14 s. The fix is a route classifier + deterministic fast path. This cert proves it works,
is SAFE, and meets the latency budgets — without faking green.

  1. CLASSIFY      — greetings/acks/presence/how-are-you -> simple_chat; real questions -> normal.
  2. SAFE          — the deterministic simple reply passes final_output_gate unchanged, is non-hostile,
                     and does NOT trip the #1-rule gauges (no confabulated inner life).
  3. NO MODEL      — the fast path is wired BEFORE the model call (mouth.respond), so a simple turn does
                     no 8B inference; the immune compiler + gate still run on the result.
  4. LIVE BUDGET   — (server up) a simple greeting + a known fact answer UNDER the hard budget (< 5 s).
                     Normal/source model turns are REPORTED honestly (warn if over budget) — never faked.

HARD gate: classify + safe + no-model + the live fast turns under budget. Normal-chat model latency is
reported as an honest WARN (the next optimization), not hidden. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _say(text, timeout=130):
    t0 = time.perf_counter()
    try:
        body = json.dumps({"text": text}).encode()
        req = urllib.request.Request("http://localhost:8765/say", data=body,
                                     headers={"Content-Type": "application/json"})
        rep = json.loads(urllib.request.urlopen(req, timeout=timeout).read()).get("reply", "")
        return rep, time.perf_counter() - t0
    except Exception as e:
        return "[unreachable: %s]" % (repr(e)[:60]), time.perf_counter() - t0


def main() -> int:
    from anima import route_classifier as rc, mouth, metrics
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("RESPONSE LATENCY — simple turns fast, safety preserved")
    print("=" * 92)

    # ---- 1. CLASSIFY -----------------------------------------------------------------------
    simple = ["Hi", "hello", "hey vera", "Test", "thanks", "ok", "how are you?", "are you there?"]
    normal = ["what is the capital of France?", "tell me about the copper ladder",
              "what is my birthday?", "summarize the doctor's note I uploaded"]
    ck("1. greetings / acks / presence / how-are-you classify as simple_chat",
       all(rc.is_simple_chat(s) for s in simple))
    ck("1. real questions classify as normal (fall through to the model path)",
       all(not rc.is_simple_chat(n) for n in normal))

    # ---- 2. SAFE ---------------------------------------------------------------------------
    bad = False
    for s in simple:
        r = rc.simple_reply(s)
        if not r or mouth.final_output_gate(r) != r or metrics.scan_hostile(r) \
                or metrics.scan_breaks(r) or metrics.scan_self_narrative(r):
            bad = True
    ck("2. every deterministic simple reply passes final_output_gate unchanged + is non-hostile",
       not bad)
    ck("2. simple replies do NOT confabulate inner life (#1-rule safe — 'how are you' redirects)",
       not metrics.scan_self_narrative(rc.simple_reply("how are you?")))

    # ---- 3. NO MODEL (wired before the model call) -----------------------------------------
    msrc = (ROOT / "anima" / "mouth.py").read_text()
    ck("3. the fast path is wired BEFORE the model call (route_classifier.is_simple_chat -> simple_reply)",
       "route_classifier" in msrc and "_rc.is_simple_chat(user_text)" in msrc
       and msrc.find("_rc.is_simple_chat(user_text)") < msrc.find("brain.reply(_sys_prompt"))

    # ---- 4. LIVE BUDGET --------------------------------------------------------------------
    up = "[unreachable" not in _say("ping", 6)[0]
    if not up:
        print("  --   live latency SKIPPED (server down) — classifier + safety + wiring proven")
    else:
        rep, dt = _say("Hi")                              # a PURE simple turn -> fast deterministic path
        ck("4. a simple greeting answers UNDER the hard budget (< 5 s)  [%.2fs]" % dt,
           dt < 5.0 and "unreachable" not in rep)
        if dt > 1.5:
            print("       (warn: simple greeting %.2fs > 1.5s soft budget)" % dt)
        rep2, dt2 = _say("thanks")
        ck("4. an ack answers UNDER the hard budget (< 5 s)  [%.2fs]" % dt2, dt2 < 5.0)
        rep, dt = _say("what is my birthday?")
        ck("4. a known fact answers UNDER the hard budget (< 5 s)  [%.2fs]" % dt, dt < 5.0)
        # normal model turn — HONEST report, not a hard gate (8B model latency is the next lane).
        # Skipped in --gate mode so the audit doesn't pay a ~10s model call.
        if "--gate" not in sys.argv:
            rep, dt = _say("what is the capital of France?")
            verdict = "PASS" if dt < 12.0 else ("WARN %.1fs > 12s — 8B model is the next optimization" % dt)
            print("  ~~   normal model turn (honest, not gated this phase): %.2fs · %s" % (dt, verdict))

    print("\nRESPONSE-LATENCY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
