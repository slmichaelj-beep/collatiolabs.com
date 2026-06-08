#!/usr/bin/env python3
"""Dependency-free plain-text PDF writer (Helvetica, multi-page)."""


def write_pdf(full_text, path):
    repl = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "…": "..."}
    for a, b in repl.items():
        full_text = full_text.replace(a, b)
    text = full_text.encode("latin-1", "replace").decode("latin-1")

    max_chars, lines_per_page = 95, 52
    wrapped = []
    for raw in text.split("\n"):
        if raw == "":
            wrapped.append("")
            continue
        while len(raw) > max_chars:
            cut = raw.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            wrapped.append(raw[:cut])
            raw = raw[cut:].lstrip()
        wrapped.append(raw)
    pages = [wrapped[i:i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[""]]

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    n_pages = len(pages)
    font_obj = 3 + n_pages * 2
    bodies, next_num, kids = {}, 3, []
    for pg in pages:
        page_num, content_num = next_num, next_num + 1
        next_num += 2
        kids.append(page_num)
        stream = "BT /F1 11 Tf 50 760 Td 13 TL\n"
        first = True
        for ln in pg:
            stream += (f"({esc(ln)}) Tj\n" if first else f"T* ({esc(ln)}) Tj\n")
            first = False
        stream += "ET"
        sb = stream.encode("latin-1", "replace")
        bodies[content_num] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(sb), sb)
        bodies[page_num] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                            b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                            % (font_obj, content_num))
    bodies[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    bodies[2] = (b"<< /Type /Pages /Kids [%s] /Count %d >>"
                 % (b" ".join(b"%d 0 R" % k for k in kids), n_pages))
    bodies[font_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    out = bytearray(b"%PDF-1.4\n")
    offs = {}
    for num in range(1, font_obj + 1):
        offs[num] = len(out)
        out += b"%d 0 obj\n" % num + bodies[num] + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (font_obj + 1)
    for num in range(1, font_obj + 1):
        out += b"%010d 00000 n \n" % offs[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (font_obj + 1, xref)
    with open(path, "wb") as f:
        f.write(out)
    return path
