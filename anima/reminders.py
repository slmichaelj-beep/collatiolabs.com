"""
reminders — Vera's tiered reminder -> call escalation, Mac-side.

The idea: Vera reminds you of something (take your meds, leave for the dentist).
A reminder is GENTLE first — a push notification with a "👍 Got it" button. If you
tap it, you're done. If you DON'T acknowledge within a short window, she escalates:
she CALLS you and says the reminder out loud, in her real voice. The escalation is
the safety net for the things that actually matter.

This module is the STATE MACHINE for that, and it is fully real and locally testable
WITHOUT any Apple account, device, or keys:

    schedule(text, *, ack_window_min=5, place=None)   # mint id, (stub) push, persist
    acknowledge(reminder_id)                           # you tapped 👍  -> cancel the call
    tick(now=None)                                     # past deadline & unacked -> (stub) CALL
    run_loop(interval=30)                              # a thread/launchd checker

Everything about TIMING, PERSISTENCE, and "ack cancels the call" is real. The ONLY
parts that are stubbed are the two DELIVERY primitives that need Apple:

    _deliver_push(record)   # an APNs alert push carrying the text + id + 👍 action
    _deliver_call(record)   # a VoIP push (PushKit) that wakes the app to start the call

Both just log "would …" today and return; the machine around them is finished. They
are wired in Phase 3 when the APNs .p8 / VoIP key + iOS app exist (see their
docstrings). Until then this whole file runs, and is tested, with no Apple at all.

State lives in .anima/reminders.json (gitignored, atomic + encrypted-at-rest via
util.save_json — same as the rest of her memory) so a pending reminder survives a
server restart: a reboot must not silently drop a reminder you were counting on.

The spoken escalation reuses proactive.compose_briefing (Vera's real voice — persona,
dials, honesty rail, live heart-state), NEVER a detached prompt — the same rule the
morning briefing follows. We just hand it `extra_guidance` so she delivers THIS
reminder instead of a day briefing, and (best-effort) render it to audio the call can
play. The voice stack is optional: an escalation never blocks on it.

CLI (no Apple needed — drives the real machine, watches the stubs fire):
    python3 -m anima.reminders add "take your meds" --window-min 5
    python3 -m anima.reminders list
    python3 -m anima.reminders ack <reminder_id>
    python3 -m anima.reminders tick
    python3 -m anima.reminders loop
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .util import load_json, save_json

STORE = Path(".anima")
_STATE = STORE / "reminders.json"

# One lock guards the read-modify-write of the reminders file. The server is
# threaded and a ~30s scheduler loop may call tick() while a request thread calls
# acknowledge(); serialising keeps the JSON and the in-memory view consistent.
_lock = threading.RLock()


# --- record -----------------------------------------------------------------

@dataclass
class Reminder:
    id: str
    text: str
    created: float                  # epoch when scheduled
    deadline: float                 # epoch after which we escalate to a call
    place: Optional[str] = None     # optional human place label (e.g. "the dentist")
    state: str = "pending"          # pending | acknowledged | escalated
    acked_at: Optional[float] = None
    escalated_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Reminder":
        # tolerate older/sparser rows without crashing the whole store
        return cls(
            id=str(d.get("id", "")),
            text=str(d.get("text", "")),
            created=float(d.get("created", 0.0)),
            deadline=float(d.get("deadline", 0.0)),
            place=d.get("place"),
            state=str(d.get("state", "pending")),
            acked_at=d.get("acked_at"),
            escalated_at=d.get("escalated_at"),
        )


# --- persistence (atomic + optionally encrypted, like the rest of .anima) ---

def _load() -> dict:
    """reminder_id -> Reminder. Missing/corrupt file -> empty (never crash a restart)."""
    raw = load_json(_STATE, default=None)
    out: dict = {}
    if isinstance(raw, list):
        for row in raw:
            try:
                r = Reminder.from_dict(row)
                if r.id:
                    out[r.id] = r
            except Exception:
                continue
    return out


def _save(items: dict) -> None:
    STORE.mkdir(exist_ok=True)
    save_json(_STATE, [r.to_dict() for r in items.values()])


# =====================================================================
#  DELIVERY PRIMITIVES — THE ONLY APPLE-DEPENDENT CODE. BOTH ARE STUBS.
# =====================================================================
# Today these just log "would …" so the whole escalation machine runs and is testable
# with no Apple account/keys/device. Swap ONLY these two when the Apple side exists;
# nothing else in this file changes. The exact stub boundary is HERE.

def _deliver_push(reminder: "Reminder") -> None:
    """STUB — wired in Phase 3 when the APNs .p8 / VoIP key + iOS app exist.

    Will send an APNs ALERT push carrying the reminder text + id + a "👍 Got it"
    action (UNNotificationAction). Tapping that action makes the app POST
    /acknowledge {reminder_id}, which cancels the escalation. To make this real:
      * an APNs auth key (.p8) + its Key ID            (Apple Developer > Keys)
      * the Apple Developer Team ID
      * the iOS app's bundle id                         (apns-topic)
      * the device's current alert push token — the app POSTs it to /device
        (see server.py:_store_device), read here as the APNs device token.
      * a notification category whose 👍 action the app registers; put reminder_id
        in the payload so the handler can POST /acknowledge with it.
    """
    print(f"[reminders] would push: {reminder.text} [👍 Got it] id={reminder.id}",
          file=sys.stderr)


def _deliver_call(reminder: "Reminder") -> None:
    """STUB — wired in Phase 3 when the APNs .p8 / VoIP key + iOS app exist.

    Will send a VoIP (PushKit) push so the iOS app reports an incoming call to
    CallKit and connects audio to Vera, who speaks the reminder in her real voice.
    This is where the VoIP push to call_server (anima/call_server.py — the aiortc
    WebRTC call server on :8766) goes once the Apple keys exist. To make this real:
      * the SAME APNs key, apns-push-type: voip, to the app's VoIP push token (also
        delivered via /device).
      * the spoken line is composed in Vera's real voice + rendered to audio here
        (see _compose_spoken_reminder); the call plays that audio / streams TTS.
    """
    print(f"[reminders] would CALL: {reminder.text}", file=sys.stderr)


# --- composing the spoken escalation (Vera's real voice, never a raw prompt) ---

def _compose_spoken_reminder(reminder: "Reminder", name: str = "Vera"):
    """Render THIS reminder in Vera's real voice (and best-effort to audio), reusing
    the proactive machinery (persona, dials, honesty rail, heart-state). Returns
    (spoken_text, audio_path). Degrades to the raw text + no audio if composition or
    synthesis can't run (no Ollama / no synth) — an escalation never blocks on voice.

    Used by _deliver_call once Apple keys exist; safe to call today (it just won't be
    pushed anywhere). Kept out of tick()'s hot path's failure surface via try/except.
    """
    text, place = reminder.text, reminder.place
    spoken, audio_path = text, None
    try:
        from . import context_gather, proactive
        guidance = (
            "RIGHT NOW you are CALLING them because a reminder they asked for went "
            "unacknowledged — they didn't tap to confirm, so you're following up out "
            "loud, gently but clearly. Lead with the reminder itself in one or two "
            "spoken sentences. The reminder is: \"" + text + "\""
            + (f" (this is about {place})" if place else "")
            + ". Do not invent any other details; just deliver this and a touch of your "
            "own warmth."
        )
        # No day-context needed for a reminder call; pass an empty DayContext so the
        # composer doesn't gather weather/calendar. She speaks from the guidance.
        empty = context_gather.DayContext(
            when=time.time(),
            weather=context_gather.Weather(ok=False, note="not needed for a reminder"),
            calendar=context_gather.Calendar(ok=False, events=[],
                                             note="not needed for a reminder"),
        )
        b = proactive.compose_briefing(name, ctx=empty, extra_guidance=guidance)
        spoken = (b.text or text).strip() or text
        try:
            audio_path = proactive.render_audio(b, name=name)
        except Exception as e:
            print(f"[reminders] audio synth failed ({e}); call would play TTS later",
                  file=sys.stderr)
    except Exception as e:
        # composition unavailable (e.g. no brain) — still escalate with the raw text
        print(f"[reminders] voice composition unavailable ({e}); using raw reminder text",
              file=sys.stderr)
    return spoken, audio_path


# --- public API -------------------------------------------------------------

def schedule(text: str, *, ack_window_min: float = 5.0,
             place: Optional[str] = None, name: str = "Vera") -> str:
    """Mint a reminder_id, (STUB) push it with a 👍 action, and persist it pending with
    a deadline = now + ack_window_min minutes. Returns the reminder_id (a uuid).

    The pending record {id, text, deadline, created} is saved to .anima/reminders.json
    so it survives a restart. `ack_window_min` may be fractional (e.g. ~0.017 ≈ 1s) —
    the in-process test uses a tiny window to exercise the deadline without a long sleep.
    """
    text = str(text or "").strip()
    if not text:
        raise ValueError("a reminder needs non-empty text")
    now = time.time()
    rid = uuid.uuid4().hex
    r = Reminder(
        id=rid,
        text=text,
        created=now,
        deadline=now + float(ack_window_min) * 60.0,
        place=(str(place).strip() or None) if place else None,
        state="pending",
    )
    with _lock:
        items = _load()
        # deliver FIRST so a push failure doesn't leave a phantom pending row; the
        # stub never fails, but a real _deliver_push might, and we want to know.
        _deliver_push(r)
        items[rid] = r
        _save(items)
    return rid


# Descriptive alias — nothing currently imports it, but `schedule` collides with a
# common verb, so keep the explicit name available for callers that prefer it.
schedule_reminder = schedule


def acknowledge(reminder_id: str) -> bool:
    """You tapped 👍 (or POST /acknowledge). Remove the pending record so tick() will
    NOT escalate it (cancels the call). Returns True if a pending reminder with that id
    was found and acknowledged, False otherwise (already acked/escalated/unknown).
    """
    rid = str(reminder_id or "")
    with _lock:
        items = _load()
        r = items.get(rid)
        if r is None or r.state != "pending":
            return False
        r.state = "acknowledged"
        r.acked_at = time.time()
        items[rid] = r
        _save(items)
    return True


def tick(now: Optional[float] = None, *, name: str = "Vera") -> list:
    """Drive escalation. For every PENDING reminder whose deadline has passed and which
    has NOT been acknowledged: (STUB) trigger the escalation CALL, clear it (mark it
    escalated), and persist. Idempotent — an already escalated/acknowledged reminder is
    never touched again. Returns the list of reminder ids escalated on this tick.

    Call it from a ~30s scheduler loop (run_loop) and/or a launchd checker.
    """
    now = time.time() if now is None else now
    escalated: list = []
    with _lock:
        items = _load()
        due = [r for r in items.values() if r.state == "pending" and now >= r.deadline]
        for r in due:
            _deliver_call(r)            # STUB today (this is where the VoIP push goes)
            r.state = "escalated"
            r.escalated_at = now
            items[r.id] = r
            escalated.append(r.id)
        if escalated:
            _save(items)
    return escalated


def pending() -> list:
    """All reminders still pending (not yet acked or escalated), soonest deadline first."""
    with _lock:
        items = _load()
    out = [r for r in items.values() if r.state == "pending"]
    out.sort(key=lambda r: r.deadline)
    return out


def all_reminders() -> list:
    """Every reminder on record (any state), newest first — for `list` / inspection."""
    with _lock:
        items = _load()
    return sorted(items.values(), key=lambda r: r.created, reverse=True)


def clear(reminder_id: str) -> bool:
    """Remove a reminder entirely (any state). Returns True if one was removed."""
    rid = str(reminder_id or "")
    with _lock:
        items = _load()
        if rid not in items:
            return False
        items.pop(rid, None)
        _save(items)
    return True


def prune(*, keep_terminal_sec: float = 86400.0, now: Optional[float] = None) -> int:
    """Drop acknowledged/escalated reminders older than keep_terminal_sec (default 1
    day) so the file doesn't grow without bound. Pending reminders are never pruned.
    Returns how many were removed."""
    now = time.time() if now is None else now
    removed = 0
    with _lock:
        items = _load()
        for rid, r in list(items.items()):
            if r.state == "pending":
                continue
            ref = r.escalated_at or r.acked_at or r.created
            if ref and (now - ref) > keep_terminal_sec:
                items.pop(rid, None)
                removed += 1
        if removed:
            _save(items)
    return removed


# --- the simple checker loop (a thread, or `python3 -m anima.reminders loop`) ----

def run_loop(interval: float = 30.0, *, name: str = "Vera",
             stop: Optional["threading.Event"] = None) -> None:
    """Call tick() forever every `interval` seconds. A slow/failing tick is guarded so
    it can never crash the loop — escalation must keep running. Meant for a daemon
    thread inside the server (start_background_loop) or a foreground launchd checker; a
    launchd `tick` job is the alternative for machines that sleep — both drive the same
    state machine.
    """
    print(f"[reminders] checker loop every {interval:.0f}s for {name}", file=sys.stderr)
    while stop is None or not stop.is_set():
        try:
            fired = tick(name=name)
            if fired:
                print(f"[reminders] escalated {len(fired)}: {', '.join(fired)}",
                      file=sys.stderr)
        except Exception as e:
            # a single bad tick must not kill the loop
            print(f"[reminders] tick failed: {e}", file=sys.stderr)
        # interruptible sleep so `stop` is honored promptly
        if stop is not None:
            if stop.wait(interval):
                break
        else:
            time.sleep(interval)


def start_background_loop(interval: float = 30.0, name: str = "Vera") -> "threading.Event":
    """Start run_loop on a daemon thread; return a stop Event. The server can call this
    once at startup so escalation runs without a separate launchd job."""
    stop = threading.Event()
    t = threading.Thread(target=run_loop, args=(interval,),
                         kwargs={"name": name, "stop": stop}, daemon=True)
    t.start()
    return stop


# --- CLI: exercise the real machine with no Apple ---------------------------

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.reminders",
        description="Tiered reminder -> call escalation (delivery stubbed; timing/persistence real).")
    ap.add_argument("--name", default="Vera")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="schedule a reminder (sends the STUB push now)")
    a.add_argument("text")
    a.add_argument("--window-min", type=float, default=5.0, help="ack window in minutes")
    a.add_argument("--place", default="", help="optional place label")

    sub.add_parser("list", help="show all reminders and their state")
    k = sub.add_parser("ack", help="acknowledge a reminder by id (cancels its call)")
    k.add_argument("id")
    sub.add_parser("tick", help="run one escalation pass now")
    sub.add_parser("loop", help="run the checker loop in the foreground")
    c = sub.add_parser("clear", help="remove a reminder by id")
    c.add_argument("id")

    args = ap.parse_args(argv)
    if args.cmd == "add":
        rid = schedule(args.text, ack_window_min=args.window_min,
                       place=(args.place or None), name=args.name)
        # find its deadline to report the countdown
        secs = 0.0
        for r in all_reminders():
            if r.id == rid:
                secs = max(0.0, r.deadline - time.time())
                break
        print(f"scheduled {rid}: \"{args.text}\" — escalates in ~{secs:.0f}s if not acked")
    elif args.cmd == "list":
        rows = all_reminders()
        if not rows:
            print("(no reminders)")
        for r in rows:
            when = time.strftime("%H:%M:%S", time.localtime(r.deadline))
            extra = f" (escalates {when})" if r.state == "pending" else ""
            print(f"  {r.id}  [{r.state}]  \"{r.text}\"{extra}")
    elif args.cmd == "ack":
        print("acknowledged — no call will happen." if acknowledge(args.id)
              else "nothing pending with that id.")
    elif args.cmd == "tick":
        fired = tick(name=args.name)
        print(f"escalated: {', '.join(fired)}" if fired else "nothing due.")
    elif args.cmd == "loop":
        run_loop(name=args.name)
    elif args.cmd == "clear":
        print("removed." if clear(args.id) else "no such reminder.")


if __name__ == "__main__":
    _main()
