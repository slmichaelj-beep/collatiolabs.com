"""
memory_lirf — the LIRF (Ledger of Indexed, Resolved Facts) memory engine.

This is the hard, queryable counterpart to the prose Portrait. The Portrait stays
the soft "who they are", distilled at sleep and injected whole. LIRF is the
append-only ledger of *atomic USER facts* with full provenance: every belief is a
row with a stable id, a confidence, a corroboration count, the verbatim snippet
that set it, and an append-only history of everything it ever displaced.

Why it exists (the live bug it fixes): `portrait.load()` reads
`.anima/{name}.portrait.md` as the USER profile, but on disk that file held persona
bullets about HER — so asked "when's my birthday?" she had zero user facts AND a
file polluting her self-image into her memory-of-you slot. LIRF kills the
conflation at the schema level with one hard invariant: **entity is ALWAYS "you"**
for the user. A belief about Vera can never enter this store. Named third parties
(a dog, a mom) get their own entity key but are never merged into "you".

Design synthesis:
  * canonical entity model — collapse I/you/Lamar/me to the single key "you"
    (the actual root-cause fix);
  * rich audit spine — per-row stable id, append-only history[], status, verbatim
    evidence, source, confidence, support — so it is explainable, not a black box.

Three behaviours the Portrait can't give you:
  1. capture-NOW — facts land the same turn they're stated (Portrait is sleep-only);
  2. O(ms) exact lookup — a dict keyed on (entity, trait), no embeddings;
  3. newest-wins merge with corroboration — and history[] never deletes the
     displaced value, so "Vera used to think June 11, you corrected it" is provable.

Storage discipline matches `{name}.mem.json` / `{name}.json`: a flat list persisted
via `util.save_json` / `util.load_json` (atomic temp-write+rename, sealed under
ANIMA_KEY iff set). NEVER a bespoke open()/JSONL writer — that would leave the
ledger plaintext while the rest of .anima is sealed, and a crash mid-write could
corrupt it. Footprint bet: tens to low-hundreds of rows for a personal companion;
thousands is the documented ceiling where a real store would be needed.
"""

from __future__ import annotations

import math
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from .util import save_json, load_json

STORE = Path(".anima")

# The user is ALWAYS this entity. Folding I/you/Lamar/me onto one key is the
# root-cause fix: lookup never has to string-match a name, so the conflation that
# caused the live bug cannot reappear structurally.
SELF = "you"

VERSION = 1

# Confidence a freshly-stated declarative fact enters at.
CONF_NEW = 0.9
# An explicit user correction ("no it's the 12th", "actually I moved to Portland")
# enters higher — the user just told us directly.
CONF_CORRECTION = 0.97
# Floor for a belief to be eligible for the injected fact-block. Low-confidence
# beliefs stay on disk (and in lookup of last resort) but out of the prompt.
CONF_BLOCK_FLOOR = 0.55
# Confidence a HEDGED self-statement enters at ("I guess my favorite color is
# probably green"). A hedge ("I guess", "probably", "maybe", "I think", "kind of",
# "I'm not sure", "might be") is the user telling us they are NOT sure — so the fact
# must NOT clear the [KNOWN] FACT bar curiosity enforces (curiosity._CONF_KNOWN, 0.85),
# or LAW 002 would shield a guess forever and Vera would never learn the real value.
# Pinned BELOW that bar (so the gap stays OPEN / SUSPECTED and curiosity keeps asking)
# yet kept as a real low-confidence hint. A later confident restatement climbs/supersedes
# it the moment the user commits. Must stay < curiosity._CONF_KNOWN; cross-checked by the
# selftest so a drift in either constant is caught.
CONF_HEDGED = 0.6
# Asymptotic climb on agreement: conf -> conf + (1-conf)*RATE, capped.
CONF_AGREE_RATE = 0.34
CONF_CEIL = 0.99

# Near-immutable traits: if one of these *flips* to a new value, we don't silently
# overwrite — we install it but flag a soft re-confirm so the UI / a later turn can
# double-check (a one-off mistyped birthday shouldn't bury the right one silently).
NEAR_IMMUTABLE = frozenset({"birthday", "birthplace", "name", "blood_type"})

# Traits that hold a *set* of values rather than a single one. Captures append with
# dedupe instead of superseding ("I hate cilantro" + "I hate olives" -> both).
# ``reported_feeling`` is list-valued because a person voices MANY transient affect states
# over time ("I've been stressed", later "I'm excited"); each is an OBSERVED report worth
# keeping, none supersedes the other (see the affect rules + RULE #1 GUARDRAIL below).
LIST_TRAITS = frozenset({"dislikes", "likes", "pets", "allergies", "children", "siblings",
                         "reported_feeling"})


# --- canonical trait slugs --------------------------------------------------
# Trait-slug drift (birthday vs bday vs date_of_birth) fragments the O(1) lookup,
# so synonyms fold to ONE slug at write time. Unknown traits are allowed but
# normalised to snake_case.
_ALIASES = {
    "bday": "birthday",
    "bday_date": "birthday",
    "date_of_birth": "birthday",
    "dob": "birthday",
    "born": "birthday",
    "birth_date": "birthday",
    "birthplace": "birthplace",
    "born_in": "birthplace",
    "hometown": "birthplace",
    "lives": "lives",
    "lives_in": "lives",
    "location": "lives",
    "city": "lives",
    "home": "lives",
    "residence": "lives",
    "works_at": "employer",
    "work": "employer",
    "workplace": "employer",
    "company": "employer",
    "job": "occupation",
    "role": "occupation",
    "title": "occupation",
    "profession": "occupation",
    "works_on": "works_on",
    "project": "works_on",
    "dog": "dog_name",
    "dogs_name": "dog_name",
    "dog_name": "dog_name",
    "cat": "cat_name",
    "cats_name": "cat_name",
    "partner": "partner",
    "spouse": "partner",
    "wife": "partner",
    "husband": "partner",
    "gf": "partner",
    "bf": "partner",
    "girlfriend": "partner",
    "boyfriend": "partner",
    "mom": "mother",
    "mum": "mother",
    "mother": "mother",
    "dad": "father",
    "father": "father",
    "name": "name",
    "full_name": "name",
    "middle_name": "middle_name",
    "phone": "phone",
    "phone_number": "phone",
    "email": "email",
    "favorite_color": "favorite_color",
    "favourite_color": "favorite_color",
    "fav_color": "favorite_color",
}


def canon_trait(trait: str) -> str:
    """Fold a raw trait to its canonical snake_case slug (alias-resolved)."""
    s = re.sub(r"[^a-z0-9]+", "_", str(trait).strip().lower()).strip("_")
    return _ALIASES.get(s, s)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_value(v):
    """Case/space-normalised key for same-value comparison (lists compared as sets)."""
    if isinstance(v, list):
        return frozenset(re.sub(r"\s+", " ", str(x).strip().lower()) for x in v)
    return re.sub(r"\s+", " ", str(v).strip().lower())


def _new_id() -> str:
    return "f_" + secrets.token_hex(6)


# ---------------------------------------------------------------------------
# Tier-A extraction: cheap, synchronous regex matchers over the USER's text ONLY.
# Anchored to declarative FIRST-PERSON PRESENT so wishes/hypotheticals don't land
# ("I wish I lived in Paris", "if I worked at Google"). Each returns a candidate
# dict {trait, value, evidence}; evidence is the verbatim user snippet.
# ---------------------------------------------------------------------------

# A guard: the matched clause must not be governed by a wish / conditional / past
# longing. Applied to the text immediately preceding the match.
_HYPOTHETICAL = re.compile(
    r"\b(?:wish|hope|if|would|could|someday|one day|want to|wanna|going to|gonna|"
    r"used to|maybe|might|planning to|plan to|dream)\b", re.I)


def _local_clause(text: str, start: int) -> str:
    """The local clause governing a match: the text from the last sentence/clause break
    up to the match. Shared by the hypothetical guard and the hedge detector so both judge
    the SAME span (e.g. the words right before 'my favorite color ...')."""
    head = text[:start]
    return re.split(r"[.!?;]|\b(?:but|and|because|so)\b", head, flags=re.I)[-1]


def _not_hypothetical(text: str, start: int) -> bool:
    return _HYPOTHETICAL.search(_local_clause(text, start)) is None


# --- HEDGE detection -------------------------------------------------------
# A hedge is the user signalling they are NOT sure of a self-fact ("I guess my favorite
# color is probably green", "I think I live in Portland", "kind of my thing"). Unlike a
# _HYPOTHETICAL (a wish/conditional that means "this is NOT a fact, drop it"), a hedge means
# "this IS a fact but a soft one" — so we still CAPTURE it, only at a low confidence that
# stays BELOW curiosity's [KNOWN] bar (CONF_HEDGED). That keeps the gap OPEN so curiosity
# keeps asking and LAW 002 never shields a guess as if it were certain.
#
# Two surfaces a hedge shows up on, both handled:
#   1. governing the CLAUSE before the fact  -> "I guess my favorite color is green",
#      "I think my birthday is the 12th", "I'm not sure but I live in Portland".
#   2. sitting INSIDE the value slot          -> "... is probably green", "... is maybe blue".
# For (2) a rule may expose an optional named group `hedge` (consumed BEFORE the real value
# group `v`, so the value is the REAL word — "green", not "probably"); extract() reads that
# group's presence. As a belt-and-suspenders for any rule WITHOUT a hedge group, extract()
# also strips a leading hedge token off the captured value and flags it hedged.
_HEDGE_CLAUSE = re.compile(
    r"\b(?:i\s+guess|i\s+think|i\s+suppose|i\s+believe|i'?m\s+not\s+(?:really\s+)?sure|"
    r"i'?m\s+not\s+certain|probably|possibly|maybe|perhaps|might\s+be|kind\s+of|"
    r"sort\s+of|i\s+feel\s+like)\b", re.I)

# A hedge word/phrase sitting at the START of a captured value, to strip so the stored value
# is the REAL word. "probably green" -> "green" (+hedged); a bare hedge ("probably") strips to
# nothing -> we store NO value (the gap stays open) rather than the hedge word itself.
_HEDGE_LEADING = re.compile(
    r"^(?:probably|possibly|maybe|perhaps|kind\s+of|sort\s+of|i\s+guess|i\s+think)\s+",
    re.I)

# A value that is ENTIRELY a hedge word (e.g. the value-group backtracked and grabbed
# "probably" with no real word after it, as in "my favorite color is probably"). Such a value
# is meaningless AND must never be stored — it's the exact bug ("favorite_color=probably").
# Treated as hedged with NO value so the slot stays empty and the gap stays open.
_BARE_HEDGE = frozenset({"probably", "possibly", "maybe", "perhaps", "guess", "i guess",
                         "i think", "kind of", "sort of", "dunno", "unsure", "not sure"})

# The alternation a rule embeds as an optional (?P<hedge>...) group right before its value,
# so a single-word value rule (favorite_color/favorite_X) parses PAST the hedge to the real
# value instead of capturing the hedge word. Kept as a string so rules compose it inline.
_HEDGE_PREFIX = (r"(?P<hedge>(?:probably|possibly|maybe|perhaps|kind\s+of|sort\s+of|"
                 r"i\s+think|i\s+guess)\s+)?")


def _is_hedged(text: str, start: int) -> bool:
    """True iff the local clause governing a match carries a hedge marker."""
    return _HEDGE_CLAUSE.search(_local_clause(text, start)) is not None


def _strip_leading_hedge(val):
    """Strip a leading hedge token off a value. Returns (clean_value_or_None, was_hedged).
    'probably green' -> ('green', True); 'probably' -> (None, True); 'green' -> ('green',
    False). Operates on a single scalar string; list values are returned unchanged."""
    if not isinstance(val, str):
        return val, False
    # value that is ONLY a hedge word (a backtracked single-word grab) -> drop it, hedged.
    if re.sub(r"[^a-z ]", "", val.strip().lower()).strip() in _BARE_HEDGE:
        return None, True
    m = _HEDGE_LEADING.match(val)
    if not m:
        return val, False
    return _clean(val[m.end():]), True


# Each rule: (compiled regex, trait, value-builder(match) -> value|None).
# Value-builders strip trailing punctuation and reject empties.
def _clean(s):
    s = re.sub(r"\s+", " ", (s or "").strip()).strip(" .,!?;:\"'")
    return s or None


# A capitalised word in an APPOSITIVE name slot ("my daughter <X>") that is NOT a real
# name — a sentence-initial / clause-initial function word, a pronoun, or a common aux that
# can appear Title-cased mid-stream. The appositive rules already require a leading capital
# AND lowercase-rest AND a negative-lookahead on copulas; this is the final guard so a
# stray "My daughter Then..." / "my friend They..." can never be mistaken for a name.
# (Observed > Assumed: when in doubt, capture NOTHING rather than fabricate a name.)
_STOPNAMES = frozenset(
    w.lower() for w in (
        "I", "Im", "Ive", "Id", "Ill", "My", "We", "Weve", "Were", "Our", "The", "A",
        "An", "This", "That", "These", "Those", "He", "She", "It", "They", "You", "Your",
        "Last", "Next", "Then", "And", "But", "So", "Because", "When", "Where", "What",
        "Who", "Why", "How", "If", "Yeah", "Honestly", "Lately", "Recently", "Now", "Just",
        "Today", "Yesterday", "Tomorrow", "Tonight", "Maybe", "Really", "After", "Before",
        "Since", "While", "Also", "Still", "Yes", "No", "Oh", "Well", "Is", "Are", "Was",
        "Were", "Has", "Have", "Had", "Named", "Called", "Got", "Started", "Moved", "Left",
        "Quit", "Joined", "Loves", "Lives", "Works", "Said", "Told", "Came", "Went", "Made",
    )
)


def _is_stopname(v) -> bool:
    """True iff an appositive-slot capture is a function word / pronoun / aux, not a name."""
    s = re.sub(r"[^a-z]", "", str(v or "").strip().lower())
    return (not s) or s in _STOPNAMES


# --- AFFECT / FEELING lexicon (for the reported_feeling rule) ----------------------------
# THE #1-RULE GUARDRAIL — read this before touching the affect rules:
#   The reported_feeling trait stores that the USER *reported* feeling a way, as an OBSERVED
#   fact about the user, grounded verbatim in their words (the evidence snippet is the user's
#   own sentence). It is the durable record of "the user SAID they've been stressed", NEVER a
#   claim that Vera feels anything. Vera's #1 rule (never confabulate a feeling) is preserved
#   precisely because the value is the user's stated affect word, captured only from an
#   explicit FIRST-PERSON feeling frame ("I'm / I've been / I feel / we are <affect>"). There
#   is no inference: if the user did not say it, nothing is stored.
# A closed set of common affect adjectives the user applies to THEMSELVES. Kept as bare
# adjectives (the rule's frame supplies the "the user is/feels" part) so a stray noun can
# never match. Mirrors the conservation observatory's tone lexicon so the durable capture
# lines up with what that tool counts as tone salience.
_AFFECT_WORDS = (
    r"stressed|stress|stressful|anxious|nervous|overwhelmed|worried|scared|afraid|"
    r"excited|thrilled|happy|glad|grateful|hopeful|proud|relieved|content|calm|"
    r"sad|down|depressed|lonely|tired|exhausted|drained|burnt|burned|burnt\s*out|"
    r"frustrated|angry|upset|miserable|heartbroken|devastated|furious|uneasy|restless|"
    r"hopeless|ashamed|guilty|delighted|joyful|fearful"
)
# Degree adverbs that modify an affect ("really stressed", "so anxious"). Captured WITH the
# affect word so the stored value keeps the user's stated INTENSITY ("really stressed"),
# which is itself the signal the conservation ledger reported lost at capture.
_AFFECT_DEGREE = (r"(?:really|very|so|super|extremely|incredibly|deeply|terribly|totally|"
                  r"completely|utterly|quite|pretty|kinda|a\s+bit|a\s+little)\s+")


def _affect_value(m):
    """Build the reported_feeling value: the user's stated affect WITH any degree modifier,
    e.g. "really stressed", "excited". Returns the verbatim phrase the user used so both the
    feeling AND its intensity are kept durably (and so the value is unmistakably the USER's
    word, never an inference). None if the affect group is empty (defensive)."""
    aff = (m.group("aff") or "").strip()
    if not aff:
        return None
    deg = (m.groupdict().get("deg") or "").strip()
    phrase = (deg + " " + aff).strip() if deg else aff
    return _clean(phrase)


_RULES = [
    # name
    (re.compile(r"\bmy name(?:'s| is)\s+(?P<v>[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+){0,2})", re.I),
     "name", lambda m: _clean(m.group("v"))),
    (re.compile(r"\b(?:i'?m|i am|call me)\s+(?P<v>(?-i:[A-Z])[a-z'][\w'-]+)(?:\b(?!\s+(?:from|in|at|on|to|a|an|the|going|getting|feeling|allergic|working|trying|sorry|here|there|back|home|done|off|out|fine|good|great|okay|sure|so|very|really|not|just|still|now|also|gonna|about)\b))", re.I),
     "name", lambda m: _clean(m.group("v"))),
    # birthday — "my birthday is June 12", "my birthday's the 12th", "I was born on June 12"
    (re.compile(r"\bmy\s+(?:birthday|bday|b-?day)(?:'s| is| falls on|:)?\s+(?:on\s+)?(?P<v>(?:[A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)|(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)|(?:the\s+\d{1,2}(?:st|nd|rd|th)))", re.I),
     "birthday", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi was born on\s+(?P<v>[A-Z][a-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)", re.I),
     "birthday", lambda m: _clean(m.group("v"))),
    # location — "I live in Portland", "I'm in Portland, OR", "I'm based in Berlin"
    (re.compile(r"\bi\s+(?:live|reside|am based|'m based|stay)\s+in\s+(?P<v>[A-Z][\w'-]+(?:[ ,]+[A-Z][\w'.-]+){0,3})", re.I),
     "lives", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi'?m\s+(?:currently\s+)?in\s+(?P<v>[A-Z][\w'-]+(?:,\s*[A-Z]{2})?)\b(?!\s+(?:a|an|the|trouble|love|charge|the\s+middle)\b)", re.I),
     "lives", lambda m: _clean(m.group("v"))),
    # employer / occupation
    (re.compile(r"\bi work\s+at\s+(?P<v>(?-i:[A-Z])[\w'&.-]+(?:\s+(?:(?:of|&|de|la|von|van)\s+)?(?-i:[A-Z])[\w'&.-]+){0,3})", re.I),
     "employer", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi work\s+(?:as\s+(?:an?\s+)?|in\s+)(?P<v>[a-z][\w'-]+(?:\s+[\w'-]+){0,2})", re.I),
     "occupation", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi'?m\s+(?:an?\s+)?(?P<v>(?:software|data|product|research)?\s*(?:engineer|developer|designer|scientist|teacher|nurse|doctor|lawyer|writer|artist|founder|manager|professor|student))\b", re.I),
     "occupation", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi(?:'?m| am)\s+working\s+on\s+(?P<v>[\w'-]+(?:\s+[\w'-]+){0,4})", re.I),
     "works_on", lambda m: _clean(m.group("v"))),
    # pets — "my dog's name is Biscuit", "I have a dog named Biscuit", "my cat is Mochi"
    (re.compile(r"\bmy\s+dog(?:'s)?(?:\s+is)?\s+(?:(?:name(?:'s| is)?|named|called)\s+)?(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "dog_name", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+dog\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "dog_name", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+cat(?:'s)?(?:\s+is)?\s+(?:(?:name(?:'s| is)?|named|called)\s+)?(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "cat_name", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+cat\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "cat_name", lambda m: _clean(m.group("v"))),
    # relations — "my mom's name is Carol", "my wife Jen", "my sister is Anna"
    (re.compile(r"\bmy\s+(?:mom|mum|mother)(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "mother", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+(?:dad|father)(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "father", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+(?:wife|husband|partner|gf|bf|girlfriend|boyfriend|spouse)(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)?(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "partner", lambda m: _clean(m.group("v"))),
    # favorite color — the value group is single-word, so an optional hedge ("... is
    # probably green") is consumed by the (?P<hedge>...) prefix FIRST, leaving v="green"
    # (the REAL value, never "probably"). extract() reads the hedge group to lower confidence.
    (re.compile(r"\bmy\s+favou?rite\s+colou?r\s+is\s+" + _HEDGE_PREFIX + r"(?P<v>[a-z][\w'-]+)", re.I),
     "favorite_color", lambda m: _clean(m.group("v"))),
    # likes / dislikes (list-valued) — "I love sushi", "I hate cilantro", "I can't stand olives".
    # The object stops before a conjunction so "X and Y" yields two separate hits, not
    # one value "X and Y" (the negative-lookahead on each extra word does the cut).
    (re.compile(r"\bi\s+(?:love|really like|adore)\s+(?P<v>(?!and\b|but\b|or\b)[a-z][\w'-]+(?:\s+(?!and\b|but\b|or\b)[\w'-]+){0,2})", re.I),
     "likes", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi\s+(?:hate|can'?t stand|despise|loathe|really dislike)\s+(?P<v>(?!and\b|but\b|or\b)[a-z][\w'-]+(?:\s+(?!and\b|but\b|or\b)[\w'-]+){0,2})", re.I),
     "dislikes", lambda m: _clean(m.group("v"))),
    # siblings — "my brother is Sam", "my sister's name is Anna"
    (re.compile(r"\bmy\s+brother(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "brother", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+sister(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "sister", lambda m: _clean(m.group("v"))),
    # allergy (list-valued) — "I'm allergic to shellfish", "I have an allergy to peanuts".
    # NOTE: this also stops "I'm allergic to X" from mis-firing the name rule (allergic is lowercase).
    (re.compile(r"\bi(?:'?m| am)\s+allergic\s+to\s+(?P<v>(?!and\b|or\b)[a-z][\w'-]+(?:\s+(?!and\b|or\b)[\w'-]+){0,2})", re.I),
     "allergy", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+an?\s+allergy\s+to\s+(?P<v>(?!and\b|or\b)[a-z][\w'-]+(?:\s+(?!and\b|or\b)[\w'-]+){0,2})", re.I),
     "allergy", lambda m: _clean(m.group("v"))),
    # car — "I drive a Tesla Model 3", "my car is a Subaru"
    (re.compile(r"\b(?:i drive|my car is)\s+(?:an?\s+)?(?P<v>(?-i:[A-Z])[\w'-]+(?:\s+[\w'-]+){0,2})", re.I),
     "car", lambda m: _clean(m.group("v"))),
    # phone / email
    (re.compile(r"\bmy\s+(?:phone\s+|cell\s+|mobile\s+)?number(?:'s| is)\s+(?P<v>[\d][\d\-().\s]{6,}\d)", re.I),
     "phone", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+email(?:\s+address)?(?:'s| is)\s+(?P<v>[\w.+-]+@[\w-]+\.[\w.-]+)", re.I),
     "email", lambda m: _clean(m.group("v"))),
    # children — "my son is Theo", "my daughter's name is Mia", "I have a son named Theo"
    (re.compile(r"\bmy\s+son(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "son", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bmy\s+daughter(?:'s)?\s+(?:name(?:'s| is)?\s+|named\s+|called\s+|is\s+(?:(?:named|called)\s+)?)(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "daughter", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+(?:son|boy)\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "son", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+(?:daughter|girl)\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "daughter", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+brother\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "brother", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi have\s+a\s+sister\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "sister", lambda m: _clean(m.group("v"))),
    # --- APPOSITIVE names (WAVE A) -----------------------------------------------------
    # A name stated in apposition, WITHOUT a copula: "my daughter Maya", "my friend Sloane",
    # "a dog named Cooper". The capital-guard ((?-i:[A-Z])) is what makes this safe: the
    # token right after the role must START with a capital AND be otherwise lowercase, so
    # "my daughter started school" (started is lowercase) and "my friend and I" (and) can
    # never be read as a name. _is_stopname is the final guard against a function/aux word
    # that happens to be Title-cased mid-stream ("my friend Then we left"). These mirror the
    # copula rules above but drop the "is/named/called" requirement — the #1 total-loss class
    # the conservation ledger named. (Copula rules are listed FIRST so "my daughter's name is
    # Mia" still prefers the specific form; extract() keeps the first hit for a scalar trait.)
    (re.compile(r"\bmy\s+daughter\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "daughter", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+son\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "son", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+(?:wife|husband|partner|gf|bf|girlfriend|boyfriend|spouse)\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "partner", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+(?:mom|mum|mother)\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "mother", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+(?:dad|father)\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "father", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+brother\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "brother", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+sister\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "sister", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    (re.compile(r"\bmy\s+friend\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "friend", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    # "a dog named Cooper" / "we adopted a dog named Cooper" — pet appositive WITHOUT "my".
    (re.compile(r"\b(?:a|our|the)\s+dog\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "dog_name", lambda m: _clean(m.group("v"))),
    (re.compile(r"\b(?:a|our|the)\s+cat\s+(?:named|called)\s+(?P<v>(?-i:[A-Z])[\w'-]+)", re.I),
     "cat_name", lambda m: _clean(m.group("v"))),
    # --- LIFE-EVENT durable facts (WAVE A) ---------------------------------------------
    # A stated transition becomes a DURABLE trait, not a dropped verb. "I moved to Austin"
    # -> moved_to=Austin. EVERY capital-class is wrapped (?-i:...) so re.I can't make it match
    # a lowercase common noun: "I moved to the city/a new place" captures NOTHING, and the
    # hypothetical guard in extract() rejects "maybe I'll move to X". The place run only
    # extends across ADDITIONAL capitalised tokens ("New York", "Austin, TX"), so it stops at
    # the first lowercase word ("Austin because ..." -> "Austin"). These are kept as their OWN
    # traits (moved_to/employer/business) so they neither fight nor silently overwrite the
    # current-state slots (lives/employer) the Spine already owns.
    (re.compile(r"\bi\s+(?:just\s+|recently\s+|finally\s+)?moved\s+(?:back\s+)?to\s+(?P<v>(?-i:[A-Z])[\w'-]+(?:[ ,]+(?-i:[A-Z])[\w'.-]+){0,3})", re.I),
     "moved_to", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bwe\s+(?:just\s+|recently\s+|finally\s+)?moved\s+(?:back\s+)?to\s+(?P<v>(?-i:[A-Z])[\w'-]+(?:[ ,]+(?-i:[A-Z])[\w'.-]+){0,3})", re.I),
     "moved_to", lambda m: _clean(m.group("v"))),
    # "I started/founded/launched a company (called X)" -> the durable event; X is captured
    # when named (capital-guarded), else the trait alone records that the event happened.
    (re.compile(r"\bi\s+(?:just\s+|recently\s+|finally\s+|co-?)?(?:started|launched|founded|co-?founded|opened)\s+(?:my\s+own\s+|my\s+|a\s+|an\s+)?(?:company|business|startup|firm|nonprofit|shop|store|practice|brand)(?:\s+(?:called|named)\s+(?P<v>(?-i:[A-Z])[\w'&.-]+(?:\s+(?-i:[A-Z])[\w'&.-]+){0,3}))?", re.I),
     "business", lambda m: _clean(m.group("v")) if m.group("v") else "started a company"),
    # "I quit my job" / "I left my job" -> a durable event marker.
    (re.compile(r"\bi\s+(?:just\s+|recently\s+|finally\s+)?(?:quit|left|resigned\s+from)\s+(?:my\s+)?(?:job|position|role|company)\b", re.I),
     "job_change", lambda m: "quit my job"),
    # "I got a new job" / "I started a new job" -> a durable event marker.
    (re.compile(r"\bi\s+(?:just\s+|recently\s+)?(?:got|started|landed|accepted)\s+(?:a\s+)?new\s+job\b", re.I),
     "job_change", lambda m: "started a new job"),
    # "I joined Acme" / "I started at Acme" -> employer (capital-guarded company name).
    (re.compile(r"\bi\s+(?:just\s+|recently\s+)?(?:joined|started\s+at|started\s+working\s+at)\s+(?P<v>(?-i:[A-Z])[\w'&.-]+(?:\s+(?-i:[A-Z])[\w'&.-]+){0,3})", re.I),
     "employer", lambda m: _clean(m.group("v"))),
    # "I married Jen" / "we got married" -> a durable relationship event (name captured
    # when given; the partner copula/appositive rules above also catch "my wife Jen").
    (re.compile(r"\bi\s+married\s+(?P<v>(?-i:[A-Z])[a-z'-]+)\b", re.I),
     "married_to", lambda m: _clean(m.group("v")) if not _is_stopname(m.group("v")) else None),
    # "we adopted a dog/cat" / "I adopted a dog" -> a pet exists (the NAME, when appositive,
    # is caught by the pet rules above; this records the species as a list-valued pet event).
    (re.compile(r"\b(?:we|i)\s+(?:just\s+|recently\s+)?adopted\s+(?:a\s+|an\s+|our\s+)?(?P<v>dog|cat|puppy|kitten|kitty)\b", re.I),
     "pets", lambda m: _clean(m.group("v"))),
    # "we had a baby" / "I had a baby" / "we just had a baby boy" -> a durable life event.
    (re.compile(r"\b(?:we|i)\s+(?:just\s+|recently\s+|finally\s+)?had\s+(?:a\s+|our\s+)?(?P<v>baby|baby\s+(?:boy|girl)|son|daughter|kid|child|twins)\b", re.I),
     "life_event", lambda m: "had a " + (_clean(m.group("v")) or "baby")),
    # work — clear job titles only, and a business owned/founded (capital-guarded so "I run errands" can't match)
    (re.compile(r"\bi'?m\s+(?:the|a|an)\s+(?P<v>(?:senior\s+|lead\s+|principal\s+|chief\s+|head\s+|junior\s+|staff\s+)?(?:founder|co-?founder|ceo|cto|cfo|coo|president|vp|director|manager|engineer|developer|designer|scientist|analyst|consultant|architect|researcher|professor|owner|partner))\b", re.I),
     "role", lambda m: _clean(m.group("v"))),
    (re.compile(r"\b(?:i\s+(?:run|own|founded|started)|my\s+(?:company|business|startup)\s+is(?:\s+called)?)\s+(?:an?\s+)?(?:(?:company|business|startup)\s+(?:called\s+)?)?(?P<v>(?-i:[A-Z])[\w'&.-]+(?:\s+(?:(?:of|&|de|la|von|van)\s+)?(?-i:[A-Z])[\w'&.-]+){0,3})", re.I),
     "business", lambda m: _clean(m.group("v"))),
    # health — diet + medical condition
    (re.compile(r"\bi'?m\s+(?:a\s+)?(?P<v>vegetarian|vegan|pescatarian|pescetarian|gluten-?free|dairy-?free|lactose intolerant|keto|paleo|kosher|halal)\b", re.I),
     "diet", lambda m: _clean(m.group("v"))),
    (re.compile(r"\bi (?:have|was diagnosed with)\s+(?P<v>(?:type \d )?(?:diabetes|asthma|adhd|add|anxiety|depression|hypertension|arthritis|epilepsy|migraines?|insomnia|celiac|crohn'?s|ibs|ocd|ptsd|dyslexia)|(?-i:[A-Z])[\w'-]+\s+(?:disease|syndrome|disorder))\b", re.I),
     "condition", lambda m: _clean(m.group("v"))),
    # age (distinct from birthday) — "I'm 34", "I'm 34 years old"; guarded so "I'm 5 minutes late" can't match
    (re.compile(r"\bi(?:'?m| am)\s+(?P<v>\d{1,3})(?=\s+years?\s+old\b|\s*[.!?,]|\s*$)", re.I),
     "age", lambda m: _clean(m.group("v"))),
    # generalized favorite — "my favorite food is pizza" -> favorite_food: pizza. The optional
    # (?P<hedge>...) prefix consumes a leading "probably/maybe/I think ..." so the value is the
    # REAL one ("pizza", not "probably") and extract() lowers confidence below the KNOWN bar.
    (re.compile(r"\bmy\s+favou?rite\s+(?P<cat>food|meal|dish|cuisine|movie|film|show|series|band|artist|musician|song|book|author|team|drink|beer|wine|season|sport|game|hobby|place|city|number|animal|colou?r)\s+is\s+" + _HEDGE_PREFIX + r"(?P<v>[\w'\d][\w'-]*(?:\s+[\w'-]+){0,3})", re.I),
     lambda m: "favorite_" + m.group("cat").lower().replace("colour", "color").replace("film", "movie").replace("series", "show"),
     lambda m: _clean(m.group("v"))),
    # --- REPORTED FEELING (affect / tone) ----------------------------------------------
    # RULE #1 GUARDRAIL (see _AFFECT_WORDS above): captures that the USER reported a feeling
    # state — an OBSERVED fact grounded in their verbatim words — NOT that Vera feels anything.
    # Frame: an explicit first-person feeling clause "I'm / I am / I've been / I feel / I was /
    # we are <[degree] affect>", e.g. "I've been really stressed", "we are excited". The value
    # is the user's stated phrase WITH its intensity ("really stressed"). _not_hypothetical
    # (applied in extract()) rejects "I wish I were less stressed"; the closed affect set keeps
    # a non-feeling word from matching; list-valued so successive distinct feelings accumulate.
    # The conservation ledger named tone the #1 routinely-dropped class — this gives it a slot.
    (re.compile(r"\b(?:i(?:'?m| am| are|'?ve been| have been| feel| felt| was| was feeling| keep feeling| get| got)|"
                r"we(?:'?re| are|'?ve been| have been))\s+"
                r"(?P<deg>" + _AFFECT_DEGREE + r")?(?P<aff>(?:" + _AFFECT_WORDS + r"))\b", re.I),
     "reported_feeling", _affect_value),
    # "feeling <affect>" / "been feeling <affect>" without an explicit subject pronoun right
    # before (e.g. "honestly, feeling pretty overwhelmed") — still a first-person report in a
    # chat turn; guarded the same closed-set way. Kept narrow (the gerund "feeling" anchors it).
    (re.compile(r"\b(?:been\s+)?feeling\s+(?P<deg>" + _AFFECT_DEGREE + r")?(?P<aff>(?:" + _AFFECT_WORDS + r"))\b", re.I),
     "reported_feeling", _affect_value),
]

# Explicit-correction cues: when present, the captured fact enters as a correction
# (higher confidence, prior row tagged 'user-corrected').
_CORRECTION_CUE = re.compile(
    r"\b(?:no,?\s+it'?s|actually|correction|i meant|not\s+\w+,?\s+it'?s|"
    r"that'?s wrong|let me correct|i misspoke|scratch that)\b", re.I)

# Retraction cues: "forget that", "forget my birthday", "that's not true anymore".
_RETRACT_CUE = re.compile(
    r"\b(?:forget (?:that|about that|my)|delete (?:that|my)|that'?s (?:no longer|not) true|"
    r"i (?:don'?t|do not) (?:have|live)|never mind that)\b", re.I)


def extract(text: str):
    """TIER A. Pull durable first-person facts from a USER utterance via rules.

    Returns a list of candidate dicts {trait, value, evidence, correction:bool}.
    Operates on `text` (the user's words) ONLY — never the reply. Anchored to
    declarative present so wishes/hypotheticals are rejected.
    """
    if not text or not text.strip():
        return []
    is_corr = bool(_CORRECTION_CUE.search(text))
    found = {}
    for rx, trait, build in _RULES:
        for m in rx.finditer(text):
            if not _not_hypothetical(text, m.start()):
                continue
            val = build(m)
            # HEDGE: a soft self-statement ("I guess my favorite color is probably green").
            # A rule may capture the hedge in an optional (?P<hedge>...) group placed before
            # its value; either way we (a) flag the candidate hedged so merge() enters it
            # BELOW the [KNOWN] bar (leaving the gap open for curiosity), and (b) strip any
            # leading hedge token off the value so we store the REAL word ("green"), never the
            # hedge ("probably"). A value that is ONLY a hedge word strips to nothing -> we
            # store NO value (the slot stays empty -> still an open gap), never the hedge.
            hedged = bool(m.groupdict().get("hedge")) or _is_hedged(text, m.start())
            val, leading_hedged = _strip_leading_hedge(val)
            hedged = hedged or leading_hedged
            if not val:
                continue
            ev = _clean(text[max(0, m.start() - 0):m.end()]) or text.strip()
            ct = canon_trait(trait(m) if callable(trait) else trait)
            # within one utterance, list traits accumulate; scalar traits keep the
            # first clean hit (rules are ordered most-specific first).
            if ct in LIST_TRAITS:
                cand = found.setdefault(ct, {"trait": ct, "value": [], "evidence": ev,
                                             "correction": is_corr, "hedged": False})
                if val not in cand["value"]:
                    cand["value"].append(val)
                if hedged:
                    cand["hedged"] = True
            elif ct not in found:
                found[ct] = {"trait": ct, "value": val, "evidence": ev,
                             "correction": is_corr, "hedged": hedged}
    return list(found.values())


# ---------------------------------------------------------------------------
# Tier B (optional): a strict, model-assisted extractor. Off by default; runs the
# real local brain with a tight "never infer" instruction and parses STRICT JSON.
# Returns the same candidate shape. Used by the bench's LIRF condition and wired
# behind a flag — never on the critical path of a live turn.
# ---------------------------------------------------------------------------

_TIERB_SYSTEM = (
    "You extract DURABLE personal facts a person stated about THEMSELVES, for their "
    "companion's memory. Output ONLY a JSON array. Each item: "
    '{"trait": snake_case_slug, "value": string, "evidence": verbatim quote from '
    "the user}. Rules: include a fact ONLY if the user EXPLICITLY stated it about "
    "their own life (name, birthday, where they live, work, pets, family, strong "
    "likes/dislikes). NEVER infer, guess, or include anything about the assistant. "
    "Ignore questions, hypotheticals ('I wish...'), and the assistant's words. If "
    "there are no durable self-facts, output []. Output the JSON array and nothing else."
)


def extract_model(text: str, brain) -> list:
    """TIER B. Model-assisted strict extraction. `brain` has .reply(system,user,history).
    Best-effort: any parse failure yields []. Never raises into the caller."""
    if not text or not text.strip() or brain is None:
        return []
    try:
        raw = brain.reply(_TIERB_SYSTEM, f'User said: "{text.strip()}"\n\nJSON:', [])
    except Exception:
        return []
    import json as _json
    m = re.search(r"\[.*\]", raw or "", re.S)
    if not m:
        return []
    try:
        arr = _json.loads(m.group(0))
    except Exception:
        return []
    out = []
    if isinstance(arr, list):
        for it in arr:
            if not isinstance(it, dict):
                continue
            trait, value = it.get("trait"), it.get("value")
            if not trait or value in (None, "", []):
                continue
            out.append({"trait": canon_trait(trait), "value": value,
                        "evidence": str(it.get("evidence") or text).strip(),
                        "correction": False})
    return out


# ---------------------------------------------------------------------------
# The store.
# ---------------------------------------------------------------------------

class Facts:
    """The LIRF ledger for one creature: a flat list of belief rows, indexed two
    ways in memory (by (entity,trait) for O(1) lookup, by id for edit/retract)."""

    def __init__(self, rows=None):
        self.rows = rows or []
        self._reindex()

    # --- indexing -----------------------------------------------------------
    def _reindex(self):
        # Active row per (entity, trait) — the lookup spine.
        self._by_key = {}
        # id -> row — the editor spine.
        self._by_id = {}
        for r in self.rows:
            self._by_id[r["id"]] = r
            if r.get("status") == "active":
                self._by_key[(r["entity"], r["trait"])] = r

    # --- persistence (atomic + encrypted, via util — never a bespoke writer) -
    @classmethod
    def path(cls, name):
        return STORE / f"{name}.lirf.json"

    @classmethod
    def load(cls, name) -> "Facts":
        """Load the LIRF ledger with LAW-001 self-healing (ANIMA LAW 001 — NEVER LOSE
        CONTINUITY). A clean file loads exactly as before (single parse, no added latency).

        A CORRUPT/unreadable ledger no longer silently returns 0 rows — the prior raw
        util.load_json swallowed JSON/decode errors and returned None, which is TOTAL SILENT
        MEMORY LOSS. Instead reliability.guarded_store_load recovers from the most-recent good
        backup if one exists, else stops CLEANLY (flagged-empty) and records a
        constitution.approved_loss — a clean stop is strictly better than a silently-wrong
        empty store. On a clean load we also take a guarded snapshot (only when the file is
        good) so a recoverable backup always exists. A corrupt store can never overwrite a
        good backup. The reliability layer is optional: if it cannot be imported we fall back
        to the original load (degraded, but never a hard dependency on the safety net)."""
        path = cls.path(name)
        try:
            from . import reliability
        except Exception:                               # pragma: no cover - reliability is core
            d = load_json(path)
            rows = d.get("rows", []) if isinstance(d, dict) else []
            return cls(rows)
        # reliability calls are keyed on the CURRENT module STORE (honours a redirected
        # test store), so backups + recovery resolve against the same .anima the ledger uses.
        d, info = reliability.guarded_store_load(
            name, path, store=STORE, kind="LIRF ledger", expect_key="rows")
        rows = d.get("rows", []) if isinstance(d, dict) else []
        inst = cls(rows)
        # remember whether this load was a flagged stop (vs a normal empty/new store), so a
        # caller can tell "honestly empty" from "corrupt + unrecoverable, do not overwrite".
        inst._load_flagged_empty = bool(info.get("flagged"))
        if info.get("ok") and not info.get("empty"):
            # the file parsed clean (incl. after a successful recovery) — capture that good
            # state so a future corruption always has a snapshot to fall back to. Throttled +
            # guarded; never raises, never slows the happy path beyond a stat()-cheap check.
            reliability.maybe_backup_store(name, path, store=STORE, kind="LIRF ledger",
                                           expect_key="rows")
        return inst

    def save(self, name) -> None:
        STORE.mkdir(exist_ok=True)
        save_json(self.path(name), {"version": VERSION, "rows": self.rows})

    # --- capture: utterance -> candidates -----------------------------------
    def capture(self, name, user_text, reply=None, brain=None, model_pass=False):
        """Extract durable USER facts from `user_text` (Tier A always; Tier B iff
        model_pass and a brain). `reply` is accepted for signature parity but is
        NEVER read — facts come only from the user's words. Returns the candidate
        list (already shaped for merge); does not persist (caller merges + saves)."""
        cands = extract(user_text)
        seen = {(c["trait"], _norm_value(c["value"])) for c in cands}
        if model_pass and brain is not None:
            for c in extract_model(user_text, brain):
                k = (c["trait"], _norm_value(c["value"]))
                if k not in seen:
                    cands.append(c)
                    seen.add(k)
        # honour an explicit retraction in the same utterance
        if _RETRACT_CUE.search(user_text or ""):
            for c in cands:
                c["retract"] = True
        return cands

    # --- merge: candidate -> ledger (the heart) -----------------------------
    def merge(self, cand) -> dict:
        """Fold one candidate into the ledger, keyed on (SELF, trait). Returns the
        row touched. INVARIANT: entity is always SELF for the user — a third party
        gets its own entity but never SELF; here every captured user-fact is SELF."""
        trait = canon_trait(cand["trait"])
        entity = cand.get("entity", SELF)
        # hard schema-level guard against the conflation bug: a belief about HER can
        # never enter as the user. Anything that isn't an explicit third party folds
        # to SELF.
        if entity in ("vera", "assistant", "me", "i", "myself", None, ""):
            entity = SELF
        value = cand["value"]
        now = _now()
        is_corr = bool(cand.get("correction"))
        hedged = bool(cand.get("hedged"))
        # Entry confidence for a NEW or SUPERSEDING value. An explicit correction is the
        # user telling us directly (highest). A HEDGE is the user telling us they are unsure,
        # so it enters BELOW curiosity's [KNOWN] bar (CONF_HEDGED) — the gap stays open and
        # LAW 002 never shields a guess. Correction beats hedge if (rarely) both are present.
        entry_conf = CONF_CORRECTION if is_corr else (CONF_HEDGED if hedged else CONF_NEW)
        src = cand.get("source") or f"chat {now[:10]}"
        ev = cand.get("evidence") or ""
        existing = self._by_key.get((entity, trait))

        if cand.get("retract") and existing is not None:
            return self.retract(existing["id"])

        if existing is None:
            row = {
                "id": _new_id(),
                "entity": entity,
                "trait": trait,
                "value": value,
                "confidence": entry_conf,
                "support": 1,
                "source": src,
                "evidence": ev,
                "created": now,
                "updated": now,
                "status": "active",
                "history": [],
            }
            if trait in NEAR_IMMUTABLE:
                row["needs_reconfirm"] = False
            self.rows.append(row)
            self._by_id[row["id"]] = row
            self._by_key[(entity, trait)] = row
            return row

        same = _same_value(existing, value, trait)
        if same:
            # corroboration: support++, confidence climbs asymptotically; refresh
            # provenance to the most recent mention.
            if trait in LIST_TRAITS:
                existing["value"] = _merge_list(existing["value"], value)
            existing["support"] = int(existing.get("support", 1)) + 1
            existing["confidence"] = _climb(existing.get("confidence", CONF_NEW))
            existing["source"] = src
            existing["evidence"] = ev or existing.get("evidence", "")
            existing["updated"] = now
            return existing

        # DIFFERENT value -> newest wins. Push the old value into history[] (never
        # deleted — the explainability spine), install the new one.
        existing["history"].append({
            "value": existing["value"],
            "confidence": existing.get("confidence"),
            "source": existing.get("source"),
            "at": existing.get("updated"),
            "reason": "user-corrected" if is_corr else "superseded",
        })
        existing["value"] = value
        existing["confidence"] = entry_conf
        existing["support"] = 1                 # fresh claim, not yet re-confirmed
        existing["source"] = src
        existing["evidence"] = ev
        existing["updated"] = now
        existing["status"] = "active"
        if trait in NEAR_IMMUTABLE and not is_corr:
            # a silent flip of a near-immutable trait is suspicious — flag, don't bury
            existing["needs_reconfirm"] = True
        else:
            existing.pop("needs_reconfirm", None)
        return existing

    # --- lookup: O(1) single active row -------------------------------------
    def lookup(self, entity, trait):
        """The constant-time exact lookup. Returns the active row or None."""
        return self._by_key.get((entity, canon_trait(trait)))

    def value_of(self, trait, entity=SELF):
        r = self.lookup(entity, trait)
        return r["value"] if r else None

    # --- about: ranked one-pass scan ----------------------------------------
    def about(self, entity=SELF):
        """All active rows for an entity, ranked by salience = conf*log(1+support).
        Backs the viewer and block()."""
        rows = [r for r in self.rows
                if r.get("status") == "active" and r["entity"] == entity]
        rows.sort(key=_salience, reverse=True)
        return rows

    # --- block: the compact injected fact-block -----------------------------
    def block(self, name=None, budget=15, entity=SELF) -> str:
        """Dense, model-friendly fact-block for prompt injection. Active rows with
        confidence>=floor, ranked, top ~budget. ~200 tokens of auditable beliefs vs
        a 60-line transcript. Empty string if nothing qualifies."""
        rows = [r for r in self.about(entity)
                if r.get("confidence", 0) >= CONF_BLOCK_FLOOR][:budget]
        if not rows:
            return ""
        lines = ["KNOWN FACTS ABOUT THE PERSON (treat as true, do not re-ask):"]
        for r in rows:
            lines.append(f"- {r['trait'].replace('_', ' ')}: {_fmt_value(r['value'])}")
        return "\n".join(lines)

    # --- editor surface (backs GET/POST /facts) -----------------------------
    def correct(self, id, value, source="user-edit"):
        """User edits one belief to `value` (enters as a correction, ~0.97)."""
        r = self._by_id.get(id)
        if r is None:
            return None
        now = _now()
        if not _same_value(r, value, r["trait"]):
            r["history"].append({
                "value": r["value"], "confidence": r.get("confidence"),
                "source": r.get("source"), "at": r.get("updated"),
                "reason": "user-edited",
            })
            r["value"] = value
        r["confidence"] = CONF_CORRECTION
        r["support"] = max(1, int(r.get("support", 1)))
        r["source"] = source
        r["updated"] = now
        r["status"] = "active"
        r.pop("needs_reconfirm", None)
        self._by_key[(r["entity"], r["trait"])] = r
        return r

    def retract(self, id):
        """Flip a belief to retracted: kept on disk for audit, excluded from
        lookup() and block()."""
        r = self._by_id.get(id)
        if r is None:
            return None
        r["history"].append({
            "value": r["value"], "confidence": r.get("confidence"),
            "source": r.get("source"), "at": r.get("updated"), "reason": "retracted",
        })
        r["status"] = "retracted"
        r["updated"] = _now()
        # drop from the active lookup index
        if self._by_key.get((r["entity"], r["trait"])) is r:
            del self._by_key[(r["entity"], r["trait"])]
        return r

    # --- canonical-schema view (additive bridge to the event bus) -----------
    def as_memories(self, name=None) -> list:
        """Project the ACTIVE ledger rows onto canonical `memory_schema` Memories.

        Returns a list of validated Memory dicts — one per active row (retracted
        rows are excluded, exactly like lookup()/block()) — each produced via
        `memory_schema.make()` and already asserted through
        `memory_schema.validate()` by `_row_to_memory`. This is the read-side seam
        that lets the LIRF ledger publish what it knows onto the universal bus
        without changing a single byte of its on-disk format. `name` is accepted
        for call-site symmetry with the rest of the module's `(name, …)` API and
        is not otherwise required (the rows already live on this instance)."""
        return [_row_to_memory(r) for r in self.rows if r.get("status") == "active"]


# --- ranking / value helpers (module-level so tests can reach them) ----------
def _salience(r) -> float:
    return float(r.get("confidence", 0.0)) * math.log(1 + int(r.get("support", 1)))


def _climb(conf) -> float:
    conf = float(conf)
    return min(CONF_CEIL, conf + (1 - conf) * CONF_AGREE_RATE)


def _same_value(row, value, trait) -> bool:
    if trait in LIST_TRAITS:
        # a list candidate is "same" if it adds nothing new
        cur = _norm_value(row["value"] if isinstance(row["value"], list) else [row["value"]])
        new = _norm_value(value if isinstance(value, list) else [value])
        return new.issubset(cur)
    return _norm_value(row["value"]) == _norm_value(value)


def _merge_list(cur, add):
    cur = list(cur) if isinstance(cur, list) else [cur]
    add = add if isinstance(add, list) else [add]
    seen = {_norm_value(x) for x in cur}
    for x in add:
        if _norm_value(x) not in seen:
            cur.append(x)
            seen.add(_norm_value(x))
    return cur


def _fmt_value(v) -> str:
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


# ---------------------------------------------------------------------------
# Universal Memory Schema bridge — ADDITIVE. Folds a live LIRF ledger row onto
# the canonical `memory_schema.Memory` (the interlingua spoken on the event bus)
# WITHOUT touching the on-disk row format or any capture/merge/lookup behaviour.
#
# The ledger row and the canonical Memory disagree on two fields, reconciled here:
#   * the row's `support` is an INT count; the canon `support` is a LIST of
#     corroboration evidence ids -> the int is expanded into N synthetic string ids
#     derived from the row id (`{id}#c0 … {id}#c{N-1}`), so the ledger keeps its
#     cheap counter on disk while the bus carries a real list;
#   * the row's provenance is a single `source` str plus a verbatim `evidence`
#     snippet; the canon `sources` is a LIST -> we emit `[source, evidence]`
#     (evidence only when present and distinct), preserving the audit trail.
# Type is inferred the same way memory_schema does: a non-SELF entity is a
# relationship, everything else a fact. EVERY produced Memory is run through
# `memory_schema.validate()` and asserted before it leaves this module, so a
# malformed object can never reach the bus.
#
# memory_schema imports a handful of names FROM this module at its top level, so
# the schema import here is done lazily inside each function to stay free of any
# import-order cycle and keep this module importable in isolation.
# ---------------------------------------------------------------------------

def _row_to_memory(row: dict) -> dict:
    """Map ONE live LIRF ledger row -> a validated canonical `memory_schema` Memory.

        entity        -> subject
        trait         -> predicate
        value         -> value
        confidence    -> confidence
        type          := "relationship" if subject != SELF else "fact"
        source(+ev)   -> sources       (source first; verbatim evidence appended)
        support:int   -> support:list  (N corroboration ids derived from the row id)
        updated       -> updated
        (row id reused so the SAME memory is addressable in both worlds; `lirf`
         is stamped by make() via to_lirf, then re-rendered by validate-time)

    Asserts `memory_schema.validate()` on the result: a row can only ever leave
    here as a schema-valid Memory.
    """
    from . import memory_schema as _ms

    rid = row.get("id") or _new_id()
    subject = row.get("entity", SELF) or SELF
    mem_type = "relationship" if subject != SELF else "fact"

    # provenance: source first, then the verbatim evidence snippet if it adds info.
    src = row.get("source")
    sources: list = []
    if isinstance(src, str) and src:
        sources.append(src)
    elif isinstance(src, list):
        sources.extend(str(x) for x in src if x)
    ev = row.get("evidence")
    if isinstance(ev, str) and ev.strip() and ev not in sources:
        sources.append(ev)

    # corroboration: int count -> list of synthetic string ids tied to the row id.
    raw_support = row.get("support", 0)
    try:
        n = int(raw_support)
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        n = 0
    support = [f"{rid}#c{i}" for i in range(n)]

    mem = _ms.make(
        type=mem_type,
        subject=subject,
        predicate=row.get("trait", "") or "",
        value=row.get("value"),
        confidence=row.get("confidence", 0.0),
        sources=sources,
        support=support,
        id=rid,
        updated=row.get("updated"),
    )
    ok, why = _ms.validate(mem)
    assert ok, f"memory_lirf._row_to_memory produced an invalid Memory: {why} ({mem!r})"
    return mem


def from_memory(mem: dict) -> dict:
    """Best-effort INVERSE: a canonical `memory_schema` Memory -> a LIRF ledger row.

    The forward map is lossy at the boundary (support int<->list, evidence folded
    into sources), so this reconstructs a *plausible* on-disk row rather than a
    byte-identical one:

        subject     -> entity            (None/blank -> SELF, honouring the invariant)
        predicate   -> trait             (re-run through canon_trait)
        value       -> value
        confidence  -> confidence        (clamped into [0,1])
        sources[0]  -> source            (primary provenance)
        sources[1:] -> evidence          ("; "-joined verbatim trail)
        support:list-> support:int       (len of the corroboration list, >=1)
        updated     -> created & updated

    Produces a fully-formed `active` row (stable id, empty history[]) suitable for
    seeding a `Facts` ledger or feeding `Facts.merge` semantics. It does NOT
    persist and does NOT mutate any store — purely a value transform.
    """
    sources = mem.get("sources") or []
    source = sources[0] if sources else ""
    evidence = "; ".join(str(x) for x in sources[1:]) if len(sources) > 1 else ""

    entity = mem.get("subject", SELF) or SELF
    if entity in ("vera", "assistant", "me", "i", "myself", None, ""):
        entity = SELF

    try:
        conf = float(mem.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = 0.0 if conf < 0.0 else (1.0 if conf > 1.0 else conf)

    support_list = mem.get("support") or []
    support = max(1, len(support_list)) if support_list else 1

    ts = mem.get("updated") or _now()
    trait = canon_trait(mem.get("predicate", "") or "")

    row = {
        "id": mem.get("id") or _new_id(),
        "entity": entity,
        "trait": trait,
        "value": mem.get("value"),
        "confidence": conf,
        "support": support,
        "source": source,
        "evidence": evidence,
        "created": ts,
        "updated": ts,
        "status": "active",
        "history": [],
    }
    if trait in NEAR_IMMUTABLE:
        row["needs_reconfirm"] = False
    return row


# ---------------------------------------------------------------------------
# Module-level convenience API — the surface the task asked for by name.
# Thin wrappers over Facts so callers don't have to juggle load/merge/save.
# ---------------------------------------------------------------------------

def capture(name, text, reply=None, brain=None, model_pass=False) -> list:
    """Extract durable user-facts from one utterance and PERSIST them immediately
    with full provenance. Returns the rows touched. Intended to be called inside the
    server's per-turn lock (the turn is already serialised, so the read-modify-write
    is race-free with no new lock)."""
    f = Facts.load(name)
    cands = f.capture(name, text, reply, brain=brain, model_pass=model_pass)
    # CONSENT & BOUNDARIES (Human Operating Layer): a SENSITIVE-domain conclusion (health, therapy,
    # finance, trauma, …) is never written to durable memory SILENTLY. Without standing consent it is
    # HELD for the user to approve/reject — non-sensitive facts pass through unchanged. Guarded: a
    # consent hiccup must never break capture (on error, sensitive items fail safe to held).
    try:
        from .consent import policy as _consent
        cands, _held = _consent.gate_memory_candidates(name, cands)
    except Exception:
        pass
    touched = [f.merge(c) for c in cands]
    if touched:
        f.save(name)
    return touched


def retrieve(name, query="") -> str:
    """Return a compact LIRF fact-block for prompt injection via O(ms) lookup.

    If `query` names a specific known trait (e.g. "when's my birthday?"), the most
    relevant single fact is surfaced first; then the ranked block follows. Empty
    string when nothing is on record. Cloud guard is the CALLER's job (blank this
    under cloud.is_cloud(), exactly like the Portrait) — kept here so the store has
    no opinion about transport.
    """
    f = Facts.load(name)
    hit = _query_trait(query, f) if query else None
    block = f.block(name)
    if hit and block:
        return block
    if hit:
        return ("KNOWN FACTS ABOUT THE PERSON (treat as true, do not re-ask):\n"
                f"- {hit['trait'].replace('_', ' ')}: {_fmt_value(hit['value'])}")
    return block


# Question-word cues mapped to the trait they ask about — backs a deterministic
# route.py handler ("provenance not vibes"): on "when's my birthday?" we can answer
# from the ledger with provenance, or say honestly it's not on record.
_Q_TRAITS = [
    # birthPLACE must precede birthDAY: the birthday rule owns "\bborn\b", but a
    # "WHERE was I born / where did I grow up / hometown / from ... originally" asks for
    # the PLACE, not the date. Routed first so the honesty wall binds the right empty slot
    # and a fabricated city ("you grew up in X") is caught against birthplace, not birthday.
    # Hometown lives here (a place of ORIGIN), deliberately NOT under "lives" (current city).
    (re.compile(r"\bwhere (?:was|were|wuz) (?:i|you)\b.{0,20}\bborn\b|\bwhere (?:do|did) (?:i|you)\s+(?:grow up|come from)\b|grew up\b|\bhometown\b|home\s*town\b|\bborn and raised\b|\bwhere (?:am|are) (?:i|you)\b.{0,18}\b(?:from|originally)\b|\b(?:from|come from)\b.{0,12}\boriginally\b|\boriginally from\b|\bwhere(?:'?s| is) (?:my|your) (?:home\s*town|birthplace)\b|\b(?:my|your) birthplace\b|\bwhere (?:was|were) (?:i|you) raised\b|\braised\b", re.I), "birthplace"),
    (re.compile(r"\bbirthday|\bbday|\bborn\b|date of birth\b", re.I), "birthday"),
    (re.compile(r"\bwhere (?:do|am) i (?:live|living)|\bmy (?:city|address|location)\b|where i live", re.I), "lives"),
    (re.compile(r"\bwhere (?:do|did) i work|\bmy (?:job|employer|company|workplace)\b", re.I), "employer"),
    (re.compile(r"\bwhat do i do\b|\bmy (?:occupation|profession|role|title)\b", re.I), "occupation"),
    (re.compile(r"\bmy dog'?s? name|what'?s my dog|dog called\b", re.I), "dog_name"),
    (re.compile(r"\bmy cat'?s? name|what'?s my cat\b", re.I), "cat_name"),
    (re.compile(r"\bmy (?:mom|mum|mother)'?s? name|what'?s my mom\b", re.I), "mother"),
    (re.compile(r"\bmy (?:dad|father)'?s? name|what'?s my dad\b", re.I), "father"),
    (re.compile(r"\bmy (?:wife|husband|partner|spouse|gf|bf)'?s? name\b", re.I), "partner"),
    (re.compile(r"\bmy name\b|what'?s my name|who am i\b", re.I), "name"),
    (re.compile(r"\bmy (?:middle name)\b", re.I), "middle_name"),
    (re.compile(r"\bfavou?rite colou?r\b", re.I), "favorite_color"),
    (re.compile(r"\bwhat am i working on\b|my (?:project|current work)\b", re.I), "works_on"),
    # remaining hard-personal traits get honest routing too, so an unstored value
    # emits [UNKNOWN] instead of confabulating (universalizing the birthday wall).
    (re.compile(r"\bmy (?:phone|cell|mobile)(?:\s+number)?\b|what'?s my (?:phone|number)\b|my number\b", re.I), "phone"),
    (re.compile(r"\bmy email(?:\s+address)?\b|what'?s my email\b", re.I), "email"),
    (re.compile(r"\bhow old am i\b|\bwhat'?s my age\b|\bmy age\b", re.I), "age"),
    (re.compile(r"\bmy (?:wedding )?anniversary\b|when(?:'?s| is) (?:my|our) anniversary\b", re.I), "anniversary"),
    (re.compile(r"\bmy blood type\b|what'?s my blood type\b", re.I), "blood_type"),
]


def _query_trait(query, f: "Facts"):
    for rx, trait in _Q_TRAITS:
        if rx.search(query):
            r = f.lookup(SELF, trait)
            if r is not None:
                return r
    return None


def fact_note(name, text):
    """Deterministic route.py hook (cap_note channel). On a known-fact question,
    return a ground-truth note carrying the ACTUAL stored value + provenance, so the
    swappable mouth narrates only what code proved. Returns None if the turn isn't a
    known-fact question (let normal flow handle it). If the trait IS asked but not on
    record, return an honest 'not on record' note instead of letting her confabulate.
    The CALLER must skip this under cloud.is_cloud() (PII guard)."""
    asked = None
    for rx, trait in _Q_TRAITS:
        if rx.search(text or ""):
            asked = trait
            break
    if asked is None:
        return None
    f = Facts.load(name)
    r = f.lookup(SELF, asked)
    label = asked.replace("_", " ")
    if r is None:
        return (f"[fact — the user's {label} is NOT on record. In one honest, warm "
                f"sentence tell them you don't have it yet and ask them to tell you. "
                f"Invent nothing.]")
    learned = (r.get("updated") or "")[:10]
    return (f"[fact — the user's {label} is {_fmt_value(r['value'])} "
            f"(learned {learned}; provenance: {r.get('source','')}). State it warmly "
            f"and naturally as something you remember. Do not hedge or say you're unsure.]")


def render(name) -> str:
    """Human-readable 'what Vera knows about you', with provenance per fact —
    the 'you own what it believes about you' promise, now per-belief. Includes
    superseded/retracted history so a correction is visible and restorable."""
    f = Facts.load(name)
    active = f.about(SELF)
    others = sorted({r["entity"] for r in f.rows if r["entity"] != SELF and r.get("status") == "active"})
    out = [f"What {name} knows about you ({len(active)} active facts):"]
    if not active:
        out.append("  (nothing on record yet — tell her about yourself and it lands here)")
    for r in active:
        flag = "  ⚠ needs re-confirm" if r.get("needs_reconfirm") else ""
        out.append(
            f"  • {r['trait'].replace('_', ' ')}: {_fmt_value(r['value'])}{flag}\n"
            f"      confidence {r['confidence']:.2f} · corroborated {r['support']}x · "
            f"{r.get('source','?')}\n"
            f"      evidence: \"{r.get('evidence','')}\"")
        for h in r.get("history", []):
            out.append(f"      ↩ was {_fmt_value(h.get('value'))} "
                       f"({h.get('reason','?')} {(h.get('at') or '')[:10]})")
    for ent in others:
        rows = [r for r in f.about(ent)]
        out.append(f"\n  About {ent}:")
        for r in rows:
            out.append(f"    • {r['trait'].replace('_', ' ')}: {_fmt_value(r['value'])}")
    return "\n".join(out)


def as_memories(name) -> list:
    """Load `{name}`'s ledger and project its ACTIVE rows onto validated canonical
    `memory_schema` Memories. Module-level convenience over `Facts.as_memories`,
    mirroring `capture`/`retrieve`/`render` — the one call a bus publisher needs to
    turn everything LIRF knows about a creature's user into schema-valid Memory
    dicts. Read-only: never mutates or persists the store."""
    return Facts.load(name).as_memories(name)


# ---------------------------------------------------------------------------
# STEP 0 migration — the precondition for the live-bug fix, packaged as an
# idempotent helper rather than run eagerly (the destructive disk change stays
# human-gated, consistent with deferring integration to review).
#
# The bug: `.anima/{name}.portrait.md` held persona bullets about HER, but
# `portrait.load()` reads that path as the USER profile. Fix = a 3-namespace split:
#   {name}.persona.md  -> facts about the creature   (mouth.persona_path targets this)
#   {name}.portrait.md -> prose profile of the USER  (portrait.consolidate writes this)
#   {name}.lirf.json   -> structured USER beliefs     (this organ)
# A polluted portrait is one whose first non-empty line is the creature's name with a
# trailing colon ("Vera:") followed by persona-style bullets — heuristically detected
# so we never clobber a genuine user profile.
# ---------------------------------------------------------------------------

def portrait_is_polluted(name) -> bool:
    """True iff {name}.portrait.md looks like persona bullets about the creature
    (the live bug), not a profile of the user."""
    from .util import load_text
    txt = load_text(STORE / f"{name}.portrait.md", "") or ""
    head = next((ln.strip() for ln in txt.splitlines() if ln.strip()), "")
    return head.rstrip(":").strip().lower() == str(name).strip().lower() and head.endswith(":")


def migrate_persona_split(name, apply=False) -> dict:
    """Idempotent STEP-0 migration. With apply=False (default) returns a plan only.
    With apply=True: if {name}.portrait.md is polluted, move its body to
    {name}.persona.md (only if no persona file exists yet) and blank the portrait,
    so portrait.load() no longer serves persona bullets as the user profile.
    Returns {polluted, persona_exists, action}.
    """
    from .util import load_text, save_text
    from . import mouth
    portrait_p = STORE / f"{name}.portrait.md"
    persona_p = mouth.persona_path(name)
    polluted = portrait_is_polluted(name)
    persona_exists = bool((load_text(persona_p, "") or "").strip())
    plan = {"polluted": polluted, "persona_exists": persona_exists, "action": "none"}
    if not apply or not polluted:
        if polluted:
            plan["action"] = "would move portrait body -> persona.md and blank portrait"
        return plan
    body = (load_text(portrait_p, "") or "").strip()
    if not persona_exists and body:
        save_text(persona_p, body)              # her self-image lands where it belongs
        plan["action"] = "moved portrait body -> persona.md; blanked portrait"
    else:
        plan["action"] = "blanked portrait (persona already present)"
    save_text(portrait_p, "")                   # free the user-profile slot
    return plan


# ---------------------------------------------------------------------------
# Self-test — run directly: `python3 -m anima.memory_lirf` (no model, no network).
# Proves capture, the entity invariant, O(1) lookup, newest-wins + history, the
# block, list traits, retraction, and round-trip persistence.
# ---------------------------------------------------------------------------

def _selftest() -> int:
    import tempfile, os, glob
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    # --- extraction: the obvious declaratives land, hypotheticals don't ---
    c = extract("my birthday is June 12 and I live in Portland, OR")
    byt = {x["trait"]: x["value"] for x in c}
    ok("extract: birthday", byt.get("birthday") == "June 12")
    ok("extract: lives", byt.get("lives") in ("Portland, OR", "Portland"))
    ok("extract: rejects 'I wish I lived in Paris'",
       all(x["trait"] != "lives" for x in extract("honestly I wish I lived in Paris")))
    ok("extract: rejects 'if I worked at Google'",
       all(x["trait"] != "employer" for x in extract("if I worked at Google I'd be rich")))
    ok("extract: dog name", any(x["trait"] == "dog_name" and x["value"] == "Biscuit"
                                for x in extract("my dog's name is Biscuit")))
    ok("extract: list-valued dislikes accumulate",
       set((extract("I hate cilantro and I can't stand olives")[0]["value"])) == {"cilantro", "olives"}
       if extract("I hate cilantro and I can't stand olives") else False)

    # --- WAVE A: APPOSITIVE names (no copula) + LIFE-EVENT durable facts ---------------
    # The conservation ledger surfaced these as total-loss classes; these asserts lock the
    # widening in and guard the capital/stopname/hypothetical rails (mirrors the #21 widen).
    def _xt(text):
        return {x["trait"]: x["value"] for x in extract(text)}
    ok("WAVE-A appositive: 'my daughter Maya' -> daughter=Maya (no copula needed)",
       _xt("My daughter Maya started kindergarten last week").get("daughter") == "Maya")
    ok("WAVE-A appositive: 'my friend Sloane' -> friend=Sloane",
       _xt("my friend Sloane is visiting").get("friend") == "Sloane")
    ok("WAVE-A appositive: 'a dog named Cooper' -> dog_name=Cooper (no 'my')",
       _xt("We adopted a dog named Cooper in 2024").get("dog_name") == "Cooper")
    ok("WAVE-A life-event: 'I moved to Austin' -> moved_to=Austin (stops before 'because')",
       _xt("I moved to Austin because my manager changed").get("moved_to") == "Austin")
    ok("WAVE-A life-event: multi-word place 'I moved to New York' kept whole",
       _xt("I moved to New York last year").get("moved_to") == "New York")
    ok("WAVE-A life-event: 'I started a company called Collatio' -> business=Collatio",
       _xt("I started a company called Collatio").get("business") == "Collatio")
    ok("WAVE-A life-event: 'I started a company' (unnamed) -> business marker",
       "company" in (_xt("I started a company").get("business") or ""))
    ok("WAVE-A life-event: 'I quit my job' -> job_change marker",
       "quit" in (_xt("I quit my job").get("job_change") or ""))
    ok("WAVE-A life-event: 'I joined Acme' -> employer=Acme",
       _xt("I joined Acme").get("employer") == "Acme")
    ok("WAVE-A life-event: 'I married Jen' -> married_to=Jen",
       _xt("I married Jen").get("married_to") == "Jen")
    ok("WAVE-A life-event: 'we had a baby' -> a durable life_event",
       "baby" in (_xt("we had a baby").get("life_event") or ""))
    # GUARDS — Observed > Assumed: never fabricate a name or a place.
    ok("WAVE-A guard: 'my daughter started kindergarten' (no name) captures NO daughter",
       "daughter" not in _xt("my daughter started kindergarten"))
    ok("WAVE-A guard: 'I moved to the city' (common noun) captures NO moved_to",
       "moved_to" not in _xt("I moved to the city")
       and "moved_to" not in _xt("I moved to a new place"))
    ok("WAVE-A guard: hypothetical 'maybe I'll move to Paris' captures NOTHING durable",
       "moved_to" not in _xt("maybe I'll move to Paris")
       and "moved_to" not in _xt("I wish I moved to Denver"))
    ok("WAVE-A guard: 'my friend and I' does not read 'and'/'I' as a name",
       "friend" not in _xt("my friend and I went out for dinner"))
    ok("WAVE-A guard: capitalised aux in name slot ('my son Then we left') is no name",
       "son" not in _xt("my son Then we left for the park"))

    # --- REPORTED FEELING (affect / tone capture) --------------------------------------
    # The conservation ledger named TONE the #1 routinely-dropped class. These lock in the
    # reported_feeling widening AND its RULE #1 GUARDRAIL: we store that the USER reported a
    # feeling (an observed fact, grounded in their words), never that Vera feels anything; the
    # stored value is the user's stated affect WITH its intensity ("really stressed"); and the
    # never-infer rails (hypothetical guard + closed affect set + first-person frame) hold.
    def _feels(text):
        f = next((x for x in extract(text) if x["trait"] == "reported_feeling"), None)
        return set(f["value"]) if f and isinstance(f.get("value"), list) else set()
    ok("AFFECT: 'I've been really stressed' -> reported_feeling='really stressed' (intensity kept)",
       "really stressed" in _feels("I've been really stressed about the Q3 launch"))
    ok("AFFECT: 'we are excited' -> reported_feeling='excited'",
       "excited" in _feels("My wife Jen and I are excited about the move to Denver in March"))
    ok("AFFECT: 'I'm so anxious' -> reported_feeling='so anxious'",
       "so anxious" in _feels("I'm so anxious about tomorrow"))
    ok("AFFECT: 'feeling pretty overwhelmed' -> reported_feeling='pretty overwhelmed'",
       "pretty overwhelmed" in _feels("honestly, been feeling pretty overwhelmed"))
    ok("AFFECT: 'I feel grateful' -> reported_feeling='grateful'",
       "grateful" in _feels("I feel grateful"))
    ok("AFFECT: list-valued — two affects in one utterance BOTH accumulate (neither lost)",
       _feels("I'm stressed and I'm excited") == {"stressed", "excited"})
    # RULE #1 GUARDRAIL: the value is the USER's word, drawn from their sentence — an OBSERVED
    # report, not a feeling claimed for Vera. Asserted by grounding: every token of the stored
    # value appears in the user's utterance.
    _src = "i've been really stressed about the q3 launch"
    ok("AFFECT [RULE #1]: stored affect is GROUNDED in the user's words (no confabulation)",
       all(tok in _src for v in _feels("I've been really stressed about the Q3 launch")
           for tok in v.lower().split()))
    # GUARDS — Observed > Assumed: never invent a feeling.
    ok("AFFECT guard: hypothetical 'I wish I were less stressed' captures NO feeling",
       "reported_feeling" not in _xt("I wish I were less stressed")
       and "reported_feeling" not in _xt("I hope I'm not too stressed"))
    ok("AFFECT guard: a non-affect statement ('I am 34 years old') captures NO feeling",
       "reported_feeling" not in _xt("I am 34 years old")
       and "reported_feeling" not in _xt("I work at Collatio"))
    ok("AFFECT guard: a feeling stated ABOUT someone else is not read as the user's",
       "reported_feeling" not in _xt("my boss is stressed"))

    # --- HEDGE capture (extract layer): a guess parses to the REAL value, flagged hedged,
    # and NEVER stores the hedge word. The auditor's regression: "I guess my favorite color
    # is probably green" must yield value='green' (not 'probably'), hedged=True. -----------
    def _xc(text, trait):
        """The single extracted candidate for `trait` (or None)."""
        return next((x for x in extract(text) if x["trait"] == trait), None)

    aud = _xc("I guess my favorite color is probably green", "favorite_color")
    ok("HEDGE [auditor]: value is the REAL word 'green', NEVER the hedge 'probably'",
       aud is not None and aud["value"] == "green")
    ok("HEDGE [auditor]: the candidate is flagged hedged (so merge enters it below KNOWN)",
       aud is not None and aud.get("hedged") is True)
    # the confident control is NOT hedged and keeps its value
    ctl = _xc("my favorite color is green", "favorite_color")
    ok("HEDGE [control]: 'my favorite color is green' -> value 'green', NOT hedged",
       ctl is not None and ctl["value"] == "green" and not ctl.get("hedged"))
    # hedge sitting INSIDE the value slot ("is maybe blue") -> real value, hedged
    inv = _xc("my favorite color is maybe blue", "favorite_color")
    ok("HEDGE [in-value]: '... is maybe blue' -> value 'blue' (past the hedge), hedged",
       inv is not None and inv["value"] == "blue" and inv.get("hedged"))
    # clause-governing hedge ("I think ...") flags hedged on a multi-word favorite value
    clz = _xc("I think my favorite food is sushi", "favorite_food")
    ok("HEDGE [clause]: 'I think my favorite food is sushi' -> value 'sushi', hedged",
       clz is not None and clz["value"] == "sushi" and clz.get("hedged"))
    # a value that is ONLY a hedge word stores NOTHING (never 'favorite_color=probably')
    ok("HEDGE [bare]: '... is probably' (no real value) captures NO favorite_color row",
       _xc("my favorite color is probably", "favorite_color") is None)
    # CONF_HEDGED is, by construction, below the curiosity [KNOWN] bar — assert the relation
    # here so a drift in either constant trips a test rather than silently re-locking a guess.
    try:
        from .curiosity import _CONF_KNOWN as _CK
    except Exception:
        _CK = 0.85
    ok("HEDGE [invariant]: CONF_HEDGED < curiosity._CONF_KNOWN (a guess never clears KNOWN)",
       CONF_HEDGED < _CK and CONF_HEDGED >= CONF_BLOCK_FLOOR)

    # --- a throwaway store (FULLY HERMETIC) ---------------------------------------
    # Redirect EVERY module store the load path now writes, for the whole block:
    # memory_lirf.STORE on both the __main__ and package bindings, constitution.STORE
    # (the continuity ledger) and reliability.DEFAULT_STORE (guarded backups). Before
    # the LAW-001 wiring this block only dropped a {name}.lirf.json it cleaned up; a
    # good load now ALSO emits a {name}.continuity.jsonl and a backup snapshot, which
    # the old per-name cleanup didn't know about and leaked into the real .anima (the
    # cert's footprint guardrail correctly caught this). One temp dir + finally-restore
    # makes a leak impossible regardless of what the load path writes.
    name = "lirf_selftest_" + secrets.token_hex(3)
    import sys as _sys2
    _self_td = tempfile.mkdtemp(prefix="lirf-self-")
    _self_tp = Path(_self_td)
    _self_targets = [(_sys2.modules[__name__], "STORE")]
    try:
        import anima.memory_lirf as _pkg_ml2
        if _pkg_ml2 is not _sys2.modules[__name__]:
            _self_targets.append((_pkg_ml2, "STORE"))
    except Exception:
        pass
    for _modpath, _attr in (("anima.constitution", "STORE"),
                            ("anima.reliability", "DEFAULT_STORE"),
                            ("anima.curiosity", "STORE")):
        try:
            _self_targets.append((__import__(_modpath, fromlist=["_"]), _attr))
        except Exception:
            pass
    _self_saved = [(m, a, getattr(m, a, None)) for (m, a) in _self_targets]
    for (m, a) in _self_targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, _self_tp)
    try:
        f = Facts(load_json(Facts.path(name)) if False else [])

        # capture + merge a battery
        for c in f.capture(name, "my birthday is June 11"):
            f.merge(c)
        ok("merge: inserted birthday active", f.value_of("birthday") == "June 11")
        ok("lookup: O(1) returns the row", f.lookup(SELF, "birthday") is not None)

        # corroboration climbs confidence, bumps support
        conf0 = f.lookup(SELF, "birthday")["confidence"]
        for c in f.capture(name, "yeah my birthday is June 11"):
            f.merge(c)
        r = f.lookup(SELF, "birthday")
        ok("merge: same value -> support++", r["support"] == 2)
        ok("merge: same value -> confidence climbs", r["confidence"] > conf0)

        # correction: newest wins, old value preserved in history, higher confidence
        for c in f.capture(name, "no it's the 12th — my birthday is June 12"):
            f.merge(c)
        r = f.lookup(SELF, "birthday")
        ok("merge: correction installs new value", r["value"] == "June 12")
        ok("merge: history keeps the displaced value",
           any(h["value"] == "June 11" for h in r["history"]))
        ok("merge: correction resets support to 1", r["support"] == 1)
        ok("merge: near-immutable correction is NOT silently flagged (explicit corr)",
           not r.get("needs_reconfirm"))

        # the entity invariant: a belief about HER folds to 'you', never 'vera'
        f.merge({"trait": "mood", "value": "warm", "entity": "vera", "evidence": "x"})
        ok("invariant: entity=='vera' folded to SELF (no 'vera' key)",
           all(r2["entity"] == SELF for r2 in f.rows))

        # list trait append-with-dedupe across turns
        for c in f.capture(name, "I hate cilantro"):
            f.merge(c)
        for c in f.capture(name, "honestly I hate cilantro and I can't stand olives"):
            f.merge(c)
        dis = f.value_of("dislikes") or []
        ok("list trait: dedupes + accumulates", set(dis) == {"cilantro", "olives"})

        # block: dense, only confident rows, no re-ask noise
        for c in f.capture(name, "I live in Portland"):
            f.merge(c)
        blk = f.block(name)
        ok("block: contains birthday line", "birthday: June 12" in blk)
        ok("block: contains lives line", "lives: Portland" in blk)
        ok("block: header tells model not to re-ask", "do not re-ask" in blk)

        # --- HEDGE merge + curiosity gap-open (the auditor's end-to-end regression) -------
        # Isolate in a throwaway temp store so curiosity's own ledger never touches real
        # .anima (it reads/writes {name}.curiosity.jsonl). Redirect BOTH module STOREs, run,
        # restore. This proves the fix at the layer the auditor named: a hedged self-fact
        # enters BELOW the [KNOWN] bar, so curiosity keeps the gap OPEN (LAW 002 cannot shield
        # a guess), while a confident control is KNOWN and suppressed (not re-asked).
        try:
            import anima.curiosity as _cur
            _have_cur = True
        except Exception:
            _cur = None
            _have_cur = False
        if _have_cur:
            import sys as _sys
            # Redirect the STORE on EVERY module that resolves it. Under
            # `python3 -m anima.memory_lirf` this function runs inside the __main__ module,
            # whose bare STORE is a SEPARATE binding from anima.memory_lirf.STORE — and
            # curiosity.Facts.load() reads the PACKAGE copy. Redirect both (+ curiosity), or
            # the gap lookups leak to the real .anima (the exact gotcha curiosity's selftest
            # documents). Mutate the module attr, never a local 'STORE'.
            _hmods = [_sys.modules[__name__]]
            try:
                import anima.memory_lirf as _pkg_ml
                if _pkg_ml is not _hmods[0]:
                    _hmods.append(_pkg_ml)
            except Exception:
                pass
            _hmods.append(_cur)
            _hstore_saved = [(m, getattr(m, "STORE", None)) for m in _hmods]
            _htd = tempfile.mkdtemp(prefix="lirf-hedge-self-")
            _htp = Path(_htd)
            for _m in _hmods:
                _m.STORE = _htp
            try:
                # AUDITOR: "I guess my favorite color is probably green"
                an = "lirf_hedge_aud_" + secrets.token_hex(3)
                fa = Facts([])
                for c in fa.capture(an, "I guess my favorite color is probably green"):
                    fa.merge(c)
                fa.save(an)
                ra = Facts.load(an).lookup(SELF, "favorite_color")
                ok("HEDGE merge [auditor]: value is 'green', NEVER 'probably'",
                   ra is not None and ra["value"] == "green")
                ok("HEDGE merge [auditor]: confidence is below the [KNOWN] bar "
                   f"(conf={None if ra is None else ra['confidence']} < {_cur._CONF_KNOWN})",
                   ra is not None and float(ra["confidence"]) < _cur._CONF_KNOWN)
                ok("HEDGE curiosity [auditor]: the hedged row is NOT _is_known_row "
                   "(LAW 002 cannot shield it -> the gap stays OPEN, Vera keeps asking)",
                   not _cur._is_known_row(ra))

                # AUDITOR via a TAXONOMY slot ('lives') so detect_gaps emits the OPEN gap:
                # "I think I live in Portland" -> SUSPECTED 'lives' gap (hint=Portland), not KNOWN.
                ah = "lirf_hedge_liv_" + secrets.token_hex(3)
                fh = Facts([])
                for c in fh.capture(ah, "I think I live in Portland"):
                    fh.merge(c)
                fh.save(ah)
                rh = Facts.load(ah).lookup(SELF, "lives")
                lives_gaps = [g for g in _cur.detect_gaps(ah) if g["slot"] == "lives"]
                ok("HEDGE curiosity [taxonomy]: a hedged 'lives' -> an OPEN SUSPECTED gap "
                   "(curiosity keeps asking), value still 'Portland'",
                   rh is not None and rh["value"] == "Portland"
                   and len(lives_gaps) == 1 and lives_gaps[0]["kind"] == "SUSPECTED")

                # CONTROL: a confident direct statement stays KNOWN and is SUPPRESSED.
                cn = "lirf_hedge_ctl_" + secrets.token_hex(3)
                fc = Facts([])
                for c in fc.capture(cn, "my favorite color is green"):
                    fc.merge(c)
                for c in fc.capture(cn, "I live in Portland"):
                    fc.merge(c)
                fc.save(cn)
                rc = Facts.load(cn).lookup(SELF, "favorite_color")
                ok("HEDGE control: a confident 'favorite color is green' stays ~KNOWN "
                   f"(conf={None if rc is None else rc['confidence']} >= {_cur._CONF_KNOWN})",
                   rc is not None and float(rc["confidence"]) >= _cur._CONF_KNOWN
                   and _cur._is_known_row(rc))
                ok("HEDGE control: a confident 'lives' produces NO gap (KNOWN, never re-asked)",
                   all(g["slot"] != "lives" for g in _cur.detect_gaps(cn)))
            finally:
                for _m, _old in _hstore_saved:
                    if _old is not None:
                        _m.STORE = _old
                for _fp in glob.glob(str(_htp / "*")):
                    try:
                        os.remove(_fp)
                    except OSError:
                        pass
                try:
                    os.rmdir(_htd)
                except OSError:
                    pass

        # retrieve + fact_note reload from disk (they're the live per-turn entry
        # points), so flush the in-memory ledger first.
        f.save(name)
        # retrieve + fact_note (the deterministic provenance seam)
        ok("retrieve: birthday question surfaces stored value",
           "June 12" in retrieve(name, "when's my birthday?"))
        note = fact_note(name, "when's my birthday?")
        ok("fact_note: carries the real value + 'state it warmly'",
           "June 12" in note and "warmly" in note)
        ok("fact_note: unknown trait -> honest 'NOT on record'",
           "NOT on record" in (fact_note(name, "what's my middle name?") or ""))
        ok("fact_note: non-fact question -> None (let normal flow run)",
           fact_note(name, "tell me a joke") is None)

        # retract: gone from lookup/block, kept on disk
        bid = f.lookup(SELF, "birthday")["id"]
        f.retract(bid)
        ok("retract: removed from active lookup", f.lookup(SELF, "birthday") is None)
        ok("retract: row kept on disk as retracted",
           any(r2["id"] == bid and r2["status"] == "retracted" for r2 in f.rows))

        # round-trip persistence (atomic + encrypted via util)
        f.save(name)
        g = Facts.load(name)
        ok("persist: round-trips active dislikes",
           set(g.value_of("dislikes") or []) == {"cilantro", "olives"})
        ok("persist: retracted row survives reload",
           any(r2["id"] == bid and r2["status"] == "retracted" for r2 in g.rows))
        ok("persist: id index rebuilt on load", g._by_id.get(bid) is not None)

        # render is human-readable and shows provenance + history
        rep = render(name)
        ok("render: shows a corroboration count", "corroborated" in rep)

        # --- canonical Memory bridge (additive; on-disk format unchanged) ---
        from . import memory_schema as _ms

        # a hand-built row exercises every mapped field (incl. evidence + support int)
        sample_row = {
            "id": "f_abc123",
            "entity": SELF,
            "trait": "birthday",
            "value": "June 12",
            "confidence": 0.93,
            "support": 3,                 # INT on disk -> must become a 3-element list
            "source": "chat 2026-06-04",
            "evidence": "my birthday is June 12",
            "created": "2026-06-04T12:00:00Z",
            "updated": "2026-06-04T12:00:00Z",
            "status": "active",
            "history": [],
        }
        mem = _row_to_memory(sample_row)
        ok("bridge: _row_to_memory result passes memory_schema.validate()",
           _ms.validate(mem)[0])
        ok("bridge: exactly the 10 canonical keys",
           set(mem.keys()) == set(_ms.KEYS))
        ok("bridge: entity->subject, trait->predicate, value->value",
           mem["subject"] == SELF and mem["predicate"] == "birthday"
           and mem["value"] == "June 12")
        ok("bridge: row id reused (same memory both worlds)", mem["id"] == "f_abc123")
        ok("bridge: support int(3) -> list of 3 corroboration ids",
           isinstance(mem["support"], list) and len(mem["support"]) == 3
           and mem["support"][0] == "f_abc123#c0")
        ok("bridge: source + evidence both land in sources",
           mem["sources"] == ["chat 2026-06-04", "my birthday is June 12"])
        ok("bridge: SELF entity -> type 'fact'", mem["type"] == "fact")
        ok("bridge: non-SELF entity -> type 'relationship'",
           _row_to_memory({**sample_row, "entity": "mom"})["type"] == "relationship")

        # from_memory: best-effort inverse, round-trips the essentials back to a row
        back = from_memory(mem)
        ok("from_memory: rebuilds a well-formed active row",
           back["status"] == "active" and back["entity"] == SELF
           and back["trait"] == "birthday" and back["value"] == "June 12")
        ok("from_memory: support list -> int count",
           isinstance(back["support"], int) and back["support"] == 3)
        ok("from_memory: sources[0] -> source", back["source"] == "chat 2026-06-04")
        ok("from_memory: sources[1:] -> evidence trail",
           back["evidence"] == "my birthday is June 12")
        ok("round-trip: row -> Memory -> row preserves entity/trait/value/conf",
           back["entity"] == sample_row["entity"] and back["trait"] == sample_row["trait"]
           and back["value"] == sample_row["value"]
           and abs(back["confidence"] - sample_row["confidence"]) < 1e-9)

        # as_memories(): EVERY active fact projects to a validated Memory; retracted
        # rows are excluded (mirrors lookup()/block()). The ledger here still holds
        # the captured battery from above (dislikes, lives, …) minus the retracted
        # birthday.
        mems = f.as_memories(name)
        ok("as_memories: returns a non-empty list of Memories", len(mems) > 0)
        ok("as_memories: EVERY produced Memory passes validate()",
           all(_ms.validate(mm)[0] for mm in mems))
        ok("as_memories: count == active rows (retracted excluded)",
           len(mems) == len([r for r in f.rows if r.get("status") == "active"]))
        ok("as_memories: retracted birthday is NOT projected",
           all(mm["predicate"] != "birthday" for mm in mems))
        ok("as_memories: a known active fact (dislikes) is present",
           any(mm["predicate"] == "dislikes" for mm in mems))

        # module-level convenience wrapper agrees with the instance method (reloads
        # from the same on-disk ledger saved earlier in this test).
        ok("as_memories(module): loads + validates from disk",
           all(_ms.validate(mm)[0] for mm in as_memories(name))
           and len(as_memories(name)) > 0)

        # STEP-0 migration detector (non-destructive: dry-run plans only)
        from .util import save_text
        pol_name = "lirf_pol_" + secrets.token_hex(3)
        try:
            save_text(STORE / f"{pol_name}.portrait.md", f"{pol_name}:\n• a warm AI companion")
            ok("migration: detects a polluted (persona-as-user) portrait",
               portrait_is_polluted(pol_name))
            ok("migration: dry-run proposes the move, touches nothing",
               migrate_persona_split(pol_name, apply=False)["action"].startswith("would move"))
            save_text(STORE / f"{pol_name}.portrait.md", "• lives in Portland\n• works at Acme")
            ok("migration: a real user profile is NOT flagged polluted",
               not portrait_is_polluted(pol_name))
        finally:
            for fp in glob.glob(str(STORE / f"{pol_name}.*")):
                try:
                    os.remove(fp)
                except OSError:
                    pass
    finally:
        for (_m, _a, _old) in _self_saved:
            if _old is not None:
                setattr(_m, _a, _old)
        import shutil as _sh2
        _sh2.rmtree(_self_td, ignore_errors=True)

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL LIRF SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
