"""Entrypoint so the package self-test runs as ``python -m anima.organs --selftest``."""

from __future__ import annotations

import sys

from . import _selftest

if "--selftest" in sys.argv:
    raise SystemExit(_selftest())
print("anima.organs — run with --selftest to verify in isolation")
