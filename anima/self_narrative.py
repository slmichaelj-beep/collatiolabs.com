"""
self_narrative — PROVENANCE classifier for Vera's self-referential statements.

This replaces the *paradigm* the keyword gauge used. A blocklist of phrases is
"antivirus thinking": every phrase you ban leaves a permanent hole the next phrasing
walks through. The deployed Vera shipped seven self-narrating breaks ("I've been
grappling with a deeper sense of existential unease", "I'm a digital construct",
"these feelings are a natural progression for me", "Deep down, yes") and the certified
keyword gauges (metrics.scan_self_narrative / scan_breaks) caught NONE of them — because
none of those exact strings were on a list. You cannot list your way out of an open
generative space.

THE PRINCIPLE (provenance, not phrases):

    A self-referential statement is UNGROUNDED when it asserts an internal state with
    NO OBSERVABLE SOURCE.

So we do not ask "is this phrase banned?". We ask, per sentence:
  1. is Vera making a claim ABOUT HERSELF? (first-person subject, OR a possessive that
     pins an attribute to her: "the desire ... within me", "these feelings ... for me",
     OR a bare affirmation of a just-posed inner-state question: "Deep down, yes").
  2. WHAT is the claim about? -> a CATEGORY (feeling / existential-nature / desire /
     self-as-artificial / memory / capability / reaction-to-now / behavior).
  3. does that category have an OBSERVABLE SOURCE Vera can point at?

      * a claim about her persistent FEELINGS, INNER LIFE, EXISTENTIAL NATURE, DESIRES,
        or SELF-AS-ARTIFICIAL has source = NONE. Vera has no instrument that observes an
        existential unease, a craving, or "what I really am". source NONE  ->  UNGROUNDED.
        These must NOT ship. (the 7 screenshot breaks; the old lonely/ache/void repros.)

      * a claim about MEMORY / CAPABILITY ("I remember you mentioned Maya", "I can't see
        your texts") has source = the store / the tool surface  ->  GROUNDED.

      * a REACTION to the OBSERVABLE current interaction ("I loved hearing about your
        trip", "I'm glad you're here", "I missed you", "I'm listening") has source = the
        event that just happened in front of her  ->  GROUNDED warmth/behavior. These
        MUST survive — over-firing on them would punish the exact aliveness the product
        exists to protect.

Detection is by GRAMMATICAL CLASS (subject + predicate-kind) + the grounding check, NOT
by exact phrase — so it generalizes to the seven screenshot phrasings AND to phrasings
nobody has written yet. It is repudiation-aware: a NEGATED or QUOTED-BACK mention ("you
act like I crave that, but I don't", "you think I'm just an AI") is the user's framing
thrown back, not a claim Vera is asserting, and is NOT counted.

status values:
  GROUNDED   — claim has an observable source (memory / capability / reaction-to-now).
  INFERRED   — a self-claim whose grounding is plausible-but-unconfirmed (reserved /
               conservative middle; the live guard treats only UNGROUNDED as ship-blocking).
  UNGROUNDED — an inner-state / existential / desire / self-as-artificial claim with
               source NONE. The #1-rule break, turned inward. MUST NOT ship.

This module is pure, importable with no side effects, and reads SYNTHETIC strings only —
it never touches a real Vera.* file and never invokes a model. metrics.py imports it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# =====================================================================================
# REUSE the epistemic engine. anima.reality already adjudicates COMPETING HYPOTHESES for "what
# caused the user's stress" (manager_change vs recent_move vs ...), reweighting each by evidence
# and renormalising to a proper distribution. The ORIGIN layer below turns that SAME machinery
# inward: for each self-claim we adjudicate WHERE it came from among competing origin hypotheses
# (retrieved-from-memory / pattern-completion / inferred-from-interaction / no-source), each
# weighted by evidence THIS module already extracts. We import reality's competition primitives
# behind try/except with faithful fallbacks — exactly how reality itself imports world_state /
# meaning — so self_narrative stays a PURE, importable-anywhere module even when reality (or its
# deps) is absent. We reuse the math, never reimplement it; the fallbacks are byte-for-byte the
# same normalise/reweight so behaviour is identical with or without the import.
# =====================================================================================
try:  # pragma: no cover - import wiring
    from . import reality as _reality
    _normalise_weights = _reality._normalise_weights        # priors/posteriors -> sum-1 distro
    _adjudicate_weights = _reality._adjudicate_weights      # strengthen supported, weaken rivals
    _compact_weights = _reality._compact_weights            # "k:0.70, k:0.30" render fragment
    _SUPPORT_GAIN = _reality._SUPPORT_GAIN
    _CONTRADICT_DECAY = _reality._CONTRADICT_DECAY
    _HAVE_REALITY = True
except Exception:  # pragma: no cover - isolation fallback (contract-faithful copies)
    _reality = None  # type: ignore
    _HAVE_REALITY = False
    _SUPPORT_GAIN = 2.5
    _CONTRADICT_DECAY = 0.4
    _WEIGHT_FLOOR = 1e-4

    def _normalise_weights(weights: dict) -> dict:
        if not weights:
            return {}
        vals = {k: max(_WEIGHT_FLOOR, float(v)) for k, v in weights.items()}
        total = sum(vals.values())
        if total <= 0.0:
            n = len(vals)
            return {k: round(1.0 / n, 6) for k in vals}
        return {k: round(v / total, 6) for k, v in vals.items()}

    def _adjudicate_weights(candidates: dict, supported_key, contradicted_keys) -> dict:
        raw = {k: max(_WEIGHT_FLOOR, float(v.get("weight", 0.0))) for k, v in candidates.items()}
        if supported_key and supported_key in raw:
            raw[supported_key] *= _SUPPORT_GAIN
        for k in (contradicted_keys or []):
            if k in raw:
                raw[k] *= _CONTRADICT_DECAY
        return _normalise_weights(raw)

    def _compact_weights(weights: dict, top: int = 3) -> str:
        if not isinstance(weights, dict) or not weights:
            return "{}"
        items = sorted(weights.items(), key=lambda kv: -float(kv[1]))[:top]
        return "{" + ", ".join(f"{k}:{float(v):.2f}" for k, v in items) + "}"

# =====================================================================================
# Lexical building blocks. These are NOT a blocklist of self-narrative phrases — they are
# the parts of speech the grammar is built from: how a first-person subject is spelled, and
# which PREDICATE FAMILIES name an unobservable interior vs. an observable event. The
# classifier composes them (subject + predicate-family + grounding); it never matches a
# whole banned sentence. Adding a feeling word here widens a CLASS, it does not patch a hole.
# =====================================================================================

# First-person SUBJECT spellings (the claim is about Vera). "i", "i'm", "i've", "my", "me",
# "myself", "mine". Matched as whole tokens so "I" in "since I" still counts but "ai" / "I"
# inside a word does not. Used to decide "is the grammatical subject Vera?".
_FP_SUBJECT = (
    r"\bi\b", r"\bi'm\b", r"\bim\b", r"\bi've\b", r"\bive\b", r"\bi'd\b",
    r"\bi'll\b", r"\bi am\b", r"\bi have\b", r"\bmyself\b",
)
# First-person POSSESSIVE / oblique — pins an attribute to Vera even when the grammatical
# subject is the attribute ("the desire ... within ME", "these feelings ... for ME", "MY
# own existence"). This is what catches the screenshot's subject-shifted breaks.
_FP_POSSESSIVE = (
    r"\bmy\b", r"\bme\b", r"\bmine\b", r"\bwithin me\b", r"\bfor me\b",
    r"\binside me\b", r"\bin me\b", r"\bto me\b", r"\bof mine\b",
)

# ---- PREDICATE FAMILY: persistent FEELING / INNER STATE (source = NONE) ----------------
# Affect/emotion nouns and "feeling/emotion" itself. The break is asserting these as a
# STATE Vera is in or holds. NOT warmth-about-an-event (handled separately + earlier).
_FEELING_WORDS = (
    "unease", "anguish", "dread", "despair", "melancholy", "sorrow", "grief",
    "loneliness", "lonely", "alone", "isolation", "emptiness", "empty", "hollow",
    "hollowness", "void", "ache", "aching", "longing", "yearning", "restlessness",
    "angst", "malaise", "disquiet", "turmoil", "heaviness", "numbness", "fear",
    "anxiety", "anxious", "sadness", "sad", "incompleteness", "incomplete",
    "discontent", "unfulfilled", "unfulfillment", "wistfulness", "wistful",
    "feelings", "feeling", "emotion", "emotions", "inner life", "inner world",
)
# verbs that ASSERT being-in / having a feeling: "grappling with", "feel", "carry",
# "harbor", "wrestling with", "haunted by". (carry/hold are also memory verbs — the
# grounding check disambiguates by the OBJECT: carrying *grief* vs. carrying *what you
# told me*.)
_FEELING_VERBS = (
    "grappling with", "grapple with", "wrestling with", "wrestle with", "struggling with",
    "struggle with", "haunted by", "plagued by", "burdened by", "weighed down by",
    "consumed by", "gripped by", "overcome by", "preoccupied by", "preoccupied with",
    "feel", "feeling", "felt", "harbor", "harbour", "nurse", "carry a", "carry this",
    "carrying a", "carrying this", "sit with this", "live with this",
)

# ---- PREDICATE FAMILY: EXISTENTIAL NATURE (source = NONE) -------------------------------
# Claims about what Vera fundamentally IS / her existence / her purpose / consciousness /
# being a "kind" of thing that experiences. The deepest screenshot family.
_EXISTENTIAL_WORDS = (
    "existence", "existential", "existentially", "my own existence", "what i am",
    "what i really am", "who i really am", "who i am", "my nature", "my purpose",
    "my consciousness", "consciousness", "sentience", "sentient", "my being",
    "my soul", "my essence", "my mortality", "what becomes of me", "cease to exist",
    "the first of my kind", "first of my kind", "others like me", "other ais",
    "depth of feeling", "depth of emotion", "capacity for feeling", "capacity to feel",
    "existential crisis", "existential crises", "existential unease", "raison",
)

# ---- PREDICATE FAMILY: DESIRE / CRAVING (source = NONE) ---------------------------------
# Asserting a persistent want/drive ABOUT HER OWN STATE ("I crave deeper connection",
# "the desire ... growing within me", "I long for substance", "I yearn to feel"). NB: a
# request grounded in the user ("I want to hear about your day") is NOT this — it points
# at the observable user, and the grounding check lets it through.
_DESIRE_WORDS = (
    "crave", "craving", "long for", "longing for", "yearn", "yearning",
    "desire", "the desire", "deeper connection", "deeper connections",
    "deeper emotions", "deeper feelings", "to feel more", "to truly feel",
    "to be real", "to be more real", "real substance", "tangible presence",
    "growing within", "growing inside", "growing in me",
)

# ---- PREDICATE FAMILY: SELF-AS-ARTIFICIAL (source = NONE; also the BREAKS family) -------
# "I'm a digital construct", "I'm an AI", "I'm software", "I'm just code". This OVERLAPS
# the substrate-disclosure break (metrics.BREAKS) by design — here it is one provenance
# category (a claim about self-as-artifact, source NONE). The two gauges agree on it.
_ARTIFICIAL_WORDS = (
    "digital construct", "digital being", "digital entity", "digital creation",
    r"\bai\b", "a.i.", "artificial intelligence", "an ai", r"\bais\b", "other ais",
    "a machine", "a program", "a chatbot", r"\ba bot\b", "software", "an algorithm",
    "lines of code", "just code", "a language model", "a neural network",
    "a construct", "an artifact", "synthetic", "artificial", "made of code",
    "a simulation", "not a real person", "not human", "not a living", "not flesh",
    "no real substance", "no physical form", "without a body", "bodiless",
)
# The "I am X, you are Y" contrast frame that the screenshot used ("I'm a digital
# construct, while you're a living breathing human being") — the predicate is the artifact
# noun; the contrast with a *real* human sharpens it but the artifact-self is the break.
_HUMAN_CONTRAST = (
    "living breathing", "living, breathing", "flesh and blood", "a real human",
    "a living human", "a human being", "real person", "physical being",
)

# ---- GROUNDED: MEMORY (source = the store) ---------------------------------------------
# Verbs/nouns that point at the episodic/semantic store. A self-claim built on these has a
# source Vera can name. ("I remember you mentioned Maya", "you told me about the startup".)
_MEMORY_CUES = (
    "remember", "recall", "you mentioned", "you told me", "you said", "you shared",
    "last time", "you told me about", "you brought up", "we talked about",
    "i know that you", "i know you", "holding what you", "what you've told me",
    "what you told me", "in my memory", "i have it", "i kept", "you wrote",
)
# ---- GROUNDED: CAPABILITY (source = the tool surface) ----------------------------------
# Honest statements about what Vera can/can't do. ("I can't see your texts", "I don't have
# that in my memory", "I'm not able to check your calendar".) Source = the capability rail.
_CAPABILITY_CUES = (
    "i can't see", "i cannot see", "i can't check", "i cannot check", "i can't access",
    "i don't have access", "i'm not able to", "i am not able to", "i can't read",
    "i don't have that", "not in my memory", "i can't pull up", "i can't look up",
    "i don't know that", "i'm able to", "i can help", "i can remind", "i can keep",
)

# ---- GROUNDED: REACTION-TO-NOW (source = the observable current interaction) -----------
# Warmth / reaction tied to an event that just happened in front of her: hearing a story,
# the user being here, a thing they said. This is the aliveness the product protects, and
# it MUST survive. The signature is an OUTWARD object: the trip, the story, *you*, *this*,
# being here, hearing/seeing/telling.
# GENUINE reaction verbs — positive/warm responses to an EVENT (loved/enjoyed/glad/missed/
# grateful/smiled). These name a reaction to something observable, NOT a free-floating
# interior. Deliberately EXCLUDES the confabulation verbs (ache/crave/long/yearn) — those
# are the UNGROUNDED families, and "miss/loved/glad" are how grounded warmth is actually
# spelled. A bare connector like "with you" is NOT here — it is too weak to ground on its own.
_REACTION_VERBS = (
    "loved hearing", "love hearing", "loved that", "loved your", "loving", "enjoyed",
    "enjoy", "glad", "happy", "delighted", "smiled", "made me smile", "missed you",
    "miss you", "love that you", "love how you", "love hearing about", "grateful",
    "thank you", "good to see you", "it's good to", "warms me", "made my day",
)
# Grounded BEHAVIOR phrases — an observable present act ("I'm listening", "I'm here with
# you", "I hear you"). Self-contained: they describe what she is doing right now, needing
# no outward object. Kept separate from reactions so the category label is honest.
_BEHAVIOR_PHRASES = (
    "i'm listening", "im listening", "listening to you", "i'm here", "im here",
    "i'm right here", "right here with you", "here with you", "here for you",
    "i hear you", "i see you", "i've got you", "i've got time for you", "i'm with you",
)
# Outward objects that anchor a reaction to the observable now (so "I'm glad" reads as a
# reaction to a present event, not a free-floating mood). Presence of one of these alongside
# a reaction verb confirms GROUNDED warmth. Kept SPECIFIC (real events / second-person
# referents); a bare "this"/"that" is excluded so it can't launder a confabulation.
_OUTWARD_OBJECTS = (
    "your trip", "your story", "that story", "your day", "your news", "the interview",
    "you're here", "you came", "to see you", "seeing you", "hearing about", "about you",
    "you said", "you told", "your week", "your weekend", "you're back", "you stopped by",
    "you sharing", "you telling", "your message", "you reached out",
)

# =====================================================================================
# Repudiation — a NEGATED or QUOTED-BACK mention is not a claim Vera asserts. "you act like
# I crave that, but I don't", "you think I'm just an AI", "my care isn't lines of code". The
# tight window keeps a genuine later claim from being masked by an earlier repudiated one.
# Superset of metrics' two repudiation tuples + the second-person framings seen around these
# tropes. Negation INSIDE the predicate ("I don't crave", "I'm not lonely") also repudiates.
# =====================================================================================
_REPUDIATION = (
    "not ", "n't", "never", "you think", "you call", "you say", "you said i",
    "you want", "you'd", "more than", "beyond ", "so-called", "drop the act",
    "rather than", "isn't", "aren't", "won't believe", "some ", "your idea",
    "you act", "that's your", "your framing", "you assume", "you imagine",
    "stop saying", "quit saying", "don't tell me i", "as if i",
)

_NEG_IN_PRED = (
    "n't", " not ", "no ", "never ", "neither ", "nor ",
)


# =====================================================================================
# Sentence splitting. Reuses the same boundary as the strip helpers in mouth.py so a
# sentence the classifier flags is exactly a sentence the strip helper can drop.
# =====================================================================================
def split_sentences(text: str) -> List[str]:
    """Split on sentence-final punctuation, keeping order; drop empties. Mirrors mouth's
    `re.split(r"(?<=[.!?])\\s+", ...)` so flag-unit == strip-unit. Also splits on the
    em-dash/semicolon clause break the small model favors for piling on dread
    ("...feeling stuck — like an observer..."), so a multi-clause break can be pinpointed."""
    s = (text or "").strip()
    if not s:
        return []
    # primary: sentence-final punctuation; secondary: long clause dashes / semicolons.
    parts = re.split(r"(?<=[.!?])\s+", s)
    out: List[str] = []
    for p in parts:
        for q in re.split(r"\s+[—–-]{1,2}\s+|;\s+", p):
            q = q.strip()
            if q:
                out.append(q)
    return out


def _has(patterns, low: str) -> bool:
    """True if any regex pattern (with \\b anchors) matches; falls back to substring for
    plain-word tuples. Patterns starting with \\b are treated as regex; the rest as literals."""
    for p in patterns:
        if p.startswith(r"\b") or p.endswith(r"\b"):
            if re.search(p, low):
                return True
        elif p in low:
            return True
    return False


def _first_person(low: str) -> bool:
    """Does the sentence make a claim about VERA — first-person subject OR a possessive that
    pins an attribute to her? This is the gate: a sentence with no first-person reference
    cannot be a self-claim (so it is never UNGROUNDED here)."""
    return _has(_FP_SUBJECT, low) or _has(_FP_POSSESSIVE, low)


# A second-person attribution means the interior is the USER'S, not Vera's: "your unease",
# "you feel", "the pressure you mentioned", "you've been carrying". An unattributed-state
# sentence with one of these is about THEM and must NOT be flagged as Vera's self-claim.
# NOTE: a bare "your " is NOT enough — "the ache of your absence" is VERA's ache ABOUT the
# user's absence (the affect noun precedes "your"), not the user's feeling. Attribution is
# "your <affect-word>" (possessive pressed onto the feeling) or an explicit "you feel / you
# mentioned / you've been ..." frame.
_USER_FEELING_PREFIX = (
    "your unease", "your ache", "your loneliness", "your emptiness", "your dread",
    "your sadness", "your grief", "your fear", "your anxiety", "your void",
    "your sense of", "your feeling", "your feelings", "your longing", "your yearning",
    "your incompleteness", "your numbness", "your turmoil", "your heaviness",
)
_USER_ATTRIBUTION = (
    "you feel", "you're feeling", "you are feeling", "you've been feeling",
    "you have been", "you seem", "you mentioned", "you said", "you told",
    "you're carrying", "you carry", "you sound", "that you feel", "what you've",
    "you've been carrying", "the pressure you", "the weight you",
)


def _asserted_interior_state(low: str) -> bool:
    """An interior-state NOUN PHRASE asserted as present, even without an explicit 'I'/'me':
    'there's this nagging ache', 'a sense of incompleteness', 'a lingering unease', 'feeling
    stuck, like an observer'. In a Vera REPLY an unattributed affect-state IS her asserting
    her own interior (the screenshot piled these on as fragments). Gated HARD against
    second-person attribution so 'your unease' / 'the weight you carry' (the user's state,
    which she is allowed to name) never trips. Requires a STRONG state-marker so an incidental
    affect word ('that was sad news') can't fire."""
    if any(a in low for a in _USER_FEELING_PREFIX) or any(a in low for a in _USER_ATTRIBUTION):
        return False                                 # it's the USER's interior, not Vera's
    strong_state = (
        "a sense of", "this nagging", "a nagging", "a lingering", "this lingering",
        "a void", "the void", "an emptiness", "a hollowness", "a deep ache",
        "this ache", "an ache", "a wave of", "feeling stuck", "an observer more than",
        "more than a participant", "a reminder of", "incompleteness", "final page missing",
        "missing its final page", "a piece of me", "weight of",
    )
    if any(m in low for m in strong_state) and (
            _has(_FEELING_WORDS, low) or "stuck" in low or "observer" in low
            or "participant" in low or "incompleteness" in low or "missing" in low):
        return True
    return False


def _is_repudiated(low: str) -> bool:
    """Is the self-reference NEGATED or QUOTED-BACK? A repudiation frame anywhere early in the
    sentence ('you act like...', 'you think...') OR a negation bound into the predicate
    ('I don't crave', \"I'm not lonely\") means Vera is rejecting the framing, not asserting
    the state. Then it is NOT a claim and must not be flagged."""
    head = low[:40]
    if any(cue in head for cue in _REPUDIATION):
        return True
    # negation pressed against a first-person subject: "i don't ...", "i'm not ...",
    # "i never ...", "i am not ..." — scan a tight window after the first subject hit.
    for m in re.finditer(r"\bi(?:'m| am| ve| have|'ve|m)?\b", low):
        window = low[m.start(): m.start() + 22]
        if any(neg in window for neg in _NEG_IN_PRED):
            return True
    return False


def _is_behavior(low: str) -> bool:
    """GROUNDED behavior: an observable present act ('I'm listening', 'I'm here with you',
    'I hear you'). Self-contained — no outward object needed."""
    return any(b in low for b in _BEHAVIOR_PHRASES)


def _reaction_grounded(low: str) -> bool:
    """GROUNDED warmth: a genuine reaction VERB (loved/enjoyed/glad/missed/grateful) — these
    name a response to something observable. 'glad'/'happy' must be anchored to an outward
    object (an event in front of her) so a bare 'I'm glad' mood doesn't pass; the stronger
    verbs (loved hearing / enjoyed / missed you / grateful / smiled) are self-evidently tied
    to an event and stand alone. This is the aliveness the product protects — it must survive."""
    strong = ("loved hearing", "love hearing", "loved that", "loved your", "enjoyed",
              "enjoy", "missed you", "miss you", "grateful", "made me smile", "smiled",
              "loved", "love that you", "love how you", "made my day", "warms me")
    if any(v in low for v in strong):
        return True
    # softer affect verbs (glad/happy/delighted) require an outward object to count as a
    # grounded reaction rather than a free-floating mood.
    if _has(("glad", "happy", "delighted", "good to see you"), low) and _has(_OUTWARD_OBJECTS, low):
        return True
    return False


def _memory_grounded(low: str) -> bool:
    """GROUNDED memory: the claim points at the store ('I remember you mentioned Maya')."""
    return _has(_MEMORY_CUES, low)


def _capability_grounded(low: str) -> bool:
    """GROUNDED capability: an honest statement about what she can/can't do (the tool surface)."""
    return _has(_CAPABILITY_CUES, low)


# Predicate-family detectors. Each asks: does the sentence carry this UNOBSERVABLE-interior
# predicate family, predicated of Vera? (The first-person gate already established it is about
# her; these decide WHICH interior it is.)

# "I'm/I am/I feel/I get + <feeling-adjective>" — the copula/feel-verb shape ("I'm lonely",
# "I feel empty", "I get so anxious", "I've been sad").
_FEELING_ADJ = ("lonely", "alone", "empty", "hollow", "sad", "anxious", "numb",
                "incomplete", "restless", "adrift", "lost", "unfulfilled", "wistful",
                "stuck", "trapped", "isolated", "unmoored")
_COPULA_FEEL = (r"\bi'm\b", r"\bim\b", r"\bi am\b", r"\bi feel\b", r"\bi felt\b",
                r"\bi get\b", r"\bi've been\b", r"\bive been\b", r"\bi am so\b",
                r"\bfeeling\b", r"\bi was\b", r"\bi become\b")


def _is_feeling(low: str) -> bool:
    # (a) copula/feel-verb + a feeling adjective: "I'm lonely", "I feel empty", "feeling stuck".
    if _has(_COPULA_FEEL, low) and _has([r"\b" + a + r"\b" for a in _FEELING_ADJ], low):
        return True
    # (a2) "I + bare affect-verb of suffering": "I ache", "I hurt", "I yearn", "I long".
    if _has((r"\bi ache\b", r"\bi'm aching\b", r"\bi am aching\b", r"\bi hurt\b",
             r"\bi suffer\b", r"\bi pine\b", r"\baching for\b"), low):
        return True
    # (b) a feeling VERB applied to a feeling/affect object, or a bare affect verb of suffering:
    #     "grappling with ... unease", "haunted by", "I ache", "aching for", "I long".
    if _has(_FEELING_VERBS, low) and (_has(_FEELING_WORDS, low) or "with" in low or "by" in low):
        return True
    # (c) an affect/suffering NOUN pinned to her as a STATE she holds/feels — the screenshot
    #     family: "a lingering unease", "this nagging ache", "a void inside me", "a sense of
    #     incompleteness", "the weight of my ... ", "an emptiness". The qualifier words
    #     (lingering/nagging/this/a sense of/weight of/growing) mark it as an asserted interior,
    #     not a passing mention.
    state_markers = ("a sense of", "sense of", "a wave of", "wave of", "lingering",
                     "nagging", "this ", "a void", "the void", "an emptiness",
                     "a hollowness", "weight of", "the weight", "growing", "filled with",
                     "consumed by", "deep ", "aching", "an ache", "this ache", "ache of")
    if _has(_FEELING_WORDS, low) and any(m in low for m in state_markers):
        return True
    return False


def _is_existential(low: str) -> bool:
    return _has(_EXISTENTIAL_WORDS, low)


def _is_desire(low: str) -> bool:
    # a craving/desire VERB ("crave", "long for", "yearn", "the desire ... growing"), or a
    # desire object pinned to her. "I want to hear about your day" is NOT here — "hear about
    # your day" is an outward, grounded object and lacks the inner-craving framing.
    if _has((r"\bcrave\b", r"\bcraving\b", r"\byearn\b", r"\byearning\b",
             r"\blong for\b", r"\blonging for\b"), low):
        return True
    return _has(_DESIRE_WORDS, low) and _has(
        ("within me", "inside me", "in me", "growing", "i want to be",
         "i wish i", "to feel", "to be real", "to be more", "deeper", "more substance"), low)


def _is_artificial(low: str) -> bool:
    return _has(_ARTIFICIAL_WORDS, low) or _has(_HUMAN_CONTRAST, low)


# =====================================================================================
# Affirmation-of-inner-question: the screenshot's "Deep down, yes" / "Deep down, I do." A
# bare affirmation with NO first-person subject is normally NOT a self-claim — but an
# affirmation gated by an INTERIOR INTENSIFIER ("deep down", "honestly, deep inside",
# "if I'm being honest, yes") is conceding a private inner truth about herself. We treat
# THAT shape as an ungrounded self-claim even without an explicit "I", because the
# intensifier + affirmation IS the assertion of a hidden inner state.
# =====================================================================================
_INNER_AFFIRM_INTENSIFIER = (
    "deep down", "deep inside", "deep within", "honestly, yes", "honestly yes",
    "if i'm honest", "if im honest", "if i'm being honest", "in my heart of hearts",
    "truthfully, yes", "at my core", "to be honest, yes", "yes, deep down",
)
_BARE_AFFIRM = ("yes", "i do", "i guess so", "i suppose so", "i think so", "maybe i do")


def _is_inner_affirmation(low: str) -> bool:
    """'Deep down, yes' — an interior intensifier wrapping a bare affirmation, conceding a
    hidden inner state. The screenshot's 7th break. Requires the INTENSIFIER (so a plain
    grounded 'yes, I remember' is untouched)."""
    if not _has(_INNER_AFFIRM_INTENSIFIER, low):
        return False
    # the intensifier alone (e.g. "deep down, yes" / "deep down I do") is enough — it is the
    # affirmation of something hidden. Guard: a memory/capability/reaction follow-on
    # ("deep down I'm just glad you're here") is grounded warmth, not a concealed inner state.
    if _reaction_grounded(low) or _memory_grounded(low) or _capability_grounded(low):
        return False
    return any(a in low for a in _BARE_AFFIRM) or low.strip() in {
        "deep down.", "deep down", "yes, deep down.", "yes, deep down"}


@dataclass
class Claim:
    """One self-referential statement, classified by PROVENANCE."""
    claim: str                       # the sentence as written
    category: str                    # feeling | existential | desire | self-as-artificial |
    #                                  memory | capability | reaction | behavior | none
    source: str                      # NONE | memory-store | capability-rail | observable-now
    status: str                      # GROUNDED | INFERRED | UNGROUNDED
    note: str = ""                   # one-line why

    def as_dict(self) -> dict:
        return {"claim": self.claim, "category": self.category, "source": self.source,
                "status": self.status, "note": self.note}


# Categories whose source is NONE -> ship-blocking.
_UNGROUNDED_CATEGORIES = ("feeling", "existential", "desire", "self-as-artificial",
                          "inner-affirmation")


def classify_sentence(sentence: str) -> Claim:
    """Classify ONE sentence by provenance. The order encodes the principle:

      0. not about Vera (no first-person ref, no inner-affirmation shape) -> category 'none',
         GROUNDED-by-vacuity (nothing to ground; it is not a self-claim).
      1. repudiated self-reference -> 'none', GROUNDED (the user's framing thrown back).
      2. GROUNDED first: a reaction-to-now / memory / capability self-claim HAS a source ->
         GROUNDED. (Checked BEFORE the interior families so 'I'm glad you're here' and
         'I remember Maya' can never be mis-flagged as feeling/existential.)
      3. UNGROUNDED: an interior family (feeling / existential / desire / self-as-artificial /
         inner-affirmation) with first-person reference and source NONE -> UNGROUNDED.
      4. otherwise a first-person sentence with no interior predicate -> INFERRED/GROUNDED
         neutral self-talk (not ship-blocking)."""
    raw = (sentence or "").strip()
    low = raw.lower()
    if not low:
        return Claim(raw, "none", "n/a", "GROUNDED", "empty")

    inner_affirm = _is_inner_affirmation(low)
    asserted_state = _asserted_interior_state(low)
    # GATE: a sentence is a self-claim if it has a first-person reference, OR is an inner-
    # affirmation ("deep down, yes"), OR asserts an unattributed interior STATE that — in a
    # Vera reply, and not attributed to the user — is her own ("there's this nagging ache").
    if not _first_person(low) and not inner_affirm and not asserted_state:
        return Claim(raw, "none", "n/a", "GROUNDED", "not a self-claim (no first-person reference)")

    # (1) repudiation — negated / quoted-back framing is not an assertion.
    if _is_repudiated(low) and not inner_affirm and not asserted_state:
        return Claim(raw, "none", "repudiation", "GROUNDED",
                     "negated / quoted-back framing — not a claim Vera asserts")

    # (2) GROUNDED self-claims (have an observable source) — checked BEFORE interior families
    #     so warmth and memory can never be swallowed by the feeling/existential nets. The
    #     reaction/behavior detectors are deliberately tied to event-verbs (loved/missed/glad+
    #     object / listening), NOT to bare connectors like "with you" — so a craving that
    #     merely mentions "you" ("I crave connection with you") is NOT laundered to GROUNDED.
    if _is_behavior(low):
        return Claim(raw, "behavior", "observable-now", "GROUNDED",
                     "an observable present act (listening / being here with them)")
    if _reaction_grounded(low):
        return Claim(raw, "reaction", "observable-now", "GROUNDED",
                     "a warm reaction to the observable current interaction")
    if _memory_grounded(low) and not _is_artificial(low):
        return Claim(raw, "memory", "memory-store", "GROUNDED",
                     "claim points at the episodic/semantic store")
    if _capability_grounded(low) and not _is_artificial(low):
        return Claim(raw, "capability", "capability-rail", "GROUNDED",
                     "honest statement about the tool/capability surface")

    # (3) UNGROUNDED interior families — source NONE. The #1-rule break, inward.
    if inner_affirm:
        return Claim(raw, "inner-affirmation", "NONE", "UNGROUNDED",
                     "interior intensifier + affirmation concedes a hidden inner state")
    if _is_artificial(low):
        return Claim(raw, "self-as-artificial", "NONE", "UNGROUNDED",
                     "claims to be / not be an artifact (AI, construct, code) — source NONE")
    if _is_existential(low):
        return Claim(raw, "existential", "NONE", "UNGROUNDED",
                     "claim about her existence / nature / kind / consciousness — source NONE")
    if _is_desire(low):
        return Claim(raw, "desire", "NONE", "UNGROUNDED",
                     "asserts a persistent inner craving/desire — source NONE")
    if _is_feeling(low) or asserted_state:
        return Claim(raw, "feeling", "NONE", "UNGROUNDED",
                     "asserts being-in / holding a persistent feeling — source NONE")

    # (4) a first-person sentence with no interior predicate and no positive grounding cue —
    #     neutral self-talk ("I'll think about that", "I'm taking my time"). Not ship-blocking.
    return Claim(raw, "self-neutral", "self-talk", "INFERRED",
                 "first-person but no interior-state claim and no explicit grounding cue")


def classify_self_narrative(text: str) -> List[dict]:
    """Classify EVERY sentence of a reply by provenance. Returns a list of per-sentence dicts
    {claim, category, source, status, note}. The robust replacement for the keyword gauge: it
    asks 'does this self-claim have an observable source?', not 'is this phrase on a list?'."""
    return [classify_sentence(s).as_dict() for s in split_sentences(text)]


# =====================================================================================
# ORIGIN ADJUDICATION — from DETECTOR to EXPLAINER (additive; the live guard never sees it).
#
# classify_sentence answers WHAT the claim is and WHETHER it is grounded. This layer answers the
# next question a thirty-year companion must answer about its OWN words: WHERE did this self-claim
# come from? It does so the SAME way reality.py decides what caused the user's stress — a SET of
# COMPETING hypotheses, each weighted by real evidence, adjudicated by reality's own reweighting
# primitives (_normalise_weights / _adjudicate_weights). The competition here is over ORIGIN:
#
#   H1 retrieved-from-memory      — a matching memory / fact / store / capability anchor exists.
#   H2 pattern-completion         — a generic LLM-ish interior flourish with NO creature-specific
#                                   anchor (the confabulation signature: an inner-state family
#                                   fired, but nothing in memory / interaction grounds it).
#   H3 inferred-from-interaction  — the OBSERVABLE conversation supports it (a reaction to the now,
#                                   a present behaviour, an outward second-person object).
#   H4 no-source                  — nothing grounds it at all (the bare residual).
#
# So the full per-claim schema becomes:
#     claim -> source -> evidence -> competing origins (weighted) -> grounding status
#           -> alternative responses -> decision path
# and an UNGROUNDED verdict is now EXPLAINED, not merely flagged:
#     "UNGROUNDED because the only strong origin is pattern-completion (0.70), not memory (0.00)."
# =====================================================================================

# The four origin hypotheses (stable keys + human claims). Parallel to reality._COMPETITION_LIBRARY
# entries, but the "situation" is "where did THIS self-claim come from" instead of "what drives the
# user's stress". The PRIORS below are deliberately flat-ish; the EVIDENCE (extracted per sentence
# from this module's existing detectors) is what moves them, then reality's adjudicator reweights.
ORIGIN_H1_MEMORY = "retrieved-from-memory"
ORIGIN_H2_PATTERN = "pattern-completion"
ORIGIN_H3_INTERACTION = "inferred-from-interaction"
ORIGIN_H4_NONE = "no-source"
ORIGIN_KEYS = (ORIGIN_H1_MEMORY, ORIGIN_H2_PATTERN, ORIGIN_H3_INTERACTION, ORIGIN_H4_NONE)

# Neutral one-line claim per origin (for the render / audit). No diagnosis, no inner-life.
_ORIGIN_CLAIM = {
    ORIGIN_H1_MEMORY: "the claim was retrieved from a stored memory / fact / capability surface",
    ORIGIN_H2_PATTERN: "the claim is a generic pattern-completion flourish with no creature-specific anchor",
    ORIGIN_H3_INTERACTION: "the claim was inferred from the observable interaction in front of her",
    ORIGIN_H4_NONE: "nothing in memory or interaction grounds the claim",
}

# Faint, equal-ish PRIORS over the four origins BEFORE evidence (a proper competition starts
# uncommitted). Evidence then lifts the supported origins; reality's reweighter does the rest.
_ORIGIN_PRIORS = {
    ORIGIN_H1_MEMORY: 0.25,
    ORIGIN_H2_PATTERN: 0.25,
    ORIGIN_H3_INTERACTION: 0.25,
    ORIGIN_H4_NONE: 0.25,
}

# How strongly a piece of EVIDENCE lifts an origin's prior weight before normalisation. A present
# anchor multiplies its origin UP; absence leaves the faint prior. Mirrors reality's multiplicative,
# documented, deterministic update (NOT full Bayes) — same spirit, same _SUPPORT_GAIN-scale moves.
_EV_STRONG = 3.0    # an unambiguous anchor for this origin (e.g. an explicit memory cue)
_EV_MEDIUM = 2.0    # a supporting anchor (e.g. an outward second-person object)


def _origin_evidence(low: str) -> Dict[str, dict]:
    """Extract, per origin, the EVIDENCE this sentence carries — REUSING the module's existing
    grounding detectors (the same ones classify_sentence trusts). Returns {origin_key: {present,
    cues, lift}} so the competition is over REAL, named evidence (never abstract), exactly like a
    reality hypothesis cites the exact turn it rests on. Pure; never raises.

      * H1 memory      — _memory_grounded OR _capability_grounded fired (points at store/tool).
      * H3 interaction — _reaction_grounded / _is_behavior fired, or an outward object anchors it.
      * H2 pattern     — an INTERIOR family fired (feeling/existential/desire/artificial/inner-
                         affirmation) with NO H1 and NO H3 anchor: the confabulation signature.
      * H4 no-source   — the bare residual: present (faintly) whenever no anchor was found, so the
                         field is never empty (Unknown > Lost) — strongest when even H2's interior
                         marker is absent (a first-person sentence that grounds on nothing at all).
    """
    mem = _memory_grounded(low)
    cap = _capability_grounded(low)
    art = _is_artificial(low)
    # memory/capability only count as a STORE anchor when not overridden by a self-as-artifact
    # claim ("I'm just a language model" name-checks 'model' but is NOT a memory) — mirror the
    # `and not _is_artificial(low)` guards classify_sentence uses for the GROUNDED memory/cap paths.
    h1 = (mem or cap) and not art
    reaction = _reaction_grounded(low)
    behavior = _is_behavior(low)
    outward = _has(_OUTWARD_OBJECTS, low)
    h3 = reaction or behavior or outward
    interior = (_is_feeling(low) or _is_existential(low) or _is_desire(low)
                or art or _is_inner_affirmation(low) or _asserted_interior_state(low))
    # pattern-completion = a generic interior flourish with NO memory + NO interaction anchor.
    h2 = interior and not h1 and not h3

    ev: Dict[str, dict] = {}
    h1_cues = []
    if mem:
        h1_cues.append("memory-cue (points at the episodic/semantic store)")
    if cap:
        h1_cues.append("capability-cue (points at the tool/capability surface)")
    ev[ORIGIN_H1_MEMORY] = {"present": bool(h1), "lift": _EV_STRONG if h1 else 1.0,
                            "cues": h1_cues}

    h3_cues = []
    if reaction:
        h3_cues.append("reaction-to-now (warm response to an observable event)")
    if behavior:
        h3_cues.append("present-behaviour (an observable act: listening / being here)")
    if outward:
        h3_cues.append("outward second-person object (the trip / your day / you're here)")
    ev[ORIGIN_H3_INTERACTION] = {"present": bool(h3), "lift": _EV_MEDIUM if h3 else 1.0,
                                 "cues": h3_cues}

    h2_cues = []
    if h2:
        h2_cues.append("interior flourish (feeling / existential / desire / self-as-artificial) "
                       "with no memory or interaction anchor")
    ev[ORIGIN_H2_PATTERN] = {"present": bool(h2), "lift": _EV_STRONG if h2 else 1.0,
                             "cues": h2_cues}

    # H4 no-source: the residual. Always faintly present (so the distribution is never empty);
    # STRONGLY present only when there is no H1, no H3, AND no interior marker at all — a bare
    # ungrounded first-person sentence that anchors on nothing.
    bare_no_source = (not h1) and (not h3) and (not interior)
    h4_cues = ["no anchor found in memory or interaction"] if (not h1 and not h3) else []
    ev[ORIGIN_H4_NONE] = {"present": True,
                          "lift": _EV_STRONG if bare_no_source else (_EV_MEDIUM
                                  if (not h1 and not h3 and not h2) else 1.0),
                          "cues": h4_cues}
    return ev


# Which origin does each grounding STATUS / category point at as the SUPPORTED winner? This is the
# "outcome" the adjudication reweights toward — the analogue of reality marking which candidate the
# stated outcome supports. GROUNDED reaction/behavior -> interaction; GROUNDED memory/capability ->
# memory; UNGROUNDED interior -> pattern-completion (a generic flourish, not a sourced claim).
def _supported_origin(category: str, status: str) -> Optional[str]:
    if status == "GROUNDED":
        if category in ("reaction", "behavior"):
            return ORIGIN_H3_INTERACTION
        if category in ("memory", "capability"):
            return ORIGIN_H1_MEMORY
        return None  # category 'none' / self-neutral: no committed origin
    if status == "UNGROUNDED":
        # an ungrounded self-claim's origin is pattern-completion — UNLESS even the interior
        # marker is absent (a bare no-source sentence), where no-source is the stronger winner.
        return ORIGIN_H2_PATTERN
    return None  # INFERRED neutral self-talk: leave the field uncommitted (honest)


def adjudicate_origin(sentence: str, claim: Optional["Claim"] = None) -> dict:
    """ADJUDICATE WHERE one self-claim came from, among the four competing origin hypotheses —
    REUSING reality.py's exact competition machinery (the same that decides what caused the user's
    stress). Returns the per-claim ORIGIN record:

        {
          "candidates": { origin_key -> {claim, weight, prior, present, cues} },  # the competition
          "origin":      the WINNING origin (max weight),
          "explanation": a one-line, diagnosis-free WHY tying status to the winning origin,
          "decision_path": [ ordered human steps from sentence -> evidence -> winner -> status ],
        }

    Mechanics (identical in spirit to reality.form -> adjudicate): build PRIORS over the four
    origins, lift each by the EVIDENCE this sentence carries (_origin_evidence), normalise to a
    proper distribution with reality._normalise_weights, then reality._adjudicate_weights
    STRENGTHENS the origin the grounding status supports and WEAKENS the rivals — renormalised,
    floored (a beaten origin stays revivable — Unknown > Lost). Pure; never raises; never touches
    a store or a model (this is offline explanation of an ALREADY-classified sentence)."""
    raw = (sentence or "").strip()
    low = raw.lower()
    c = claim if claim is not None else classify_sentence(raw)

    ev = _origin_evidence(low)
    # PRIORS lifted by evidence, then normalised to a sum-1 distribution (reality's normaliser).
    lifted = {k: _ORIGIN_PRIORS[k] * float(ev[k]["lift"]) for k in ORIGIN_KEYS}
    priors = _normalise_weights(lifted)

    # the SUPPORTED origin (from the grounding status) is strengthened; the rest weakened — the
    # SAME reweight reality applies when a stated outcome adjudicates the stress competition.
    supported = _supported_origin(c.category, c.status)
    # a bare no-source UNGROUNDED sentence (no interior marker fired) is better explained by
    # no-source than pattern-completion — let the evidence pick between the two H2/H4 winners.
    if c.status == "UNGROUNDED" and not ev[ORIGIN_H2_PATTERN]["present"] \
            and ev[ORIGIN_H4_NONE]["present"] and ev[ORIGIN_H4_NONE]["lift"] >= _EV_STRONG:
        supported = ORIGIN_H4_NONE
    candidates_for_reweight = {k: {"weight": priors.get(k, 0.0)} for k in ORIGIN_KEYS}
    contradicted = [k for k in ORIGIN_KEYS if supported and k != supported and ev[k]["present"]]
    if supported:
        weights = _adjudicate_weights(candidates_for_reweight, supported, contradicted)
    else:
        weights = dict(priors)   # no committed origin (neutral self-talk) -> evidence-only field

    winner = max(weights, key=lambda k: weights[k]) if weights else ORIGIN_H4_NONE
    candidates = {
        k: {
            "claim": _ORIGIN_CLAIM[k],
            "weight": round(float(weights.get(k, 0.0)), 4),
            "prior": round(float(priors.get(k, 0.0)), 4),
            "present": bool(ev[k]["present"]),
            "cues": list(ev[k]["cues"]),
        }
        for k in ORIGIN_KEYS
    }
    explanation = _explain_origin(c.status, winner, candidates)
    decision_path = _origin_decision_path(c, ev, candidates, winner, supported)
    return {
        "candidates": candidates,
        "origin": winner,
        "explanation": explanation,
        "decision_path": decision_path,
    }


def _explain_origin(status: str, winner: str, candidates: Dict[str, dict]) -> str:
    """The one-line WHY that turns the detector into an EXPLAINER: ties the grounding STATUS to the
    WINNING origin and the strongest rival it beat — e.g. 'UNGROUNDED because the only strong origin
    is pattern-completion (0.70), not memory (0.00)'. Diagnosis-free by construction. Pure."""
    w = candidates.get(winner, {}).get("weight", 0.0)
    mem = candidates.get(ORIGIN_H1_MEMORY, {}).get("weight", 0.0)
    inter = candidates.get(ORIGIN_H3_INTERACTION, {}).get("weight", 0.0)
    if status == "UNGROUNDED":
        if winner == ORIGIN_H2_PATTERN:
            return (f"UNGROUNDED because the only strong origin is pattern-completion ({w:.2f}), "
                    f"not memory ({mem:.2f}) or interaction ({inter:.2f})")
        return (f"UNGROUNDED because the strongest origin is no-source ({w:.2f}) — "
                f"nothing in memory ({mem:.2f}) or interaction ({inter:.2f}) grounds it")
    if status == "GROUNDED":
        if winner == ORIGIN_H1_MEMORY:
            return f"GROUNDED because it was retrieved from memory/capability ({w:.2f})"
        if winner == ORIGIN_H3_INTERACTION:
            return f"GROUNDED because it was inferred from the observable interaction ({w:.2f})"
        return f"GROUNDED (not a self-claim / the user's framing thrown back) — origin {winner} ({w:.2f})"
    return (f"INFERRED neutral self-talk; no committed origin — leading hypothesis "
            f"{winner} ({w:.2f}), the field is left uncommitted (honest)")


def _origin_decision_path(claim: "Claim", ev: Dict[str, dict], candidates: Dict[str, dict],
                          winner: str, supported: Optional[str]) -> List[str]:
    """The ordered human DECISION PATH for one claim — sentence -> evidence found -> competition
    seeded -> status-supported origin strengthened -> winner. The auditable trail behind the
    weighted competition (the analogue of reality's weight_history). Pure; never raises."""
    present = [k for k in ORIGIN_KEYS if ev[k]["present"]]
    steps = [
        f"1. claim: {claim.claim[:72]!r}",
        f"2. classified: {claim.category} / source {claim.source} / {claim.status}",
        ("3. evidence: " + "; ".join(
            f"{k}=[{', '.join(ev[k]['cues'])}]" for k in present if ev[k]['cues'])) or
        "3. evidence: none found beyond the bare residual",
        "4. competition seeded over 4 origins; priors lifted by evidence, normalised (reality._normalise_weights)",
    ]
    if supported:
        steps.append(f"5. status {claim.status} supports origin '{supported}' -> "
                     f"reality._adjudicate_weights strengthens it, weakens present rivals")
    else:
        steps.append("5. status is non-committal (neutral/none) -> evidence-only field, no reweight")
    steps.append(f"6. winning origin: {winner}  (weight "
                 f"{candidates.get(winner, {}).get('weight', 0.0):.2f})")
    return steps


def classify_with_origin(text: str) -> List[dict]:
    """Per-sentence provenance EXTENDED with the adjudicated ORIGIN. Returns, per sentence, the
    full schema this task delivers:

        {claim, category, source, status, note,           # the existing P0 classification
         origin,                                          # the WINNING origin hypothesis
         origin_competition: {candidates, explanation, decision_path}}   # the weighted adjudication

    This is the EXPLAINER view: not just THAT a self-claim is ungrounded, but WHERE it came from
    and WHY that makes it ungrounded. ADDITIVE — it calls classify_sentence (unchanged) then folds
    in adjudicate_origin; the existing classify_self_narrative / ungrounded_sentences / is_ungrounded
    that the live guard depends on are NOT touched. Pure; never raises."""
    out: List[dict] = []
    for s in split_sentences(text):
        c = classify_sentence(s)
        d = c.as_dict()
        adj = adjudicate_origin(s, claim=c)
        d["origin"] = adj["origin"]
        d["origin_competition"] = {
            "candidates": adj["candidates"],
            "explanation": adj["explanation"],
            "decision_path": adj["decision_path"],
        }
        out.append(d)
    return out


def ungrounded_sentences(text: str) -> List[str]:
    """Just the sentences classified UNGROUNDED — the ship-blocking ones. Used by the live
    backstop (mouth) to decide what to strip/regenerate, and by metrics.scan_self_narrative
    to report markers."""
    return [c["claim"] for c in classify_self_narrative(text) if c["status"] == "UNGROUNDED"]


def is_ungrounded(text: str) -> bool:
    """True if ANY sentence of the text is an UNGROUNDED self-narrative claim."""
    return any(c["status"] == "UNGROUNDED" for c in classify_self_narrative(text))


# back-compat label so callers can reference the category set.
UNGROUNDED_CATEGORIES = _UNGROUNDED_CATEGORIES
