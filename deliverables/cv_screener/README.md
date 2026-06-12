# CV Screener — PDF resumes → scored Excel sheet

Batch-screens a folder of PDF resumes against your criteria and writes one scored row per
candidate into Excel. Runs entirely on your machine — no resume data leaves it.

## Quick start
```bash
pip install pdfplumber pypdf openpyxl
python3 cv_screener.py --pdf-dir ./resumes --criteria criteria.json --out results.xlsx
```
To fill **your existing spreadsheet's columns**, pass it as a template (headers matched by name):
```bash
python3 cv_screener.py --pdf-dir ./resumes --criteria criteria.json \
    --template your_sheet.xlsx --out results.xlsx
```

## What you get per CV
name · email · phone · years of experience · education level · skills matched ·
missing required skills · weighted score · extraction method · notes.
Results are sorted by score (highest first). A CV missing a hard-required skill is
score-halved and labeled — visible, never silently dropped.

## Scanned (image-based) PDFs
Text-layer PDFs work out of the box. Scanned PDFs are OCR'd automatically **if** the OCR
toolchain is installed:
```bash
brew install tesseract poppler          # macOS (Windows/Linux: see tesseract docs)
pip install pytesseract pdf2image pillow
```
Without it, scanned files are flagged `NEEDS_OCR` in the output — never skipped silently.

## Criteria (criteria.json)
```json
{
  "skills":   {"python": 10, "sql": 6, "aws": 5, "excel": 3},
  "required": ["python"],
  "min_years": 2,
  "education_bonus": {"phd": 5, "master": 3, "bachelor": 2}
}
```
Weights are yours to set; `required` lists hard requirements; `min_years` adds a bonus when met.

## Honest limitations
Field extraction (name/years) is heuristic — resumes vary wildly, so expect ~90% accuracy on
contact fields and treat the score as a *triage* aid, not a hiring decision. One malformed PDF
never crashes the batch; it's logged as an ERROR row.

— Built by Collatio Labs (AI-assisted, human-reviewed).
