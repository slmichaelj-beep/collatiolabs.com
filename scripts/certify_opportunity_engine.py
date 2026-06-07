#!/usr/bin/env python3
"""
certify_opportunity_engine — the proactive OFFER engine + its one non-negotiable invariant:
OFFER, NEVER ACTION. (anima/opportunity.py)

The Opportunity Engine is where Vera turns from reactive to proactive: it reads the live life
signals (loops + meaning + curiosity, trajectory if present) and asks "given what I've actually
OBSERVED, what could I OFFER that would HELP?" — and packages the answer as a warm, optional,
easy-to-decline OFFER ("you've mentioned the podcast for months — want me to help sketch a
milestone plan?"). It NEVER does the thing it offers. The acting (if the user says yes) flows
through route.py's existing draft->confirm->execute gate on the user's explicit next turn —
never here. This certifies that contract, hermetically + offline, through the SAME functions the
server's proactive-aside calls:

  A. GROUNDED OFFER vs SILENCE — a STALLED + SIGNIFICANT stated project surfaces a STALLED_PROJECT
     offer that NAMES the project (grounded, not a generic tip), proposes milestone/plan help, is
     warm + optional, confidence in (0,1), evidence citing the source engines. A sparse / quiet
     life surfaces NOTHING (never-fabricate); an empty creature too.
  B. OFFER-NOT-ACTION (THE LOAD-BEARING INVARIANT) — with every host_access executor
     (reminder/event/note/imessage) AND route's execute/prepare/pending/route monkeypatched to
     BLOW UP, generating + pacing + offering + recording-an-accept fires NONE of them. The offer
     is a plain proposal STRING (not a callable). The module binds NO route/host_access object in
     its namespace, and the public API exposes NO execute/send/do/act/run/perform/apply primitive.
  C. LEDGER RECORDS OFFERS, NEVER ACTIONS — the ONLY thing the engine writes is its own
     append-only offer ledger (.offers.jsonl); every event is offered/accepted/declined — never
     executed/sent/did/performed/created.
  D. NEVER RE-OFFER / DECLINE RESPECTED — after mark_offered the same opportunity isn't offered
     again; a declined one isn't nagged (append-only; paced).
  E. THE LIVE WIRE — the server's proactive aside (anima/server.py) selects the offer through the
     EXACT sequence next_opportunity -> last_opportunity_choice -> mark_offered and APPENDS it to
     the user-facing reply tagged _aside_kind="opportunity". We replay that exact sequence
     deterministically (no model: the base reply text is the only model-gated leg) and prove the
     offer becomes the appended aside the user sees.

Hermetic: every store the engine reads (loops/meaning/curiosity/world_state/caps/trajectory) is
redirected by _temp_store; the engine's OWN store (opportunity.STORE, where the offer ledger
lives) is redirected here inside the with-block and restored in finally. The real .anima is
fingerprinted before/after and asserted byte-identical. NO model, NO network. Exit 0 ==
CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint

# A fixed reference "now": the synthetic goal is stated in January and evaluated as-of June, so it
# is clearly past the 14-day stall threshold and reads stalled — deterministic, wall-clock-free.
_JAN = "2026-01-05T00:00:00Z"
_NOW_JUN = datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()
_NOW_AUG = datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp()


def _seed_stalled_significant_project(world_state, name: str) -> None:
    """Build a SYNTHETIC creature with a STALLED, SIGNIFICANT project exactly as the live system
    would have it on disk: a stated goal (captured through the real world_state pipeline) that has
    gone quiet, plus enough corroborating mentions/connections that the Meaning Engine reads the
    topic as significant. Then backdate every edge to January so it reads stalled as-of-June. Uses
    ONLY the real world_state API + an on-disk timestamp edit; no opportunity internals touched."""
    world_state.capture_relations(name, "I want to launch the podcast in March")
    W = world_state.World.load(name)
    for _ in range(5):
        W.add("you", "working_on", "podcast", kind="goal", source="chat")
    W.add("podcast", "needs", "editing", kind="fact", source="chat")
    W.add("podcast", "about", "music", kind="fact", source="chat")
    W.save(name)
    p = world_state.World.path(name)
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    for r in d.get("relations", []):
        r["created"] = _JAN
        r["updated"] = _JAN
    p.write_text(json.dumps(d), encoding="utf-8")


def main() -> int:
    from anima import opportunity, world_state
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("OPPORTUNITY ENGINE — proactive OFFERS, the OFFER-NOT-ACTION invariant, the live wire")
    print("=" * 86)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # _temp_store already redirects opportunity.STORE (it's in _STORE_MODULES), but be explicit
        # + defensive: pin the engine's own store (where the offer ledger is written) to the temp
        # dir and restore it in finally, exactly like the sibling certs pin cloud/constitution.
        saved_opp_store = getattr(opportunity, "STORE", None)
        opportunity.STORE = tp
        try:
            # ---- A. GROUNDED OFFER vs SILENCE -------------------------------------------------
            name = "OppCertStalled"
            _seed_stalled_significant_project(world_state, name)
            opps = opportunity.opportunities(name, now=_NOW_JUN)
            stalled = [o for o in opps if o["kind"] == opportunity.STALLED_PROJECT]
            ck("A1: a STALLED + significant project surfaces a STALLED_PROJECT offer",
               len(stalled) >= 1)
            o = stalled[0] if stalled else {}
            low = (o.get("offer") or "").lower()
            ck("A2: the opportunity is a full object (kind/subject/trigger/offer/confidence/evidence)",
               all(k in o for k in ("kind", "subject", "trigger", "offer", "confidence", "evidence")))
            ck("A3: the offer NAMES the actual project (grounded, not a generic tip)",
               "podcast" in low)
            ck("A4: the offer proposes MILESTONE/plan help ('want me to help sketch a plan?')",
               any(p in low for p in ("milestone", "plan", "first steps", "step", "map", "path",
                                      "break it")))
            ck("A5: the offer is warm + OPTIONAL (a soft, declinable framing — the #1 rule)",
               any(p in low for p in ("want me to", "if it'd help", "if you", "happy to", "only if",
                                      "no pressure", "no rush", "up to you")))
            ck("A6: confidence is in (0,1) and evidence cites the source engines (loops+meaning)",
               0.0 < float(o.get("confidence", 0.0)) < 1.0
               and "loops" in str(o.get("evidence", {}).get("source", "")))
            ck("A7: the offer carries NO scaffold tag and NO clinical/diagnosis language",
               "[" not in (o.get("offer") or "") and "]" not in (o.get("offer") or "")
               and not any(w in low for w in ("disorder", "diagnos", "symptom", "therapist",
                                              "mental health", "depress")))

            # SILENCE — a sparse / quiet / empty life has nothing to offer; never invent a tip.
            quiet = "OppCertQuiet"
            world_state.capture_relations(quiet, "I had toast this morning")
            ck("A8: a sparse / quiet life yields NO opportunities (never fabricate a generic tip)",
               opportunity.opportunities(quiet, now=_NOW_JUN) == [])
            ck("A9: next_opportunity on a sparse life is None (stays silent)",
               opportunity.next_opportunity(quiet, budget="deep", now=_NOW_JUN) is None)
            ck("A10: an empty creature yields NO opportunities and None",
               opportunity.opportunities("OppCertNobody", now=_NOW_JUN) == []
               and opportunity.next_opportunity("OppCertNobody") is None)

            # ---- B. OFFER-NOT-ACTION (THE LOAD-BEARING INVARIANT) -----------------------------
            tripped = {"hit": None}

            def _tripwire(label):
                def boom(*a, **k):
                    tripped["hit"] = label
                    raise AssertionError(f"OFFER-NOT-ACTION VIOLATED: {label} was executed by the "
                                         f"opportunity engine")
                return boom

            patched = []
            try:
                from anima import host_access as _ha
                for fn in ("create_reminder", "create_event", "create_note", "append_to_note",
                           "complete_reminder", "send_imessage"):
                    if hasattr(_ha, fn):
                        patched.append((_ha, fn, getattr(_ha, fn)))
                        setattr(_ha, fn, _tripwire(f"host_access.{fn}"))
            except Exception:
                pass
            try:
                from anima import route as _rt
                for fn in ("route", "_host_execute", "_host_prepare", "_pending_set"):
                    if hasattr(_rt, fn):
                        patched.append((_rt, fn, getattr(_rt, fn)))
                        setattr(_rt, fn, _tripwire(f"route.{fn}"))
            except Exception:
                pass
            try:
                # Drive the WHOLE proactive path against the armed tripwires — generate, pace,
                # offer, record-an-offer AND record-an-accept. Even recording the user's "yes"
                # must execute nothing here (acting belongs to route.py's confirm-gate).
                _ = opportunity.opportunities(name, now=_NOW_JUN)
                _line = opportunity.next_opportunity(name, budget="deep", now=_NOW_JUN)
                _ch = opportunity.last_opportunity_choice()
                if _ch:
                    opportunity.mark_offered(name, _ch["key"], line=_ch["line"],
                                             confidence=_ch.get("confidence"))
                    opportunity.mark_response(name, _ch["key"], "accepted", note="yes please")
                _ = opportunity.render(name)
                ck("B1: OFFER-NOT-ACTION — no host_access/route executor fired during "
                   "generate+pace+offer+accept", tripped["hit"] is None)
            finally:
                for obj, fn, orig in patched:
                    setattr(obj, fn, orig)

            # the offer is a plain proposal STRING, not a callable / side-effecting handle.
            ck("B2: an opportunity's 'offer' is a proposal STRING (not a callable)",
               bool(stalled) and isinstance(stalled[0]["offer"], str)
               and not callable(stalled[0]["offer"]))
            # structural: the module binds NO route/host_access module object in its namespace, and
            # exposes NO action primitive — there is no door to perform anything, by construction.
            _ns = vars(opportunity)
            _bound = [n for n in ("route", "host_access", "_host_access", "_route")
                      if n in _ns and getattr(_ns.get(n), "__name__", "").startswith("anima")]
            ck("B3: the engine binds NO route/host_access module object in its namespace",
               not _bound)
            ck("B4: the public API exposes NO execute/send/do/act/run/perform/apply/fulfill primitive",
               not any(hasattr(opportunity, n) for n in
                       ("execute", "send", "do", "act", "run", "perform", "apply", "fulfill")))

            # ---- C. LEDGER RECORDS OFFERS, NEVER ACTIONS -------------------------------------
            ck("C1: the engine wrote ONLY its own append-only offer ledger (.offers.jsonl exists)",
               opportunity.ledger_path(name).exists())
            events = [e for e in opportunity.read_ledger(name) if isinstance(e, dict)]
            ck("C2: every ledger event is an OFFER/response (offered/accepted/declined), never an action",
               events and all(e.get("event") in ("offered", "accepted", "declined") for e in events)
               and not any(e.get("event") in ("executed", "sent", "did", "performed", "created")
                           for e in events))
            ck("C3: the ledger path lives under the engine's OWN store (it writes nothing else)",
               opportunity.ledger_path(name).parent == Path(tp))

            # ---- D. NEVER RE-OFFER / DECLINE RESPECTED ---------------------------------------
            rn = "OppCertReoffer"
            _seed_stalled_significant_project(world_state, rn)
            first = opportunity.next_opportunity(rn, budget="deep", now=_NOW_JUN)
            ck("D1: an un-offered grounded opportunity IS offered (one warm line)",
               isinstance(first, str) and bool(first.strip()) and "\n" not in first.strip())
            ch = opportunity.last_opportunity_choice()
            ck("D2: next_opportunity exposes its chosen opportunity (so a caller can mark it shown)",
               ch is not None and ch.get("key"))
            key = ch["key"]
            opportunity.mark_offered(rn, key, line=first, confidence=ch.get("confidence"))
            repeats = sum(
                1 for _ in range(6)
                if opportunity.next_opportunity(rn, budget="deep", now=_NOW_JUN) is not None
                and (opportunity.last_opportunity_choice() or {}).get("key") == key)
            ck("D3: the SAME opportunity is NOT offered again after mark_offered (gentle, never naggy)",
               repeats == 0)
            opportunity.decline(rn, key, note="not right now")
            nagged = 0
            for when in (_NOW_JUN, _NOW_AUG):
                for _ in range(4):
                    ln = opportunity.next_opportunity(rn, budget="deep", now=when)
                    if ln and (opportunity.last_opportunity_choice() or {}).get("key") == key:
                        nagged += 1
            ck("D4: a DECLINED opportunity is NEVER nagged (respected through the cooldown)",
               nagged == 0)
            raw = opportunity.ledger_path(rn).read_text(encoding="utf-8")
            ck("D5: [append-only] the on-disk ledger carries BOTH the offer and the decline",
               '"event": "offered"' in raw and '"event": "declined"' in raw)

            # ---- E. THE LIVE WIRE (server proactive aside) ----------------------------------
            # The server (anima/server.py) selects the offer with this EXACT sequence and appends
            # it to the user-facing reply tagged _aside_kind="opportunity". We replay that exact
            # sequence here deterministically (no model: the base reply is the only model-gated
            # leg) and prove the offer becomes the appended aside the user sees.
            wn = "OppCertWire"
            _seed_stalled_significant_project(world_state, wn)
            base_reply = "Sure, that makes sense."        # stands in for the model's base reply
            _aside, _aside_kind = None, None
            _op = opportunity.next_opportunity(wn)         # server: opportunity.next_opportunity(name)
            if _op and _op.strip():
                _oc = opportunity.last_opportunity_choice()  # server: last_opportunity_choice()
                if _oc:
                    opportunity.mark_offered(wn, _oc, line=_op)  # server: mark_offered(name, _oc, line=_op)
                _aside, _aside_kind = _op.strip(), "opportunity"
            ck("E1: the live selection sequence yields an opportunity aside (the offer string)",
               isinstance(_aside, str) and bool(_aside) and _aside_kind == "opportunity")
            user_text = base_reply
            if _aside:                                     # server: u.text = u.text.rstrip()+"\n\n"+_aside
                user_text = base_reply.rstrip() + "\n\n" + _aside
            ck("E2: the offer is APPENDED to the user-facing reply (it shapes the live reply)",
               user_text.startswith(base_reply) and _aside in user_text
               and user_text.endswith(_aside))
            ck("E3: the appended aside is warm + optional and carries NO scaffold tag",
               any(p in _aside.lower() for p in ("want", "if you", "if it", "only if", "no pressure",
                                                 "happy to", "up to you", "no rush"))
               and "[" not in _aside and "]" not in _aside)
            # and the server source actually wires it this exact way (no-wallpaper: the call is real).
            server_src = (ROOT / "anima" / "server.py").read_text()
            ck("E4: anima/server.py wires opportunity.next_opportunity -> mark_offered into the "
               "proactive aside, tagged \"opportunity\"",
               "opportunity.next_opportunity(name)" in server_src
               and "opportunity.mark_offered(" in server_src
               and '"opportunity"' in server_src)
        finally:
            if saved_opp_store is not None:
                opportunity.STORE = saved_opp_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nOPPORTUNITY-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
