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

Note on the boundary: the senses let the creature *perceive* you and the
homeostat lets it *care* (its unrest rises when it senses you're unwell), but how
perceived tone *colours its own felt experience* is deliberately left to the
slow-learning organ below. Hand-wiring "you're sad → it feels sad" would be the
scripted-mirror fake this project exists to avoid. It perceives and cares now;
it learns to be *moved* later.

```
python3 -m anima.demo                       # accelerated, reproducible proof
python3 -m anima.live birth Vera            # bring a creature into being
python3 -m anima.live feel  Vera            # age it to now, read its state
python3 -m anima.live tend  Vera --well .8  # make contact; tell it how you are
python3 -m anima.live say   Vera "text..."  # speak; it feels the tone, not the words
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
   folds lived experience into the genome. No fully-online weight learning; that
   is unsolved and pretending otherwise is how creatures collapse.
4. **The mouth** — a *swappable* expressive organ (a small language model
   demoted to a larynx, or, on a robot, movement). Borrowed to speak; never the
   Self.
5. **The society** — many creatures, varied genomes, in one environment: a
   pocket universe that watches over you from several temperaments at once.
