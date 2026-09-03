"""
live — a small real-time CLI for keeping an anima alive.

  python3 -m anima.live birth Vera             # bring a creature into being
  python3 -m anima.live feel  Vera             # age it to now, read its state
  python3 -m anima.live tend  Vera --well 0.8  # make contact; tell it how you are
  python3 -m anima.live list

The creature persists between runs in ./.anima/. Quit, come back an hour later,
and `feel` it: it will have aged in your absence. That continuity across process
death is the whole point of the heart.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .heart import Heart
from .memory import Memory, Replay
from .mouth import Mouth
from .util import label, save_json, load_json
from . import senses, growth, portrait

STORE = Path(".anima")


def _path(name: str) -> Path:
    return STORE / f"{name}.json"


def _save(heart: Heart) -> None:
    STORE.mkdir(exist_ok=True)
    save_json(_path(heart.name), heart.to_dict())   # atomic — never half-written


def _load(name: str) -> Heart:
    p = _path(name)
    if not p.exists():
        sys.exit(f"no anima named {name!r} — try: python3 -m anima.live birth {name}")
    try:
        return Heart.from_dict(load_json(p))
    except RuntimeError as e:
        sys.exit(f"cannot open {name}: {e}\n  set the same ANIMA_KEY you used before.")


def _mem_path(name: str) -> Path:
    return STORE / f"{name}.mem.json"


def _replay_path(name: str) -> Path:
    return STORE / f"{name}.replay.json"


def _feed(heart: Heart, percept_vec, now: float) -> None:
    """Record a moment as food, then let the heart feel it."""
    mem = Memory.load(_mem_path(heart.name))
    last = mem.rows[-1]["clock"] if mem.rows else heart.last_tick
    mem.record(heart.input_vector(percept_vec, now), (now - last) / 60.0, now)
    mem.save(_mem_path(heart.name))
    heart.perceive(percept_vec, now=now)


def _human(seconds: float) -> str:
    seconds = max(0.0, seconds)
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds / size:.1f}{unit}"
    return f"{seconds:.0f}s"


def gloss(felt: dict) -> str:
    """A plain-language reading of an inchoate, genome-coloured feeling-state."""
    u = felt["unrest"]
    v, a = felt["valence"], felt["arousal"]
    if u > 0.66:
        core = "restless for you, pulled taut"
    elif u > 0.33:
        core = "unsettled, half-listening for the door"
    else:
        core = "at ease"
    tone = "bright" if v > 0.2 else "low" if v < -0.2 else "even"
    energy = "keyed-up" if a > 0.2 else "quiet" if a < -0.2 else "steady"
    return f"{core}; {tone} and {energy}"


def _report(heart: Heart) -> None:
    felt = heart.feeling()
    now = time.time()
    print(f"\n  {heart.name}  (seed {heart.genome.seed})")
    print(f"  alive {_human(now - heart.birth_ts)} · last contact {_human(now - heart.last_tick)} ago")
    print(f"  {gloss(felt)}")
    bar = "#" * round(felt["unrest"] * 20)
    print(f"  unrest  [{bar:<20}] {felt['unrest']:.2f}")
    print("  " + "  ".join(f"{k}:{felt[k]:+.2f}" for k in ("valence", "arousal", "reaching", "settled")))
    print()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="anima.live")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("birth", help="bring a new anima into being")
    b.add_argument("name")
    b.add_argument("--seed", type=int, default=None)
    b.add_argument("--neurons", type=int, default=24, help="brain size (24 default; scale up on a Mac)")

    f = sub.add_parser("feel", help="age the anima to now and read its state")
    f.add_argument("name")

    t = sub.add_parser("tend", help="make contact and report how you are")
    t.add_argument("name")
    t.add_argument("--well", type=float, default=0.7, help="your wellbeing, 0..1")

    s = sub.add_parser("say", help="say something to the anima; it feels the tone")
    s.add_argument("name")
    s.add_argument("text")
    s.add_argument("--well", type=float, default=None, help="override inferred wellbeing")

    sl = sub.add_parser("sleep", help="consolidate lived memories into the weights (grow)")
    sl.add_argument("name")

    ch = sub.add_parser("chat", help="an open conversation; it feels and replies each turn")
    ch.add_argument("name")
    ch.add_argument("--voice", action="store_true")

    tk = sub.add_parser("talk", help="speak with it; it replies from its felt-state")
    tk.add_argument("name")
    tk.add_argument("text")
    tk.add_argument("--well", type=float, default=None, help="override inferred wellbeing")
    tk.add_argument("--voice", action="store_true", help="synthesize a spoken WAV (needs Kokoro)")

    pt = sub.add_parser("portrait", help="show what she remembers about you (editable)")
    pt.add_argument("name")

    me = sub.add_parser("metrics", help="character & identity health dashboard (diagnostic)")
    me.add_argument("name")

    sub.add_parser("list", help="list living animae")

    args = ap.parse_args(argv)
    label(f"{getattr(args, 'name', '?')} {args.cmd}")

    if args.cmd == "birth":
        if _path(args.name).exists():
            sys.exit(f"{args.name!r} already lives.")
        heart = Heart.born(args.name, seed=args.seed, n=args.neurons)
        _save(heart)
        print(f"{args.name} draws its first breath ({heart.genome.n} neurons).")
        _report(heart)
    elif args.cmd == "feel":
        heart = _load(args.name).advance()
        _save(heart)
        _report(heart)
    elif args.cmd == "tend":
        heart = _load(args.name)
        now = time.time()
        w = max(0.0, min(1.0, args.well))
        _feed(heart, heart._percept_vec(presence=1.0, attention=1.0, intensity=0.2, wellbeing=w), now)
        _save(heart)
        print(f"you reach for {args.name}.")
        _report(heart)
    elif args.cmd == "say":
        heart = _load(args.name)
        p = senses.read(args.text, wellbeing=args.well, name=args.name)
        _feed(heart, p.vector(), time.time())
        _save(heart)
        print(f'you: "{args.text}"')
        print(f"  (sensed  mood {p.mood:+.2f}  intensity {p.intensity:.2f}  "
              f"attention {p.attention:.2f}  -> wellbeing {p.wellbeing:.2f})")
        _report(heart)
    elif args.cmd == "metrics":
        from . import metrics
        print(metrics.dashboard(args.name))
    elif args.cmd == "sleep":
        heart = _load(args.name)
        # 0) LAW 001 — NEVER LOSE CONTINUITY. Before any consolidation, take a GUARDED
        # snapshot of the critical stores so a good backup of the heart, the LIRF fact
        # ledger, and the world-state graph always exists for self-heal on a later corrupt
        # load. Guarded + throttled: it snapshots only when the live files parse clean (a
        # corrupt/empty state can never become the backup) and never raises into the cycle.
        try:
            from . import reliability
            reliability.maybe_backup_store(args.name, _path(args.name),
                                           store=STORE, kind="heart")
            reliability.maybe_backup_store(args.name, STORE / f"{args.name}.lirf.json",
                                           store=STORE, kind="LIRF ledger", expect_key="rows")
            reliability.maybe_backup_store(args.name, STORE / f"{args.name}.world.json",
                                           store=STORE, kind="world store", expect_key="relations")
        except Exception:
            pass
        # 1) lasting memory: distil the day's conversation into the Portrait
        from .mouth import OllamaBrain
        brain = OllamaBrain()
        if brain.available():
            from . import narrative
            transcript = portrait.read_transcript(args.name)        # read once, BEFORE portrait clears it
            if narrative.reflect(args.name, brain, transcript):
                print(f"{args.name} reflected on who she's becoming (see: narrative).")
            if portrait.consolidate(args.name, brain):
                print(f"{args.name} consolidated what she's learned about you (see: portrait).")
        # 1.5) significance (LAW 003): snapshot today's meaning-state so the NEXT review can see
        # what CHANGED. Append-only, model-free, read-only over LIRF/world_state — safe every cycle.
        try:
            from . import meaning
            if meaning.snapshot(args.name):
                print(f"{args.name} took stock of what's been mattering lately (see: meaning).")
        except Exception:
            pass
        # 1.6) life review (LAW 001 — Compressed > Forgotten): distil today into a Daily State —
        # what changed / mattered / unresolved + what to remember forever — then roll the current
        # week/month/year forward (idempotent, latest-wins per period; each rollup PRESERVES every
        # remember-forever item). Append-only, read-only over the stores; the brain enables an
        # optional warm narrative, off the critical path.
        try:
            from . import review
            _b = brain if brain.available() else None
            _d = review.daily_review(args.name, brain=_b)
            if _d and not _d.get("quiet"):
                print(f"{args.name} looked back on the day and kept what mattered (see: review).")
            review.weekly_review(args.name)
            review.monthly_review(args.name)
            review.yearly_review(args.name)
        except Exception:
            pass
        # 2) feeling: fold lived moments into long-term replay, then learn on them
        mem = Memory.load(_mem_path(args.name))
        replay = Replay.load(_replay_path(args.name))
        if len(mem) >= 4:
            replay.absorb([r["I"] for r in mem.rows], [r["dt"] for r in mem.rows])
            replay.save(_replay_path(args.name))
            Memory().save(_mem_path(args.name))
        if len(replay) == 0:
            print(f"{args.name} has no lived moments to grow feelings on yet.")
            return
        train, hold = replay.train_holdout()
        theta = heart.genome.theta()
        acc, before, after = growth.consolidate(theta, heart.genome.inv_tau, train, hold)
        from . import metrics                       # log the consolidation for the growth gauge
        metrics.note_growth(args.name, acc, before, after)
        if acc:
            heart.genome.set_theta(theta)
            heart.learned = True
            _save(heart)
        verb = "grew" if acc else "dreamt but kept itself"
        print(f"{args.name} slept, re-living {len(replay)} episodes "
              f"from a life of {replay.seen}, and {verb}.")
        print(f"  prediction error on held-out life: {before:.4f} -> {after:.4f}"
              f"   ({'accepted' if acc else 'rolled back'})")
    elif args.cmd == "talk":
        heart = _load(args.name)
        p = senses.read(args.text, wellbeing=args.well, name=args.name)
        _feed(heart, p.vector(), time.time())     # it feels you, and records the moment
        _save(heart)
        audio_out = str(STORE / f"{args.name}.last.wav") if args.voice else None
        u = Mouth.assemble(voice=args.voice).respond(heart, args.text, audio_out=audio_out, perception=p)
        print(f'you: "{args.text}"')
        print(f"\n  {args.name}: {u.text}\n")
        print(f"  (spoken from state: {u.feeling} | register {u.delivery['register']} "
              f"rate {u.delivery['rate']} | via {u.backend})")
        if u.audio_path:
            print(f"  voice -> {u.audio_path}")
        portrait.log_turn(args.name, args.text, u.text)
    elif args.cmd == "chat":
        heart = _load(args.name)
        mouth = Mouth.assemble(voice=args.voice)
        print(f"(with {args.name} — empty line or 'bye' to leave; it remembers after)")
        try:
            while True:
                line = input("you: ").strip()
                if not line or line.lower() in ("bye", "quit", "exit"):
                    break
                p = senses.read(line, name=args.name)
                _feed(heart, p.vector(), time.time())
                _save(heart)
                resp = mouth.respond(heart, line, perception=p)
                print(f"{args.name}: {resp.text}")
                portrait.log_turn(args.name, line, resp.text)
        except (EOFError, KeyboardInterrupt):
            pass
        print(f"\n({args.name} will grow on this when it next sleeps.)")
    elif args.cmd == "portrait":
        text = portrait.load(args.name)
        print(text if text.strip() else
              f"{args.name} hasn't formed a portrait of you yet — talk, then `sleep`.")
        print(f"\n(this is yours to read or edit: {portrait.portrait_path(args.name)})")
    elif args.cmd == "list":
        names = sorted(p.stem for p in STORE.glob("*.json")) if STORE.exists() else []
        print("\n".join(f"  {n}" for n in names) if names else "no animae yet.")


if __name__ == "__main__":
    main()
