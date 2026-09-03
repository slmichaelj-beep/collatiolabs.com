"""
The portable identity layer — the part of "who she is" that must outlive any single
model, machine, or decade. Designed to be readable and migratable in 1000 years.

The hard design decision is the SPLIT:

  * PORTABLE CORE (model-independent, travels as plain JSON, never expires):
      dials, persona text, values, and the distilled Portrait of the bonded person.
      These describe character and relationship in words/numbers — no model
      assumptions, so they're valid against any future brain.

  * MODEL-BOUND ARTIFACTS (referenced, not embedded; regenerated on model swap):
      control vectors and the LoRA/DoRA adapter. These ARE specific to one model's
      weight space, so the bundle records their file hashes and the model family
      they were built for — never pretending they're portable. When you move to a
      better model in 2031, the core carries over untouched and you regenerate the
      artifacts (scripts/make_vectors.py, scripts/forge.py) for the new model.

Forward-compatibility is explicit: every bundle is versioned (SCHEMA) and passes
through migrate() on import, so a v1 bundle still loads into a v9 reader. That is
what makes this a 1000-year format and not a snapshot.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

STORE = Path(".anima")
SCHEMA = 1


def _hash_file(path) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(65536), b""):
                h.update(blk)
        return "sha256:" + h.hexdigest()
    except Exception:
        return ""


def _artifact_refs(name: str, model_family: str) -> dict:
    """Record (don't embed) the model-bound files: hashes + the model they fit."""
    from . import llamacpp
    vecs = {}
    vdir = llamacpp.VECTOR_DIR
    if os.path.isdir(vdir):
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith(".gguf"):
                vecs[fn] = _hash_file(os.path.join(vdir, fn))
    adapter_dir = os.path.join(".anima", "forge", name, "adapter")
    adapter = _hash_file(os.path.join(adapter_dir, "adapters.safetensors")) if \
        os.path.isdir(adapter_dir) else ""
    return {"model_family": model_family, "vectors": vecs,
            "adapter": adapter, "adapter_path": adapter_dir if adapter else ""}


def export(name: str, model_family: str = "") -> dict:
    """Build the portable identity bundle for `name`. The core is always embedded;
    model-bound artifacts are referenced by hash + model family."""
    from . import dials, portrait
    from .mouth import load_persona, load_values
    return {
        "schema": SCHEMA,
        "kind": "anima.identity",
        "name": name,
        "exported_at": int(time.time()),
        "core": {                                     # model-INDEPENDENT, the real "self"
            "dials": dials.load(name),
            "persona": load_persona(name),
            "values": load_values(name),
            "portrait": portrait.load(name),
        },
        "artifacts": _artifact_refs(name, model_family),  # model-BOUND, by reference
    }


def to_file(name: str, path: str, model_family: str = "") -> str:
    b = export(name, model_family)
    Path(path).write_text(json.dumps(b, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def from_file(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def migrate(bundle: dict) -> dict:
    """Bring any older bundle up to the current SCHEMA. Add a branch per bump; old
    bundles must keep loading forever — that's the 1000-year contract."""
    b = dict(bundle or {})
    v = int(b.get("schema", 0))
    # while v < SCHEMA: ... transform ...; v += 1
    b["schema"] = SCHEMA
    b.setdefault("core", {})
    return b


def validate(bundle: dict):
    """(ok, reason). A bundle is loadable if it's our kind and has a core."""
    if not isinstance(bundle, dict):
        return (False, "not a bundle")
    if bundle.get("kind") != "anima.identity":
        return (False, "not an anima identity bundle")
    if not isinstance(bundle.get("core"), dict):
        return (False, "missing portable core")
    return (True, "ok")


def import_bundle(bundle: dict, name: str) -> dict:
    """Write a bundle's PORTABLE core onto `name` (overwrites dials/persona/values/
    portrait). Artifacts are NOT auto-installed — they're model-bound; the caller
    decides whether the current model matches `artifacts.model_family` and, if not,
    regenerates them. Returns a summary of what was applied + an artifact verdict."""
    ok, why = validate(bundle)
    if not ok:
        return {"ok": False, "error": why}
    b = migrate(bundle)
    core = b.get("core", {})
    from . import dials, portrait
    from .mouth import save_persona, save_values
    applied = []
    if isinstance(core.get("dials"), dict):
        dials.save(name, core["dials"]); applied.append("dials")
    if core.get("persona"):
        save_persona(name, str(core["persona"])); applied.append("persona")
    if isinstance(core.get("values"), list):
        save_values(name, core["values"]); applied.append("values")
    if core.get("portrait"):
        portrait.save(name, str(core["portrait"])); applied.append("portrait")
    art = b.get("artifacts", {})
    return {"ok": True, "applied": applied,
            "artifacts": _artifact_status(name, art)}


def _artifact_status(name: str, art: dict) -> dict:
    """Are the bundle's model-bound artifacts valid for THIS install's model?
    Honest 'regenerate' guidance when they don't match — never silent breakage."""
    from . import llamacpp
    have_vecs = os.path.isdir(llamacpp.VECTOR_DIR) and any(
        f.endswith(".gguf") for f in os.listdir(llamacpp.VECTOR_DIR))
    needs = []
    if art.get("vectors") and not have_vecs:
        needs.append("control vectors — run scripts/make_vectors.py for this model")
    if art.get("adapter"):
        needs.append("voice adapter — re-run scripts/forge.py for this model")
    return {"model_family": art.get("model_family", ""),
            "regenerate": needs,
            "note": ("Portable core applied. Model-bound artifacts are tied to "
                     f"'{art.get('model_family') or 'another model'}'; regenerate "
                     "them for your current model.") if needs else "fully portable"}


def summary(name: str) -> dict:
    """Human-readable one-glance state of her identity (for the UI / CLI)."""
    from . import dials
    d = dials.load(name)
    return {"name": name, "schema": SCHEMA,
            "dials": {k: d[k] for k in d},
            "axes": len(d)}
