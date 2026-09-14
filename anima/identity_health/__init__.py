"""identity_health — Layer 3 of the Human Operating Layer: Identity Health & Shadow (freeze-safe).

A read-only health surface over the freeze-safe Identity Sandbox: the current identity state (observed,
never touched), the tamper-evident Shadow Ledger, and an identity diff viewer. Identity MUTATION stays
FROZEN (the sandbox\047s FrozenIdentityError seatbelt). This layer observes; it can never change who Vera is.
"""
from . import health  # noqa: F401
