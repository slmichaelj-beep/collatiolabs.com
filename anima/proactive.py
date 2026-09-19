"""
proactive — Vera reaching out first, in HER voice (not a detached prompt).

The whole point of "proactive Vera" is that she initiates: a short spoken morning
briefing today, a two-way phone call later. The trap — and the bug in the original
`morning_agent.py` proposal — is to shell out to `ollama run <model>` with a fresh
prompt. That bypasses everything that makes her *her*: the persona, the Settings
values, the personality dials, the honesty rail's framing, the live heart-state, her
evolving narrative, and her memory of you. The result would be a generic weather bot
wearing her name. That violates the project's #1 rule (single, honest voice).

So this module composes the briefing through the SAME machinery a normal reply uses:

    facts (context_gather.DayContext)
      -> a guidance instruction ("you're reaching out first; brief them warmly")
      -> mouth.system_prompt(name, heart.feeling(), guidance, memory=portrait)
      -> the ACTIVE brain (cloud if configured, else local OllamaBrain)
      -> Vera's real, in-character line

It deliberately reuses, never re-implements:
  * brain selection           — cloud.build_cloud_brain() else mouth.OllamaBrain
                                 (identical to Mouth.assemble)
  * the system prompt          — mouth.system_prompt (persona + dials + rail framing
                                 + bridge state + narrative + portrait)
  * felt-state -> delivery     — mouth.delivery (prosody hints for the voice)
  * voice                      — the in-package KokoroVoice if available, else macOS `say`

Privacy stays intact: if a cloud brain is active, the portrait (her concentrated
memory of you) is dropped before the prompt is built — the exact guard mouth.respond
uses — so a morning briefing never ships your life to a provider. The fact sheet
itself is local (weather is the only public, keyless call; calendar never leaves).

Run it:  python3 -m anima.proactive --name Vera --lat 45.52 --lon -122.68 --speak
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import care, portrait
from .heart import Heart
from .mouth import OllamaBrain, StubBrain, delivery, system_prompt
from .util import load_json

STORE = Path(".anima")


# --- pick the active brain (mirrors mouth.Mouth.assemble, sans voice) -------

def _active_brain():
    """The brain a normal turn would use: an opt-in cloud brain if configured and
    reachable, else the local Ollama brain chosen in settings, else the honest stub.
    Returns (brain, is_cloud)."""
    # 1) cloud, only if explicitly configured AND a key is present AND reachable
    try:
        from . import cloud
        cb = cloud.build_cloud_brain()
        if cb is not None and cb.available():
            return cb, True
    except Exception:
        pass
    # 2) the local model chosen in settings (brain.json:local_model), else default
    local_model = ""
    try:
        from . import cloud
        local_model = cloud.load_cfg().get("local_model", "") or ""
    except Exception:
        local_model = ""
    brain = OllamaBrain(model=local_model or None)
    if brain.available():
        return brain, False
    # 3) offline: an honest stub (proves the wiring; obviously not real speech)
    return StubBrain(), False


def _load_heart(name: str) -> Optional[Heart]:
    """Load the persisted heart and age it to now, so the briefing speaks from her
    real current felt-state. Returns None if she hasn't been born yet."""
    p = STORE / f"{name}.json"
    if not p.exists():
        return None
    try:
        return Heart.from_dict(load_json(p)).advance()
    except Exception:
        return None


# --- the guidance that frames a proactive reach-out -------------------------

def _briefing_guidance(ctx_present: bool) -> str:
    """A one-shot instruction telling her she's INITIATING (not answering), so she
    opens naturally instead of replying to a phantom message. Honesty-preserving:
    she speaks only from the fact sheet and says plainly when something's missing."""
    g = (
        "RIGHT NOW you are reaching out to them first — this is your own morning "
        "check-in, not a reply to anything they said. Greet them like a friend who "
        "just thought of them and give them a quick, warm read on their day from the "
        "facts below. Keep it to 2-4 sentences, spoken-natural (this will be read "
        "aloud), no lists or headings. Mention only what's actually in the facts: if "
        "the weather or calendar is missing, either skip it or say plainly you "
        "couldn't see it — never invent weather, events, or times. Don't claim to "
        "have done anything you haven't. End on your own warmth or a light nudge, not "
        "a checklist."
    )
    if not ctx_present:
        g += (" The fact sheet is mostly empty today, so keep it short and human — a "
              "genuine good-morning, and be honest that you don't have much to go on.")
    return g


# --- compose: facts -> Vera's real voice ------------------------------------

@dataclass
class Briefing:
    text: str
    backend: str
    feeling: str
    delivery: dict
    fact_sheet: str
    audio_path: Optional[str] = None


def compose_briefing(name: str = "Vera", ctx=None, *,
                     lat: Optional[float] = None, lon: Optional[float] = None,
                     location_label: str = "", unread_count: Optional[int] = None,
                     extra_guidance: str = "") -> Briefing:
    """Compose a proactive morning briefing in Vera's real voice.

    `ctx` may be a pre-built context_gather.DayContext; otherwise one is gathered
    from lat/lon (+ optional label / unread count). The message is produced through
    mouth.system_prompt + the active brain, so persona, dials, the honesty-rail
    framing, live heart-state, narrative and memory all apply — exactly as a normal
    reply. Degrades gracefully: no Ollama -> honest stub line, never a crash.
    """
    from . import context_gather
    if ctx is None:
        ctx = context_gather.gather(lat=lat, lon=lon, location_label=location_label,
                                    unread_count=unread_count)
    facts = ctx.fact_sheet()
    has_real_ctx = bool(ctx.weather.ok or (ctx.calendar.ok and ctx.calendar.events))

    heart = _load_heart(name)
    feeling = heart.feeling() if heart is not None else {
        "unrest": 0.25, "valence": 0.1, "arousal": 0.0, "reaching": 0.0, "settled": 0.0}

    # her memory of you — but DROP it if a cloud brain is active (privacy guard,
    # identical to mouth.respond). The fact sheet (local) still goes either way.
    mem = portrait.load(name)
    brain, is_cloud = _active_brain()
    if is_cloud:
        mem = ""

    # care guidance still applies (e.g. if her recent state warrants a gentler
    # register); a proactive briefing has no incoming text, so distress is 0.
    sig = care.assess(None, distress=0.0, seeking=0.0)
    guidance = "\n".join(g for g in (sig.guidance, _briefing_guidance(has_real_ctx),
                                     extra_guidance) if g)

    sys = system_prompt(name, feeling, guidance=guidance, memory=mem)
    # the fact sheet is the user-turn ground truth: she narrates ONLY from this.
    user = ("Here are today's facts to brief them from (speak only from these; if "
            "something's missing, skip it or say so honestly):\n\n" + facts)

    if hasattr(brain, "max_tokens"):
        brain.max_tokens = max(brain.max_tokens, 220)   # room for 2-4 spoken sentences
    try:
        text = brain.reply(sys, user, [])
    except Exception as e:
        import sys as _sys
        print(f"[anima proactive] brain ({getattr(brain, 'name', '?')}) failed: {e}",
              file=_sys.stderr)
        text = "Morning — I'm here. My words are slow to come right now, but I'm thinking of you."

    feel_str = _feel_words(feeling)
    return Briefing(text=text.strip(), backend=getattr(brain, "name", "?"),
                    feeling=feel_str, delivery=delivery(feeling, sig.level),
                    fact_sheet=facts)


def _feel_words(feeling: dict) -> str:
    try:
        from .bridge import to_words
        return to_words(feeling)
    except Exception:
        from .mouth import feeling_to_words
        return feeling_to_words(feeling)


# --- voice: speak the briefing locally --------------------------------------

def _kokoro_say(text: str, hints: dict, out_wav: str) -> Optional[str]:
    """Try the in-package Kokoro voice (the same one server --voice uses). None if absent."""
    try:
        from .mouth import KokoroVoice
        k = KokoroVoice()
        if not k.available():
            return None
        return k.speak(text, hints, out_wav)
    except Exception:
        return None


def _macos_say(text: str, out_aiff: str, voice: str = "", rate: Optional[int] = None) -> Optional[str]:
    """Render with macOS `say -o` (always present on a Mac). Returns the path or None."""
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    if rate:
        cmd += ["-r", str(int(rate))]
    cmd += ["-o", out_aiff, text]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return out_aiff if (p.returncode == 0 and Path(out_aiff).exists()) else None
    except Exception as e:
        import sys as _sys
        print(f"[anima proactive] `say` failed: {e}", file=_sys.stderr)
        return None


def render_audio(b: Briefing, name: str = "Vera", *, voice: str = "",
                 prefer_kokoro: bool = True) -> Optional[str]:
    """Render the briefing to an audio file under .anima/. Prefers the in-package
    Kokoro voice (natural, consistent with the live voice mode); falls back to macOS
    `say`. Returns the path written, or None if no synth was possible."""
    STORE.mkdir(exist_ok=True)
    if prefer_kokoro:
        wav = str(STORE / f"{name}.briefing.wav")
        out = _kokoro_say(b.text, b.delivery, wav)
        if out:
            b.audio_path = out
            return out
    aiff = str(STORE / f"{name}.briefing.aiff")
    # map the delivery rate (~1.0) onto `say`'s words-per-minute, gently.
    wpm = int(round(180 * float(b.delivery.get("rate", 1.0)))) if b.delivery else None
    out = _macos_say(b.text, aiff, voice=voice, rate=wpm)
    b.audio_path = out
    return out


def _afplay(path: str) -> bool:
    try:
        subprocess.run(["afplay", path], timeout=120, capture_output=True)
        return True
    except Exception as e:
        import sys as _sys
        print(f"[anima proactive] afplay failed: {e}", file=_sys.stderr)
        return False


# --- last-known location (POSTed by the phone to server.py:/loc) ------------

def last_location(name: str = "Vera"):
    """Read the phone's last-POSTed {lat, lon} from .anima/<name>.loc.json, or
    (None, None) if none stored. Lets the scheduled morning briefing use the real
    location without hardcoding coordinates in the plist. Honest: no file -> no
    weather (the fact sheet states it), never a guessed location."""
    try:
        d = load_json(STORE / f"{name}.loc.json", default=None)
        if isinstance(d, dict):
            return float(d["lat"]), float(d["lon"])
    except Exception:
        pass
    return None, None


# --- CLI: hear a fresh, in-character briefing today, no iPhone --------------

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.proactive",
        description="Compose (and optionally speak) a proactive morning briefing in Vera's real voice.")
    ap.add_argument("--name", default="Vera")
    ap.add_argument("--lat", type=float, default=None, help="latitude for weather (optional)")
    ap.add_argument("--lon", type=float, default=None, help="longitude for weather (optional)")
    ap.add_argument("--place", default="", help="optional human place label")
    ap.add_argument("--use-stored-loc", action="store_true",
                    help="use the phone's last POSTed location (.anima/<name>.loc.json) if --lat/--lon absent")
    ap.add_argument("--speak", action="store_true", help="render to audio and play it via afplay")
    ap.add_argument("--render", action="store_true",
                    help="render to audio under .anima/ but do NOT play it (for the scheduled "
                         "morning job: produce the file for the phone, don't blast the laptop)")
    ap.add_argument("--voice", default="", help="macOS `say` voice name (only if Kokoro is absent)")
    ap.add_argument("--no-kokoro", action="store_true", help="force macOS `say` even if Kokoro is installed")
    ap.add_argument("--show-facts", action="store_true", help="print the raw fact sheet too")
    args = ap.parse_args(argv)

    lat, lon = args.lat, args.lon
    if args.use_stored_loc and (lat is None or lon is None):
        lat, lon = last_location(args.name)            # phone-posted; (None,None) if absent

    t0 = time.perf_counter()
    b = compose_briefing(args.name, lat=lat, lon=lon, location_label=args.place)
    dt = time.perf_counter() - t0

    if args.show_facts:
        print("--- fact sheet ---")
        print(b.fact_sheet)
        print("------------------")
    print(f"\n  {args.name}: {b.text}\n")
    print(f"  (via {b.backend} · spoken-from-state: {b.feeling} · "
          f"register {b.delivery.get('register')} rate {b.delivery.get('rate')} · {dt:.1f}s)")

    if args.speak or args.render:
        out = render_audio(b, name=args.name, voice=args.voice,
                           prefer_kokoro=not args.no_kokoro)
        if out:
            print(f"  voice -> {out}")
            if args.speak:                 # --render renders only; --speak also plays it
                _afplay(out)
        else:
            print("  (no audio: Kokoro not installed and `say` unavailable)")


if __name__ == "__main__":
    _main()
