"""rover — the SYNTHETIC USER executor for the Total Reality Test (Level 2).

runner.py walks the Total Scenario Matrix and EXECUTES each Level-2 scenario against the REAL server
backing path (the actual data functions + served pages), classifying pass/fail/blocked with severity.
It is the systematic, full-surface complement to scripts/vera_rover.py (which drives live-model journeys).
"""
from . import runner  # noqa: F401
