# PO → compliant label-instruction file (working prototype)

A working demo of milestone 1: read a purchase order, validate it, apply your brand-licence and
retailer rules from an editable library, and output a finished `.xlsx` instruction file.

## Run it
```bash
pip install pdfplumber openpyxl
python3 po_pipeline.py sample_po_retailco.pdf --out label_instructions.xlsx
```

## What it does (your spec, in order)
1. **Reads the PO** and extracts header + line items.
2. **Validates EAN13** check digits. An invalid code is **blocked from the output and flagged** in a
   Review sheet — no silent errors. (The sample PO has one bad code planted to prove this.)
3. **Applies brand-licence rules** (credit line + year) from `brand_rules.csv`. A licence with **no
   confirmed credit line is held, never guessed.**
4. **Applies retailer/country rules** (hanger colour, alarm code, OEKO-TEX, label languages) from
   `retailer_rules.csv` — from data, not from a person's memory.
5. **Writes the `.xlsx`** with EAN13/DUN14 codes kept as **text** (not numbers) + a Review Flags sheet.

## The editable rule library (your "non-technical staff" requirement)
`brand_rules.csv` and `retailer_rules.csv` stand in for what would be **Google Sheets** in production.
Your team edits a row to add a licence, change a credit line, or update a retailer rule — no developer
needed. The system reads it at run time and validates entries (an empty credit line becomes an
automatic hold).

## On the full build
Extraction of your varied/changing PDF layouts would use an LLM (Claude) constrained to a strict JSON
schema, with **everything it returns passing through these same deterministic validators** before a
cell is written. The model reads; the validators decide. Your Excel-format retailer needs no model at
all — direct parsing, cheaper and exact.

This demo runs on a synthetic PO built from your description. Milestone 1 is about proving it on your
real files. — Collatio Labs (AI-assisted, human-reviewed).
