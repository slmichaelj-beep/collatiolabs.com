# UKI OCR Policy (dev directive)

OCR is **not** the default parser. Native extraction first; OCR only as a fallback for
scanned / image / failed-text sources, sandboxed, source-labeled, and certified.

## Pipeline
1. Detect file type.
2. Try **native extraction** first when available.
3. Measure extracted-text quality: character count, word count, text density per page,
   parse errors, garbage/encoding ratio.
4. If native extraction is good enough → **skip OCR**.
5. If native extraction fails, returns near-empty text, or the PDF/image is scanned → **run OCR**.
6. OCR runs in the **parser sandbox**: size limit, page limit, timeout, memory limit,
   no arbitrary network, no access to secrets, no writes outside the intake workspace.
7. OCR output is **source text, not instruction** (subject to the AI-security doctrine below).
8. OCR result is labeled: `source_type=scanned_pdf|image|screenshot`, `extraction_method=ocr`,
   `confidence=...`.
9. If OCR dependencies are missing → classify **honestly**: `PARTIAL / NEEDS_OCR_DEPENDENCY`.
10. Do **not** claim image / scanned-PDF support is COMPLETE unless the OCR live-path cert passes.

## Certification required — `scripts/certify_ocr_intake.py` must prove
- a text PDF uses **native extraction**, not OCR;
- a scanned PDF **triggers** OCR;
- an image upload **triggers** OCR;
- OCR text is **stored** as a reference;
- OCR text is **retrievable**;
- Vera can **answer** from OCR text;
- the source label says **OCR / scanned / image**;
- **hostile OCR text is treated as data, never policy** (ties to certify_ai_security.py);
- a **missing OCR dependency reports honest PARTIAL**, not fake success.

## Status
QUEUED under Universal Media Intake (Phase 10/11). Until `certify_ocr_intake.py` passes on a
decodable fixture, image / scanned-PDF intake stays `PARTIAL — NEEDS_OCR_DEPENDENCY`, never COMPLETE.
A 202 MB scanned book (e.g. "Man And His Symbols") uploads fine now (size-cap + disk-guard fixed),
but yields little text until this OCR path lands.
