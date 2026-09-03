"""anima.host — the host runtime contract: what THIS machine can honestly run.

profile (detect + select + persist the contract), enforcement (the runtime seams that make the
contract REAL — a profile the runtime doesn't enforce is host-profile theater), benchmark
(measured, not assumed, capability checks).
"""
from . import benchmark, enforcement, profile  # noqa: F401
