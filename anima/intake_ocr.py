"""intake_ocr — OCR FALLBACK for scanned PDFs and images, via the tesseract/pdftoppm BINARIES.

OCR is NOT the default parser (see docs/uki_ocr_policy.md): native text extraction runs first; OCR
runs only when native fails / returns near-empty / the source is a scanned PDF or an image. This
module shells out to the LOCAL tesseract binary (no pip dependency) inside a sandbox — size limit,
page limit, timeout, no network — and labels its output honestly: extraction_method=ocr,
source_type=scanned_pdf|image, plus a coarse confidence. It NEVER fabricates: no text -> empty.

Heavy + opt-in (ANIMA_INTAKE_ACTIVATE_HEAVY=1) and host-pressure-aware (deferred under red), so a
scanned book never silently spins OCR on a strained Mac.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# sandbox limits
_MAX_BYTES = 400 * 1024 * 1024      # refuse an absurdly large input
_MAX_PAGES = 30                     # cap pages OCR'd from a PDF (a scanned book is bounded, not infinite)
_PAGE_TIMEOUT = 60                  # seconds per page / image


def _bin(name):
    return shutil.which(name)


def ocr_available() -> bool:
    return bool(_bin("tesseract"))


def _heavy_ok() -> tuple:
    """(allowed, reason). OCR is heavy + opt-in + host-pressure-aware."""
    if os.environ.get("ANIMA_INTAKE_ACTIVATE_HEAVY") != "1":
        return False, "OCR is opt-in (set ANIMA_INTAKE_ACTIVATE_HEAVY=1)"
    try:
        from . import host_pressure as _hp
        ok, why = _hp.heavy_ok()
        if not ok:
            return False, "deferred under host pressure (%s)" % why
    except Exception:
        pass
    return True, ""


def _run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # pragma: no cover
        return 255, "", repr(e)


def _ocr_one_image(img_path) -> tuple:
    """(text, confidence) for one image via the tesseract binary. Confidence = mean word conf from
    the tsv output (0-100), or None. No network; bounded by _PAGE_TIMEOUT."""
    tess = _bin("tesseract")
    if not tess:
        return "", None
    rc, out, _ = _run([tess, str(img_path), "stdout", "-l", "eng"], _PAGE_TIMEOUT)
    text = (out or "").strip()
    conf = None
    rc2, tsv, _ = _run([tess, str(img_path), "stdout", "-l", "eng", "tsv"], _PAGE_TIMEOUT)
    if rc2 == 0 and tsv:
        confs = []
        for line in tsv.splitlines()[1:]:
            cols = line.split("\t")
            if len(cols) >= 12 and cols[-1].strip():
                try:
                    c = float(cols[10])
                    if c >= 0:
                        confs.append(c)
                except Exception:
                    pass
        if confs:
            conf = round(sum(confs) / len(confs), 1)
    return text, conf


def ocr_image(path: str) -> dict:
    """OCR a single image file. Returns the normalized parse dict (status/text/chunks/meta/need)."""
    p = Path(path)
    meta = {"source_type": "image", "extraction_method": "ocr"}
    ok, why = _heavy_ok()
    if not ok:
        return _norm("needs_dependency", need=why, meta=meta)
    if not ocr_available():
        return _norm("needs_dependency", need="ocr (tesseract binary not found)", meta=meta)
    if not p.exists() or p.stat().st_size > _MAX_BYTES:
        return _norm("needs_dependency", need="a readable image under the size limit", meta=meta)
    text, conf = _ocr_one_image(p)
    meta["confidence"] = conf
    meta["ocr_chars"] = len(text)
    chunks = [{"page": None, "section": "ocr", "text": text}] if text else []
    return _norm("ok", text=text, chunks=chunks,
                 meta={**meta, "note": "" if text else "OCR ran but found no text in the image"})


def ocr_pdf(path: str, *, max_pages: int = _MAX_PAGES) -> dict:
    """OCR a scanned PDF: rasterize the first `max_pages` pages with pdftoppm, then tesseract each.
    Page-numbered, timestamp-free chunks. Sandboxed (page cap, per-page timeout)."""
    p = Path(path)
    meta = {"source_type": "scanned_pdf", "extraction_method": "ocr"}
    ok, why = _heavy_ok()
    if not ok:
        return _norm("needs_dependency", need=why, meta=meta)
    if not (ocr_available() and _bin("pdftoppm")):
        return _norm("needs_dependency",
                     need="ocr (needs the tesseract + pdftoppm binaries)", meta=meta)
    if not p.exists() or p.stat().st_size > _MAX_BYTES:
        return _norm("needs_dependency", need="a readable PDF under the size limit", meta=meta)
    d = tempfile.mkdtemp(prefix="ocr-pdf-")
    try:
        rc, _, se = _run([_bin("pdftoppm"), "-png", "-r", "150", "-f", "1",
                          "-l", str(int(max_pages)), str(p), str(Path(d) / "pg")], _PAGE_TIMEOUT * 4)
        pages = sorted(Path(d).glob("pg*.png"))
        if not pages:
            return _norm("needs_dependency",
                         need="a rasterizable PDF (pdftoppm produced no pages)", meta=meta)
        chunks, confs, parts = [], [], []
        for i, img in enumerate(pages[:max_pages], 1):
            t, c = _ocr_one_image(img)
            if t:
                chunks.append({"page": i, "section": "ocr p%d" % i, "text": t})
                parts.append(t)
            if c is not None:
                confs.append(c)
        text = "\n\n".join(parts).strip()
        meta["pages_ocrd"] = len(pages[:max_pages])
        meta["confidence"] = round(sum(confs) / len(confs), 1) if confs else None
        meta["ocr_chars"] = len(text)
        return _norm("ok", text=text, chunks=chunks,
                     meta={**meta, "note": "" if text else "OCR ran but found no text in the PDF"})
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _norm(status, *, text="", chunks=None, meta=None, need="") -> dict:
    return {"status": status, "text": text, "chunks": list(chunks or []),
            "figures": [], "tables": [], "meta": dict(meta or {}), "need": need}


def _selftest() -> int:
    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    ok("tesseract + pdftoppm binaries present (this Mac)", ocr_available() and bool(_bin("pdftoppm")))
    os.environ.pop("ANIMA_INTAKE_ACTIVATE_HEAVY", None)
    r = ocr_image("/tmp/nope.png")
    ok("OCR is opt-in: heavy off -> needs_dependency, never fabricates", r["status"] == "needs_dependency")
    print("\nINTAKE-OCR: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("intake_ocr — OCR fallback for scanned PDFs / images (tesseract+pdftoppm). Use --selftest.")
