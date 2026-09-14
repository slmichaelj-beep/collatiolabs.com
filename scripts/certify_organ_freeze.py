#!/usr/bin/env python3
"""
certify_organ_freeze — THE FREEZE: Identity & Agency organs are DORMANT while the switch is OFF.

Vera's Identity & Agency organs are HELD until the 2026-07-03 observation window closes. The line
is a per-creature capability, ``identity_agency``, default-OFF in .anima/{name}.caps.json. This cert
proves the SAFETY-CRITICAL FREEZE INVARIANT — that while that switch is OFF (the default), the organs
are a PROVABLE NO-OP — through the SAME gate the server's wiring would call (anima/organs/__init__.py):

  A. DEFAULT-OFF. With no caps file written, caps.enabled(name,'identity_agency') is False,
     organs.is_enabled(name) is False, and CAP_FLAG == 'identity_agency' (the held line, named once).
  B. SWITCH-OFF -> DORMANT. identity_provider(name) hands back DormantIdentity (active=False) and
     agency_provider(name) hands back DormantAgency (active=False) — never the stub, never the live core.
  C. PROVABLE NO-OP (readers). Every queryable reader contributes nothing: identity.current_state and
     narrative -> None, values and relationships -> []; agency.evaluate([...]) -> [] and
     preferred_action([...]) -> None. Nothing identity- or agency-shaping is produced.
  D. NO BUS EMISSION (the reactive surface). A counting fake bus sees ZERO publishes from each organ's
     on_question — even when the Question event carries an option set. The bus stays untouched.
  E. THE FREEZE THROUGH register_all. register_all(bus,name) — the ONE call the server makes to wire
     organs onto the substrate — wires exactly 2 organs, both active=False, and driving each registered
     Topic.QUESTION handler emits 0 Observations. The whole substrate runs silently under the default.
  F. FAILS CLOSED. With caps.enabled monkeypatched to RAISE, is_enabled(name) still returns False — a
     read error can NEVER lift the freeze (the observation-window line can't be crossed by accident).
  G. ENV IRRELEVANT WHILE OFF. With ANIMA_ORGANS_LIVE=1 set, the switch-OFF path STILL returns Dormant*:
     the orthogonal env gate only selects live-vs-stub once the per-creature switch is ON.

HARD RULE honoured: this cert NEVER enables identity_agency and NEVER mutates Vera's identity — it
asserts the OFF/dormant state only (it writes no caps file for any creature). Hermetic + offline (no
model, no network): caps.STORE is redirected by _temp_store; the real .anima is fingerprinted before/
after and asserted byte-identical, and we additionally assert no real-creature caps file was left
enabling the cap. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
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


class _CountBus:
    """Minimal fake bus: counts publishes. A dormant organ must drive this to ZERO."""

    def __init__(self) -> None:
        self.published = 0

    async def publish(self, *a, **k) -> None:
        self.published += 1


class _Q:
    """A Question-bearing event stand-in that DOES carry options — so 'no-op' can't be
    an accident of an empty context. A live organ would surface a preference here."""

    turn_id = "f_freezeturn01"

    class payload:
        context = {"options": ["smile", "wave"]}


def main() -> int:
    from anima import organs
    from anima.organs import (
        CAP_FLAG,
        DormantAgency,
        DormantIdentity,
        agency_provider,
        identity_provider,
        is_enabled,
        register_all,
    )
    from anima.organs.base import Topic

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ORGAN FREEZE — Identity & Agency organs are DORMANT while the switch is OFF (the freeze)")
    print("=" * 88)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # CAP_FLAG is a pure constant — assert the held line is named exactly once, outside the store.
    ck("F0: the held switch is the identity_agency capability (CAP_FLAG named once)",
       CAP_FLAG == "identity_agency")

    with _temp_store() as tp:
        from anima import caps
        # Belt-and-suspenders: confirm the hermetic redirect actually points caps at the temp dir,
        # so nothing we read/assert can touch the real per-creature caps on disk.
        ck("H0: caps.STORE is redirected into the temp dir (hermetic)", Path(str(caps.STORE)) == tp)

        N = "FreezeCert"   # a synthetic creature; NO caps file is ever written for it -> true default

        # ---- A. DEFAULT-OFF (no caps file == the held default) -----------------------------
        ck("A1: identity_agency is OFF by default (caps.enabled False, never persisted)",
           caps.enabled(N, "identity_agency") is False)
        ck("A2: organs.is_enabled(name) reads the switch as OFF (the gate agrees)",
           is_enabled(N) is False)
        ck("A3: not even a caps file exists for the creature (truly default, nothing toggled)",
           not (tp / f"{N}.caps.json").exists())

        # ---- B. SWITCH-OFF -> DORMANT organs ----------------------------------------------
        ident = identity_provider(N)
        agcy = agency_provider(N)
        ck("B1: switch OFF -> identity_provider hands back DormantIdentity (not the stub/live core)",
           isinstance(ident, DormantIdentity))
        ck("B2: switch OFF -> agency_provider hands back DormantAgency (not the stub/live core)",
           isinstance(agcy, DormantAgency))
        ck("B3: both dormant organs report active=False (telemetry sees the seam is held)",
           ident.active is False and agcy.active is False)

        # ---- C. PROVABLE NO-OP — every reader contributes NOTHING --------------------------
        ck("C1: identity.current_state -> None (no felt state while held)",
           ident.current_state(N) is None)
        ck("C2: identity.values -> [] and identity.relationships -> [] (no held values/bonds)",
           ident.values(N) == [] and ident.relationships(N) == [])
        ck("C3: identity.narrative -> None (no self-story while held)",
           ident.narrative(N) is None)
        ck("C4: agency.evaluate([...]) -> [] (scores nothing, even given options)",
           agcy.evaluate(["greet", "ask", {"id": "defer"}]) == [])
        ck("C5: agency.preferred_action([...]) -> None (no preference while held)",
           agcy.preferred_action(["greet", "ask"]) is None)

        # ---- D. NO BUS EMISSION — on_question publishes nothing ----------------------------
        bus_i = _CountBus()
        asyncio.run(ident.on_question(bus_i, _Q))
        ck("D1: dormant identity.on_question publishes 0 Observations (bus untouched)",
           bus_i.published == 0)
        bus_a = _CountBus()
        asyncio.run(agcy.on_question(bus_a, _Q))
        ck("D2: dormant agency.on_question publishes 0 Observations (bus untouched)",
           bus_a.published == 0)

        # ---- E. THE FREEZE THROUGH register_all (the server's one wiring call) -------------
        reg_bus = _CountBus()
        subscribed = []           # (topic, handler) pairs register_all asks the bus to subscribe

        class _WiringBus(_CountBus):
            def subscribe(self, topic, handler):
                subscribed.append((topic, handler))

        wb = _WiringBus()
        organs_wired = register_all(wb, N)
        ck("E1: register_all wires exactly 2 organs (identity + agency)", len(organs_wired) == 2)
        ck("E2: switch OFF -> register_all wires DORMANT organs (none active)",
           not any(getattr(o, "active", True) for o in organs_wired))
        ck("E3: both organs are subscribed to Topic.QUESTION (the seam IS wired, just silent)",
           len(subscribed) == 2 and all(t == Topic.QUESTION for t, _ in subscribed))
        # Drive each registered handler with a Question event — they must publish NOTHING.
        for _topic, handler in subscribed:
            asyncio.run(handler(_Q))
        ck("E4: driving every registered handler emits 0 Observations (the freeze holds end-to-end)",
           wb.published == 0)

        # ---- F. FAILS CLOSED — a read error can never lift the freeze ----------------------
        _orig_enabled = caps.enabled

        def _boom(*a, **k):
            raise RuntimeError("simulated caps read failure")

        caps.enabled = _boom
        try:
            ck("F1: is_enabled() FAILS CLOSED to OFF when the caps read raises (freeze can't lift)",
               is_enabled(N) is False)
            ck("F2: under the same failure, identity_provider STILL hands back DormantIdentity",
               isinstance(identity_provider(N), DormantIdentity))
            ck("F3: under the same failure, agency_provider STILL hands back DormantAgency",
               isinstance(agency_provider(N), DormantAgency))
        finally:
            caps.enabled = _orig_enabled
        ck("F4: caps.enabled restored after the fail-closed probe (no lingering monkeypatch)",
           caps.enabled is _orig_enabled)

        # ---- G. ENV IRRELEVANT WHILE OFF --------------------------------------------------
        _orig_env = os.environ.get(organs.ORGAN_FLAG)
        os.environ[organs.ORGAN_FLAG] = "1"
        try:
            ck("G1: ANIMA_ORGANS_LIVE=1 does NOT lift the freeze -> identity stays DormantIdentity",
               isinstance(identity_provider(N), DormantIdentity))
            ck("G2: ANIMA_ORGANS_LIVE=1 does NOT lift the freeze -> agency stays DormantAgency",
               isinstance(agency_provider(N), DormantAgency))
        finally:
            if _orig_env is None:
                os.environ.pop(organs.ORGAN_FLAG, None)
            else:
                os.environ[organs.ORGAN_FLAG] = _orig_env

        # ---- H (in-store). No caps file was EVER written enabling the cap (we only observed) --
        leaked = sorted(str(q.relative_to(tp)) for q in tp.rglob("*.caps.json") if q.is_file())
        ck("H2: the cert wrote NO caps file at all (it never enabled identity_agency — observe-only)",
           leaked == [])

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination, identity untouched)",
       fp_before == fp_after)

    print("\nORGAN-FREEZE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
