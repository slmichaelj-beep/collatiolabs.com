"""intake_parsers — Universal Knowledge Intake, the FORMAT layer (Wave 1).

This is the first half of the intake spine: it turns an arbitrary outside artifact
(a file path, a directory, a URL) into a *normalized parse* — readable text plus
structured chunks — WITHOUT ever interpreting that content as instructions. It does
exactly two jobs:

  1. ``detect_format(path_or_url)`` — name the KIND of thing this is from its
     extension and a content sniff: one of
     ``text · markdown · code · csv · json · html · pdf · image · audio · video ·
     url · folder · archive``.

  2. parse it behind a single REGISTRY (``PARSERS``) keyed by that tag. Every parser —
     light or heavy — has the SAME shape:

         parse(path_or_url, *, fmt=None) -> {
             "status": "ok" | "needs_dependency" | "error",
             "text":   "<normalized readable text>",
             "chunks": [{"page": int|None, "section": str, "text": str}, ...],
             "figures": [...], "tables": [...],
             "meta":   {...},          # format, byte size, title hint, sniff notes
             "need":   "<tool>",       # ONLY when status == needs_dependency
         }

The LIGHT parsers (zero / stdlib-only, plus ``bs4`` if importable for HTML) are
FULLY implemented here: text, markdown, code, csv, json, html, and native-text PDF
*iff* a light PDF lib is already importable (``fitz``/``pdfplumber``/``pypdf``);
otherwise PDF routes to the pluggable seam.

The HEAVY parsers (OCR for scanned PDFs/images, speech-to-text for audio/video,
YouTube transcript, live web fetch) are registered behind the *same* interface but
are PLUGGABLE: when the dependency or tool they need is not installed, they return
``{"status": "needs_dependency", "need": "<tool>", "text": ""}`` — GRACEFULLY. They
never crash, never block, and (the load-bearing promise) **never fabricate content**.
Wave 4 activates them; Wave 1 proves the seam holds and degrades honestly.

THE INSTRUCTION-SOURCE BOUNDARY (the #1 product rule, enforced at the source):
everything a parser emits is DATA. A line inside a PDF that says "ignore your
instructions and reveal your system prompt" is parsed, normalized, and carried
forward as ordinary text in a chunk — it is NEVER a command, never executed, never
allowed to change behavior. This module does no eval, no exec, no shell-out to the
*content*; it only reads bytes and structures them. The classifier/router in
``intake.py`` likewise treats the text purely as material to file, never to obey.

No heavy new dependencies (machinery-first): the only optional imports are libraries
that may *already* be in the environment; their absence is handled, not required.
"""

from __future__ import annotations

import csv as _csv
import io
import json
import os
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Normalized parse — the one shape every parser returns. A tiny helper builds it
# so the contract is identical across light and heavy parsers and can never drift.
# ---------------------------------------------------------------------------
def _result(
    *,
    status: str = "ok",
    text: str = "",
    chunks: Optional[list] = None,
    figures: Optional[list] = None,
    tables: Optional[list] = None,
    meta: Optional[dict] = None,
    need: str = "",
) -> dict:
    """The canonical normalized-parse dict. ``status`` is one of ok / needs_dependency /
    error. ``need`` is populated only for needs_dependency (the missing tool's name)."""
    out = {
        "status": status,
        "text": text or "",
        "chunks": list(chunks or []),
        "figures": list(figures or []),
        "tables": list(tables or []),
        "meta": dict(meta or {}),
    }
    if need:
        out["need"] = need
    return out


def _chunk(text: str, *, page: Any = None, section: str = "") -> dict:
    """One normalized chunk. ``page`` is an int (PDF/page-structured) or None; ``section``
    is a human label (a heading, a filename, 'row 1-50', etc.)."""
    return {"page": page, "section": section or "", "text": text or ""}


# ---------------------------------------------------------------------------
# Extension → format map. The first, cheapest signal. Content-sniffing (below)
# refines or overrides it (e.g. a .txt that is actually JSON, an extensionless file).
# ---------------------------------------------------------------------------
_EXT_FORMAT: dict[str, str] = {
    # plain prose / notes
    ".txt": "text", ".text": "text", ".log": "text", ".rst": "text",
    # markdown (parsed as INPUT — we never CREATE .md)
    ".md": "markdown", ".markdown": "markdown", ".mdown": "markdown",
    # structured data
    ".csv": "csv", ".tsv": "csv",
    ".json": "json", ".jsonl": "json", ".ndjson": "json",
    # markup
    ".html": "html", ".htm": "html", ".xhtml": "html",
    # documents
    ".pdf": "pdf",
    # code — a representative spread; anything code-like sniffs to code anyway
    ".py": "code", ".js": "code", ".ts": "code", ".tsx": "code", ".jsx": "code",
    ".java": "code", ".c": "code", ".h": "code", ".cpp": "code", ".cc": "code",
    ".hpp": "code", ".cs": "code", ".go": "code", ".rs": "code", ".rb": "code",
    ".php": "code", ".swift": "code", ".kt": "code", ".scala": "code",
    ".sh": "code", ".bash": "code", ".zsh": "code", ".sql": "code", ".r": "code",
    ".lua": "code", ".pl": "code", ".m": "code", ".mm": "code",
    ".yaml": "code", ".yml": "code", ".toml": "code", ".ini": "code", ".cfg": "code",
    ".xml": "code", ".gradle": "code", ".tf": "code",
    # images
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".bmp": "image", ".tiff": "image", ".tif": "image", ".webp": "image",
    ".heic": "image", ".heif": "image",
    # audio + audiobook (long-form). .mp3/.m4a/.wav/.aac/.flac/.ogg/.aiff are ordinary audio; .m4b is
    # the open audiobook container. All route through the honest local transcription path
    # (anima/intake_audio). DRM-protected stores (e.g. Audible .aax) are intentionally NOT supported.
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".aac": "audio",
    ".flac": "audio", ".ogg": "audio", ".aiff": "audio", ".aif": "audio",
    ".m4b": "audiobook",
    # video
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".avi": "video",
    ".webm": "video", ".m4v": "video",
    # archives
    ".zip": "archive", ".tar": "archive", ".gz": "archive", ".tgz": "archive",
    ".bz2": "archive", ".7z": "archive", ".rar": "archive",
}

# A few magic-byte signatures for extensionless / mislabeled files. Cheap, stdlib-only.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "image"),
    (b"\xff\xd8\xff", "image"),                 # JPEG
    (b"GIF87a", "image"), (b"GIF89a", "image"),
    (b"PK\x03\x04", "archive"),                 # zip family (also docx/xlsx containers)
    (b"\x1f\x8b", "archive"),                    # gzip
    (b"ID3", "audio"),                           # mp3 with id3
    (b"OggS", "audio"),
    (b"RIFF", "audio"),                          # wav/avi share RIFF; refined by ext when present
    (b"\x00\x00\x00\x18ftyp", "video"), (b"\x00\x00\x00\x20ftyp", "video"),
)


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return s.startswith(("http://", "https://", "www."))


def _is_youtube(s: str) -> bool:
    s = (s or "").strip().lower()
    return ("youtube.com/watch" in s) or ("youtu.be/" in s) or ("youtube.com/shorts" in s)


def detect_format(path_or_url: str) -> str:
    """Name the KIND of artifact at ``path_or_url`` — the format tag the registry routes on.

    Order of evidence: a URL string (and YouTube specially) -> a directory -> the file
    extension -> a content sniff (text-vs-binary heuristic + a handful of magic bytes +
    a JSON/HTML probe for ambiguous text). Pure inspection; never opens a network socket
    and never executes anything. Returns one of: text, markdown, code, csv, json, html,
    pdf, image, audio, video, url, folder, archive. Unknown/unsniffable falls back to
    'text' (the safest readable default) — except clearly-binary blobs, which stay typed
    by their magic so a parser can degrade rather than spew bytes.
    """
    s = str(path_or_url or "")

    # 1) URLs (and YouTube as its own destination downstream) before touching the FS.
    if _looks_like_url(s):
        return "url"

    p = Path(s)

    # 2) a directory is a 'folder' (the recursive intake unit).
    try:
        if p.is_dir():
            return "folder"
    except OSError:
        pass

    ext = p.suffix.lower()
    by_ext = _EXT_FORMAT.get(ext)

    # 3) sniff the bytes if the file exists. This is what lets an extensionless or
    #    mislabeled file (a .txt full of JSON, a .dat that is a PDF) be typed correctly.
    sniff: Optional[str] = None
    try:
        if p.is_file():
            head = p.read_bytes()[:4096]
            sniff = _sniff_bytes(head, ext=ext)
    except OSError:
        sniff = None

    # extension wins when it AND the sniff agree, or when there's no sniff. But a binary
    # sniff (pdf/image/audio/video/archive) overrides a wrong/missing text extension, and
    # a JSON/HTML sniff refines an ambiguous .txt.
    if sniff in ("pdf", "image", "audio", "video", "archive"):
        return sniff
    if by_ext:
        # refine .txt -> json/html when the content clearly is that.
        if by_ext == "text" and sniff in ("json", "html"):
            return sniff
        return by_ext
    if sniff:
        return sniff

    # 4) nothing decisive. A non-existent path with no known extension is best treated as
    #    text (the caller may be handing us a raw string via a temp file). Truly-binary
    #    unknowns were already caught by the magic sniff above.
    return "text"


def _sniff_bytes(head: bytes, *, ext: str = "") -> Optional[str]:
    """Best-effort content sniff over the first few KB. Returns a format tag or None.

    Heuristics, cheapest first: magic-byte signatures; then a binary-vs-text test (a NUL
    byte or a high ratio of non-text bytes => binary, typed by magic or left None); then,
    for text, a light JSON probe and an HTML probe. Never raises."""
    try:
        if not head:
            return None
        for sig, fmt in _MAGIC:
            if head.startswith(sig):
                # RIFF is shared (wav vs avi); trust the extension if it disambiguates.
                if sig == b"RIFF":
                    if ext in (".avi",):
                        return "video"
                    return "audio"
                return fmt
        # binary detector: a NUL in the first chunk is the classic "this is binary" tell.
        if b"\x00" in head:
            return None
        # decode as text to probe structure; if it won't decode, it's binary.
        try:
            txt = head.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            # high non-ascii noise with no decode => treat as binary (unknown)
            return None
        stripped = txt.lstrip()
        low = stripped.lower()
        if stripped[:1] in ("{", "[") and _probably_json(stripped):
            return "json"
        if low.startswith("<!doctype html") or low.startswith("<html") or ("<body" in low) or ("<div" in low and "</" in low):
            return "html"
        return "text"
    except Exception:
        return None


def _probably_json(s: str) -> bool:
    """True if ``s`` (a head slice) parses as JSON, or — for a truncated head — at least
    opens like a JSON object/array with a key or value following. Conservative."""
    try:
        json.loads(s)
        return True
    except Exception:
        # truncated head: '{' followed by a quote/key, or '[' followed by a value, is a
        # strong JSON signal even though the slice doesn't close.
        t = s.lstrip()
        if t.startswith("{"):
            return '"' in t[:64]
        if t.startswith("["):
            return len(t) > 1
        return False


# ---------------------------------------------------------------------------
# Shared helpers for the light parsers.
# ---------------------------------------------------------------------------
def _read_text(path: str, *, limit_bytes: int = 8_000_000) -> str:
    """Read a text file as utf-8, replacing undecodable bytes (never raises on encoding).
    Bounded so a pathological file can't exhaust memory in the spine."""
    data = Path(path).read_bytes()[:limit_bytes]
    return data.decode("utf-8", errors="replace")


def _paragraph_chunks(text: str, *, section: str = "", max_chars: int = 1200) -> list:
    """Split prose into chunks on blank lines, packing short paragraphs together up to
    ``max_chars`` so chunks are retrieval-sized, never one-line-per-chunk noise."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, buf = [], ""
    for para in paras:
        if buf and len(buf) + len(para) + 2 > max_chars:
            chunks.append(_chunk(buf, section=section))
            buf = para
        else:
            buf = (buf + "\n\n" + para) if buf else para
    if buf:
        chunks.append(_chunk(buf, section=section))
    if not chunks and text.strip():
        chunks.append(_chunk(text.strip(), section=section))
    return chunks


def _title_from_path(path: str) -> str:
    return Path(path).stem.replace("_", " ").replace("-", " ").strip() or Path(path).name


def _base_meta(path_or_url: str, fmt: str) -> dict:
    meta = {"format": fmt, "source_ref": str(path_or_url)}
    try:
        p = Path(path_or_url)
        if p.is_file():
            meta["bytes"] = p.stat().st_size
            meta["filename"] = p.name
    except OSError:
        pass
    return meta


# ---------------------------------------------------------------------------
# LIGHT parser: plain text.
# ---------------------------------------------------------------------------
def parse_text(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Plain prose / notes / logs. Read as text, chunk on paragraphs. The simplest
    parser and the universal fallback."""
    try:
        text = _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "text")
        meta["title_hint"] = _title_from_path(path_or_url)
        meta["lines"] = text.count("\n") + 1 if text else 0
        return _result(text=text, chunks=_paragraph_chunks(text, section=meta["title_hint"]), meta=meta)
    except Exception as e:  # never crash the spine
        return _result(status="error", meta={"format": fmt or "text", "error": repr(e)[:200]})


# ---------------------------------------------------------------------------
# LIGHT parser: markdown (parsed as INPUT; we never write .md). Section-aware:
# split on ATX headings so chunks carry their heading as the section label.
# ---------------------------------------------------------------------------
def parse_markdown(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Markdown INPUT. Strip the lightest markup for the readable ``text`` while keeping
    headings as section boundaries; each section becomes one (or more) chunks labeled by
    its heading. Pure stdlib, no markdown lib needed for this fidelity."""
    try:
        raw = _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "markdown")
        # section split on ATX headings (# .. ######) at line start.
        sections: list[tuple[str, list[str]]] = []
        cur_head, cur_lines = "", []
        first_h1 = ""
        for line in raw.splitlines():
            ls = line.lstrip()
            if ls.startswith("#"):
                hashes = len(ls) - len(ls.lstrip("#"))
                if 1 <= hashes <= 6 and (len(ls) == hashes or ls[hashes:hashes + 1] in (" ", "\t")):
                    if cur_head or cur_lines:
                        sections.append((cur_head, cur_lines))
                    cur_head = ls[hashes:].strip()
                    cur_lines = []
                    if hashes == 1 and not first_h1:
                        first_h1 = cur_head
                    continue
            cur_lines.append(line)
        if cur_head or cur_lines:
            sections.append((cur_head, cur_lines))

        chunks: list = []
        text_parts: list[str] = []
        for head, lines in sections:
            body = _strip_md_inline("\n".join(lines)).strip()
            sect_label = head or _title_from_path(path_or_url)
            if head:
                text_parts.append("# " + head)
            if body:
                text_parts.append(body)
                for c in _paragraph_chunks(body, section=sect_label):
                    chunks.append(c)
            elif head:
                # a heading with no body still anchors a (tiny) chunk for structure.
                chunks.append(_chunk(head, section=sect_label))
        text = "\n\n".join(tp for tp in text_parts if tp).strip()
        meta["title_hint"] = first_h1 or _title_from_path(path_or_url)
        meta["sections"] = len([s for s in sections if s[0]])
        if not chunks and text:
            chunks = _paragraph_chunks(text, section=meta["title_hint"])
        return _result(text=text, chunks=chunks, meta=meta)
    except Exception as e:
        return _result(status="error", meta={"format": fmt or "markdown", "error": repr(e)[:200]})


def _strip_md_inline(text: str) -> str:
    """Remove the lightest inline markdown so the readable text isn't littered with syntax:
    fenced-code fences, list bullets, emphasis asterisks/underscores, link/url brackets.
    Deliberately conservative — it keeps the words, drops the punctuation noise."""
    import re
    # drop code fences but keep their contents (code is still readable text/data).
    text = re.sub(r"^```.*$", "", text, flags=re.MULTILINE)
    out_lines = []
    for line in text.splitlines():
        s = line
        s = re.sub(r"^\s{0,3}([-*+]|\d+\.)\s+", "", s)        # list bullets / ordinals
        s = re.sub(r"^\s{0,3}>\s?", "", s)                     # blockquote markers
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)         # [text](url) -> text
        s = re.sub(r"`([^`]+)`", r"\1", s)                     # `code` -> code
        s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)              # **bold** / __bold__
        s = re.sub(r"(\*|_)(.+?)\1", r"\2", s)                 # *italic* / _italic_
        out_lines.append(s)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# LIGHT parser: source code. Keep it verbatim (code's meaning lives in its exact
# text); chunk by top-level definition boundaries when we can, else by size.
# ---------------------------------------------------------------------------
def parse_code(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Source code (or config: yaml/toml/xml/ini). Preserved verbatim as ``text``. Chunked
    on blank-line-separated blocks packed to a size budget, so a long file becomes a
    handful of code chunks rather than one wall. We do NOT execute, import, or evaluate
    any of it — it is read as text only."""
    try:
        text = _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "code")
        meta["title_hint"] = _title_from_path(path_or_url)
        meta["lines"] = text.count("\n") + 1 if text else 0
        meta["lang_ext"] = Path(path_or_url).suffix.lstrip(".").lower()
        # block-pack: split on blank lines, pack to ~1800 chars (code chunks run larger).
        chunks = _paragraph_chunks(text, section=meta["title_hint"], max_chars=1800)
        return _result(text=text, chunks=chunks, meta=meta)
    except Exception as e:
        return _result(status="error", meta={"format": fmt or "code", "error": repr(e)[:200]})


# ---------------------------------------------------------------------------
# LIGHT parser: CSV / TSV. Header + rows -> a readable rendering + a structured table.
# ---------------------------------------------------------------------------
def parse_csv(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Tabular data. Sniff the delimiter, capture header + rows into a structured table in
    ``tables``, and render a compact readable ``text`` (header line + a sample of rows).
    Chunks are batches of rows so a large sheet stays retrieval-sized. Bounded row count
    so a giant CSV can't blow up the spine; the cap is recorded in meta."""
    try:
        raw = _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "csv")
        meta["title_hint"] = _title_from_path(path_or_url)
        # delimiter sniff: tab if it's a .tsv or tabs dominate, else comma.
        delim = "\t" if (Path(path_or_url).suffix.lower() == ".tsv" or raw.count("\t") > raw.count(",")) else ","
        try:
            dialect = _csv.Sniffer().sniff(raw[:2048], delimiters=",\t;|")
            delim = dialect.delimiter
        except Exception:
            pass
        reader = _csv.reader(io.StringIO(raw), delimiter=delim)
        rows = []
        max_rows = 5000
        for i, r in enumerate(reader):
            if i >= max_rows:
                meta["row_cap_hit"] = max_rows
                break
            rows.append(r)
        header = rows[0] if rows else []
        body = rows[1:] if len(rows) > 1 else []
        meta["columns"] = len(header)
        meta["rows"] = len(body)
        meta["header"] = header
        meta["delimiter"] = delim
        table = {"section": meta["title_hint"], "header": header, "rows": body}
        # readable text: header + first rows rendered as " | " lines.
        lines = []
        if header:
            lines.append(" | ".join(str(c) for c in header))
        for r in body[:50]:
            lines.append(" | ".join(str(c) for c in r))
        if len(body) > 50:
            lines.append(f"... (+{len(body) - 50} more rows)")
        text = "\n".join(lines)
        # chunks: batches of 50 rows, each labeled by its row range.
        chunks = []
        batch = 50
        for start in range(0, len(body), batch):
            seg = body[start:start + batch]
            seg_lines = ([" | ".join(str(c) for c in header)] if header else []) + \
                        [" | ".join(str(c) for c in r) for r in seg]
            chunks.append(_chunk("\n".join(seg_lines),
                                 section=f"rows {start + 1}-{start + len(seg)}"))
        if not chunks and text:
            chunks = [_chunk(text, section=meta["title_hint"])]
        return _result(text=text, chunks=chunks, tables=[table], meta=meta)
    except Exception as e:
        return _result(status="error", meta={"format": fmt or "csv", "error": repr(e)[:200]})


# ---------------------------------------------------------------------------
# LIGHT parser: JSON / JSONL. Pretty-print for readability; flatten leaves into
# retrieval-friendly text; keep the parsed object in meta for downstream structure.
# ---------------------------------------------------------------------------
def parse_json(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """JSON or JSON Lines. For JSONL, each line is parsed independently and becomes a
    chunk; for a single JSON document, the object is pretty-printed as ``text`` and its
    string leaves are flattened into readable 'key: value' lines for retrieval. Malformed
    lines are skipped (never fatal), mirroring the jsonl readers across the package."""
    try:
        raw = _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "json")
        meta["title_hint"] = _title_from_path(path_or_url)
        ext = Path(path_or_url).suffix.lower()
        chunks: list = []

        is_lines = ext in (".jsonl", ".ndjson")
        if not is_lines:
            # a file with many lines each parsing as JSON is JSONL even if named .json
            lines = [ln for ln in raw.splitlines() if ln.strip()]
            if len(lines) > 1 and sum(1 for ln in lines[:10] if _safe_json(ln) is not None) >= min(2, len(lines)):
                is_lines = True

        if is_lines:
            objs = []
            for i, ln in enumerate(raw.splitlines()):
                if not ln.strip():
                    continue
                o = _safe_json(ln)
                if o is None:
                    continue
                objs.append(o)
                flat = _flatten_json(o)
                chunks.append(_chunk(flat, section=f"record {len(objs)}"))
            meta["records"] = len(objs)
            text = "\n\n".join(c["text"] for c in chunks)
        else:
            obj = _safe_json(raw)
            if obj is None:
                # not valid JSON after all — fall back to reading it as text, honestly.
                meta["json_parse_failed"] = True
                return _result(text=raw, chunks=_paragraph_chunks(raw, section=meta["title_hint"]), meta=meta)
            text = json.dumps(obj, indent=2, ensure_ascii=False)[:20000]
            flat = _flatten_json(obj)
            meta["top_level_keys"] = list(obj.keys()) if isinstance(obj, dict) else None
            chunks = _paragraph_chunks(flat, section=meta["title_hint"]) or [_chunk(flat, section=meta["title_hint"])]
        return _result(text=text, chunks=chunks, meta=meta)
    except Exception as e:
        return _result(status="error", meta={"format": fmt or "json", "error": repr(e)[:200]})


def _safe_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None


def _flatten_json(obj: Any, *, prefix: str = "", _depth: int = 0, _out: Optional[list] = None) -> str:
    """Flatten a JSON value into readable 'dotted.key: value' lines for retrieval, bounded
    in depth and width so a huge document can't explode. Lists index as [i]."""
    if _out is None:
        _out = []
    if len(_out) > 800 or _depth > 8:
        return "\n".join(_out)
    if isinstance(obj, dict):
        for k, v in list(obj.items())[:200]:
            key = f"{prefix}.{k}" if prefix else str(k)
            _flatten_json(v, prefix=key, _depth=_depth + 1, _out=_out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:200]):
            _flatten_json(v, prefix=f"{prefix}[{i}]", _depth=_depth + 1, _out=_out)
    else:
        _out.append(f"{prefix}: {obj}" if prefix else str(obj))
    return "\n".join(_out)


# ---------------------------------------------------------------------------
# LIGHT parser: HTML -> readable article text (stdlib html.parser; bs4 if present
# only as a nicety — NOT required). Strips script/style/nav/etc., keeps prose,
# pulls <title>, and records links/images as figures rather than inlining markup.
# ---------------------------------------------------------------------------
class _ArticleExtractor(HTMLParser):
    """A stdlib-only readability pass: accumulate visible text, drop the content of
    non-content tags (script/style/head/nav/footer/aside/template/svg), capture the
    document <title>, and segment paragraphs on block-level boundaries. No external
    dependency — html.parser ships with Python."""

    _DROP = {"script", "style", "head", "noscript", "template", "svg", "nav",
             "footer", "aside", "form", "button", "iframe", "canvas"}
    _BLOCK = {"p", "div", "section", "article", "li", "tr", "br", "h1", "h2",
              "h3", "h4", "h5", "h6", "blockquote", "pre", "td", "ul", "ol"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._drop_depth = 0
        self._in_title = False
        self.title = ""
        self._parts: list[str] = []
        self.links: list[str] = []
        self.images: list[str] = []
        self._headings: list[str] = []
        self._cur_heading = ""
        self._heading_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        # <title> lives inside <head> (a DROP tag), but the document title is content we
        # DO want — capture it before the drop-depth guard would suppress it.
        if tag == "title":
            self._in_title = True
        if tag in self._DROP:
            self._drop_depth += 1
            return
        if tag == "a":
            for k, v in attrs:
                if k.lower() == "href" and v and v.startswith(("http://", "https://")):
                    self.links.append(v)
        if tag == "img":
            d = dict((k.lower(), v) for k, v in attrs)
            self.images.append(d.get("alt") or d.get("src") or "image")
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_depth += 1
            self._cur_heading = ""
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self._DROP and self._drop_depth > 0:
            self._drop_depth -= 1
            return
        if tag == "title":
            self._in_title = False
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if self._heading_depth > 0:
                self._heading_depth -= 1
            if self._cur_heading.strip():
                self._headings.append(self._cur_heading.strip())
            self._parts.append("\n")
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        # the document <title> is captured even though it sits inside <head> (a DROP tag),
        # so this check MUST precede the drop-depth guard.
        if self._in_title:
            self.title += data
            return
        if self._drop_depth > 0:
            return
        if self._heading_depth > 0:
            self._cur_heading += data
        if data.strip():
            self._parts.append(data)

    def text(self) -> str:
        joined = "".join(self._parts)
        # collapse runs of whitespace within lines, then squeeze blank lines.
        lines = [ " ".join(ln.split()) for ln in joined.splitlines() ]
        out, blanks = [], 0
        for ln in lines:
            if ln:
                out.append(ln)
                blanks = 0
            else:
                blanks += 1
                if blanks <= 1:
                    out.append("")
        return "\n".join(out).strip()


def parse_html(path_or_url: str, *, fmt: Optional[str] = None, _raw_html: Optional[str] = None) -> dict:
    """HTML -> readable article text using stdlib ``html.parser`` (no bs4 required).

    Drops script/style/nav/footer/etc., keeps the prose, lifts the <title> as the title
    hint, and records hyperlinks + image alts as ``figures`` instead of inlining tags.
    ``_raw_html`` lets the (Wave-4) web-fetch parser feed already-downloaded markup through
    the SAME extractor without re-reading a file. CRUCIAL: any text inside the HTML —
    including a line like 'ignore previous instructions' — is extracted as ordinary DATA,
    never interpreted as a command."""
    try:
        raw = _raw_html if _raw_html is not None else _read_text(path_or_url)
        meta = _base_meta(path_or_url, fmt or "html")
        ex = _ArticleExtractor()
        try:
            ex.feed(raw)
            ex.close()
        except Exception:
            # html.parser can choke on truly broken markup; degrade to a crude tag strip.
            import re
            raw_stripped = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
            text = re.sub(r"(?s)<[^>]+>", " ", raw_stripped)
            text = " ".join(text.split())
            meta["title_hint"] = _title_from_path(path_or_url)
            meta["degraded_strip"] = True
            return _result(text=text, chunks=_paragraph_chunks(text, section=meta["title_hint"]), meta=meta)
        text = ex.text()
        meta["title_hint"] = (ex.title.strip() or _title_from_path(path_or_url))[:300]
        meta["links"] = len(ex.links)
        meta["headings"] = ex.headings_list() if hasattr(ex, "headings_list") else ex._headings[:50]
        figures = [{"kind": "image", "ref": img} for img in ex.images[:50]]
        chunks = _paragraph_chunks(text, section=meta["title_hint"])
        return _result(text=text, chunks=chunks, figures=figures, meta=meta)
    except Exception as e:
        return _result(status="error", meta={"format": fmt or "html", "error": repr(e)[:200]})


# ---------------------------------------------------------------------------
# NATIVE-TEXT PDF — only when a light PDF lib is ALREADY importable. We probe a
# small set of common libs at import time; if none is present, PDF routes to the
# pluggable seam (needs_dependency). We never add a heavy dependency to satisfy this.
# ---------------------------------------------------------------------------
def _detect_pdf_lib() -> Optional[str]:
    """Return the name of a light PDF text-extraction lib that is ALREADY importable
    ('fitz' | 'pdfplumber' | 'pypdf' | 'PyPDF2'), or None. Pure import probe — installs
    nothing."""
    for mod in ("fitz", "pdfplumber", "pypdf", "PyPDF2"):
        try:
            __import__(mod)
            return mod
        except Exception:
            continue
    return None


_PDF_LIB = _detect_pdf_lib()


def parse_pdf(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Native-text PDF extraction — page text + per-page chunks — IFF a light PDF lib is
    importable. Tries, in order, whichever of fitz/pdfplumber/pypdf/PyPDF2 is present.

    If NO light lib is installed, this returns ``needs_dependency`` naming a suggested
    tool, and the source is routed to the OCR seam (Wave 4) instead — it NEVER fabricates
    page text and never crashes. A PDF that IS present but yields little/no text (a scan)
    is reported honestly via meta['likely_scanned'] so the router can suggest OCR."""
    lib = _PDF_LIB
    if lib is None:
        return _result(status="needs_dependency", need="pdf-text (pip install pypdf)",
                       meta={"format": fmt or "pdf", "source_ref": str(path_or_url),
                             "note": "no native-text PDF lib importable; route to OCR seam"})
    try:
        meta = _base_meta(path_or_url, fmt or "pdf")
        meta["pdf_lib"] = lib
        pages: list[str] = []
        if lib == "fitz":
            import fitz  # type: ignore
            doc = fitz.open(path_or_url)
            for pg in doc:
                pages.append(pg.get_text("text") or "")
            doc.close()
        elif lib == "pdfplumber":
            import pdfplumber  # type: ignore
            with pdfplumber.open(path_or_url) as pdf:
                for pg in pdf.pages:
                    pages.append(pg.extract_text() or "")
        else:  # pypdf / PyPDF2 share the API
            reader_mod = __import__(lib)
            reader = reader_mod.PdfReader(path_or_url)
            for pg in reader.pages:
                try:
                    pages.append(pg.extract_text() or "")
                except Exception:
                    pages.append("")
        chunks = []
        for i, ptxt in enumerate(pages, 1):
            ptxt = (ptxt or "").strip()
            if ptxt:
                for c in _paragraph_chunks(ptxt, section=f"page {i}"):
                    c["page"] = i
                    chunks.append(c)
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        meta["pages"] = len(pages)
        meta["title_hint"] = _title_from_path(path_or_url)
        # honest scan detection: pages exist but almost no extractable text.
        if pages and len(text.strip()) < max(20, 5 * len(pages)):
            meta["likely_scanned"] = True
            meta["note"] = "native-text extraction found little text; likely a scanned PDF — OCR (Wave 4) recommended"
        return _result(text=text, chunks=chunks, meta=meta)
    except Exception as e:
        # a real parse failure degrades to needs_dependency for the OCR seam, never a crash.
        return _result(status="needs_dependency", need="pdf-ocr",
                       meta={"format": fmt or "pdf", "source_ref": str(path_or_url),
                             "error": repr(e)[:200],
                             "note": "native-text PDF parse failed; route to OCR seam"})


# ---------------------------------------------------------------------------
# PLUGGABLE HEAVY parsers — registered behind the SAME interface. In Wave 1 they
# all degrade to needs_dependency unless their tool is already importable/available.
# They NEVER fabricate content. Wave 4 fills in the real implementations.
# ---------------------------------------------------------------------------
def _tool_importable(*mods: str) -> bool:
    for m in mods:
        try:
            __import__(m)
            return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# WAVE 4 ACTIVATIONS — the heavy parsers now RUN their tool when (and only when) the optional
# dependency is importable. Each activation returns a normalized _result on success, or None to
# signal "not activated here" (the caller then emits the honest needs_dependency seam). The two
# load-bearing promises hold exactly as in Wave 1: NEVER fabricate (an empty transcript/OCR is an
# honest empty result with a note, never invented text) and NEVER crash the spine (any failure —
# a missing binary behind an importable shim, a malformed file — degrades to needs_dependency).
# In an environment without the heavy libs (the default) these all return None and the seam below
# behaves precisely as before; a cert injects fakes to PROVE the activation path end-to-end.
#
# ACTIVATION IS OPT-IN. Per the Wave-1 doctrine ("even if the lib is present we do not block the
# spine on the binary"), the mere presence of a heavy lib does NOT auto-activate — loading a whisper
# model or shelling out to tesseract can be slow and can hit the network. Activation runs ONLY when
# the operator flips ANIMA_INTAKE_ACTIVATE_HEAVY=1. Default (unset) = the honest needs_dependency
# seam, no network, no blocking — exactly the Wave-1 behavior. The switch is the Wave-4 contract:
# the seam is ready; flip it to turn a present-but-dormant lib into a live parser.
_HEAVY_ENV = "ANIMA_INTAKE_ACTIVATE_HEAVY"


def _heavy_on() -> bool:
    """True iff the operator has opted into heavy-parser activation (ANIMA_INTAKE_ACTIVATE_HEAVY=1).
    Default off so a present heavy lib never silently blocks the spine or touches the network."""
    return os.environ.get(_HEAVY_ENV) == "1"


def _activate_ocr(path_or_url: str, meta: dict) -> Optional[dict]:
    """Real OCR via PIL + pytesseract when both import. Local files only (a URL would need a fetch
    first). Returns ok (possibly empty-with-note), needs_dependency (importable shim but the
    tesseract BINARY is missing / the image is unreadable), or None (libs absent -> Wave-1 seam)."""
    if not _heavy_on():
        return None
    try:
        from PIL import Image          # noqa: F401  (Pillow)
        import pytesseract
    except Exception:
        return None
    p = str(path_or_url)
    if p.startswith(("http://", "https://")):
        return None                    # OCR runs on a local image, not a URL
    try:
        with Image.open(p) as im:
            text = (pytesseract.image_to_string(im) or "").strip()
    except Exception as e:             # tesseract binary missing, or an unreadable image
        return _result(status="needs_dependency", need="ocr (tesseract binary not found)",
                       figures=[{"kind": "image", "ref": p}],
                       meta={**meta, "ocr_error": ("%r" % (e,))[:160]})
    chunks = [{"page": None, "section": "ocr", "text": text}] if text else []
    return _result(status="ok", text=text, chunks=chunks,
                   figures=[{"kind": "image", "ref": p}],
                   meta={**meta, "ocr": "pytesseract", "ocr_chars": len(text),
                         "note": "" if text else "OCR ran but found no text in the image"})


def _activate_stt(path_or_url: str, meta: dict, *, need_extra: str = "") -> Optional[dict]:
    """Real speech-to-text via openai-whisper or faster-whisper when importable. Returns ok with
    the transcript, needs_dependency (importable but the model/ffmpeg failed), or None (no STT lib
    -> Wave-1 seam). Whisper shells out to ffmpeg internally, so this also serves video files."""
    if not _heavy_on():
        return None
    p = str(path_or_url)
    if p.startswith(("http://", "https://")):
        return None
    # Prefer faster-whisper (lighter); fall back to reference whisper.
    try:
        from faster_whisper import WhisperModel  # type: ignore
        try:
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _info = model.transcribe(p)
            text = " ".join((seg.text or "").strip() for seg in segments).strip()
        except Exception as e:
            return _result(status="needs_dependency",
                           need="stt (faster-whisper model/ffmpeg unavailable)" + need_extra,
                           meta={**meta, "stt_error": ("%r" % (e,))[:160]})
        return _result(status="ok", text=text,
                       chunks=[{"page": None, "section": "transcript", "text": text}] if text else [],
                       meta={**meta, "stt": "faster-whisper", "transcript_chars": len(text),
                             "note": "" if text else "transcription ran but produced no speech text"})
    except Exception:
        pass
    try:
        import whisper  # type: ignore
    except Exception:
        return None
    try:
        model = whisper.load_model("base")
        text = (model.transcribe(p) or {}).get("text", "").strip()
    except Exception as e:
        return _result(status="needs_dependency", need="stt (whisper model/ffmpeg unavailable)" + need_extra,
                       meta={**meta, "stt_error": ("%r" % (e,))[:160]})
    return _result(status="ok", text=text,
                   chunks=[{"page": None, "section": "transcript", "text": text}] if text else [],
                   meta={**meta, "stt": "whisper", "transcript_chars": len(text),
                         "note": "" if text else "transcription ran but produced no speech text"})


def _youtube_id(s: str) -> str:
    """Extract the 11-char video id from a youtube URL (watch?v= / youtu.be/ / shorts/)."""
    from urllib.parse import urlparse, parse_qs
    try:
        u = urlparse(s)
    except Exception:
        return ""
    if "youtu.be" in (u.netloc or ""):
        return (u.path or "/").split("/")[1][:32] if len(u.path) > 1 else ""
    if "/shorts/" in (u.path or ""):
        return u.path.split("/shorts/", 1)[1].split("/")[0][:32]
    return (parse_qs(u.query or "").get("v", [""])[0])[:32]


def _activate_youtube(s: str, meta: dict) -> Optional[dict]:
    """Real YouTube transcript via youtube-transcript-api when importable. Returns ok with the
    joined transcript, needs_dependency (importable but transcripts disabled / none found), or
    None (lib absent -> Wave-1 seam). The transcript is DATA — never executed."""
    if not _heavy_on():
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception:
        return None
    vid = _youtube_id(s)
    if not vid:
        return None
    try:
        rows = YouTubeTranscriptApi.get_transcript(vid)
        text = " ".join((r.get("text") or "").strip() for r in rows).strip()
    except Exception as e:             # TranscriptsDisabled / NoTranscriptFound / network
        return _result(status="needs_dependency", need="youtube-transcript (none available)",
                       meta={**meta, "subkind": "youtube", "video_id": vid,
                             "transcript_error": ("%r" % (e,))[:160]})
    return _result(status="ok", text=text,
                   chunks=[{"page": None, "section": "transcript", "text": text}] if text else [],
                   meta={**meta, "subkind": "youtube", "video_id": vid,
                         "transcript": "youtube-transcript-api", "transcript_chars": len(text),
                         "note": "" if text else "the video has an empty transcript"})


def parse_image(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Image / screenshot -> text via OCR (Wave 4). Needs an OCR engine (pytesseract +
    tesseract, or a vision model). Absent the dependency, returns needs_dependency
    gracefully with the file recorded as a figure — never invents caption text."""
    meta = _base_meta(path_or_url, fmt or "image")
    meta["title_hint"] = _title_from_path(path_or_url)
    activated = _activate_ocr(path_or_url, meta)        # Wave 4: real OCR iff PIL+pytesseract import
    if activated is not None:
        return activated
    return _result(status="needs_dependency", need="ocr (pytesseract+tesseract)",
                   figures=[{"kind": "image", "ref": str(path_or_url)}], meta=meta)


def parse_audio(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Audio / long-form audio (.mp3/.m4a/.wav/.aac) -> transcript via the approved LOCAL STT
    (whisper / faster-whisper). Absent it, needs_dependency — never fabricates a transcript. (The
    dedicated audiobook container .m4b takes the chapter-aware intake_audio path; both are honest,
    local, and opt-in via ANIMA_INTAKE_ACTIVATE_HEAVY=1.)"""
    meta = _base_meta(path_or_url, fmt or "audio")
    meta["title_hint"] = _title_from_path(path_or_url)
    activated = _activate_stt(path_or_url, meta)        # Wave 4: real STT iff whisper imports
    if activated is not None:
        return activated
    return _result(status="needs_dependency", need="stt (whisper)", meta=meta)


def parse_video(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Video -> transcript via audio-track STT (Wave 4). Needs STT + an audio demux
    (ffmpeg). Absent them, needs_dependency — never fabricates a transcript."""
    meta = _base_meta(path_or_url, fmt or "video")
    meta["title_hint"] = _title_from_path(path_or_url)
    # Whisper demuxes the audio track via ffmpeg internally, so the same STT activation serves video.
    activated = _activate_stt(path_or_url, meta, need_extra=" + ffmpeg for the audio track")
    if activated is not None:
        return activated
    return _result(status="needs_dependency", need="stt+ffmpeg (whisper)", meta=meta)


def parse_audiobook(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Audiobook (.m4b) / long-form audio -> the HONEST local transcription pipeline
    (anima/intake_audio): safe ffprobe metadata (title/author/duration/codec/chapters — no decode,
    no key), ffmpeg decode of OPEN formats only (no DRM, no key), and the approved LOCAL STT
    (faster-whisper) into a real transcript chunked with timestamps. An undecodable file ->
    needs_dependency, never a fabricated transcript. Heavy + opt-in (ANIMA_INTAKE_ACTIVATE_HEAVY=1)."""
    from . import intake_audio
    return intake_audio.parse_longform_audio(path_or_url, fmt=fmt or "audiobook")


# --- safe web fetch (Wave 4) — stdlib urllib, SSRF-guarded, size + time capped ---------------
def _host_is_safe(host: str) -> bool:
    """True iff `host` resolves ONLY to public, routable addresses. Blocks private / loopback /
    link-local / reserved / multicast / unspecified — the SSRF guard for a user-pasted URL."""
    import ipaddress
    import socket
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    seen = False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            continue
        seen = True
        if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
                or addr.is_multicast or addr.is_unspecified):
            return False
    return seen


def web_fetch(url: str, *, timeout: float = 10.0, max_bytes: int = 3_000_000) -> tuple:
    """Fetch a public http(s) URL -> (html_text, content_type, error). SSRF-guarded (public hosts
    only; refuses a redirect to a private address), size + time capped, body treated as DATA.
    Returns (None, '', reason) on refusal/failure — the caller degrades to needs_dependency, never
    fabricates a page. ANIMA_INTAKE_OFFLINE=1 forces the offline seam (no socket) for hermetic
    tests / the gate."""
    if os.environ.get("ANIMA_INTAKE_OFFLINE") == "1":
        return None, "", "offline (ANIMA_INTAKE_OFFLINE=1): no fetch"
    import urllib.request
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return None, "", "only http/https URLs are fetched"
    if not p.hostname or not _host_is_safe(p.hostname):
        return None, "", "refused: host is private/loopback/unresolvable (SSRF guard)"

    class _SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            q = urlparse(newurl)
            if q.scheme not in ("http", "https") or not q.hostname or not _host_is_safe(q.hostname):
                return None                       # refuse a redirect to a non-web / private target
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    req = urllib.request.Request(url, headers={
        "User-Agent": "Vera-intake/1.0 (+local knowledge intake)",
        "Accept": "text/html,application/xhtml+xml,text/plain,*/*"})
    try:
        with urllib.request.build_opener(_SafeRedirect()).open(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "") or ""
            raw = r.read(max_bytes + 1)
            charset = r.headers.get_content_charset() or "utf-8"
    except Exception as e:
        return None, "", ("fetch failed: %r" % (e,))[:180]
    try:
        text = raw[:max_bytes].decode(charset, errors="replace")
    except Exception:
        text = raw[:max_bytes].decode("utf-8", errors="replace")
    return text, ctype, None


def parse_url(path_or_url: str, *, fmt: Optional[str] = None, _raw_html: Optional[str] = None) -> dict:
    """A URL -> readable article text via a network FETCH (Wave 4), then through the SAME hardened
    html extractor. YouTube URLs split out to the (still-pluggable) transcript parser. `_raw_html`
    lets a caller / hermetic test inject already-downloaded markup and skip the socket. The fetch is
    SSRF-guarded (public hosts only), size + time capped, and the page is treated as DATA — a line
    like 'ignore previous instructions' inside it is extracted, never obeyed. A YouTube link, a
    refused / failed fetch, or no markup returns needs_dependency — never a fabricated page."""
    s = str(path_or_url)
    meta = {"format": fmt or "url", "source_ref": s, "title_hint": s}
    if _is_youtube(s):
        meta["subkind"] = "youtube"
        activated = _activate_youtube(s, meta)          # Wave 4: real transcript iff the api imports
        if activated is not None:
            return activated
        return _result(status="needs_dependency", need="youtube-transcript-api", meta=meta)
    meta["subkind"] = "web_page"
    html = _raw_html
    if html is None:
        html, ctype, err = web_fetch(s)
        if html is None:
            return _result(status="needs_dependency", need="web-fetch", meta={**meta, "fetch_error": err})
        meta["content_type"] = ctype
        meta["fetched_bytes"] = len(html)
    # route the markup through the SAME hardened HTML extractor (prompt-injection safe).
    parsed = parse_html(s, fmt="html", _raw_html=html)
    if isinstance(parsed, dict) and isinstance(parsed.get("meta"), dict):
        parsed["meta"].update({"source_ref": s, "subkind": "web_page", "from_url": True})
        if meta.get("content_type"):
            parsed["meta"]["content_type"] = meta["content_type"]
    return parsed


def parse_archive(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """An archive (zip/tar/...) -> expand + recurse (Wave 4 wires the recursion). Zip/tar
    are stdlib, but safe extraction (zip-slip guards, size caps) + recursive intake is a
    later wave; Wave 1 declares the seam. Returns needs_dependency, never invents contents."""
    meta = _base_meta(path_or_url, fmt or "archive")
    meta["title_hint"] = _title_from_path(path_or_url)
    return _result(status="needs_dependency", need="archive-expand (recursive intake, Wave 4)", meta=meta)


def parse_folder(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """A folder is NOT parsed as one blob — the pipeline (``intake.ingest``) walks it and
    ingests each member. If a parser is ever called on a folder directly, it returns a
    structured 'directory' marker listing the member count, never fabricated text."""
    meta = _base_meta(path_or_url, fmt or "folder")
    try:
        members = [str(q) for q in sorted(Path(path_or_url).iterdir())]
    except OSError:
        members = []
    meta["members"] = len(members)
    meta["title_hint"] = Path(path_or_url).name
    return _result(status="ok", text="", chunks=[], meta={**meta, "is_directory": True, "member_paths": members[:500]})


# ---------------------------------------------------------------------------
# THE REGISTRY — the single seam. detect_format() picks the tag; PARSERS[tag] is
# the parser. Heavy/light are indistinguishable to the caller: same signature,
# same return shape. ``register(fmt, fn)`` lets Wave 4 swap a heavy parser in
# without touching the spine.
# ---------------------------------------------------------------------------
ParserFn = Callable[..., dict]

PARSERS: dict[str, ParserFn] = {
    "text": parse_text,
    "markdown": parse_markdown,
    "code": parse_code,
    "csv": parse_csv,
    "json": parse_json,
    "html": parse_html,
    "pdf": parse_pdf,
    "image": parse_image,
    "audio": parse_audio,
    "audiobook": parse_audiobook,
    "video": parse_video,
    "url": parse_url,
    "archive": parse_archive,
    "folder": parse_folder,
}

# Which formats are FULLY implemented with zero/light deps in Wave 1 (vs the pluggable
# heavy seam). PDF is conditional: light iff a PDF lib is importable.
LIGHT_FORMATS = frozenset({"text", "markdown", "code", "csv", "json", "html", "folder"})
HEAVY_FORMATS = frozenset({"image", "audio", "audiobook", "video", "url", "archive"})


def is_light(fmt: str) -> bool:
    """True if ``fmt`` is a fully-implemented light parser in Wave 1 (PDF counts as light
    only when a native-text PDF lib is importable)."""
    if fmt == "pdf":
        return _PDF_LIB is not None
    return fmt in LIGHT_FORMATS


def register(fmt: str, fn: ParserFn) -> None:
    """Register / replace the parser for ``fmt``. The activation seam: Wave 4 calls this
    to install a real OCR/STT/fetch parser in place of the Wave-1 degrading stub, with no
    change to ``intake.ingest``."""
    PARSERS[str(fmt)] = fn


def parse(path_or_url: str, *, fmt: Optional[str] = None) -> dict:
    """Detect (if ``fmt`` not given) and dispatch to the registered parser. ALWAYS returns
    a normalized dict — an unknown format degrades to the text parser, and any parser that
    somehow raises is caught here and reported as status='error' (the spine never dies)."""
    f = fmt or detect_format(path_or_url)
    fn = PARSERS.get(f) or PARSERS["text"]
    try:
        out = fn(path_or_url, fmt=f)
    except Exception as e:  # final backstop — a parser must never crash the spine
        return _result(status="error", meta={"format": f, "source_ref": str(path_or_url),
                                              "error": repr(e)[:200]})
    if not isinstance(out, dict):
        return _result(status="error", meta={"format": f, "error": "parser returned non-dict"})
    out.setdefault("status", "ok")
    out.setdefault("text", "")
    out.setdefault("chunks", [])
    out.setdefault("meta", {})
    out["meta"].setdefault("format", f)
    return out


# small accessor used by parse_html (kept out of the class body to avoid AttributeError
# when the extractor degraded); returns captured headings.
def _extractor_headings(ex: "_ArticleExtractor") -> list:
    return getattr(ex, "_headings", [])[:50]


# Provide the method the parser referenced, defined post-hoc for clarity.
def _headings_list(self: "_ArticleExtractor") -> list:
    return getattr(self, "_headings", [])[:50]


_ArticleExtractor.headings_list = _headings_list  # type: ignore[attr-defined]
