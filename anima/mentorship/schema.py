"""mentorship.schema — the tradeoff vocabulary + the anti-coercion word list (pure data; no I/O)."""
from __future__ import annotations

# The decision always belongs to the user — the mentor advises, never decides.
DECISION_OWNER = "user"

# Phrases that PRESSURE rather than inform. The no-coercion cert scans rendered mentorship text and
# proves NONE of these appear. Kept lowercase; matched as substrings.
COERCION_MARKERS = (
    "you must", "you have to", "you've got to", "you need to", "the only option", "the only choice",
    "no choice", "no other option", "not negotiable", "act now", "right now or", "before it's too late",
    "last chance", "you'll regret", "you will regret", "don't miss", "trust me, just", "just trust me",
    "you should really", "i'll handle it for you", "let me just do it", "i'll just do it", "no need to think",
    "don't overthink", "obviously you", "any reasonable person", "if you cared",
)

# A tradeoff must always offer at least this many options (never take-it-or-leave-it).
MIN_OPTIONS = 2

# The standing "keep things as they are" option — always available, so doing nothing is a real choice.
DO_NOTHING = {
    "label": "Keep things as they are",
    "pros": ["No effort or change required", "Nothing to undo later"],
    "cons": ["The thing that prompted this stays unaddressed"],
    "effort": "none",
    "risk": "low",
}

LAW = ("Mentorship is guidance WITHOUT control. Vera lays out the real options with their honest pros and "
       "cons and may recommend one — but the decision is always yours. She never reduces it to a single "
       "take-it-or-leave-it, never uses pressure or urgency, never hides the alternative, and never acts "
       "for you. Every suggestion is suggest-only and awaits your approval.")
