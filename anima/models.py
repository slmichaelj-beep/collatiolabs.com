"""models — the local-model manager: a curated, fit-checked list you can pick from and
download, so you never load something that won't run on your Mac.

The active local model lives in the brain config (.anima/brain.json, key 'local_model');
Mouth.assemble reads it for the local brain. Downloads go through Ollama's /api/pull
(streamed progress). A model the resource check says "won't fit" is blocked from being
selected — the whole point is to not choke the machine.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

from . import cloud, sysinfo
from .util import load_json, save_json

OLLAMA = "http://localhost:11434"

# Redirectable store root (mirrors anima/lerf.STORE and anima/cloud.STORE) so a hermetic test
# or a twin can isolate model-usage.json into a temp dir instead of churning the real .anima.
# Default is the real store; tests point it at a temp dir. The path is resolved against STORE at
# call time (via _usage_path), never frozen at import — otherwise redirection couldn't take.
STORE = Path(".anima")
STALE_DAYS = 14                                  # unused this long = a cleanup candidate


def _usage_path() -> Path:
    """The model-usage ledger path (ref -> last-used epoch), resolved against the redirectable
    STORE at call time so a redirected test/twin writes into its temp dir, not real .anima."""
    return STORE / "model-usage.json"

# Curated for the companion: refs proven to pull, varied sizes. 'params' lets the
# resource check verdict gate selection/download. Not exhaustive — any ANIMA_MODEL
# still works; this is the guided path.
CURATED = [
    {"ref": "hf.co/bartowski/Llama-3.2-3B-Instruct-GGUF", "label": "Llama 3.2 · 3B", "params": 3, "note": "fastest, lightest"},
    {"ref": "hf.co/bartowski/L3-8B-Stheno-v3.2-GGUF", "label": "Stheno · 8B", "params": 8, "note": "warm companion · default", "default": True},
    {"ref": "hf.co/bartowski/Rocinante-12B-v1.1-GGUF", "label": "Rocinante · 12B", "params": 12, "note": "expressive companion"},
    {"ref": "hf.co/mradermacher/EVA-Qwen2.5-14B-v0.2-i1-GGUF", "label": "EVA Qwen2.5 · 14B", "params": 14, "note": "articulate"},
    {"ref": "hf.co/bartowski/Llama-3.3-70B-Instruct-GGUF", "label": "Llama 3.3 · 70B", "params": 70, "note": "powerful · big Macs only"},
]

# pull progress, shared with the UI via GET /models
_PULL = {"ref": "", "status": "", "pct": 0, "done": False, "error": ""}


def _installed_refs() -> set:
    """Model names Ollama already has (from /api/tags). Empty set if Ollama is down."""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        return {m.get("name", "") for m in data.get("models", [])} | \
               {m.get("name", "").split(":")[0] for m in data.get("models", [])}
    except Exception:
        return set()


def _is_installed(ref: str, have: set) -> bool:
    return bool(ref) and (ref in have or (ref + ":latest") in have or ref.split(":")[0] in have)


def active_local() -> str:
    import os
    from .mouth import DEFAULT_MODEL
    return cloud.load_cfg().get("local_model", "") or os.environ.get("ANIMA_MODEL", DEFAULT_MODEL)


def _fit_of(params: int) -> dict:
    f = sysinfo.fit(f"{params}B")
    return {"need_gb": f["need_gb"], "verdict": f["verdict"]}


def listing() -> dict:
    have = _installed_refs()
    from .mouth import DEFAULT_MODEL
    import os
    active = cloud.load_cfg().get("local_model", "") or os.environ.get("ANIMA_MODEL", DEFAULT_MODEL)
    rows = []
    for m in CURATED:
        fit = _fit_of(m["params"])
        rows.append({**m, "installed": _is_installed(m["ref"], have),
                     "active": m["ref"] == active, "fit": fit["verdict"], "need_gb": fit["need_gb"]})
    return {"models": rows, "active": active, "pull": dict(_PULL),
            "ram_gb": sysinfo.ram_gb(), "comfy_b": sysinfo.comfy_params_b(),
            "cleanup": cleanup_candidates()}


def _usage() -> dict:
    try:
        u = load_json(_usage_path())
        return u if isinstance(u, dict) else {}
    except Exception:
        return {}


def touch(ref: str):
    """Record that a model was just used (called each turn for the active model)."""
    if not ref:
        return
    u = _usage(); u[ref] = time.time()
    STORE.mkdir(exist_ok=True)
    try:
        save_json(_usage_path(), u)
    except Exception:
        pass


def _ref_size_gb(ref: str, have_models: list) -> float:
    for m in have_models:
        nm = m.get("name", "")
        if nm == ref or nm == ref + ":latest" or nm.split(":")[0] == ref.split(":")[0]:
            return round((m.get("size", 0) or 0) / 1e9, 1)
    return 0.0


def cleanup_candidates() -> dict:
    """Installed models that aren't the active one and haven't been used in STALE_DAYS —
    the disk they're eating (e.g. on the LaCie drive) and what removing them would free."""
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=3) as r:
            have_models = json.loads(r.read()).get("models", [])
    except Exception:
        have_models = []
    active = active_local()
    usage, now, cands, free = _usage(), time.time(), [], 0.0
    for m in have_models:
        ref = m.get("name", "")
        if not ref or ref == active or ref.split(":")[0] == active.split(":")[0]:
            continue
        last = usage.get(ref) or usage.get(ref.split(":")[0]) or 0
        idle_days = int((now - last) / 86400) if last else None
        if last and (now - last) < STALE_DAYS * 86400:
            continue                                  # used recently — keep
        gb = round((m.get("size", 0) or 0) / 1e9, 1)
        cands.append({"ref": ref, "gb": gb, "idle_days": idle_days})
        free += gb
    return {"candidates": cands, "free_gb": round(free, 1)}


def remove(ref: str) -> dict:
    """Delete a model from Ollama (frees disk). Never removes the active model."""
    if ref == active_local() or ref.split(":")[0] == active_local().split(":")[0]:
        return {"ok": False, "error": "that's the active model"}
    try:
        body = json.dumps({"name": ref}).encode()
        req = urllib.request.Request(OLLAMA + "/api/delete", body,
                                     {"Content-Type": "application/json"}, method="DELETE")
        urllib.request.urlopen(req, timeout=30).read()
        u = _usage(); u.pop(ref, None); save_json(_usage_path(), u)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cleanup_unused() -> dict:
    """Remove every stale unused model (the 'clean them all up' action)."""
    removed, freed = [], 0.0
    for c in cleanup_candidates()["candidates"]:
        if remove(c["ref"]).get("ok"):
            removed.append(c["ref"]); freed += c["gb"]
    return {"ok": True, "removed": removed, "freed_gb": round(freed, 1)}


def _curated(ref: str):
    return next((m for m in CURATED if m["ref"] == ref), None)


def select(ref: str) -> dict:
    """Make a model the active local brain — only if it's installed and actually fits."""
    m = _curated(ref)
    if m and _fit_of(m["params"])["verdict"] == "too big":
        return {"ok": False, "error": "that model won't fit your Mac's memory"}
    if not _is_installed(ref, _installed_refs()):
        return {"ok": False, "error": "not downloaded yet"}
    cur = cloud.load_cfg()
    cloud.save_cfg(cur["provider"], cur["model"], "", cur["base"], cur["budget"], local_model=ref)
    return {"ok": True}


def start_pull(ref: str) -> dict:
    """Download a model via Ollama (background). Blocks models that won't fit."""
    m = _curated(ref)
    if m and _fit_of(m["params"])["verdict"] == "too big":
        return {"ok": False, "error": "that model won't fit your Mac's memory — not downloading"}
    if _PULL["ref"] and not _PULL["done"]:
        return {"ok": False, "error": "already downloading " + _PULL["ref"]}
    _PULL.update({"ref": ref, "status": "starting", "pct": 0, "done": False, "error": ""})
    threading.Thread(target=_pull_worker, args=(ref,), daemon=True).start()
    return {"ok": True}


def _pull_worker(ref: str):
    try:
        body = json.dumps({"name": ref, "stream": True}).encode()
        req = urllib.request.Request(OLLAMA + "/api/pull", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3600) as r:
            for line in r:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("error"):
                    _PULL.update({"error": d["error"], "done": True}); return
                _PULL["status"] = d.get("status", "")
                tot, comp = d.get("total"), d.get("completed")
                if tot:
                    _PULL["pct"] = round(100 * (comp or 0) / tot)
        _PULL.update({"status": "done", "pct": 100, "done": True})
    except Exception as e:
        _PULL.update({"error": str(e), "done": True})
