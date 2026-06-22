"""
platform — PLATFORMIZATION (Phase E): carry your WHOLE mind to any app or model.

portable.py exports the CHARACTER + the how-you-think cognitive objects. This goes the rest of the
way: a FULL, model-agnostic bundle of the entire grounded cognitive substrate — identity (dials /
persona / values) + every active lerf object (skills, decision-patterns, heuristics, mental-models,
the user's preferences/values, failure-modes) + the WISDOM theories & lessons (which are lerf objects
in the 'theory' domain) — that round-trips losslessly into a FRESH creature on another machine or
under another brain. It is the "your mind is yours" promise made whole: not just who she is, but
everything she has learned + how she reasons, portable as one file.

It COMPOSES the certified pieces — it never forks them: identity rides anima.portable.export_mind /
import_mind, and the cognitive vault rides anima.lerf's public all_objects / store_object. Because
store_object is the single freeze-guarded persistence choke point, IMPORT is freeze-safe for free: a
bundle object that is a Vera-self PREFERENCE/VALUE is REFUSED (FreezeViolation) and counted, never
silently written. An empty mind yields an empty (honest) bundle.

CLI:  python3 -m anima.platform --selftest        # hermetic round-trip + freeze proof
      python3 -m anima.platform --export NAME      # print the full bundle JSON
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from . import lerf
from . import portable

BUNDLE_VERSION = 1
SCHEMA = "vera.full-mind"


def _vault(name: str) -> List[Dict[str, Any]]:
    """Every ACTIVE cognitive object across ALL lerf object types — the complete grounded vault
    (skills, decision-patterns, heuristics, mental-models incl. THEORIES, preferences, values,
    failure-modes). Read through lerf's public API; [] if the vault is empty (never fabricated)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for t in lerf.OBJECT_TYPES:
        try:
            for o in lerf.all_objects(t, name=name):
                oid = o.get("id")
                if oid and oid not in seen:
                    seen.add(oid)
                    out.append(o)
        except Exception:
            continue
    return out


def export_full(name: str = "Vera") -> Dict[str, Any]:
    """The FULL portable mind: the character bundle (identity + how-you-think) PLUS the entire active
    cognitive vault (every skill/model/theory/lesson/heuristic/preference/value). Model-agnostic,
    JSON-round-trippable. An empty mind yields an empty-but-honest bundle (no fabrication)."""
    base = portable.export_mind(name)                 # identity + cognitive_objects + personal + facets
    vault = _vault(name)
    by_type: Dict[str, int] = {}
    for o in vault:
        by_type[o.get("type", "?")] = by_type.get(o.get("type", "?"), 0) + 1
    theories = sum(1 for o in vault if o.get("type") == lerf.MENTAL_MODEL
                   and o.get("domain") == "theory")
    lessons = sum(1 for o in vault if o.get("type") == lerf.HEURISTIC
                  and o.get("domain") == "theory:lesson")
    identity_facts = int(((base.get("manifest") or {}).get("counts") or {}).get("identity_facts", 0))
    return {
        "manifest": {
            "schema": SCHEMA,
            "version": BUNDLE_VERSION,
            "person": name,
            "counts": {
                "identity_facts": identity_facts,
                "vault_objects": len(vault),
                "by_type": by_type,
                "theories": theories,
                "lessons": lessons,
            },
            "round_trip_layers": ["identity", "cognitive_objects", "full_vault", "theories"],
            "note": ("The WHOLE grounded mind: who she is (identity), how she thinks + what she has "
                     "learned about you (cognitive objects), and what holds over time (theories & "
                     "lessons). Restores losslessly into a fresh creature; freeze-safe on import (a "
                     "Vera-self value/preference is refused). Model-agnostic — carry it anywhere."),
        },
        "identity_bundle": base,                       # the certified portable.export_mind payload
        "vault": vault,                                # every active lerf cognitive object
    }


def import_full(bundle: Dict[str, Any], target: str) -> Dict[str, Any]:
    """Restore a FULL bundle into `target` (a fresh creature): the identity bundle via the certified
    portable.import_mind, then every vault object via lerf.store_object — the single freeze-guarded
    choke point, so a Vera-self preference/value in the bundle is REFUSED (counted, never written).
    Returns {ok, identity, vault_restored, vault_refused, vault_skipped}."""
    if not isinstance(bundle, dict) or bundle.get("manifest", {}).get("schema") != SCHEMA:
        return {"ok": False, "error": "not a vera.full-mind bundle"}
    idres = portable.import_mind(bundle.get("identity_bundle") or {}, target)
    restored = refused = skipped = 0
    for o in bundle.get("vault") or []:
        if not isinstance(o, dict):
            skipped += 1
            continue
        try:
            lerf.store_object(o, name=target)
            restored += 1
        except lerf.FreezeViolation:
            refused += 1                               # freeze boundary held — a Vera-self object
        except Exception:
            skipped += 1
    return {"ok": True, "identity": idres, "vault_restored": restored,
            "vault_refused": refused, "vault_skipped": skipped}


def save_bundle(bundle: Dict[str, Any], path: Path, *, allow_plaintext: bool = False) -> Path:
    """Write the full-mind bundle, encrypted by default."""
    from . import secure_store
    path = Path(path)
    secure_store.save_export_json(path, bundle, allow_plaintext=allow_plaintext)
    return path


def load_bundle(path: Path) -> Dict[str, Any]:
    from . import secure_store
    return secure_store.load_export_json(path, {})


# ── selftest (hermetic round-trip + freeze proof) ──────────────────────────────────────────

def _footprint(root: Path):
    import hashlib
    root = Path(root)
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _selftest() -> int:
    import tempfile
    import secrets as _secrets
    from . import memory_lirf, theory
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("PLATFORM (full portable mind) selftest — hermetic round-trip + freeze")
    print("=" * 66)

    old_key = os.environ.get("ANIMA_KEY")
    if old_key is None:
        os.environ["ANIMA_KEY"] = "platform-selftest-key"

    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    td = tempfile.mkdtemp(prefix="platform-self-")
    tp = Path(td)
    saves = []
    from . import crypto as _crypto
    old_crypto = (_crypto._STORE, _crypto._fernet, _crypto._resolved)
    _crypto._STORE = tp / ".crypto"
    _crypto._fernet = None
    _crypto._resolved = False
    # Redirect EVERY store-bearing module the export/import path may touch (matches the canonical
    # _temp_store coverage) so the real .anima is provably untouched.
    _STORE_MODS = ["mouth", "portrait", "memory_lirf", "world_state", "world_model", "spine",
                   "dials", "narrative", "metrics", "review", "loops", "constitution", "telemetry",
                   "meaning", "curiosity", "trajectory", "reminders", "proactive", "caps",
                   "identity", "opportunity", "live", "lerf", "lerf_router", "whole_mri", "models",
                   "intake", "theory", "portable", "personal"]
    for modname in _STORE_MODS:
        try:
            mm = __import__("anima." + modname, fromlist=["_"])
            if getattr(mm, "STORE", None) is not None:
                saves.append((mm, "STORE", mm.STORE))
                mm.STORE = tp
        except Exception:
            pass
    try:
        import anima.reliability as _rel
        if getattr(_rel, "DEFAULT_STORE", None) is not None:
            saves.append((_rel, "DEFAULT_STORE", _rel.DEFAULT_STORE))
            _rel.DEFAULT_STORE = tp
    except Exception:
        pass
    try:
        src = "PlatSrc_" + _secrets.token_hex(3)
        dst = "PlatDst_" + _secrets.token_hex(3)

        # EMPTY mind -> empty-but-honest bundle (no fabrication)
        empty = export_full(src)
        ok("empty mind -> empty vault (no fabrication)",
           empty["manifest"]["counts"]["vault_objects"] == 0)

        # SEED a real grounded mind: a user value + a heuristic + an induced THEORY. (The lerf
        # factories take the OBJECT's name/target first; the creature goes to store_object.)
        lerf.store_object(lerf.make_value("deep-work mornings", domain="personal", weight=0.9,
                                          state=lerf.ACTIVE, source="captured"), name=src)
        lerf.store_object(lerf.make_heuristic("ship daily", "work", "shipping daily",
                                              "keep momentum", state=lerf.ACTIVE,
                                              source="captured"), name=src)
        for _ in range(3):
            theory.observe(src, "shipping daily tends to keep momentum", confirmed=True,
                           evidence="shipped, held")
        theory.induce(src)

        bundle = export_full(src)
        ok("full export -> a non-empty vault incl. the theory",
           bundle["manifest"]["counts"]["vault_objects"] >= 2
           and bundle["manifest"]["counts"]["theories"] >= 1)
        ok("bundle is a model-agnostic vera.full-mind schema",
           bundle["manifest"]["schema"] == SCHEMA)
        with tempfile.TemporaryDirectory() as btd:
            p = save_bundle(bundle, Path(btd) / "full-mind.json")
            raw = p.read_text(encoding="utf-8")
            ok("save_bundle writes an encrypted full-mind file by default",
               raw.startswith("ANIMAENC1:") and src not in raw)
            ok("load_bundle reads the encrypted full-mind file back",
               load_bundle(p)["manifest"]["schema"] == SCHEMA)
            plain = save_bundle(bundle, Path(btd) / "full-mind.plain.json",
                                allow_plaintext=True)
            ok("allow_plaintext=True writes a human-readable full-mind file",
               json.loads(plain.read_text(encoding="utf-8"))["manifest"]["schema"] == SCHEMA)

        # ROUND-TRIP into a FRESH creature
        res = import_full(bundle, dst)
        ok("import into a fresh creature restores the vault", res["ok"]
           and res["vault_restored"] >= 2)
        dst_vault = _vault(dst)
        ok("the restored creature carries the user value + the theory",
           any(o.get("type") == lerf.VALUE for o in dst_vault)
           and any(o.get("domain") == "theory" for o in dst_vault))
        re_export = export_full(dst)
        ok("re-export of the restored mind matches the original vault size",
           re_export["manifest"]["counts"]["vault_objects"]
           == bundle["manifest"]["counts"]["vault_objects"])

        # FREEZE: a Vera-self value in a bundle is REFUSED on import (counted, never written)
        try:
            self_val = {"id": "value_selftest_freeze", "type": lerf.VALUE, "name": "vera self",
                        "domain": "identity", "subject": "Vera", "target": "her own growth",
                        "weight": 0.9, "confidence": 0.9, "state": lerf.ACTIVE}
            forged = {"manifest": {"schema": SCHEMA}, "identity_bundle": {}, "vault": [self_val]}
            fr = import_full(forged, dst)
            ok("FREEZE: a Vera-self value in a bundle is REFUSED on import (never written)",
               fr["ok"] and fr["vault_refused"] >= 1 and fr["vault_restored"] == 0)
        except Exception as exc:
            ok("FREEZE: a Vera-self value in a bundle is REFUSED on import (never written)", False)
            print("       (import raised:", repr(exc), ")")
    finally:
        for m, a, old in saves:
            setattr(m, a, old)
        _crypto._STORE, _crypto._fernet, _crypto._resolved = old_crypto
        if old_key is None:
            os.environ.pop("ANIMA_KEY", None)
        else:
            os.environ["ANIMA_KEY"] = old_key

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima byte-UNCHANGED across the whole selftest", fp_before == fp_after)

    print("\nPLATFORM: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="anima.platform", description="Full portable-mind bundle.")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--export", metavar="NAME")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.export:
        print(json.dumps(export_full(args.export), ensure_ascii=False, indent=2, default=str))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
