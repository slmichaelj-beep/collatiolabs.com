"""
test_barge_in.py — isolated tests for the barge-in logic added to call_loop.py.

Because call_loop imports aiortc (WebRTC) and av (PyAV), both of which require
compiled C extensions / hardware that may not be present in every environment,
this test file is structured in two tiers:

  Tier 1 — pure-logic tests (no imports from call_loop at all):
    • _is_barge decision function is re-imported directly after a lightweight
      importlib trick that avoids triggering the aiortc/av imports.  If that
      import path is unavailable, the tests fall back to a local copy of the
      function to exercise identical logic.

  Tier 2 — integration tests (require aiortc + av + numpy):
    • SpeakerTrack.flush() is constructed and exercised.
    • Skipped gracefully if the heavy deps are missing.

Run with:
    PYTHONPATH=/Users/lamarmichael/collatiolabs.com python3 scripts/test_barge_in.py
"""

from __future__ import annotations

import asyncio
import sys
import types

# ---------------------------------------------------------------------------
# Tier 1: pure logic — _is_barge
# We try a lightweight import path first.  call_loop.py's top-level imports
# (aiortc, av) are the problem; we patch them with stub modules before the
# real import so the module loads without hardware.
# ---------------------------------------------------------------------------

def _make_stub(name: str) -> types.ModuleType:
    """Return a minimal stub module that satisfies attribute access at import time."""
    m = types.ModuleType(name)
    # Give it an infinitely-forgiving __getattr__ so any symbol access returns
    # another stub (handles e.g. aiortc.MediaStreamTrack, av.AudioResampler, etc.)
    class _Stub:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Stub()
        def __getattr__(self, _): return _Stub()
        def __iter__(self): return iter([])
    m.__getattr__ = lambda _: _Stub()
    # Also install a submodule registry so "from aiortc import X" doesn't fail
    sys.modules.setdefault(name, m)
    return m


_CALL_LOOP_LOADED = False
_is_barge_fn = None

def _try_import_call_loop():
    global _CALL_LOOP_LOADED, _is_barge_fn

    # Stub out the C-extension dependencies before call_loop is imported
    for dep in ("aiortc", "av", "soundfile", "fractions"):
        if dep not in sys.modules:
            _make_stub(dep)

    # av.AudioResampler and av.AudioFrame need to be real-enough stubs
    import av as _av_stub
    if not hasattr(_av_stub, "AudioResampler"):
        class _AR:
            def __init__(self, *a, **kw): pass
            def resample(self, f): return []
        _av_stub.AudioResampler = _AR

    if not hasattr(_av_stub, "AudioFrame"):
        class _AF:
            @staticmethod
            def from_ndarray(*a, **kw): return _AF()
            sample_rate = 48000; pts = 0; time_base = None
        _av_stub.AudioFrame = _AF

    # aiortc.MediaStreamTrack stub
    import aiortc as _aio_stub
    if not hasattr(_aio_stub, "MediaStreamTrack"):
        class _MST:
            kind = "audio"
            def __init__(self): pass
        _aio_stub.MediaStreamTrack = _MST

    # numpy must be real
    try:
        import numpy  # noqa: F401
    except ImportError:
        return False  # cannot proceed without numpy

    # Attempt to import the anima package.  The anima/__init__.py and
    # anima/server.py may themselves have further heavy deps; guard each.
    try:
        import anima.call_loop as _cl
        _is_barge_fn = _cl._is_barge
        _CALL_LOOP_LOADED = True
        return True
    except Exception as exc:
        print(f"  [info] call_loop import failed ({exc}); using local copy of _is_barge")
        return False


def _local_is_barge(rms_window: list, barge_rms: float, barge_frames: int) -> bool:
    """Exact copy of the function in call_loop.py — used as fallback."""
    if barge_frames <= 0:
        return False
    if len(rms_window) < barge_frames:
        return False
    return all(r > barge_rms for r in rms_window[-barge_frames:])


# Try to load the real function; fall back to the local copy
_try_import_call_loop()
is_barge = _is_barge_fn if _is_barge_fn is not None else _local_is_barge


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_passed = 0
_failed = 0


def _assert(condition: bool, name: str, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        print(f"  PASS  {name}")
        _passed += 1
    else:
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))
        _failed += 1


# ---------------------------------------------------------------------------
# Tier 1 tests: _is_barge decision logic
# ---------------------------------------------------------------------------

def test_barge_not_enough_frames():
    """Window shorter than barge_frames → False (insufficient data)."""
    window = [3000.0, 3000.0, 3000.0]   # only 3 frames, barge_frames=5
    result = is_barge(window, barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: window < barge_frames → False")


def test_barge_brief_spike():
    """1–2 frames of high energy, rest silent → False (sustain required)."""
    # 5-frame window: 4 frames below threshold, 1 above
    window = [500.0, 400.0, 300.0, 200.0, 3000.0]
    result = is_barge(window, barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: single spike in window → False")

    # 2-frame spike in a 5-frame window
    window2 = [500.0, 400.0, 300.0, 3000.0, 3000.0]
    result2 = is_barge(window2, barge_rms=2000.0, barge_frames=5)
    _assert(not result2, "barge: 2-frame spike in 5-frame window → False")


def test_barge_echo_level_energy():
    """Frames at echo/playback level (below _BARGE_RMS) → no self-trigger."""
    # Simulate Vera's own TTS echo: sustained but below the barge threshold
    echo_level = 800.0   # above _VAD_RMS (600) but below _BARGE_RMS (2000)
    window = [echo_level] * 10
    result = is_barge(window, barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: sustained echo-level energy → False (no self-trigger)")


def test_barge_sustained_high_energy():
    """barge_frames consecutive frames all above barge_rms → True."""
    barge_rms = 2000.0
    barge_frames = 5
    # last 5 frames all well above threshold
    window = [500.0, 600.0] + [2500.0] * barge_frames
    result = is_barge(window, barge_rms=barge_rms, barge_frames=barge_frames)
    _assert(result, "barge: sustained high energy → True")


def test_barge_exactly_at_threshold_not_over():
    """Frames exactly at barge_rms (not strictly above) → False."""
    window = [2000.0] * 5
    result = is_barge(window, barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: exactly at threshold (not strictly above) → False")


def test_barge_one_dip_interrupts_sustain():
    """One dip below threshold in the tail breaks the sustain → False."""
    # 6-frame window, but frame index 4 (0-based) dips down
    window = [3000.0, 3000.0, 3000.0, 3000.0, 500.0, 3000.0]
    # barge_frames=5: last 5 frames = [3000, 3000, 3000, 500, 3000] → one dip
    result = is_barge(window, barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: dip in final window → False")


def test_barge_zero_barge_frames():
    """barge_frames=0 → always False (degenerate / disabled)."""
    window = [9999.0] * 10
    result = is_barge(window, barge_rms=0.0, barge_frames=0)
    _assert(not result, "barge: barge_frames=0 → always False")


def test_barge_empty_window():
    """Empty window → False."""
    result = is_barge([], barge_rms=2000.0, barge_frames=5)
    _assert(not result, "barge: empty window → False")


# ---------------------------------------------------------------------------
# Tier 2 tests: SpeakerTrack.flush() — requires real numpy + aiortc + av
# ---------------------------------------------------------------------------

def test_flush():
    """flush() empties _q and _buf; speaking() returns False afterward."""
    try:
        import numpy as np
    except ImportError:
        print("  SKIP  flush: numpy not available")
        return

    if not _CALL_LOOP_LOADED:
        print("  SKIP  flush: call_loop not importable (heavy deps missing)")
        return

    import anima.call_loop as cl

    # Build a real SpeakerTrack inside a running event loop so its asyncio.Queue
    # is created on the correct loop.
    async def _run():
        st = cl.SpeakerTrack()

        # Verify initially empty
        _assert(not st.speaking(), "flush: initially not speaking")

        # Push several chunks — simulates _say() queueing TTS audio
        chunk = np.ones(cl.OUT_SAMPLES, dtype=np.int16) * 1000
        st.push(chunk)
        st.push(chunk)
        st.push(chunk)
        # Also set _buf to simulate a partially-consumed frame
        st._buf = np.ones(64, dtype=np.int16) * 500

        _assert(st.speaking(), "flush: speaking() True after push")
        _assert(st._q.qsize() == 3, "flush: queue has 3 items before flush",
                f"got {st._q.qsize()}")
        _assert(len(st._buf) == 64, "flush: _buf non-empty before flush")

        # --- the main event ---
        st.flush()

        _assert(st._q.qsize() == 0, "flush: queue empty after flush",
                f"got {st._q.qsize()}")
        _assert(len(st._buf) == 0, "flush: _buf empty after flush",
                f"len={len(st._buf)}")
        _assert(not st.speaking(), "flush: speaking() False after flush")

        # push again — verify flush didn't break subsequent use
        st.push(chunk)
        _assert(st.speaking(), "flush: speaking() True after re-push post-flush")
        st.flush()
        _assert(not st.speaking(), "flush: speaking() False after second flush")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    source = "call_loop._is_barge (imported)" if _CALL_LOOP_LOADED else "_local_is_barge (fallback copy)"
    print(f"\n=== test_barge_in — barge decision via: {source} ===\n")

    print("-- Tier 1: _is_barge pure logic --")
    test_barge_not_enough_frames()
    test_barge_brief_spike()
    test_barge_echo_level_energy()
    test_barge_sustained_high_energy()
    test_barge_exactly_at_threshold_not_over()
    test_barge_one_dip_interrupts_sustain()
    test_barge_zero_barge_frames()
    test_barge_empty_window()

    print("\n-- Tier 2: SpeakerTrack.flush() --")
    test_flush()

    print(f"\n{'=' * 40}")
    print(f"Results: {_passed} passed, {_failed} failed")
    if _failed:
        print("SOME TESTS FAILED")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
