"""consent — Layer 2 of the Human Operating Layer: Consent & Boundaries.

Permissions answer "CAN Vera access this?" (the caps gate). Consent asks the harder question:
"SHOULD Vera proceed this way, at this speed, with this sensitivity, in this context?"

This package classifies the SENSITIVITY of material (health, therapy, finance, relationships, …),
holds per-domain/scope CONSENT (granted / denied / ask-each-time / revoked, with pacing), and ENFORCES
the boundary that matters most: a sensitive-domain conclusion is never SILENTLY written to durable
memory — without consent it is held as a pending candidate for the user to approve, reject, or forget.

Modules: schema (domains/scopes/shape) · classifier (deterministic sensitivity) · policy (the store +
decisions + the memory gate). Read-mostly; the store lives under .anima; every decision is auditable.
"""
from . import schema, classifier, policy  # noqa: F401
