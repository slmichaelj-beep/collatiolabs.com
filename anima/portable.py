"""
portable — the PORTABLE HUMAN INTELLIGENCE SUBSTRATE: export a person's mind to a model-agnostic
bundle, and re-import its core with proven round-trip fidelity.

The 10^inf goal is a *portable* personal intelligence — one you can carry app-to-app and model-to-
model, never locked inside one vendor's weights. The Personal Digital Twin (anima/twin_dashboard)
SHOWS what Vera knows about you. This makes it MOVABLE:

    export_mind(name)  ->  a self-describing JSON bundle (manifest + identity + facets + provenance)
    import_mind(bundle, target)  ->  reconstructs the IDENTITY CORE into a fresh store

The bundle is plain JSON — no model, no vendor format — so any app or model can read it. The
identity CORE (durable LIRF facts) is the round-trip keystone: export from store A, import into a
fresh store B, and B holds the same active facts with the same values. The richer facets (how-you-
think, trajectory, what-matters, world) are exported as portable, human-readable data carrying their
provenance; importing those into arbitrary engines is engine-specific and left to each consumer (the
bundle gives them everything they need).

Design rules (mirror the rest of the substrate):
  * Pure + hermetic. export reads the per-creature stores read-only; import writes ONLY the named
    target's LIRF ledger via the normal merge path (full provenance, no bespoke writer). Never a
    model, never the live server.
  * NO FABRICATION: an empty mind exports an honest empty bundle (known:false facets), never invents.
  * Self-describing: every bundle carries a manifest (version, created, source, counts) so a consumer
    knows exactly what it holds and where it came from.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
BUNDLE_VERSION = 1


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


def _identity(name: str) -> List[Dict[str, Any]]:
    """The durable identity facts (the portable CORE), each with value + provenance."""
    def go():
        from . import memory_lirf as ml
        rows = ml.Facts.load(name).about(ml.SELF)
        out = []
        for r in rows:
            out.append({
                "trait": r.get("trait"),
                "value": r.get("value"),
                "confidence": r.get("confidence"),
                "support": r.get("support"),
                "source": r.get("source"),
                "evidence": r.get("evidence"),
                "updated": r.get("updated"),
            })
        return out
    return _safe(go, [])


def _personal(name: str) -> Dict[str, Any]:
    def go():
        from . import personal
        p = personal.personal_profile(name)
        return {"known": bool(p.get("known")), "counts": p.get("counts", {}),
                "values": [{"name": v.get("name"), "summary": v.get("summary"),
                            "evidence": v.get("evidence")} for v in (p.get("values") or [])][:50],
                "preferences": [{"name": v.get("name"), "summary": v.get("summary")}
                                for v in (p.get("preferences") or [])][:50],
                "decision_patterns": [{"name": v.get("name"), "summary": v.get("summary")}
                                      for v in (p.get("decision_patterns") or [])][:50],
                "lessons": [{"name": v.get("name"), "summary": v.get("summary")}
                            for v in (p.get("lessons") or [])][:50]}
    return _safe(go, {"known": False, "counts": {}})


def _cognitive_objects(name: str) -> List[Dict[str, Any]]:
    """The RAW 'how you think' objects (VALUE / PREFERENCE / DECISION_PATTERN / HEURISTIC) — the
    person-model cognitive layer, exported whole (with ids) so they reconstruct faithfully. These
    are about the PERSON, never Vera's self (the freeze guard refuses a self-referential one)."""
    def go():
        from . import lerf
        types = {lerf.VALUE, lerf.PREFERENCE, lerf.DECISION_PATTERN, lerf.HEURISTIC}
        out = []
        for o in (lerf._load_objects(name) or []):
            if isinstance(o, dict) and o.get("type") in types and o.get("state", "active") == "active":
                out.append(o)
        return out
    return _safe(go, [])


def _snapshot(modname: str, fn: str, name: str) -> Any:
    def go():
        mod = __import__("anima." + modname, fromlist=["_"])
        f = getattr(mod, fn, None)
        return f(name) if callable(f) else None
    return _safe(go, None)


def export_mind(name: str = "Vera") -> Dict[str, Any]:
    """Compose the portable, self-describing mind bundle for `name` (read-only)."""
    identity = _identity(name)
    personal = _personal(name)
    cognitive = _cognitive_objects(name)
    trajectory = _snapshot("trajectory", "snapshot_trajectory", name)
    meaning = _snapshot("meaning", "snapshot", name)
    world = _safe(lambda: (__import__("anima.world_state", fromlist=["_"]).render(name) or ""), "")
    counts = {
        "identity_facts": len(identity),
        "cognitive_objects": len(cognitive),
        "personal_known": bool(personal.get("known")),
        "personal_items": int(sum((personal.get("counts") or {}).values())),
        "has_trajectory": bool(trajectory),
        "has_meaning": bool(meaning),
        "has_world": bool(world and "0 relations" not in world.lower()),
    }
    return {
        "manifest": {
            "schema": "vera.portable-mind",
            "version": BUNDLE_VERSION,
            "person": name,
            "counts": counts,
            "round_trip_layers": ["identity", "cognitive_objects"],
            "read_only_layers": ["trajectory", "what_matters", "world_summary"],
            "note": ("A portable, model-agnostic export of a person's grounded personal intelligence. "
                     "The identity facts AND the cognitive objects (how-you-think: values, preferences, "
                     "decision patterns, heuristics) are the round-trip CORE (import_mind reconstructs "
                     "them). The derived facets (trajectory/meaning regenerate from the core; world is "
                     "a summary) travel as portable, provenance-carrying data for any consumer to read."),
        },
        "identity": identity,
        "cognitive_objects": cognitive,
        "personal_intelligence": personal,
        "trajectory": trajectory,
        "what_matters": meaning,
        "world_summary": world[:4000],
    }


def import_mind(bundle: Dict[str, Any], target: str) -> Dict[str, Any]:
    """Reconstruct the IDENTITY CORE from a bundle into `target`'s LIRF ledger (the portability
    keystone). Each fact re-enters through the normal merge path with provenance preserved. Returns
    {imported, traits}. Facets are intentionally NOT auto-imported (engine-specific) — the bundle
    carries them for a consumer that wants them."""
    from . import memory_lirf as ml
    facts = (bundle or {}).get("identity") or []
    f = ml.Facts.load(target)
    imported = 0
    for fact in facts:
        trait, value = fact.get("trait"), fact.get("value")
        if not trait or value in (None, "", []):
            continue
        f.merge({
            "trait": trait, "value": value,
            "correction": False,
            "evidence": fact.get("evidence") or "imported from portable bundle",
            "source": fact.get("source") or "portable-import",
        })
        imported += 1
    if imported:
        f.save(target)

    # the COGNITIVE layer (how-you-think): re-store each object through the normal lerf write path
    # (idempotent on id; the freeze guard re-refuses any self-referential object — never imported).
    obj_imported = 0
    try:
        from . import lerf
        for o in ((bundle or {}).get("cognitive_objects") or []):
            if not isinstance(o, dict):
                continue
            try:
                lerf.store_object(dict(o), name=target)
                obj_imported += 1
            except Exception:
                continue            # skip a freeze-refused / malformed object, honestly
    except Exception:
        pass

    return {"imported": imported, "objects_imported": obj_imported,
            "traits": sorted({x.get("trait") for x in facts if x.get("trait")})}


def save_bundle(bundle: Dict[str, Any], path: Path, *, allow_plaintext: bool = False) -> Path:
    """Write a portable-mind bundle.

    Disk exports are encrypted by default. Pass allow_plaintext=True only when the user
    intentionally needs a human/tool-readable JSON transfer file.
    """
    from . import secure_store
    path = Path(path)
    secure_store.save_export_json(path, bundle, allow_plaintext=allow_plaintext,
                                  trailing_newline=True)
    return path


def load_bundle(path: Path) -> Dict[str, Any]:
    from . import secure_store
    return secure_store.load_export_json(path, {})


# --------------------------------------------------------------------------------------------
# selftest — hermetic. Seed a mind in store A, EXPORT it, IMPORT into a FRESH store B, and prove
# round-trip fidelity of the identity CORE (same traits + same values, active). Plus: an empty mind
# exports an honest empty bundle; the bundle is plain JSON (serialises).
# --------------------------------------------------------------------------------------------
def _selftest() -> int:
    import importlib.util
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    spec = importlib.util.spec_from_file_location(
        "g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
    g0pe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g0pe)

    print("portable — export/import the portable mind (hermetic)")
    print("=" * 60)
    old_key = os.environ.get("ANIMA_KEY")
    if old_key is None:
        os.environ["ANIMA_KEY"] = "portable-selftest-key"
    try:
        with g0pe._temp_store() as hermetic_store:
            from anima import crypto as _crypto
            old_crypto = (_crypto._STORE, _crypto._fernet, _crypto._resolved)
            _crypto._STORE = Path(hermetic_store) / ".crypto"
            _crypto._fernet = None
            _crypto._resolved = False
            from anima import memory_lirf as ml

            # an EMPTY mind exports honestly.
            empty = export_mind("EmptyMind")
            ck("empty mind exports 0 identity facts (honest)", empty["manifest"]["counts"]["identity_facts"] == 0)
            ck("empty bundle serialises to plain JSON", isinstance(json.dumps(empty), str))

            # seed a real mind in store A — identity facts AND cognitive (how-you-think) objects.
            from anima import lerf
            a = "PortableA"
            for fact in ("my name is Lamar", "my birthday is March 4, 1991",
                         "I work at Collatio", "my dog's name is Biscuit", "I live in Portland"):
                ml.capture(a, fact)
            _v = lerf.make_value("craftsmanship", domain="user",
                                 evidence=["Lamar repeatedly chooses the rigorous path over the quick one"])
            _v["state"] = "active"
            lerf.store_object(_v, name=a)
            _p = lerf.make_preference("terse, concrete writing", domain="user",
                                      evidence=["prefers short concrete prose to flourish"])
            _p["state"] = "active"
            lerf.store_object(_p, name=a)
            bundle = export_mind(a)
            ck("export captures the seeded identity facts (>=5)",
               bundle["manifest"]["counts"]["identity_facts"] >= 5)
            ck("export captures the cognitive 'how you think' objects (>=2)",
               bundle["manifest"]["counts"]["cognitive_objects"] >= 2)
            ck("manifest declares both round-trip layers (identity + cognitive_objects)",
               "identity" in bundle["manifest"]["round_trip_layers"]
               and "cognitive_objects" in bundle["manifest"]["round_trip_layers"])
            ck("bundle is self-describing (manifest schema + version + person)",
               bundle["manifest"]["schema"] == "vera.portable-mind"
               and bundle["manifest"]["version"] == BUNDLE_VERSION
               and bundle["manifest"]["person"] == a)
            ck("bundle is plain model-agnostic JSON (round-trips through json)",
               json.loads(json.dumps(bundle))["identity"][0].get("trait") is not None)

            # serialise + reload (as if carried to another app), then IMPORT into a FRESH store B.
            wire = json.loads(json.dumps(bundle))
            b = "PortableB"
            before_b = ml.Facts.load(b).about(ml.SELF)
            ck("target B starts empty (clean re-import target)", len(before_b) == 0)
            res = import_mind(wire, b)
            ck("import reports the facts it reconstructed (>=5)", res["imported"] >= 5)
            ck("import reports the cognitive objects it reconstructed (>=2)",
               res["objects_imported"] >= 2)

            # ROUND-TRIP FIDELITY: B now holds the same traits with the same values as A.
            fa = {r["trait"]: ml._fmt_value(r["value"]) for r in ml.Facts.load(a).about(ml.SELF)}
            fb = {r["trait"]: ml._fmt_value(r["value"]) for r in ml.Facts.load(b).about(ml.SELF)}
            ck("round-trip: B has every identity trait A had", set(fa).issubset(set(fb)))
            ck("round-trip: B's values match A's exactly (no drift)",
               all(fb.get(t) == v for t, v in fa.items()))
            ck("round-trip: the birthday survived verbatim (March 4, 1991)",
               "March 4, 1991" in (fb.get("birthday") or ""))

            # ROUND-TRIP the COGNITIVE layer: B holds the same how-you-think objects (by id + subject).
            ca = {o.get("id"): (o.get("type"), o.get("subject") or o.get("target") or o.get("name"))
                  for o in _cognitive_objects(a)}
            cb = {o.get("id"): (o.get("type"), o.get("subject") or o.get("target") or o.get("name"))
                  for o in _cognitive_objects(b)}
            ck("round-trip: B has every cognitive object A had (same ids)", set(ca).issubset(set(cb)))
            ck("round-trip: cognitive object type+subject match exactly (how-you-think carried)",
               all(cb.get(i) == v for i, v in ca.items()))

            # save round-trips to disk, encrypted by default with an explicit plaintext escape hatch.
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                p = save_bundle(bundle, Path(td) / "mind.json")
                raw = p.read_text(encoding="utf-8")
                ck("save writes an encrypted bundle file by default",
                   raw.startswith("ANIMAENC1:") and a not in raw)
                ck("load_bundle reads the encrypted bundle back",
                   load_bundle(p)["manifest"]["person"] == a)
                plain = save_bundle(bundle, Path(td) / "mind.plain.json", allow_plaintext=True)
                ck("allow_plaintext=True writes a valid human-readable bundle file",
                   json.loads(plain.read_text(encoding="utf-8"))["manifest"]["person"] == a)
            _crypto._STORE, _crypto._fernet, _crypto._resolved = old_crypto
    finally:
        if old_key is None:
            os.environ.pop("ANIMA_KEY", None)
        else:
            os.environ["ANIMA_KEY"] = old_key

    print("\nPORTABLE MIND SELFTEST: " + ("PASS" if not fails else f"FAIL ({len(fails)})"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
