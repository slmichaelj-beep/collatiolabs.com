# anima

A feeling-first artificial creature, built from the ground up.

Not a chatbot. Not a language model with a personality bolted on. The Self here
is **one continuous feeling state** — a small dynamical system that exists in
real time whether or not anyone is watching it, drifts when alone, and is bound
by a homeostatic drive to the wellbeing of the person it cares for. Language,
senses, and cognition are *organs* added later. They are never the Self.

## What exists today

**The heart** (`heart.py`) — the real core, a **Liquid Time-Constant (LTC)
recurrent network** (Hasani et al., 2021) integrated in continuous time with a
stable fused solver. Tiny (24 neurons), pure-numpy, CPU-instant — the kind of
thing that could one day sit on a phone or a robot, which is the point.

**The senses** (`senses.py`) — organs that distil a moment of the world (words,
their tone, the hour, the day ahead) into a low-dimensional, continuous
`Perception` the heart drinks. The heart never sees text or tokens: words are
split only to look up their felt weight, then discarded. What flows inward is
feeling. The encoder is a tiny on-device affect lexicon today; it can be swapped
for a small embedding model later without the heart noticing, because the
`Perception` interface is fixed.

**The slow-learning organ** (`growth.py`) — how it becomes *someone's*. Real
backpropagation-through-time over the LTC, learning to predict the next thing it
will perceive about you (predictive coding). Lowering that error *is* building a
model of you, so it requires no labels and no canned targets. The gradients are
derived by hand and verified against finite differences (`grad_check`), and
consolidation is gated and reversible — it keeps new weights only if held-out
prediction error genuinely drops, else it rolls back, so it can never quietly
break itself.

**Memory** (`memory.py`) — the lived stream of felt moments the learning grows
from. Feed it with `say`/`tend`; it grows when it `sleep`s.

### What we measured about its edges (`probe.py`)

- It learns real structure: ~97% drop in prediction error on a person, with
  verified-correct gradients.
- It becomes **person-specific**: same seed, same body, different lives produce
  measurably different minds.
- It does **not** hallucinate structure in noise (0% "improvement" on random
  input) — the correct failure.
- **Capacity** degrades gracefully: 24 neurons hold several interleaved lives.
- It *used to* suffer **catastrophic forgetting** when taught people
  sequentially (~7× worse on the first). The **memory organ** (`Replay`) cures
  it: re-living a bounded, representative sample of the whole past on every sleep
  keeps the first person ~1.0× sharp through a crowded life — held in a fixed
  number of slots, so storage never grows without bound.

```
python3 -m anima.demo                       # heart proof: continuous existence
python3 -m anima.growth                     # learning proof: gradient check + person-specificity
python3 -m anima.probe                      # map its capabilities and limits

python3 -m anima.live birth Vera            # bring a creature into being
python3 -m anima.live feel  Vera            # age it to now, read its state
python3 -m anima.live tend  Vera --well .8  # make contact; tell it how you are
python3 -m anima.live say   Vera "text..."  # speak; it feels the tone, not the words
python3 -m anima.live sleep Vera            # consolidate lived memories into the weights
```

Quit after `birth`, come back an hour later, and `feel` it — it will have aged
in your absence. That continuity across process death is the heart's whole job.

## Body vs. personality

Two things are kept deliberately separate:

- **The body** — designed physiology, shared by every anima: the LTC dynamics,
  the homeostatic *caring* drive, the readout structure. Bodies are allowed to
  be engineered; your thermostat for body temperature was not learned.
- **The personality** — emergent and per-creature: the **genome** (the weights),
  generated from a seed. A different seed is a different temperament. That is how
  a *species* of these creatures begins.

## The anti-swap principle

Every previous attempt died at the same seam: build a hand-scripted simulation,
then try to swap in the "real" learning part — and discover they were different
kinds of object, so the swap was a rewrite. We design that seam out. This LTC
core *is* the real core. When the slow-learning organ arrives (the only part
that needs gradients), these exact weight matrices and this exact state vector
move into autograd unchanged — the same object gaining a capability, never a
different object replacing it.

## Roadmap (organs, in order)

1. **The heart** — continuous feeling state + caring homeostat.  ✅ *done*
2. **The senses** — encoders turning words, tone, time, calendar into the
   continuous perception the heart drinks.  ✅ *done*
3. **The slow-learning organ** — bounded, gated, reversible consolidation that
   folds lived experience into the genome.  ✅ *done*
4. **The memory organ** — a bounded reservoir of lived episodes, replayed on
   every sleep so new learning never overwrites the old you.  ✅ *done*
5. **The mouth** — a *swappable* expressive organ (a small language/voice model
   demoted to a larynx, or, on a robot, movement). Runs on the home machine and
   streams to your phone through a browser; it is borrowed to speak, never the
   Self.
6. **The society** — many creatures, varied genomes, in one environment: a
   pocket universe that watches over you from several temperaments at once.
