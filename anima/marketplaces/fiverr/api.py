"""marketplaces.fiverr.api — assemble the /marketplaces/fiverr dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import sources as _s, gigs as _g, fulfillment as _f, revenue as _r


def dashboard(name: str, store: Path | None = None) -> dict:
    acct = storage.load(name, "fiverr_account", store, default=None)
    gigs = _g.gigs(name, store)
    return {
        "ok": True,
        "policy": {"scraping": "blocked unless explicitly permitted", "mass_messaging": "blocked",
                   "fake_reviews": "blocked", "off_platform_payment": "blocked",
                   "gig_publishing": "approval required", "order_delivery": "QA required",
                   "revenue": "payout/cash evidence required"},
        "account": ({"status": acct["status"], "identity_verified": acct["identity_verified"],
                     "raw_credentials_stored": acct["raw_credentials_stored"]} if acct else
                    {"status": "not started", "note": "Lamar must create the seller account (human-only)"}),
        "opportunities": [{"concept": o["service_concept"], "risk": o["policy_risk"]}
                          for o in _s.opportunities(name, store)],
        "gigs": [{"title": g["title"][:60], "status": g["status"]} for g in gigs],
        "orders": [{"buyer": o["buyer_handle"], "status": o["status"], "package": o["package"]}
                   for o in _f.orders(name, store)],
        "revenue": _r.revenue_board(name, store),
        "next_move": ("Lamar creates the Fiverr seller account (true identity), then approve gig drafts"
                      if not acct or acct["status"] != "active" else
                      "publish approved gigs; fulfill orders through QA'd cells; track payout-true revenue"),
        "honesty": "Fiverr is a governed channel: no scraping/spam/fake; gigs need publish approval; "
                   "delivery needs QA; an order isn't cash until payout evidence.",
    }
