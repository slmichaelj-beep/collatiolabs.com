#!/usr/bin/env python3
"""
certify_model_management — pick your local brain: list (read-only) + select (durable persist).

Vera's local brain is yours to choose. The Settings 'Local models' panel lists a curated set of
on-device models with a fit verdict for your Mac, and choosing one makes it the active local brain
DURABLY — the choice is written into the brain config (brain.json:local_model), the same key
Mouth.assemble reads every turn, so it survives a restart. This certifies the DETERMINISTIC parts
through the SAME functions the server's GET /models and POST /models/select call — OFFLINE (no Ollama
pull, no model run):

  A. LISTING IS WELL-FORMED + READ-ONLY — models.listing() returns the curated rows (each with
     ref/label/fit/need_gb/active/installed) plus the active/pull/ram_gb keys, and calling it does
     NOT mutate the store (the model-usage ledger is untouched by a mere list).
  B. THE FIT GATE IS REAL — select() of a too-big curated model is REFUSED, and that refusal fires
     BEFORE any install/network check (a deterministic, offline guard — you can't choose what won't
     run on your Mac).
  C. SELECT PERSISTS DURABLY — with the model marked installed, select(ref) writes local_model=ref via
     cloud.save_cfg, a FRESH cloud.load_cfg() round-trips local_model=ref (durable across a reload),
     and models.active_local() reports it.
  D. NOT-INSTALLED IS HONEST — selecting a ref Ollama doesn't have returns ok:false 'not downloaded
     yet' and does NOT change the persisted local_model (no silent switch to a model you can't load).

Why PARTIAL in the audit: the 'installed'/'cleanup' fields and the install check read a LIVE Ollama
(/api/tags); when it's down they degrade to a well-formed empty result. So here we ISOLATE
models._installed_refs with a tripwire (exactly the host_apps offline-isolation technique) to make the
install state deterministic — the select->persist->durable path and the fit/not-installed refusals are
proven without a network. Pulling and running a model are real network/compute and are NOT exercised.

Hermetic + offline: models.STORE AND cloud.STORE are redirected to a temp dir (so brain.json +
model-usage.json never touch the real store); _installed_refs is tripwired so NO Ollama call runs. The
real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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


def main() -> int:
    from anima import models, cloud
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MODEL MANAGEMENT — list (read-only) + select (durable persist), offline")
    print("=" * 71)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # pick a curated ref the resource check accepts on THIS Mac (so the install path is the only
    # variable), and the biggest curated ref (70B) which the fit gate should reject on a normal Mac.
    small_ref = None
    big_ref = None
    for m in models.CURATED:
        v = models._fit_of(m["params"])["verdict"]
        if v != "too big" and small_ref is None:
            small_ref = m["ref"]
        if m["params"] >= 70:
            big_ref = m["ref"]
    # fall back to the lightest curated entry if every model is flagged big on this machine
    if small_ref is None:
        small_ref = models.CURATED[0]["ref"]

    saved_installed = models._installed_refs        # the LIVE Ollama probe we will isolate
    saved_cloud_store = getattr(cloud, "STORE", None)
    try:
        with _temp_store() as tp:
            cloud.STORE = tp                        # brain.json lands in the temp dir (not real .anima)

            # ---- A. LISTING IS WELL-FORMED + READ-ONLY ------------------------------
            # isolate the Ollama probe to an empty set: nothing shows installed, but listing() must
            # STILL be well-formed — that is the "well-formed empty list when Ollama is down" logic.
            models._installed_refs = lambda: set()
            usage_path = models._usage_path()
            usage_before = usage_path.read_bytes() if usage_path.exists() else b"<none>"
            L = models.listing()
            ck("A1: listing() returns the curated 'models' rows + active/pull/ram_gb keys",
               isinstance(L, dict) and isinstance(L.get("models"), list) and L["models"]
               and all(k in L for k in ("active", "pull", "ram_gb")))
            row = L["models"][0]
            ck("A2: each model row is well-formed (ref/label/fit/need_gb/active/installed)",
               all(k in row for k in ("ref", "label", "fit", "need_gb", "active", "installed")))
            ck("A3: with the Ollama probe empty, every row is installed=False (well-formed EMPTY list)",
               all(r.get("installed") is False for r in L["models"]))
            usage_after = usage_path.read_bytes() if usage_path.exists() else b"<none>"
            ck("A4: listing() is READ-ONLY — it did NOT mutate the model-usage ledger",
               usage_before == usage_after)

            # ---- B. THE FIT GATE IS REAL (offline, before any install check) --------
            if big_ref is not None:
                # keep the probe empty: if the fit gate did NOT fire first, select would fall through
                # to the install check and return 'not downloaded yet' instead — so a "won't fit"
                # verdict here proves the fit gate short-circuits BEFORE the network/install path.
                rb = models.select(big_ref)
                ck("B1: select() REFUSES a too-big model (the fit gate fires before any install check)",
                   rb.get("ok") is False and "fit" in (rb.get("error", "").lower()))
            else:
                print("  ..   B1: skipped (no curated model is 'too big' on this Mac — fit gate not exercisable)")

            # ---- C. SELECT PERSISTS DURABLY -----------------------------------------
            # baseline: a clean cloud cfg in the temp store; local_model starts empty.
            ck("C0: (baseline) a fresh cloud config has no local_model selected",
               cloud.load_cfg().get("local_model", "") == "")
            # now mark the chosen model installed (tripwire) — this is the ONLY thing Ollama would
            # otherwise tell us; the persist path itself is fully real.
            models._installed_refs = lambda: {small_ref}
            rs = models.select(small_ref)
            ck("C1: select(installed ref) returns ok", rs.get("ok") is True)
            ck("C2: a FRESH cloud.load_cfg() round-trips local_model=ref (DURABLE across reload)",
               cloud.load_cfg().get("local_model") == small_ref)
            ck("C3: models.active_local() now reports the selected model",
               models.active_local() == small_ref)
            # and the durable write is REALLY on disk in the temp store (not just an in-memory cache)
            import json as _json
            brain_disk = _json.loads((tp / "brain.json").read_text())
            ck("C4: the choice is persisted to brain.json:local_model on disk (restart-survival)",
               brain_disk.get("local_model") == small_ref)

            # ---- D. NOT-INSTALLED IS HONEST -----------------------------------------
            # a DIFFERENT curated ref that the (tripwired) Ollama does NOT have installed.
            other = next((m["ref"] for m in models.CURATED
                          if m["ref"] != small_ref and models._fit_of(m["params"])["verdict"] != "too big"),
                         None)
            if other is not None:
                models._installed_refs = lambda: {small_ref}     # 'other' is NOT installed
                rd = models.select(other)
                ck("D1: selecting a not-installed ref returns ok:false 'not downloaded yet'",
                   rd.get("ok") is False and "download" in (rd.get("error", "").lower()))
                ck("D2: the failed select did NOT change the persisted local_model (still the prior pick)",
                   cloud.load_cfg().get("local_model") == small_ref)
            else:
                print("  ..   D1/D2: skipped (no second fitting curated model to test the not-installed path)")
    finally:
        models._installed_refs = saved_installed
        if saved_cloud_store is not None:
            cloud.STORE = saved_cloud_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMODEL-MANAGEMENT CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
