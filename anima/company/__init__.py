"""anima.company — the Founder / Company Operating Layer.

Local-first company self-model + operating ledgers. Every durable company claim is approval-gated
and Truth-Ledger-traced (claim_type=system, subject 'company:<kind>:<id>'). Read-only/advisory by
default; nothing external happens here — external action lives behind the company_operator
governance core (authority + approval + budget + action ledgers + kill switch).
"""
from . import canon, decisions, doctrine, storage  # noqa: F401
