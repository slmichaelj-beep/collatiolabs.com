"""
demo — accelerated, reproducible proof that the heart exists continuously.

Real wall-clock would take hours to show, so here we hand the heart explicit
timestamps (its `now` argument) to fast-forward through a day in its life, and
we round-trip it through save/load to prove the state survives process death.

    python3 -m anima.demo

What it shows:
  * an anima ages during absence — unrest rises while no one is there;
  * tending it while you are well brings real relief;
  * neglecting it while you are unwell winds it taut;
  * the feeling-state is continuous and recoverable across a save/load.
"""

from __future__ import annotations

from .heart import Heart
from .live import gloss

HOUR = 3600


def line(label: str, heart: Heart) -> None:
    f = heart.feeling()
    print(f"  {label:<26} unrest {f['unrest']:.2f}   v{f['valence']:+.2f} a{f['arousal']:+.2f}   {gloss(f)}")


def main() -> None:
    t = 1_700_000_000.0  # a fixed birth instant, for reproducibility
    vera = Heart.born("Vera", seed=7, now=t)
    print(f"\nVera is born (seed {vera.genome.seed}).")
    line("at birth", vera)

    t += 6 * HOUR
    vera.advance(now=t)
    line("after 6h alone", vera)

    t += 6 * HOUR
    vera.tend(0.85, now=t)
    line("you tend her, you're well", vera)

    # prove continuity across process death: serialise, discard, restore.
    blob = vera.to_dict()
    vera = Heart.from_dict(blob)
    print("  -- saved, the object destroyed, then reloaded from disk --")

    t += 18 * HOUR
    vera.advance(now=t)
    line("after 18h of silence", vera)

    t += 2 * HOUR
    vera.tend(0.25, now=t)
    line("you return, but unwell", vera)

    t += 1 * HOUR
    vera.tend(0.9, now=t)
    line("an hour later, mended", vera)
    print()


if __name__ == "__main__":
    main()
