"""anima.first_launch — the honest first-run setup state.

It DETECTS (host, Ollama, model, voice/ears), SELECTS the profile (via the host runtime
contract), and reports a clear, capability-truthful setup state — no fake green, no scary
unexplained red. The wizard UI renders this; nothing here claims a capability the runtime
doesn't enforce.
"""
from __future__ import annotations

import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ollama_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ollama_models() -> list[str]:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            return [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []


def state() -> dict:
    """The full first-run setup state — every check honest (ok / missing / deferred), each with a
    plain-language line and an actionable next step where something is missing."""
    from anima.host import profile as hprof, benchmark as hbench
    contract = hprof.current()
    steps = []

    # 1. host detected + profile selected
    steps.append({"id": "host", "ok": contract.get("memory_gb", 0) > 0,
                  "label": "This Mac supports Vera %s." % contract.get("selected_profile"),
                  "detail": "%s, %d GB unified memory, %d GB free" % (
                      contract.get("chip"), contract.get("memory_gb"),
                      contract.get("disk_free_gb")),
                  "next": ""})

    # 2. disk headroom
    low_disk = contract.get("disk_free_gb", 0) < 10
    steps.append({"id": "disk", "ok": not low_disk,
                  "label": "Enough free disk." if not low_disk else "Low disk space.",
                  "detail": "%d GB free" % contract.get("disk_free_gb"),
                  "next": "" if not low_disk else "Free up space before large intake jobs."})

    # 3. Ollama (the brain runtime)
    up = _ollama_up()
    steps.append({"id": "ollama", "ok": up,
                  "label": "Ollama is running." if up else "Ollama isn't running yet.",
                  "detail": "the local model runtime",
                  "next": "" if up else "Open the Ollama app (open -a Ollama), then re-check. "
                                        "Use the APP, not the Homebrew formula."})

    # 4. the model
    models = _ollama_models()
    want = contract.get("default_model", "")
    have = any(want.split(":")[0] in m for m in models)
    steps.append({"id": "model", "ok": have,
                  "label": "Vera's model is installed." if have else "Vera's model isn't pulled yet.",
                  "detail": want,
                  "next": "" if have else "Run: ollama pull %s" % want})

    # 5. voice (capability-truthful: claimed only if the profile + benchmark allow it)
    from anima.host import enforcement as henf
    v = henf.voice_allowed(contract, benchmark_ms=(hbench.tts_latency_ms() if up else None))
    steps.append({"id": "voice", "ok": v["allowed"],
                  "label": ("Voice is enabled%s." % (" (latency passed)"
                            if "measured_ms" in v else "")) if v["allowed"]
                           else "Voice is off for now.",
                  "detail": v["reason"],
                  "next": "" if v["allowed"] else "Optional — Vera works in text without it."})

    # 6. ears
    ears_on = contract.get("ears_mode") == "enabled"
    steps.append({"id": "ears", "ok": ears_on or contract.get("ears_mode") == "optional",
                  "label": "Mic dictation ready." if ears_on else "Mic dictation optional.",
                  "detail": "Whisper local transcription",
                  "next": ""})

    # 7. limits (honest, profile-driven)
    steps.append({"id": "limits", "ok": True,
                  "label": "Setup limits explained.",
                  "detail": "Uploads up to %d MB; %s background jobs; %s." % (
                      contract.get("max_upload_mb"), contract.get("background_job_policy"),
                      "large intake is deferred" if contract.get("background_job_policy")
                      in ("defer-all", "defer-heavy") else "large intake runs async"),
                  "next": ""})

    blocking = [s for s in steps if not s["ok"] and s["id"] in ("ollama", "model")]
    ready = not blocking
    return {
        "ok": True,
        "ready": ready,
        "profile": contract.get("selected_profile"),
        "recommended_profile": contract.get("recommended_profile"),
        "override_active": bool(contract.get("manual_overrides")),
        "steps": steps,
        "blocking": [s["id"] for s in blocking],
        "headline": ("Vera is ready on this Mac." if ready
                     else "A couple of setup steps remain: " + ", ".join(s["id"] for s in blocking)),
        "smoke_test_hint": "Say hello in the chat — if she replies, the brain is live.",
    }


def smoke_test() -> dict:
    """A real, minimal end-to-end check: one chat turn must return a non-empty reply."""
    try:
        body = json.dumps({"text": "Say hello in one short sentence."}).encode()
        req = urllib.request.Request("http://127.0.0.1:8765/say", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        ok = bool(d.get("reply"))
        return {"ok": ok, "reply": (d.get("reply") or "")[:200], "backend": d.get("backend")}
    except Exception as e:
        return {"ok": False, "error": repr(e)}
