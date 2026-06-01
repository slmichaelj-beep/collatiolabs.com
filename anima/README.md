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

**The senses** (`senses.py`) — organs that distil a moment of the world into a
continuous, 9-channel `Perception` the heart drinks: presence, attention, mood,
intensity, wellbeing, load, and — for a companion that must read you — **distress**
(acute suffering), **seeking** (a bid for connection/support), and **openness**
(how much you're disclosing). The heart never sees text or tokens: words are
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

**The mouth** (`mouth.py`) — a *swappable*, heavy organ for speaking. A small
local LLM (via Ollama) is **conditioned on the creature's real felt-state** —
its valence, energy, restlessness — so the words come out shaped by its physics,
not as a generic chatbot. Voice (Kokoro TTS) and ears (faster-whisper) are
optional, loaded only if installed (`requirements-voice.txt`). With nothing
installed an honest offline stub still proves the state-conditioning. The mouth
runs on the home machine and is meant to stream to your phone through a browser;
on a robot, movement could replace it. It is never the Self.

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

python3 -m anima.live birth Vera --neurons 256   # bring a creature into being (scalable brain)
python3 -m anima.live feel  Vera            # age it to now, read its state
python3 -m anima.live tend  Vera --well .8  # make contact; tell it how you are
python3 -m anima.live say   Vera "text..."  # speak; it feels the tone, not the words
python3 -m anima.live sleep Vera            # consolidate lived memories into the weights
python3 -m anima.live talk  Vera "text..."  # it replies, in words shaped by its state
python3 -m anima.live chat  Vera            # open conversation; it remembers after
python3 -m anima.nightly install --name Vera --hour 3   # auto-sleep nightly (macOS)
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
5. **The mouth** — a *swappable* expressive organ: a small LLM conditioned on the
   creature's state, with optional Kokoro voice and Whisper ears.  ✅ *organ done*
   (next: stream it to the phone over WebRTC through a browser)
6. **Heredity** — genomes cross over and mutate into children (`reproduce.py`).
   Measured: offspring inherit *temperament* fully and a parent's *learned*
   knowledge partially; a lineage can vary and diverge.  ✅ *done*
7. **The society** — many creatures breeding and living in one environment: a
   pocket universe that watches over you from several temperaments at once.

### Scaling & acceleration

Brain size is per-creature (`birth --neurons N`, or `Heart.born(..., n=...)`) and
persists. On Apple Silicon, `accel_mlx.py` trains big creatures on the Mac GPU via
MLX (numpy `growth.py` stays the verified reference). The trainer has recipe knobs
(`weight_decay`, `clip`) that carry over to MLX.

Does scaling neurons help? Investigated thoroughly: **no, and that's expected.**
A diagnostic shows the hidden state settles into ~5 effective dimensions
regardless of neuron count (64→4.5, 256→6.2), and neither slower time-constants,
a wider 48-channel interface, nor a non-contractive cell changed it. The reason is
not a bug — it is that **the task is intrinsically low-dimensional**: modeling one
person's moods and rhythms from a few sense channels needs ~10 effective
dimensions, not 256. The human-brain "more neurons = smarter" intuition does not
transfer, because this creature does tight relational modeling, not general
intelligence. **Keep brains small (24–64); scaling neuron count is a non-goal.**
The real levers are the *quality* of the senses and the learning objective.
