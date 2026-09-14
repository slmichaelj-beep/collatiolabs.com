"""anima.teaching — Teaching Mode: the ONLY approved path for durable user-approved learning.

schema (bounded record), queue (persisted, transition-logged), review (everything visible before
deciding, incl. conflicts), apply (approval-gated persistence through the SAME memory path —
never a bypass), rollback (every persistence reversible + recorded), api (server surface).
Auto Learn and Knowledge Packs may only CREATE drafts here — they never persist directly.
"""
from . import api, apply, queue, review, rollback, schema  # noqa: F401
