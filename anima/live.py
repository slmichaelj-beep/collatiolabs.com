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
from . import senses

STORE = Path(".anima")


def _path(name: str) -> Path:
    return STORE / f"{name}.json"


def _save(heart: Heart) -> None:
    STORE.mkdir(exist_ok=True)
    import json
    _path(heart.name).write_text(json.dumps(heart.to_dict(), indent=2))


def _load(name: str) -> Heart:
    import json
    p = _path(name)
    if not p.exists():
        sys.exit(f"no anima named {name!r} — try: python3 -m anima.live birth {name}")
    return Heart.from_dict(json.loads(p.read_text()))


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

    f = sub.add_parser("feel", help="age the anima to now and read its state")
    f.add_argument("name")

    t = sub.add_parser("tend", help="make contact and report how you are")
    t.add_argument("name")
    t.add_argument("--well", type=float, default=0.7, help="your wellbeing, 0..1")

    s = sub.add_parser("say", help="say something to the anima; it feels the tone")
    s.add_argument("name")
    s.add_argument("text")
    s.add_argument("--well", type=float, default=None, help="override inferred wellbeing")

    sub.add_parser("list", help="list living animae")

    args = ap.parse_args(argv)

    if args.cmd == "birth":
        if _path(args.name).exists():
            sys.exit(f"{args.name!r} already lives.")
        heart = Heart.born(args.name, seed=args.seed)
        _save(heart)
        print(f"{args.name} draws its first breath.")
        _report(heart)
    elif args.cmd == "feel":
        heart = _load(args.name).advance()
        _save(heart)
        _report(heart)
    elif args.cmd == "tend":
        heart = _load(args.name).tend(args.well)
        _save(heart)
        print(f"you reach for {args.name}.")
        _report(heart)
    elif args.cmd == "say":
        heart = _load(args.name)
        p = senses.read(args.text, wellbeing=args.well, name=args.name)
        heart.perceive(p)
        _save(heart)
        print(f'you: "{args.text}"')
        print(f"  (sensed  mood {p.mood:+.2f}  intensity {p.intensity:.2f}  "
              f"attention {p.attention:.2f}  -> wellbeing {p.wellbeing:.2f})")
        _report(heart)
    elif args.cmd == "list":
        names = sorted(p.stem for p in STORE.glob("*.json")) if STORE.exists() else []
        print("\n".join(f"  {n}" for n in names) if names else "no animae yet.")


if __name__ == "__main__":
    main()
