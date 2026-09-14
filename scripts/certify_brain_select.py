#!/usr/bin/env python3
"""
certify_brain_select — the Local↔Cloud brain switch + the privacy moat it gates.

Vera is local-first: the brain selector lets the user pick a provider, but the moment a CLOUD brain
is active, the user's private world is protected — the API key is never exposed to the UI, structured
PII is scrubbed from anything that egresses, the creature's known personal names are scrubbed too, and
private host/inbox reads are PAUSED rather than streamed to the cloud. This certifies that contract
through the SAME functions the server's /brain endpoint and the route privacy guard call:

  A. LOCAL BY DEFAULT — a fresh config is provider=local; is_cloud() is False; public() (the /brain
     payload the UI renders) carries no key, only has_key=False.
  B. SWITCH IS REAL + DURABLE + KEY-SAFE — saving a cloud provider with a key makes is_cloud() True and
     round-trips the provider on reload; public() NEVER contains the key string (only has_key=True);
     switching back to local makes is_cloud() False again. A cloud provider WITHOUT a key stays local
     (is_cloud False) — guards can't be tricked into pausing a truly-local session.
  C. PII SCRUB — scrub() redacts an email + phone and is STABLE (same input -> same token); scrub_names
     redacts a known creature name; scrub_all combines both.
  D. PRIVATE READS PAUSE ON CLOUD — with a cloud brain active, route.route(a reminders/notes read)
     returns the honest "paused" message and pulls NO private data into the cloud stream.

Hermetic + offline (no provider network call — save_cfg is exercised directly, which is the server's
job AFTER it verifies a key): every store incl. cloud.STORE is redirected to a temp dir; the real
.anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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

_FAKE_KEY = "sk-FAKE-DUMMY-brain-cert-not-a-real-key-000"


def main() -> int:
    from anima import cloud, route
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("BRAIN SELECT — Local↔Cloud switch + the privacy moat it gates")
    print("=" * 66)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        saved_cloud_store = getattr(cloud, "STORE", None)
        cloud.STORE = tp                                  # redirect brain.json into the temp dir
        try:
            # ---- A. LOCAL BY DEFAULT ----------------------------------------------------
            cfg = cloud.load_cfg()
            ck("A1: a fresh config is provider=local", cfg.get("provider") == "local")
            ck("A2: is_cloud() is False on a local brain", cloud.is_cloud() is False)
            pub = cloud.public()
            ck("A3: the /brain payload says local + carries no key",
               pub.get("provider") == "local" and pub.get("has_key") is False
               and "key" not in pub and pub.get("is_cloud") is False)

            # ---- B. SWITCH IS REAL + DURABLE + KEY-SAFE ---------------------------------
            cloud.save_cfg("openai", "gpt-4o-mini", _FAKE_KEY, budget=1.0)
            ck("B1: saving a cloud provider WITH a key flips is_cloud() True", cloud.is_cloud() is True)
            ck("B2: the provider round-trips on reload (durable)",
               cloud.load_cfg().get("provider") == "openai")
            pub2 = cloud.public()
            import json as _json
            ck("B3: public() NEVER exposes the key string (only has_key=True)",
               _FAKE_KEY not in _json.dumps(pub2) and pub2.get("has_key") is True
               and pub2.get("is_cloud") is True)
            cloud.save_cfg("local", "", "")
            ck("B4: switching back to local flips is_cloud() False", cloud.is_cloud() is False)
            # a provider that was NEVER given a key (deepseek here) stays local — is_cloud requires a
            # key. (openai would reuse its remembered key: the per-provider 'configured' memory.)
            cloud.save_cfg("deepseek", "deepseek-chat", "")
            ck("B5: a never-keyed cloud provider stays local (is_cloud False) — no false pause",
               cloud.is_cloud() is False)

            # ---- C. PII SCRUB -----------------------------------------------------------
            s1 = cloud.scrub("email me at jane@x.com or call 415-555-0199")
            ck("C1: scrub redacts an email and a phone number",
               "jane@x.com" not in s1 and "415-555-0199" not in s1)
            ck("C2: scrub is STABLE (same input -> same token)",
               cloud.scrub("jane@x.com") == cloud.scrub("jane@x.com"))
            names = cloud.name_terms("Vera") | {"mara"}
            sn = cloud.scrub_names("how is Mara's move going?", names)
            ck("C3: scrub_names redacts a known personal name", "mara" not in sn.lower())
            sa = cloud.scrub_all("tell Mara at mara@x.com", names)
            ck("C4: scrub_all redacts both the name and the email",
               "mara@x.com" not in sa and "mara" not in sa.lower())

            # ---- D. PRIVATE READS PAUSE ON CLOUD ----------------------------------------
            cloud.save_cfg("openai", "gpt-4o-mini", _FAKE_KEY, budget=1.0)   # cloud ON
            r = route.route("BrainCert", "what are my reminders?")
            ck("D1: a private host read is PAUSED under a cloud brain (not streamed to cloud)",
               "PAUSED" in (r or {}).get("note", ""))
            r2 = route.route("BrainCert", "what notes do I have?")
            ck("D2: notes read is likewise paused under cloud",
               "PAUSED" in (r2 or {}).get("note", ""))
        finally:
            if saved_cloud_store is not None:
                cloud.STORE = saved_cloud_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nBRAIN-SELECT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
