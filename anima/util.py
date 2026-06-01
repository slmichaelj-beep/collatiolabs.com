"""Small shared helpers."""

from __future__ import annotations


def label(title: str) -> None:
    """Name this process clearly in Activity Monitor / ps, so nothing anima runs
    shows up as a generic 'python3'. Best-effort: needs `setproctitle` installed.
    """
    try:
        import setproctitle
        setproctitle.setproctitle(f"anima[{title}]")
    except Exception:
        pass
