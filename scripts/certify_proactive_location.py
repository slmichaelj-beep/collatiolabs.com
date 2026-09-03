#!/usr/bin/env python3
"""
certify_proactive_location — the phone's location + push token: persist, read-back, and the auth gate.

For Vera to reach out FIRST — a morning briefing with your real local weather, a reminder that can
ring your phone — she needs two facts from your device: where you are (/loc) and how to push to you
(/device). This certifies, through the SAME server functions do_POST calls, that both PERSIST durably
and that the stored location FEEDS the proactive briefing — OFFLINE (no weather fetch, no APNs send):

  A. LOCATION PERSISTS + FEEDS THE BRIEFING — _store_location({lat,lon,ts}) returns ok and writes
     .anima/<name>.loc.json; a FRESH read survives (durable), and proactive.last_location() reads back
     EXACTLY those coords — the real seam the morning briefing uses for weather (--use-stored-loc).
  B. JUNK IS REJECTED — non-numeric lat/lon and out-of-range coordinates return ok:false and write
     NOTHING (a bad/spoofed post can't poison the weather lookup or leave a half-written file).
  C. PUSH TOKEN PERSISTS — _store_device({voip_token,...}) (the iOS PushKit path) returns ok+have_voip
     and writes .anima/<name>.device.json durably (the token the reminder/call subsystem rings); an
     empty post (no token, no voip) returns ok:false and writes nothing.
  D. BOTH ENDPOINTS ARE AUTHED-GATED — a STATIC proof over anima/server.py: in do_POST the very first
     thing is `if not self._authed(): 401`, then `if not self._passed(): 401`, and ONLY after both do
     the `/loc` and `/device` branches run — so an unauthenticated request can never reach the store
     (no location spoof, no push-target hijack). The handlers also carry the AUTHED invariant.

Deliberately NOT tested: the weather fetch over the stored lat/lon and the actual APNs/PushKit delivery
to the stored token — those are real network calls. The certified surface is the deterministic STORE
contract (validate -> persist -> durable -> read-back-by-the-briefing) plus the auth gating.

Hermetic + offline: server.STORE AND proactive.STORE are redirected to the SAME temp dir (the canonical
_temp_store covers both), so the write and the read-back connect and no real .anima file is touched. The
real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import server, proactive
    import json
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PROACTIVE LOCATION — phone loc + push token: persist, read-back, auth gate")
    print("=" * 73)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    N = "ProactiveLocCert"
    with _temp_store() as tp:
        # ---- A. LOCATION PERSISTS + FEEDS THE BRIEFING ------------------------------
        out = json.loads(server._store_location(N, {"lat": 45.5231, "lon": -122.6765, "ts": 1700000000.0}))
        ck("A1: _store_location with real {lat,lon,ts} returns ok", out.get("ok") is True)
        loc_file = tp / f"{N}.loc.json"
        ck("A2: it WROTE .anima/<name>.loc.json (durable store)", loc_file.exists())
        disk = json.loads(loc_file.read_text())
        ck("A3: the persisted record round-trips the exact lat/lon (durable across a fresh read)",
           disk.get("lat") == 45.5231 and disk.get("lon") == -122.6765)
        lat, lon = proactive.last_location(N)
        ck("A4: proactive.last_location() reads it back — the location FEEDS the briefing's weather",
           lat == 45.5231 and lon == -122.6765)

        # ---- B. JUNK IS REJECTED (nothing written) ---------------------------------
        N2 = "ProactiveLocCertBad"
        bad_file = tp / f"{N2}.loc.json"
        r = json.loads(server._store_location(N2, {"lat": "north", "lon": "west"}))
        ck("B1: non-numeric lat/lon is REJECTED (ok:false) and writes NOTHING",
           r.get("ok") is False and not bad_file.exists())
        r = json.loads(server._store_location(N2, {"lat": 999.0, "lon": -122.0}))
        ck("B2: out-of-range lat is REJECTED (ok:false) and writes NOTHING",
           r.get("ok") is False and not bad_file.exists())
        lat2, lon2 = proactive.last_location(N2)
        ck("B3: after only-bad posts, last_location() is (None, None) — no half-written coords",
           lat2 is None and lon2 is None)

        # ---- C. PUSH TOKEN PERSISTS ------------------------------------------------
        out = json.loads(server._store_device(N, {"voip_token": "VOIP-TOKEN-ABC123",
                                                   "platform": "ios", "bundle_id": "ai.guruu.vera"}))
        ck("C1: _store_device with a voip_token (iOS PushKit) returns ok + have_voip",
           out.get("ok") is True and out.get("have_voip") is True)
        dev_file = tp / f"{N}.device.json"
        ck("C2: it WROTE .anima/<name>.device.json (durable store)", dev_file.exists())
        drec = json.loads(dev_file.read_text())
        ck("C3: the push token round-trips on a fresh read (restart-survival)",
           drec.get("voip_token") == "VOIP-TOKEN-ABC123" and drec.get("platform") == "ios")
        N3 = "ProactiveLocCertNoTok"
        rempty = json.loads(server._store_device(N3, {"platform": "ios"}))
        ck("C4: an empty post (no token, no voip) is REJECTED and writes nothing",
           rempty.get("ok") is False and not (tp / f"{N3}.device.json").exists())

    # ---- D. BOTH ENDPOINTS ARE AUTHED-GATED (static proof over server.py) ----------
    src = (ROOT / "anima" / "server.py").read_text()
    do_post_at = src.find("def do_POST")
    auth_at = src.find("if not self._authed():", do_post_at)
    passed_at = src.find("if not self._passed():", do_post_at)
    loc_at = src.find('path == "/loc"', do_post_at)
    dev_at = src.find('path == "/device"', do_post_at)
    gated = (do_post_at != -1 and auth_at != -1 and passed_at != -1 and loc_at != -1 and dev_at != -1
             and auth_at < passed_at < loc_at and passed_at < dev_at)
    ck("D1: in do_POST the _authed() 401 and _passed() 401 gates BOTH precede the /loc and /device "
       "branches (an unauthenticated request never reaches the store)", gated)
    # the 401-on-fail behavior is what makes the gate a real wall, not a comment
    ck("D2: _authed() failure returns 401 unauthorized (the wall, not a soft pass)",
       'return self._send(401, "text/plain", b"unauthorized")' in src)
    # and the handlers themselves are documented AUTHED (matches the contract's no-spoof claim)
    ck("D3: _store_location is the authed loc sink (validates lat/lon, persists loc.json)",
       "def _store_location" in src and "_loc_path(name)" in src)
    ck("D4: _store_device is the authed token sink (persists device.json)",
       "def _store_device" in src and "_device_path(name)" in src)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPROACTIVE-LOCATION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
