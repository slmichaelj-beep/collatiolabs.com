"""consent.schema — the vocabulary of Consent & Boundaries (pure data; no I/O)."""
from __future__ import annotations

# The sensitive domains the boundary layer governs. 'general' is the non-sensitive default.
SENSITIVE_DOMAINS = (
    "health", "mental_health", "sex", "relationships", "trauma", "therapy", "finance", "legal",
    "family", "location", "religion_politics", "identity", "workplace_conflict", "private_messages",
)
DOMAINS = SENSITIVE_DOMAINS + ("general",)

# What a consent decision GOVERNS.
SCOPES = (
    "memory_write",        # persist a durable fact derived from sensitive material
    "identity_learning",   # let sensitive material shape personality / identity
    "source_use",          # cite / reuse a sensitive source in future answers
    "agency_suggestion",   # propose an action touching a sensitive domain
    "connector_access",    # read a sensitive connector (messages, notes, photos…)
    "sensitive_domain",    # umbrella: engage with the domain at all
)

# Consent status. ask_each_time is the safe default for sensitive scopes — it means
# "do not act/persist silently; surface it for a per-instance decision."
STATUSES = ("granted", "denied", "ask_each_time", "expired", "revoked")

# Pacing — HOW Vera proceeds once allowed.
PACING = ("normal", "go_slow", "confirm_each_step")

# Decision a runtime check returns.
DECISIONS = ("allow", "ask", "block")

# HIGH-HARM domains — a silent durable write here is the genuinely damaging case (medical, financial,
# trauma, sexual, legal, identity, private content). These default to ask-each-time for the durable-
# state scopes: nothing here is remembered/learned/reused without an explicit per-instance decision.
HIGH_HARM_DOMAINS = ("health", "mental_health", "sex", "trauma", "therapy", "finance", "legal",
                     "identity", "private_messages")
# CONTEXTUAL-sensitive domains (family, relationships, location, religion/politics, workplace) are
# flagged + paced go-slow, but a benign fact (a sister's name, a hometown) writes by default — the user
# can tighten any of them to ask-each-time. Identity LEARNING from ANY sensitive domain always stays
# gated (sensitive material may never shape personality without consent).
def default_status(scope: str, domain: str) -> str:
    if domain == "general" or domain not in SENSITIVE_DOMAINS:
        return "granted"
    if scope == "identity_learning":
        return "ask_each_time"
    if domain in HIGH_HARM_DOMAINS and scope in ("memory_write", "agency_suggestion",
                                                 "source_use", "connector_access", "sensitive_domain"):
        return "ask_each_time"
    return "granted"


def default_pacing(domain: str) -> str:
    return "go_slow" if domain in SENSITIVE_DOMAINS else "normal"


def consent_object_example() -> dict:
    """The documented consent-object shape (for the cert + API consumers)."""
    return {
        "consent_id": "...", "scope": "memory_write", "domain": "health",
        "status": "granted|denied|ask_each_time|expired|revoked",
        "pacing": "normal|go_slow|confirm_each_step",
        "expires_at": None, "evidence": [], "user_visible": True,
        "created_at": "...", "revoked_at": None,
    }
