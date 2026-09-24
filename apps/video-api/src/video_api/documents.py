"""User-supplied source documents (PDF): extraction, storage and retention.

A document is uploaded once (``POST /v1/documents``), extracted synchronously
by the API and stored content-addressed under ``documents_root/<doc_id>/``:

    source.pdf        the original bytes
    document.json     title, sections (grounding text), figures (metadata)
    figures/fig_NN.png  each detected figure, rendered from the PDF page

Jobs reference it by ``document_id``; the worker turns the sections into
citable sources (``doc_NN``) and the figures into ``FigureScene`` media. The
renderer never reads the PDF: figures are plain PNGs copied into the job
workspace like any other resolved asset.

Figure detection is heuristic and layout-based (no ML): a caption block
starting with "Figure N" anchors a search for the adjacent graphics (embedded
images + clustered vector drawings) in the caption's column, which are then
rendered at high resolution. Figures without a recognisable caption are
skipped rather than guessed.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

DOCUMENT_ID_PATTERN = r"^doc_[0-9a-f]{24}$"
_DOCUMENT_ID_RE = re.compile(DOCUMENT_ID_PATTERN)
_FIGURE_ID_RE = re.compile(r"^fig_\d{2}$")
# Long side of a rendered figure. FigureScene zooms up to ~2.2x into a figure
# shown ~1000 px wide, so the source needs headroom to stay sharp.
_FIGURE_TARGET_PX = 2400
_MAX_FIGURES = 24
_MIN_TEXT_CHARS = 400


class DocumentError(ValueError):
    """The PDF cannot be used (encrypted, corrupt, scanned without text...)."""


class DocumentNotFound(LookupError):
    pass


class FigureRegion(BaseModel):
    id: str
    label: str
    # Normalised [x, y, w, h] in 0..1 image coordinates.
    box: list[float] = Field(min_length=4, max_length=4)


class DocumentFigure(BaseModel):
    id: str
    label: str
    caption: str = ""
    page: int
    path: str
    width: int
    height: int
    # Filled by the optional vision pass (pipeline/document_figures.py).
    description: str = ""
    regions: list[FigureRegion] = Field(default_factory=list)


class DocumentSection(BaseModel):
    id: str
    heading: str
    page: int
    text: str


class Document(BaseModel):
    id: str
    filename: str
    sha256: str
    created_at: str
    title: str
    page_count: int
    pages_analyzed: int
    char_count: int
    abstract: str = ""
    sections: list[DocumentSection] = Field(default_factory=list)
    figures: list[DocumentFigure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    # Vision model that produced figure descriptions/regions, if any.
    figures_analyzed_by: str | None = None


def is_document_id(value: str) -> bool:
    return bool(_DOCUMENT_ID_RE.match(value or ""))


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
class DocumentStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)

    def path(self, document_id: str) -> Path:
        if not is_document_id(document_id):
            raise DocumentNotFound(f"invalid document id: {document_id!r}")
        return self.root / document_id

    def exists(self, document_id: str) -> bool:
        try:
            return (self.path(document_id) / "document.json").is_file()
        except DocumentNotFound:
            return False

    def load(self, document_id: str) -> Document:
        manifest = self.path(document_id) / "document.json"
        if not manifest.is_file():
            raise DocumentNotFound(f"document not found: {document_id}")
        return Document.model_validate_json(manifest.read_text(encoding="utf-8"))

    def save(self, document: Document) -> None:
        """Atomic rewrite of document.json (the vision pass updates it)."""
        directory = self.path(document.id)
        tmp = directory / f".document.{os.getpid()}.{time.monotonic_ns()}.json"
        tmp.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(directory / "document.json")

    def figure_file(self, document_id: str, figure_id: str) -> Path:
        if not _FIGURE_ID_RE.match(figure_id or ""):
            raise DocumentNotFound(f"invalid figure id: {figure_id!r}")
        return self.path(document_id) / "figures" / f"{figure_id}.png"

    def touch(self, document_id: str) -> None:
        """Mark the document as used now (retention counts from last use)."""
        try:
            os.utime(self.path(document_id) / "document.json")
        except OSError:
            pass

    def ingest(self, data: bytes, filename: str, *, max_pages: int) -> Document:
        """Extract and store a PDF. Idempotent: the id is the content hash, so
        re-uploading the same file returns the stored extraction."""
        digest = hashlib.sha256(data).hexdigest()
        document_id = f"doc_{digest[:24]}"
        if self.exists(document_id):
            self.touch(document_id)
            return self.load(document_id)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f".staging-{document_id}-{os.getpid()}-{time.monotonic_ns()}"
        staging.mkdir(parents=True)
        try:
            (staging / "source.pdf").write_bytes(data)
            extracted = extract_pdf(data, staging, max_pages=max_pages)
            document = Document(
                id=document_id,
                filename=_safe_filename(filename),
                sha256=digest,
                created_at=datetime.now(timezone.utc).isoformat(),
                **extracted,
            )
            (staging / "document.json").write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
            final = self.root / document_id
            try:
                staging.rename(final)
            except OSError:
                # A concurrent upload of the same file won the race.
                if not self.exists(document_id):
                    raise
            return self.load(document_id)
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def gc_documents(root: Path | str, ttl_days: float) -> int:
    """Delete documents unused for *ttl_days* (mtime of document.json, bumped
    on every job that reads it). Never raises."""
    if ttl_days <= 0:
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    try:
        base = Path(root)
        if not base.is_dir():
            return 0
        for entry in base.iterdir():
            if entry.name.startswith(".staging-") and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                continue
            if not is_document_id(entry.name):
                continue
            manifest = entry / "document.json"
            stamp = manifest.stat().st_mtime if manifest.exists() else entry.stat().st_mtime
            if stamp < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
                logger.info("gc.document_removed document_id=%s", entry.name)
    except Exception:
        logger.exception("gc.documents.error")
    return removed


def _safe_filename(value: str) -> str:
    name = Path(value or "document.pdf").name
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip() or "document.pdf"
    return name[:160]


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
_CAPTION_RE = re.compile(
    r"^\s*(Figure|Fig\.|FIGURE|FIG\.|Figura|Abbildung)\s*(S?\d{1,3}[a-z]?|[IVX]{1,5})\s*([:.|]|—|–|-)?\s*"
)
_NUMBERED_HEADING_RE = re.compile(r"^(\d{1,2}(\.\d{1,2}){0,3}\.?|[IVX]{1,5}\.|[A-H](\.\d{1,2}){0,2}\.?)\s+\S")
_KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "related work", "related works", "preliminaries",
    "method", "methods", "methodology", "approach", "model", "model architecture", "experiments",
    "experimental setup", "evaluation", "results", "discussion", "conclusion", "conclusions",
    "limitations", "future work", "acknowledgments", "acknowledgements", "references", "bibliography",
    "appendix", "appendices", "summary", "résumé", "resume", "introduction générale", "méthode",
    "méthodes", "méthodologie", "résultats", "discussion", "conclusions", "remerciements",
    "références", "bibliographie", "annexe", "annexes", "materials and methods",
}
_REFERENCE_HEADINGS = {"references", "bibliography", "références", "bibliographie", "literature cited"}
_BOLD_FONT_RE = re.compile(r"bold|black|heavy|semibold|demi|cmbx|\.b$|-bx|medi", re.IGNORECASE)
_JUNK_TITLES = re.compile(r"^(microsoft word|untitled|document\d*$)|\.(dvi|pdf|tex|docx?)$", re.IGNORECASE)


@dataclass
class _Line:
    text: str
    bbox: tuple[float, float, float, float]
    size: float
    bold: bool


@dataclass
class _Block:
    page: int
    bbox: tuple[float, float, float, float]
    lines: list[_Line]

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines).strip()

    @property
    def size(self) -> float:
        weights: Counter[float] = Counter()
        for line in self.lines:
            weights[round(line.size, 1)] += len(line.text)
        return weights.most_common(1)[0][0] if weights else 0.0


def _rect_area(r: Any) -> float:
    return max(0.0, r.x1 - r.x0) * max(0.0, r.y1 - r.y0)


def _x_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _page_blocks(page: Any, page_index: int) -> list[_Block]:
    import pymupdf

    flags = (pymupdf.TEXTFLAGS_DICT | pymupdf.TEXT_DEHYPHENATE) & ~pymupdf.TEXT_PRESERVE_IMAGES
    # Native content order, not sort=True: LaTeX writes two-column pages
    # column by column, while a geometric sort interleaves the columns.
    data = page.get_text("dict", flags=flags)
    blocks: list[_Block] = []
    for raw in data.get("blocks", []):
        if raw.get("type") != 0:
            continue
        merged: list[_Line] = []
        for raw_line in raw.get("lines", []):
            direction = raw_line.get("dir") or (1, 0)
            if abs(direction[1]) > 0.1:  # rotated text: arXiv margin stamp, axis titles
                continue
            all_spans = raw_line.get("spans", [])
            # Whitespace-only spans carry the word spacing: keep them for the
            # text, ignore them for the size/weight statistics.
            spans = [s for s in all_spans if str(s.get("text") or "").strip()]
            if not spans:
                continue
            text = " ".join("".join(str(s.get("text") or "") for s in all_spans).split())
            chars = sum(len(str(s["text"]).strip()) for s in spans) or 1
            size = sum(float(s.get("size") or 0) * len(str(s["text"]).strip()) for s in spans) / chars
            bold = all(
                (int(s.get("flags") or 0) & 16) or _BOLD_FONT_RE.search(str(s.get("font") or ""))
                for s in spans
            )
            bbox = tuple(float(v) for v in raw_line["bbox"])
            # LaTeX often splits "1  Introduction" into two lines on one baseline.
            if merged and abs(merged[-1].bbox[3] - bbox[3]) < 1.5 and bbox[0] >= merged[-1].bbox[2] - 1:
                prev = merged[-1]
                merged[-1] = _Line(
                    text=f"{prev.text} {text}",
                    bbox=(prev.bbox[0], min(prev.bbox[1], bbox[1]), bbox[2], max(prev.bbox[3], bbox[3])),
                    size=max(prev.size, size),
                    bold=prev.bold and bool(bold),
                )
                continue
            merged.append(_Line(text=text, bbox=bbox, size=size, bold=bool(bold)))
        if merged:
            blocks.append(_Block(page=page_index, bbox=tuple(float(v) for v in raw["bbox"]), lines=merged))
    return blocks


def _page_graphics(page: Any) -> list[Any]:
    import pymupdf

    page_area = _rect_area(page.rect)
    rects: list[Any] = []
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if rect.width >= 16 and rect.height >= 16 and _rect_area(rect) < 0.9 * page_area:
            rects.append(rect)
    try:
        clusters = page.cluster_drawings(x_tolerance=6, y_tolerance=6)
    except Exception as exc:  # pragma: no cover - defensive against odd PDFs
        logger.warning("document.drawings.failed page=%s error=%s", page.number, exc)
        clusters = []
    for rect in clusters:
        rect = pymupdf.Rect(rect) & page.rect
        if rect.is_empty or rect.width < 3 or rect.height < 3:
            continue  # lone rules: table lines, footnote separators
        if _rect_area(rect) >= 0.85 * page_area:
            continue  # page background / frame
        rects.append(rect)
    return rects


def _is_body(block: _Block, body_size: float, page_width: float) -> bool:
    width = block.bbox[2] - block.bbox[0]
    return (
        abs(block.size - body_size) <= 0.8
        and len(block.text) >= 80
        and width >= 0.3 * page_width
    )


def _column_span(caption: tuple[float, float, float, float], width: float) -> tuple[float, float]:
    x0, _, x1, _ = caption
    if x0 < 0.42 * width and x1 > 0.58 * width:
        return 0.0, width
    if x1 <= 0.58 * width:
        return 0.0, 0.5 * width + 12
    return 0.5 * width - 12, width


def _figure_region(
    page: Any,
    caption: _Block,
    graphics: list[Any],
    blocks: list[_Block],
    body_size: float,
    captions: list[_Block],
) -> Any | None:
    import pymupdf

    width, height = page.rect.width, page.rect.height
    _, cy0, _, cy1 = caption.bbox
    span0, span1 = _column_span(caption.bbox, width)
    in_column = [
        g for g in graphics
        if g.width > 0 and _x_overlap(g.x0, g.x1, span0, span1) >= 0.6 * g.width
    ]
    body = [b for b in blocks if b is not caption and _is_body(b, body_size, width)
            and _x_overlap(b.bbox[0], b.bbox[2], span0, span1) > 0]
    others = [c for c in captions if c is not caption]

    def separated(y_top: float, y_bottom: float) -> bool:
        """A paragraph or another caption lies between these two y values."""
        for b in body + others:
            if b.bbox[1] >= y_top - 2 and b.bbox[3] <= y_bottom + 2:
                return True
        return False

    above = [g for g in in_column if g.y1 <= cy0 + 3 and g.y1 >= cy0 - 60 and not separated(g.y1, cy0)]
    direction = "above"
    seed = above
    if not seed:
        seed = [g for g in in_column if g.y0 >= cy1 - 3 and g.y0 <= cy1 + 60 and not separated(cy1, g.y0)]
        direction = "below"
    if not seed:
        return None
    region = pymupdf.Rect(seed[0])
    for g in seed[1:]:
        region |= g
    changed = True
    while changed:
        changed = False
        for g in in_column:
            if region.contains(g):
                continue
            if direction == "above":
                if g.y0 >= cy0:
                    continue
                gap = region.y0 - g.y1
                if gap > 28 or (gap > 0 and separated(g.y1, region.y0)):
                    if not (g.intersects(region)):
                        continue
            else:
                if g.y1 <= cy1:
                    continue
                gap = g.y0 - region.y1
                if gap > 28 or (gap > 0 and separated(region.y1, g.y0)):
                    if not (g.intersects(region)):
                        continue
            region |= g
            changed = True
    # Pull in the figure's own text (axis labels, legends, box labels).
    skip_ids = {id(b) for b in body} | {id(c) for c in captions}
    for _ in range(2):
        grown = pymupdf.Rect(region) + (-10, -10, 10, 10)
        for b in blocks:
            if id(b) in skip_ids:
                continue
            rect = pymupdf.Rect(b.bbox)
            inside = _rect_area(rect & grown)
            if inside and inside >= 0.5 * _rect_area(rect):
                region |= rect
    region = (region + (-4, -4, 4, 4)) & page.rect
    if direction == "above":
        region.y1 = min(region.y1, cy0 - 1)
    else:
        region.y0 = max(region.y0, cy1 + 1)
    if region.width < 60 or region.height < 40 or _rect_area(region) < 0.012 * width * height:
        return None
    return region


def _trim_whitespace(page: Any, region: Any, margin: float = 6.0) -> Any:
    """Shrink *region* to its inked content (a cheap low-res grey probe)."""
    import pymupdf

    dpi = 48
    probe = page.get_pixmap(clip=region, dpi=dpi, alpha=False, colorspace=pymupdf.csGRAY)
    width, height, stride, samples = probe.width, probe.height, probe.stride, probe.samples
    if width < 2 or height < 2:
        return region
    ink = 242
    rows = [y for y in range(height) if min(samples[y * stride:y * stride + width]) < ink]
    cols = [x for x in range(width) if min(samples[x:height * stride:stride]) < ink]
    if not rows or not cols:
        return region
    scale = 72 / dpi
    trimmed = pymupdf.Rect(
        region.x0 + cols[0] * scale - margin,
        region.y0 + rows[0] * scale - margin,
        region.x0 + (cols[-1] + 1) * scale + margin,
        region.y0 + (rows[-1] + 1) * scale + margin,
    )
    return trimmed & region


def _caption_text(caption: _Block, blocks: list[_Block]) -> str:
    text = caption.text
    # A short first block is usually continued by the next block right below.
    index = next(i for i, b in enumerate(blocks) if b is caption)
    y_bottom = caption.bbox[3]
    for nxt in blocks[index + 1:index + 3]:
        if len(text) >= 400:
            break
        if 0 <= nxt.bbox[1] - y_bottom <= 6 and abs(nxt.size - caption.size) <= 0.6:
            text = f"{text} {nxt.text}"
            y_bottom = nxt.bbox[3]
        else:
            break
    return " ".join(text.split())[:700]


def _is_heading(line: _Line, body_size: float, title_size: float, page: int) -> bool:
    text = line.text.strip()
    if not (3 <= len(text) <= 90) or text.endswith((",", ";")):
        return False
    if page == 0 and line.size >= title_size * 0.95:
        return False  # the title itself
    words = re.sub(r"^[\dIVX.\s]+", "", text).strip().lower().rstrip(".:")
    known = words in _KNOWN_HEADINGS
    numbered = bool(_NUMBERED_HEADING_RE.match(text))
    larger = line.size >= body_size * 1.12
    if text.endswith(".") and not known and not numbered:
        return False
    if larger and (numbered or known or line.size >= body_size * 1.3):
        return True
    return line.bold and (known or (numbered and len(text.split()) <= 12 and not text[-1].isdigit()))


def _document_title(doc: Any, first_page_blocks: list[_Block], page_height: float) -> tuple[str, float]:
    meta_title = str((doc.metadata or {}).get("title") or "").strip()
    candidates = [
        line
        for block in first_page_blocks
        if block.bbox[1] < 0.5 * page_height
        for line in block.lines
        if len(line.text) >= 3
    ]
    title_size = max((line.size for line in candidates), default=0.0)
    visual = " ".join(line.text for line in candidates if line.size >= title_size - 0.5).strip()
    if meta_title and len(meta_title) >= 8 and not _JUNK_TITLES.search(meta_title):
        return meta_title[:200], title_size
    return (visual[:200] or "Document"), title_size


def _repeated_margin_lines(pages: list[list[_Block]], heights: list[float]) -> set[str]:
    counts: Counter[str] = Counter()
    for blocks, height in zip(pages, heights):
        seen: set[str] = set()
        for block in blocks:
            if block.bbox[1] > 0.08 * height and block.bbox[3] < 0.92 * height:
                continue
            key = re.sub(r"\d+", "#", block.text.lower())[:80]
            if key not in seen:
                seen.add(key)
                counts[key] += 1
    threshold = max(3, len(pages) // 3)
    return {key for key, count in counts.items() if count >= threshold}


def extract_pdf(data: bytes, out_dir: Path, *, max_pages: int) -> dict[str, Any]:
    """Extract grounding text and figures. Writes figure PNGs under
    ``out_dir/figures`` and returns the fields of :class:`Document`."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentError(f"unreadable PDF: {exc}") from exc
    with doc:
        if doc.needs_pass:
            raise DocumentError("the PDF is password-protected")
        page_count = doc.page_count
        if page_count == 0:
            raise DocumentError("the PDF has no pages")
        analyzed = min(page_count, max(1, max_pages))
        warnings: list[str] = []
        if analyzed < page_count:
            warnings.append(f"only the first {analyzed} of {page_count} pages were analysed")

        pages = [doc[i] for i in range(analyzed)]
        page_blocks = [_page_blocks(page, i) for i, page in enumerate(pages)]
        sizes: Counter[float] = Counter()
        for blocks in page_blocks:
            for block in blocks:
                for line in block.lines:
                    sizes[round(line.size, 1)] += len(line.text)
        total_chars = sum(sizes.values())
        if total_chars < _MIN_TEXT_CHARS:
            raise DocumentError(
                "the PDF has no extractable text (scanned document?) — OCR is not supported"
            )
        body_size = sizes.most_common(1)[0][0]
        title, title_size = _document_title(doc, page_blocks[0], pages[0].rect.height)
        margin_noise = _repeated_margin_lines(page_blocks, [p.rect.height for p in pages])

        # Figures first: their captions and inner labels are excluded from the text.
        figures_dir = out_dir / "figures"
        figures_dir.mkdir(parents=True, exist_ok=True)
        figures: list[dict[str, Any]] = []
        excluded: set[int] = set()
        seen_labels: set[str] = set()
        for index, page in enumerate(pages):
            blocks = page_blocks[index]
            captions = [b for b in blocks if _CAPTION_RE.match(b.lines[0].text)]
            if not captions:
                continue
            graphics = _page_graphics(page)
            for caption in captions:
                match = _CAPTION_RE.match(caption.lines[0].text)
                assert match is not None
                label = f"Figure {match.group(2)}"
                region = _figure_region(page, caption, graphics, blocks, body_size, captions)
                if region is None:
                    continue
                # "Figure 3 shows ..." in running text is not a caption; a real
                # caption has punctuation after the number or sits on a graphic.
                if not match.group(3) and len(caption.text) > 200:
                    continue
                excluded.add(id(caption))
                for b in blocks:
                    rect = pymupdf.Rect(b.bbox)
                    if _rect_area(rect & region) >= 0.6 * max(_rect_area(rect), 1e-6):
                        excluded.add(id(b))
                if label in seen_labels or len(figures) >= _MAX_FIGURES:
                    continue
                seen_labels.add(label)
                region = _trim_whitespace(page, region)
                figure_id = f"fig_{len(figures) + 1:02d}"
                dpi = max(120, min(360, round(_FIGURE_TARGET_PX * 72 / max(region.width, region.height))))
                pixmap = page.get_pixmap(clip=region, dpi=dpi, alpha=False)
                pixmap.save(str(figures_dir / f"{figure_id}.png"))
                figures.append(
                    {
                        "id": figure_id,
                        "label": label,
                        "caption": _caption_text(caption, blocks),
                        "page": index + 1,
                        "path": f"figures/{figure_id}.png",
                        "width": pixmap.width,
                        "height": pixmap.height,
                    }
                )

        # Sections: split the running text on detected headings.
        sections: list[dict[str, Any]] = []
        current: dict[str, Any] = {"heading": "", "page": 1, "parts": []}
        skipping_references = False

        def flush() -> None:
            text = " ".join(" ".join(current["parts"]).split())
            if text or current["heading"]:
                sections.append({"heading": current["heading"], "page": current["page"], "text": text})

        for index, blocks in enumerate(page_blocks):
            for block in blocks:
                if id(block) in excluded:
                    continue
                if re.sub(r"\d+", "#", block.text.lower())[:80] in margin_noise:
                    continue
                if block.text.strip().isdigit():
                    continue
                for line in block.lines:
                    if _is_heading(line, body_size, title_size, index):
                        name = re.sub(r"^[\dIVX.\s]+", "", line.text).strip().lower().rstrip(".:")
                        if name in _REFERENCE_HEADINGS:
                            flush()
                            skipping_references = True
                            current = {"heading": line.text, "page": index + 1, "parts": []}
                            continue
                        if skipping_references and not (
                            name.startswith(("appendix", "annexe")) or re.match(r"^[A-H](\.\d+)*\.?\s", line.text)
                        ):
                            continue
                        if not skipping_references:
                            flush()
                        skipping_references = False
                        current = {"heading": line.text, "page": index + 1, "parts": []}
                        continue
                    if not skipping_references:
                        current["parts"].append(line.text)
                if not skipping_references:
                    current["parts"].append("\n")
        if not skipping_references:
            flush()

        # Drop the pre-abstract front matter (title, authors, affiliations).
        cleaned = [s for s in sections if s["text"] and not (s["heading"] == "" and s["page"] == 1 and len(sections) > 1)]
        abstract = ""
        for section in cleaned:
            if re.sub(r"^[\dIVX.\s]+", "", section["heading"]).strip().lower().rstrip(".:") in {"abstract", "résumé", "resume", "summary"}:
                abstract = section["text"][:3000]
                break
        if not abstract:
            for block in page_blocks[0]:
                if block.text.lower().startswith(("abstract", "résumé")):
                    abstract = re.sub(r"^(abstract|résumé)[\s.:—–-]*", "", block.text, flags=re.IGNORECASE)[:3000]
                    break
        if len([s for s in cleaned if s["heading"]]) < 2:
            warnings.append("no section headings detected; the text was split by pages")
            cleaned = _chunk_by_pages(page_blocks, excluded, margin_noise)
        char_count = sum(len(s["text"]) for s in cleaned)
        return {
            "title": title,
            "page_count": page_count,
            "pages_analyzed": analyzed,
            "char_count": char_count,
            "abstract": abstract,
            "sections": [
                {"id": f"doc_{i:02d}", "heading": s["heading"] or f"Page {s['page']}", "page": s["page"], "text": s["text"]}
                for i, s in enumerate(cleaned[:60], start=1)
            ],
            "figures": figures,
            "warnings": warnings + ([] if figures else ["no captioned figure was detected"]),
        }


def _chunk_by_pages(page_blocks: list[list[_Block]], excluded: set[int], noise: set[str], size: int = 4000) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    start = 1
    for index, blocks in enumerate(page_blocks):
        for block in blocks:
            if id(block) in excluded or re.sub(r"\d+", "#", block.text.lower())[:80] in noise:
                continue
            buffer.append(block.text)
        if sum(len(part) for part in buffer) >= size or index == len(page_blocks) - 1:
            text = " ".join(" ".join(buffer).split())
            if text:
                heading = f"Pages {start}-{index + 1}" if index + 1 > start else f"Page {start}"
                chunks.append({"heading": heading, "page": start, "text": text})
            buffer, start = [], index + 2
    return chunks


# --------------------------------------------------------------------------- #
# Prompt context
# --------------------------------------------------------------------------- #
def budget_sections(sections: list[DocumentSection], budget_chars: int) -> list[tuple[DocumentSection, str]]:
    """Fit the sections into *budget_chars* by water-filling: short sections
    stay whole, long ones share what is left equally (truncated at a sentence
    boundary when possible)."""
    remaining = max(0, budget_chars)
    pending = sorted(range(len(sections)), key=lambda i: len(sections[i].text))
    allowance: dict[int, int] = {}
    while pending:
        share = remaining // len(pending)
        index = pending[0]
        need = len(sections[index].text)
        if need <= share:
            allowance[index] = need
            remaining -= need
            pending.pop(0)
            continue
        for index in pending:
            allowance[index] = share
        break
    out: list[tuple[DocumentSection, str]] = []
    for index, section in enumerate(sections):
        limit = allowance.get(index, 0)
        text = section.text
        if len(text) > limit:
            cut = text[:limit]
            period = cut.rfind(". ")
            text = (cut[: period + 1] if period > limit * 0.6 else cut).rstrip() + " […]"
        if limit > 0:
            out.append((section, text))
    return out
