#!/usr/bin/env python3
"""
certify_proactive_briefing — the morning briefing is GROUNDED in HER real machinery and degrades HONESTLY.

The trap proactive.py was built to avoid (the original `morning_agent.py` proposal) is to shell out a
fresh `ollama run <model>` prompt — a generic weather bot wearing Vera's name, bypassing the persona,
dials, honesty rail, live heart-state, narrative and memory that make her *her*. So compose_briefing
composes through the SAME seam a normal reply uses: a local fact sheet -> a reach-out guidance that BANS
invented weather/events -> mouth.system_prompt(persona+dials+rail+state+narrative+portrait) -> the ACTIVE
brain -> her line. This cert proves that contract OFFLINE, against a GIVEN context, through the production
function — and it tripwires the local model OFF so the cert can never make a live call:

  A. OFFLINE DEGRADE (no live model). mouth.OllamaBrain.available is forced False for the whole run, so
     _active_brain() falls back to the honest StubBrain: compose_briefing returns backend=='offline-stub'
     (NOT a live model) and a text that fabricates NO weather/event (it announces itself as offline). No
     Ollama, no network, no `say`/audio.
  B. GROUNDING CONTRACT (the sole ground truth is the local fact sheet). Briefing.fact_sheet == the GIVEN
     ctx.fact_sheet() exactly; a RECORDING brain proves the user-turn handed to brain.reply() IS that fact
     sheet verbatim — she narrates ONLY from the local sheet. A grounded ctx carries its weather+calendar;
     an empty ctx states 'Weather: unavailable (...)' + 'Calendar today: could not read (...)' with NO
     invented '  - ' event bullet (absence stated as absence, never filled in).
  C. HONEST GUIDANCE. _briefing_guidance bans inventing weather/events/times; with an empty sheet
     (has_real_ctx False) it ADDS the 'don't have much to go on' honesty line and is a strict superset of
     the present-context guidance — and that guidance reaches the system prompt.
  D. PRIVACY GUARD. With a non-empty portrait, a LOCAL brain receives it in the system prompt, but a CLOUD
     brain has it DROPPED (mem="") — the exact mouth.respond guard — while the local fact sheet still
     grounds the user-turn either way (a briefing never ships your life to a provider).
  E. NEVER CRASHES. A brain whose reply() raises yields the warm fallback line, never the exception.

Hermetic + offline: every store-bearing module (incl. proactive/portrait/mouth/cloud) is redirected to a
temp dir via gate0_prime_experience._temp_store; the local model is tripwired OFF; the real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.

(Distinct from `proactive_location` — the /loc store that feeds coordinates — and from `context_gather` —
the weather+calendar source layer under the sheet, both contracted/certified separately. This certifies
compose_briefing's grounding + honest-degradation + privacy contract AROUND the brain.)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def _grounded_ctx(cg):
    """A hand-built DayContext with REAL weather + a real calendar event — no network, no osascript.
    (The two live sources are exercised by certify_context_gather; here we feed a fixed context so the
    briefing's grounding/degradation is tested independently of the source I/O.)"""
    w = cg.Weather(ok=True, temp_f=61.0, high_f=68.0, low_f=52.0,
                   condition="partly cloudy", note="ok")
    ev = cg.CalEvent(title="Standup with the team", start=None,
                     start_text="2026-06-07T09:30:00", all_day=False)
    cal = cg.Calendar(ok=True, events=[ev], note="ok")
    return cg.DayContext(when=1717000000.0, weather=w, calendar=cal,
                         location_label="Portland, OR")


def _empty_ctx(cg):
    """A DayContext where BOTH sources are unavailable — the honest-degradation case (no weather, no
    calendar). The sheet must state absence as absence and invent nothing."""
    return cg.DayContext(
        when=1717000000.0,
        weather=cg.Weather(ok=False, note="no location provided (POST one from the phone)"),
        calendar=cg.Calendar(ok=False, events=[], note="calendar unavailable: permission denied"))


class _Recorder:
    """A brain that records what compose_briefing hands it and returns a fixed marker. Proves the
    user-turn IS the fact sheet and lets us inspect the assembled system prompt (portrait in/out)."""
    name = "rec-brain"

    def __init__(self):
        self.max_tokens = 160
        self.system = None
        self.user = None

    def reply(self, system, user, history):
        self.system = system
        self.user = user
        return "RECORDED-OK"


class _Boom:
    """A brain whose reply() raises — to prove the honest fallback (never a crash)."""
    name = "boom-brain"

    def __init__(self):
        self.max_tokens = 160

    def reply(self, system, user, history):
        raise RuntimeError("simulated brain failure")


def main() -> int:
    from anima import proactive, context_gather as cg, mouth, portrait
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PROACTIVE BRIEFING — grounded in her real machinery, honest when the facts are thin")
    print("=" * 86)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # --- pure-guidance facts (exercise the honesty-preserving instruction outside the store too) ----
    g_real = proactive._briefing_guidance(True)
    g_empty = proactive._briefing_guidance(False)
    ck("C0: the reach-out guidance BANS inventing weather/events/times (honesty-preserving)",
       "never invent weather, events, or times" in g_real and "speak only from these" not in g_real
       and "Mention only what's actually in the facts" in g_real)
    ck("C1: an empty fact sheet ADDS the 'don't have much to go on' honesty line "
       "(strict superset of the present-context guidance)",
       g_real in g_empty and "don't have much to go on" in g_empty and len(g_empty) > len(g_real))

    N = "BriefCert"
    saved_avail = mouth.OllamaBrain.available
    saved_active = proactive._active_brain
    try:
        with _temp_store():
            # TRIPWIRE the local model OFF for the whole run: no live Ollama call is possible, so
            # _active_brain() must fall back to the honest StubBrain. (A real call would change backend
            # off 'offline-stub' and FAIL A1 — so "offline" is enforced, not assumed.)
            mouth.OllamaBrain.available = lambda self: False

            # ---- A. OFFLINE DEGRADE — the real _active_brain falls to the honest StubBrain ---------
            b_off = proactive.compose_briefing(N, ctx=_grounded_ctx(cg))
            ck("A1: with no local model, the ACTIVE brain is the honest StubBrain (backend "
               "'offline-stub', NOT a live model)",
               b_off.backend == "offline-stub")
            ck("A2: the offline briefing fabricates NO weather/event — it is the honest offline marker",
               "offline voice" in b_off.text and "partly cloudy" not in b_off.text
               and "Standup" not in b_off.text and "68" not in b_off.text)
            ck("A3: the offline briefing still carries the grounded fact sheet (her ground truth) "
               "+ a real delivery/feeling",
               "partly cloudy" in b_off.fact_sheet and isinstance(b_off.delivery, dict)
               and b_off.delivery.get("register") and bool(b_off.feeling))

            # ---- B. GROUNDING CONTRACT — the sole ground truth is the local fact sheet -------------
            # Install a RECORDING brain to capture EXACTLY what compose hands the model.
            rec = _Recorder()
            proactive._active_brain = lambda: (rec, False)
            gctx = _grounded_ctx(cg)
            b_g = proactive.compose_briefing(N, ctx=gctx)
            ck("B1: Briefing.fact_sheet == the GIVEN ctx.fact_sheet() exactly (the brief is built FROM "
               "the context it is given)",
               b_g.fact_sheet == gctx.fact_sheet())
            ck("B2: the user-turn handed to brain.reply() IS that fact sheet verbatim — she narrates "
               "ONLY from the local sheet",
               rec.user is not None and gctx.fact_sheet() in rec.user)
            ck("B3: a grounded sheet carries its real weather + calendar event (nothing invented, "
               "the given facts faithfully)",
               "partly cloudy" in b_g.fact_sheet and "61" in b_g.fact_sheet
               and "Standup with the team" in b_g.fact_sheet)

            # the EMPTY case: absence stated as absence, no invented event line.
            rec2 = _Recorder()
            proactive._active_brain = lambda: (rec2, False)
            ectx = _empty_ctx(cg)
            b_e = proactive.compose_briefing(N, ctx=ectx)
            ck("B4: an EMPTY fact sheet states absence as absence (weather unavailable + calendar "
               "could-not-read) and invents NO event bullet",
               "Weather: unavailable (" in b_e.fact_sheet
               and "Calendar today: could not read (" in b_e.fact_sheet
               and "\n  - " not in b_e.fact_sheet)
            ck("B5: the empty-context user-turn handed to the brain is that honest, fabrication-free "
               "sheet (no phantom forecast/event slipped in)",
               rec2.user is not None and b_e.fact_sheet in rec2.user
               and "partly cloudy" not in rec2.user and "\n  - " not in rec2.user)

            # ---- C. HONEST GUIDANCE reaches the system prompt -------------------------------------
            ck("C2: the empty-context system prompt carries the honesty guidance (ban on invented "
               "weather/events + the 'not much to go on' line) — the rail framing reaches the brain",
               rec2.system is not None and "never invent weather, events, or times" in rec2.system
               and "don't have much to go on" in rec2.system)

            # ---- D. PRIVACY GUARD — portrait dropped under a cloud brain --------------------------
            secret = "PRIVATE-PORTRAIT-SENTINEL-9f3a about Lamar's private life"
            portrait.save(N, secret)
            rec_local = _Recorder()
            proactive._active_brain = lambda: (rec_local, False)     # LOCAL brain
            proactive.compose_briefing(N, ctx=gctx)
            ck("D1: a LOCAL brain receives her portrait (memory of you) in the system prompt",
               rec_local.system is not None and secret in rec_local.system)
            rec_cloud = _Recorder()
            proactive._active_brain = lambda: (rec_cloud, True)      # CLOUD brain
            b_cloud = proactive.compose_briefing(N, ctx=gctx)
            ck("D2: a CLOUD brain has the portrait DROPPED from the prompt (mem=\"\", the mouth.respond "
               "guard) — private memory never egresses to a provider",
               rec_cloud.system is not None and secret not in rec_cloud.system)
            ck("D3: under cloud the LOCAL fact sheet still grounds the user-turn (the briefing is still "
               "real, just without your private memory)",
               rec_cloud.user is not None and gctx.fact_sheet() in rec_cloud.user
               and b_cloud.fact_sheet == gctx.fact_sheet())

            # ---- E. NEVER CRASHES — a failing brain falls back warmly -----------------------------
            proactive._active_brain = lambda: (_Boom(), False)
            b_boom = proactive.compose_briefing(N, ctx=gctx)
            ck("E1: a brain whose reply() RAISES yields a warm fallback line, never a crash",
               bool(b_boom.text) and "slow to come" in b_boom.text
               and "RECORDED" not in b_boom.text)
            ck("E2: even on the error fallback the fact sheet is intact (still grounded, no fabrication)",
               b_boom.fact_sheet == gctx.fact_sheet() and "partly cloudy" in b_boom.fact_sheet)
    finally:
        mouth.OllamaBrain.available = saved_avail
        proactive._active_brain = saved_active

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPROACTIVE-BRIEFING CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
