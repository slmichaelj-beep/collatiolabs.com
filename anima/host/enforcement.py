"""host.enforcement — the seams that make the profile REAL.

A profile the runtime doesn't enforce is host-profile theater. Every verdict here reads the
ACTIVE contract (host.profile.current) — the same record the UI shows — so a capability can
never be claimed-but-unenforced. Pure verdict functions; callers act on them.
"""
from __future__ import annotations

from . import profile as _profile

_HEAVY_KINDS = ("intake", "transcription", "ocr", "pack_build", "cert", "diamond", "rover",
                "index", "benchmark")


def allow_heavy_job(kind: str, size_mb: float = 0.0, contract: dict | None = None) -> dict:
    """{'allowed': bool, 'defer': bool, 'reason': str, 'policy': str} for one heavy job."""
    c = contract or _profile.current()
    pol = c.get("background_job_policy", "defer-all")
    prof = c.get("selected_profile", "?")
    if kind == "diamond" and c.get("diamond_policy") == "manual-only":
        return {"allowed": False, "defer": True, "policy": pol,
                "reason": "%s profile runs Diamond manually only — defer to an explicit run" % prof}
    if kind in ("cert", "diamond", "rover") and c.get("cert_policy") in ("light-only", "defer-heavy"):
        return {"allowed": False, "defer": True, "policy": pol,
                "reason": "%s profile defers heavy certification jobs" % prof}
    if kind == "pack_build":
        v = allow_pack_build(size_mb, contract=c)
        return {"allowed": v["allowed"], "defer": not v["allowed"], "policy": pol,
                "reason": v["reason"]}
    if pol == "defer-all":
        return {"allowed": False, "defer": True, "policy": pol,
                "reason": "%s profile defers ALL background jobs" % prof}
    if pol == "defer-heavy" and kind in _HEAVY_KINDS:
        return {"allowed": False, "defer": True, "policy": pol,
                "reason": "%s profile defers heavy jobs (%s) — run when docked or on a bigger host"
                          % (prof, kind)}
    cap = float(c.get("max_intake_job_mb", 0))
    if size_mb and cap and size_mb > cap:
        return {"allowed": False, "defer": True, "policy": pol,
                "reason": "%s profile bounds %s jobs at %d MB (asked: %d MB)"
                          % (prof, kind, cap, size_mb)}
    if pol == "async-bounded":
        return {"allowed": True, "defer": False, "policy": pol,
                "reason": "allowed, async + bounded under the %s profile" % prof}
    return {"allowed": True, "defer": False, "policy": pol,
            "reason": "allowed under the %s profile" % prof}


def upload_allowed(size_mb: float, contract: dict | None = None) -> dict:
    """The intake pre-flight verdict for ONE upload."""
    c = contract or _profile.current()
    cap = float(c.get("max_upload_mb", 0))
    if cap and size_mb > cap:
        return {"allowed": False,
                "reason": "this upload is %d MB but the %s profile caps uploads at %d MB — "
                          "split the file, or raise the profile (logged override)"
                          % (size_mb, c.get("selected_profile"), cap)}
    return {"allowed": True, "reason": "within the %s profile's %d MB upload budget"
                                       % (c.get("selected_profile"), cap)}


def voice_allowed(contract: dict | None = None, benchmark_ms: float | None = None) -> dict:
    """Voice verdict. 'benchmark' mode (Balanced) requires a MEASURED pass, never an assumption."""
    c = contract or _profile.current()
    mode = c.get("voice_mode", "disabled")
    if mode == "enabled":
        return {"allowed": True, "reason": "voice enabled by the %s profile"
                                           % c.get("selected_profile")}
    if mode == "optional":
        return {"allowed": True, "optional": True,
                "reason": "voice optional on this profile — off by default, user may enable"}
    if mode == "benchmark":
        if benchmark_ms is None:
            from . import benchmark as _bm
            benchmark_ms = _bm.tts_latency_ms()
        if benchmark_ms is not None and benchmark_ms < 3000:
            return {"allowed": True, "measured_ms": benchmark_ms,
                    "reason": "voice enabled: measured TTS latency %dms < 3000ms" % benchmark_ms}
        return {"allowed": False, "measured_ms": benchmark_ms,
                "reason": "voice deferred: TTS latency %s did not pass the 3000ms benchmark"
                          % (("%dms" % benchmark_ms) if benchmark_ms is not None else "unmeasured")}
    return {"allowed": False, "reason": "voice disabled by the %s profile"
                                        % c.get("selected_profile")}


def allow_pack_build(size_mb: float = 0.0, contract: dict | None = None) -> dict:
    c = contract or _profile.current()
    pol = c.get("knowledge_pack_policy", "disabled")
    if pol == "disabled":
        return {"allowed": False, "reason": "knowledge packs disabled on this profile"}
    if pol == "defer-builds":
        return {"allowed": False, "reason": "pack BUILDS defer on the %s profile (retrieval of "
                                            "ready packs still works)" % c.get("selected_profile")}
    if pol == "bounded-builds" and size_mb > float(c.get("max_intake_job_mb", 0)):
        return {"allowed": False, "reason": "pack build exceeds the %s profile's %d MB bound"
                                            % (c.get("selected_profile"), c.get("max_intake_job_mb"))}
    return {"allowed": True, "reason": "pack build allowed under the %s profile (%s)"
                                       % (c.get("selected_profile"), pol)}
