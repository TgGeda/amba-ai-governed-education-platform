from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import hashlib
import html
import json
from math import ceil
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
import zipfile

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from amba_ai.learning.domain_registry import domain_registry
from amba_ai.logger import logger
from amba_ai.models.schemas import Flashcard, MCQ

SCHEMA_VERSION = "ambaai.document-agnostic-learning-pack.v7.0.0"

MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 30_000
MAX_NOTES_CHARS = 100_000
MAX_FLASHCARDS = 50
MAX_MCQS = 50
MAX_BUNDLE_BYTES = 500 * 1024 * 1024
MAX_ARTIFACTS = 100

_GENERIC_SOURCES = {
    "",
    "uploaded learning material",
    "local study material",
    "document",
    "unknown",
    "none",
    "source unavailable",
}


@dataclass(frozen=True, slots=True)
class LearningPackArtifact:
    kind: str
    path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class LearningPackResult:
    document_id: int
    source: str
    output_dir: str
    bundle_path: str
    artifacts: list[LearningPackArtifact] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [asdict(item) for item in self.artifacts]
        return data


class AtomicFileWriter:
    @staticmethod
    def write_text(path: Path, content: str, encoding: str = "utf-8") -> Path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            dir=str(target.parent),
            prefix=f".{target.stem}.",
            suffix=".tmp",
            delete=False,
            mode="w",
            encoding=encoding,
        )
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            os.replace(tmp.name, target)
            return target
        except Exception:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            raise

    @staticmethod
    def temp_for(path: Path) -> Path:
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=f".{target.stem}.",
            suffix=".tmp",
        )
        os.close(fd)
        return Path(name)


def retry_io(attempts: int = 3, backoff: float = 0.5) -> Callable:
    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_err = None
            current_delay = backoff
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except (OSError, IOError) as exc:
                    last_err = exc
                    if attempt == attempts:
                        break
                    time.sleep(current_delay)
                    current_delay *= 2
            raise last_err or RuntimeError("IO operation failed after retries")
        return wrapper
    return decorator


def _get(obj: Any, *names: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        for name in names:
            val = obj.get(name)
            if val not in (None, "", [], (), {}):
                return val
        return default
    for name in names:
        val = getattr(obj, name, None)
        if val not in (None, "", [], (), {}):
            return val
    return default


def _clean(value: Any) -> str:
    text = str(value or "").replace("\\n", "\n")
    text = re.sub(r"<!--\s*ambaai\.[\s\S]*?-->", "", text, flags=re.IGNORECASE)
    text = re.sub(r"&lt;!--\s*ambaai\.[\s\S]*?--&gt;", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?im)^\s*(?:Detected\s+Topic|Topic)\s*:\s*", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _title(value: Any) -> str:
    text = _clean(value)
    if not text:
        return "Learning Pack"
    if "/" in text or "\\" in text or Path(text).suffix:
        text = Path(text).stem
    text = re.sub(r"[_-]+", " ", text).strip()
    words = [
        w.upper() if len(w) <= 4 and w.isalpha() and w.lower() in {"ai", "api", "ui", "ux", "json", "sql", "http", "dna", "rna", "cpu"} else w.capitalize()
        for w in text.split()
    ]
    return (" ".join(words) or "Learning Pack")[:MAX_TITLE_CHARS]


def resolve_source(document: Any, metadata: Mapping[str, Any] | None = None) -> str:
    meta = metadata or {}
    candidates = (
        meta.get("original_filename"),
        meta.get("filename"),
        meta.get("original_path"),
        meta.get("source_path"),
        meta.get("stored_path"),
        meta.get("source_name"),
        meta.get("source"),
        _get(document, "original_filename"),
        _get(document, "source_name"),
    )
    for c in candidates:
        if c:
            name = Path(str(c)).name.strip()
            if name.lower() not in _GENERIC_SOURCES and not re.fullmatch(r"document\s*\d+", name, re.IGNORECASE):
                return name
    res = _title(_get(document, "title", default=""))
    return res if res.lower() not in _GENERIC_SOURCES else "Source unavailable"


def _safe_stem(text: str) -> str:
    val = re.sub(r"[^A-Za-z0-9._-]+", "_", str(text or "study_pack")).strip("._")
    return val[:80] or "study_pack"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(kind: str, path: Path) -> LearningPackArtifact:
    return LearningPackArtifact(
        kind=kind,
        path=str(path),
        sha256=_sha256(path),
        size_bytes=path.stat().st_size,
    )


def _validate_learning_inputs(
    title: str,
    summary: str,
    notes: str,
    flashcards: Sequence[Any],
    mcqs: Sequence[Any],
) -> tuple[str, str, str, list[Flashcard], list[MCQ]]:
    valid_title = _title(title)
    valid_summary = _clean(summary)[:MAX_SUMMARY_CHARS]
    valid_notes = _clean(notes)[:MAX_NOTES_CHARS]

    clean_cards: list[Flashcard] = []
    for c in flashcards[:MAX_FLASHCARDS]:
        q = _clean(_get(c, "question", "front", default=""))
        a = _clean(_get(c, "answer", "back", default=""))
        ref = _clean(_get(c, "source_ref", "source", default=""))
        if len(q) >= 5 and len(a) >= 2:
            clean_cards.append(Flashcard(question=q, answer=a, source_ref=ref or None))

    clean_mcqs: list[MCQ] = []
    for m in mcqs[:MAX_MCQS]:
        q = _clean(_get(m, "question", default=""))
        opts = [_clean(x) for x in list(_get(m, "choices", default=[]))[:4]]
        ans = _clean(_get(m, "correct_answer", default=""))
        exp = _clean(_get(m, "explanation", default=""))
        ref = _clean(_get(m, "source_ref", "source", default=""))
        if len(q) >= 8 and len(opts) == 4 and ans in opts and exp:
            clean_mcqs.append(
                MCQ(
                    question=q,
                    choices=opts,
                    correct_answer=ans,
                    explanation=exp,
                    source_ref=ref or None,
                )
            )

    return valid_title, valid_summary, valid_notes, clean_cards, clean_mcqs


def _register_font() -> str:
    candidates = [
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                pdfmetrics.registerFont(TTFont("AmbaBody", str(p)))
                return "AmbaBody"
            except Exception:
                continue
    return "Helvetica"


class _NumberedCanvas(pdf_canvas.Canvas):
    def __init__(self, *args: Any, source: str = "", title: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self._source = source
        self._title = title

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        width, height = A4
        page = self._pageNumber
        self.saveState()
        if page > 1:
            self.setFillColor(HexColor("#0369A1"))
            self.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)
            self.setFillColor(colors.white)
            self.setFont("Helvetica-Bold", 7.5)
            self.drawString(18 * mm, height - 5.2 * mm, self._title[:72])
        self.setStrokeColor(HexColor("#CBD5E1"))
        self.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        self.setFillColor(HexColor("#64748B"))
        self.setFont("Helvetica", 7)
        self.drawString(18 * mm, 9 * mm, f"AmbaAI Learning Pack | Grounded in {self._source}")
        self.drawRightString(width - 18 * mm, 9 * mm, f"Page {page} of {total}")
        self.restoreState()


def _canvas_factory(source: str, title: str):
    def factory(*args: Any, **kwargs: Any) -> _NumberedCanvas:
        return _NumberedCanvas(*args, source=source, title=title, **kwargs)
    return factory


def _pdf_styles() -> dict[str, ParagraphStyle]:
    font = _register_font()
    base = getSampleStyleSheet()
    return {
        "cover_brand": ParagraphStyle("CoverBrand", parent=base["BodyText"], fontName=font, fontSize=12, leading=15, textColor=HexColor("#0284C7"), alignment=TA_CENTER, spaceAfter=8),
        "cover_title": ParagraphStyle("CoverTitle", parent=base["Title"], fontName=font, fontSize=24, leading=28, textColor=HexColor("#0F172A"), alignment=TA_CENTER, spaceAfter=8),
        "cover_subtitle": ParagraphStyle("CoverSubtitle", parent=base["BodyText"], fontName=font, fontSize=11, leading=16, textColor=HexColor("#64748B"), alignment=TA_CENTER, spaceAfter=14),
        "section": ParagraphStyle("Section", parent=base["Heading1"], fontName=font, fontSize=16, leading=20, textColor=HexColor("#075985"), spaceBefore=10, spaceAfter=8, keepWithNext=True),
        "subsection": ParagraphStyle("Subsection", parent=base["Heading2"], fontName=font, fontSize=12.5, leading=16, textColor=HexColor("#0F766E"), spaceBefore=8, spaceAfter=5, keepWithNext=True),
        "minor": ParagraphStyle("Minor", parent=base["Heading3"], fontName=font, fontSize=10.5, leading=14, textColor=HexColor("#7C3AED"), spaceBefore=6, spaceAfter=4, keepWithNext=True),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=13.6, textColor=HexColor("#1E293B"), spaceAfter=5),
        "bullet": ParagraphStyle("Bullet", parent=base["BodyText"], fontName=font, fontSize=9.3, leading=13.2, leftIndent=13, firstLineIndent=-7, textColor=HexColor("#1E293B"), spaceAfter=3),
        "code": ParagraphStyle("Code", parent=base["Code"], fontName="Courier", fontSize=8, leading=11, leftIndent=0, rightIndent=0, borderColor=HexColor("#CBD5E1"), borderWidth=0.5, borderPadding=7, backColor=HexColor("#F1F5F9"), textColor=HexColor("#4C1D95"), spaceBefore=4, spaceAfter=7),
        "caption": ParagraphStyle("Caption", parent=base["BodyText"], fontName=font, fontSize=7.8, leading=10.5, textColor=HexColor("#64748B"), spaceAfter=4),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontName=font, fontSize=9.5, leading=13.5, textColor=HexColor("#0F172A"), backColor=HexColor("#E0F2FE"), borderColor=HexColor("#38BDF8"), borderWidth=0.7, borderPadding=8, spaceBefore=6, spaceAfter=8),
        "quiz": ParagraphStyle("Quiz", parent=base["BodyText"], fontName=font, fontSize=9.3, leading=13, textColor=HexColor("#0F172A"), spaceAfter=3),
    }


def _pdf_inline(text: str) -> str:
    escaped = html.escape(str(text or ""))
    escaped = re.sub(r"`([^`]+)`", r'<font name="Courier" color="#1E293B" backColor="#F0F4F8"> \1 </font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", escaped)
    return escaped


def _markdown_story(markdown: str, styles: dict[str, ParagraphStyle], *, suppress_title: str = "") -> list[Any]:
    text = _clean(markdown)
    story: list[Any] = []
    first_heading = False

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level, name = len(heading.group(1)), heading.group(2).strip()
            if not first_heading and suppress_title and name.casefold() == suppress_title.casefold():
                first_heading = True
                continue
            first_heading = True
            style = styles["section"] if level <= 2 else styles["subsection"] if level == 3 else styles["minor"]
            story.extend([CondPageBreak(16 * mm), Paragraph(_pdf_inline(name), style)])
            continue
        if stripped.startswith(("- ", "* ")):
            content = stripped[2:].strip()
            story.append(Paragraph("- " + _pdf_inline(content), styles["bullet"]))
            continue
        story.append(Paragraph(_pdf_inline(stripped), styles["body"]))
    return story


def _flashcard_cell(index: int, card: Any, styles: dict[str, ParagraphStyle], source: str) -> Table:
    q = ParagraphStyle("FCQ", parent=styles["body"], fontSize=9.5, leading=11, textColor=HexColor("#075985"), spaceAfter=0)
    a = ParagraphStyle("FCA", parent=styles["body"], fontSize=8.5, leading=10, textColor=HexColor("#1E293B"), spaceAfter=0)
    c = ParagraphStyle("FCS", parent=styles["caption"], fontSize=6.5, leading=8, textColor=HexColor("#64748B"), spaceAfter=0)
    question = Paragraph(f"<b>{index}. {_pdf_inline(_get(card, 'question', 'front', default=''))}</b>", q)
    answer = Paragraph(_pdf_inline(_get(card, "answer", "back", default="")), a)
    citation = Paragraph(f"Source: {_pdf_inline(_get(card, 'source_ref', 'source', default=source))}", c)
    cell = Table([[question], [answer], [citation]], colWidths=[82.5 * mm], splitByRow=1)
    cell.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#E0F2FE")),
            ("BACKGROUND", (0, 1), (-1, -1), HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.45, HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    return cell


def _choice_row(letter: str, text: str, styles: dict[str, ParagraphStyle]) -> Table:
    badge_style = ParagraphStyle("ChoiceBadge", parent=styles["body"], fontName="Helvetica-Bold", fontSize=8.3, leading=9.5, alignment=TA_CENTER, textColor=colors.white)
    text_style = ParagraphStyle("OptionText", parent=styles["body"], fontSize=8.9, leading=10.2, textColor=HexColor("#1E293B"))
    check_style = ParagraphStyle("OptionCheck", parent=styles["body"], fontSize=9, leading=10, alignment=TA_CENTER, textColor=HexColor("#64748B"))
    table = Table([[Paragraph(letter, badge_style), Paragraph(_pdf_inline(text), text_style), Paragraph("[ ]", check_style)]], colWidths=[9 * mm, 150 * mm, 10 * mm])
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), HexColor("#2563EB")),
            ("BACKGROUND", (1, 0), (-1, 0), HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 0.45, HexColor("#D8DEE7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    return table


def _answer_reasoning(mcq: Any, styles: dict[str, ParagraphStyle], domain: str | None) -> list[Any]:
    question = str(_get(mcq, "question", default=""))
    correct = str(_get(mcq, "correct_answer", default=""))
    explanation = str(_get(mcq, "explanation", default=""))
    choices = list(_get(mcq, "choices", default=[]))[:4]

    plugin = domain_registry.resolve(question) if domain_registry else None
    result: list[Any] = [
        Paragraph(f"<b>Why this is correct:</b> {_pdf_inline(explanation)}", styles["body"]),
        Paragraph("<b>Why the alternatives are incorrect:</b>", styles["minor"]),
    ]

    for ch in choices:
        if ch.strip().lower() == correct.strip().lower():
            continue
        if plugin and hasattr(plugin, "get_alternative_distractor_rationale"):
            rationale = plugin.get_alternative_distractor_rationale(question, str(ch), correct)
        else:
            rationale = "This statement does not align with the validated evidence in the curriculum source."
        result.append(Paragraph(f"- <b>{_pdf_inline(ch)}:</b> {_pdf_inline(rationale)}", styles["bullet"]))

    return result


@retry_io()
def create_study_guide_pdf(
    path: Path,
    title: str,
    source: str,
    summary: str,
    notes: str,
    flashcards: list[Any],
    mcqs: list[Any],
    *,
    domain: str | None = None,
) -> Path:
    target_path = Path(path).resolve()
    tmp_path = AtomicFileWriter.temp_for(target_path)
    styles = _pdf_styles()
    width, height = A4

    doc = BaseDocTemplate(
        str(tmp_path),
        pagesize=A4,
        title=title,
        author="AmbaAI",
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        pageCompression=1,
    )
    cover_frame = Frame(18 * mm, 18 * mm, width - 36 * mm, height - 36 * mm, id="cov", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    body_frame = Frame(18 * mm, 18 * mm, width - 36 * mm, height - 40 * mm, id="bod", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="Cover", frames=[cover_frame]), PageTemplate(id="Body", frames=[body_frame])])

    story: list[Any] = [
        Spacer(1, 6 * mm),
        Paragraph("AmbaAI PROFESSIONAL LEARNING PACK", styles["cover_brand"]),
        Paragraph(_pdf_inline(title), styles["cover_title"]),
        Paragraph("Grounded study guide, revision cards, knowledge check, and answer key", styles["cover_subtitle"]),
        Paragraph("Understand the mechanism, practise active recall, complete the assessment, and return to the source for deeper evidence.", styles["callout"]),
    ]
    metadata = Table(
        [["SOURCE", "FORMAT", "FLASHCARDS", "QUIZ"], [source, "A4 learning pack", str(len(flashcards)), str(len(mcqs))]],
        colWidths=[65 * mm, 45 * mm, 32 * mm, 32 * mm],
        repeatRows=1,
    )
    metadata.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (-1, 1), HexColor("#F8FAFC")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.6, HexColor("#94A3B8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.extend([
        metadata,
        Spacer(1, 3 * mm),
        Paragraph("Learning path", styles["subsection"]),
        Paragraph("1. Read the summary.  2. Explore the notes.  3. Recall with flashcards.  4. Complete the quiz.  5. Review explanations.", styles["body"]),
        Spacer(1, 2 * mm),
        Paragraph("1. Executive Summary", styles["section"]),
        HRFlowable(width="100%", thickness=0.7, color=HexColor("#38BDF8"), spaceAfter=6),
    ])

    story.extend(_markdown_story(summary, styles, suppress_title=title))
    story.extend([CondPageBreak(34 * mm), Paragraph("2. Structured Study Notes", styles["section"]), HRFlowable(width="100%", thickness=0.7, color=HexColor("#38BDF8"), spaceAfter=6)])
    story.extend(_markdown_story(notes, styles, suppress_title=title))

    story.extend([CondPageBreak(72 * mm), NextPageTemplate("Body"), Paragraph("3. Active-Recall Flashcards", styles["section"]), Paragraph("Recall each answer before reading the response. Use the source label to return to the evidence.", styles["callout"])])
    rows: list[list[Any]] = []
    cards = list(flashcards)
    for start in range(0, len(cards), 2):
        left = _flashcard_cell(start + 1, cards[start], styles, source)
        right = _flashcard_cell(start + 2, cards[start + 1], styles, source) if start + 1 < len(cards) else ""
        rows.append([left, right])
    grid = Table(rows, colWidths=[84.5 * mm, 84.5 * mm], hAlign="CENTER", splitByRow=1)
    grid.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ])
    )
    story.append(grid)

    story.extend([PageBreak(), Paragraph("4. Knowledge Check Quiz", styles["section"]), Paragraph("Select one answer for each question. Answers remain on a separate page.", styles["callout"])])
    for index, mcq in enumerate(mcqs, 1):
        block: list[Any] = [Paragraph(f"<b>{index}. {_pdf_inline(_get(mcq, 'question', default=''))}</b>", styles["quiz"])]
        for choice_index, choice in enumerate(list(_get(mcq, "choices", default=[]))[:4]):
            block.append(_choice_row(chr(65 + choice_index), choice, styles))
            block.append(Spacer(1, 2))
        story.extend([KeepTogether(block), Spacer(1, 7)])

    story.extend([PageBreak(), Paragraph("5. Answer Key and Explanations", styles["section"]), Paragraph("Use this section only after completing the quiz.", styles["callout"])])
    for index, mcq in enumerate(mcqs, 1):
        block = [
            Paragraph(f"<b>{index}. Correct answer: {_pdf_inline(_get(mcq, 'correct_answer', default=''))}</b>", styles["subsection"]),
            *_answer_reasoning(mcq, styles, domain),
            Paragraph(f"Source: {_pdf_inline(_get(mcq, 'source_ref', 'source', default=source))}", styles["caption"]),
        ]
        story.extend([KeepTogether(block), Spacer(1, 3)])
    story.extend([CondPageBreak(35 * mm), Paragraph("6. Source and Grounding Statement", styles["section"]), Paragraph(f"This learning pack was generated locally from validated cached content grounded in {_pdf_inline(source)}.", styles["callout"])])

    try:
        doc.build(story, canvasmaker=_canvas_factory(source, title))
        os.replace(tmp_path, target_path)
        return target_path
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@retry_io()
def create_quiz_pdf(
    path: Path,
    title: str,
    source: str,
    mcqs: list[Any],
    answer_key: bool = False,
    *,
    domain: str | None = None,
) -> Path:
    target_path = Path(path).resolve()
    tmp_path = AtomicFileWriter.temp_for(target_path)
    styles = _pdf_styles()
    width, height = A4
    doc = BaseDocTemplate(str(tmp_path), pagesize=A4, title=title, author="AmbaAI", leftMargin=16 * mm, rightMargin=16 * mm, topMargin=11 * mm, bottomMargin=16 * mm, pageCompression=1)
    frame = Frame(16 * mm, 16 * mm, width - 32 * mm, height - 27 * mm, id="quiz", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="Quiz", frames=[frame])])

    story: list[Any] = [
        Paragraph("AmbaAI ANSWER KEY" if answer_key else "AmbaAI KNOWLEDGE CHECK", styles["cover_brand"]),
        Paragraph(_pdf_inline(title), styles["cover_title"]),
        Paragraph("Correct answers and learning explanations" if answer_key else "Select one answer for each question", styles["cover_subtitle"]),
    ]
    if not answer_key:
        story.append(Paragraph("Name: _______________________   Date: _____________   Score: ____ / ____", styles["callout"]))

    for index, mcq in enumerate(mcqs, 1):
        question = str(_get(mcq, "question", default=""))
        correct = str(_get(mcq, "correct_answer", default=""))
        explanation = str(_get(mcq, "explanation", default=""))
        block: list[Any] = [Paragraph(f"<b>{index}. {_pdf_inline(question)}</b>", styles["quiz"])]
        if answer_key:
            badge = ParagraphStyle("CorrectBadge", parent=styles["body"], fontName="Helvetica-Bold", fontSize=8.7, leading=10, textColor=HexColor("#234E52"))
            why = ParagraphStyle("CorrectWhy", parent=styles["body"], fontSize=8.7, leading=10.5, textColor=HexColor("#1F2937"))
            callout_table = Table([[Paragraph(f"[✓ Correct] {_pdf_inline(correct)}", badge)], [Paragraph(f"<b>Why this is correct:</b> {_pdf_inline(explanation)}", why)]], colWidths=[169 * mm])
            callout_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#E6FFFA")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor("#319795")),
                    ("BOX", (0, 0), (-1, -1), 0.35, HexColor("#B2F5EA")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ])
            )
            block.append(callout_table)
            block.append(Spacer(1, 2))
            block.extend(_answer_reasoning(mcq, styles, domain)[1:])
            block.append(Paragraph(f"Source: {_pdf_inline(_get(mcq, 'source_ref', 'source', default=source))}", styles["caption"]))
        else:
            for option_index, choice in enumerate(list(_get(mcq, "choices", default=[]))[:4]):
                block.append(_choice_row(chr(65 + option_index), choice, styles))
                block.append(Spacer(1, 1.3))
        story.extend([KeepTogether(block), Spacer(1, 3)])

    try:
        doc.build(story, canvasmaker=_canvas_factory(source, title))
        os.replace(tmp_path, target_path)
        return target_path
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _font_loader(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), int(size))
    return ImageFont.load_default()


def _wrap_tokens(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    tokens = " ".join(_clean(text).split()).split()
    if not tokens:
        return [""]
    lines: list[str] = []
    current = tokens[0]
    for w in tokens[1:]:
        cand = f"{current} {w}"
        bbox = draw.textbbox((0, 0), cand, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = cand
        else:
            lines.append(current)
            current = w
    lines.append(current)
    return lines


def _fit_image_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    max_size: int,
    min_size: int,
    max_lines: int,
    bold: bool = False,
    gap: int = 3,
) -> tuple[ImageFont.ImageFont, list[str], int]:
    for size in range(int(max_size), int(min_size) - 1, -1):
        f = _font_loader(size, bold)
        lines = _wrap_tokens(draw, text, f, max_width)
        bbox = draw.textbbox((0, 0), "Ag", font=f)
        lh = max(1, bbox[3] - bbox[1])
        th = len(lines) * lh + max(0, len(lines) - 1) * gap
        if len(lines) <= max_lines and th <= max_height:
            return f, lines, th

    f = _font_loader(min_size, bold)
    all_lines = _wrap_tokens(draw, text, f, max_width)
    lines = all_lines[:max_lines]
    if len(all_lines) > max_lines and lines:
        last = lines[-1].rstrip(" .,;:-")
        while last and (draw.textbbox((0, 0), last + "...", font=f)[2] - draw.textbbox((0, 0), last + "...", font=f)[0]) > max_width:
            last = last[:-1].rstrip()
        lines[-1] = last + "..." if last else "..."

    bbox = draw.textbbox((0, 0), "Ag", font=f)
    lh = max(1, bbox[3] - bbox[1])
    return f, lines, len(lines) * lh + max(0, len(lines) - 1) * gap


@retry_io()
def create_study_card_png(*args: Any, **kwargs: Any) -> Path:
    values = dict(kwargs)
    cards = None
    for key in ("flashcards", "cards", "revision_cards", "study_cards"):
        if isinstance(values.get(key), (list, tuple)):
            cards = list(values[key])
            break
    if cards is None:
        for candidate in args:
            if isinstance(candidate, (list, tuple)) and candidate and _get(candidate[0], "question", "front", "prompt") is not None:
                cards = list(candidate)
                break
    cards = list(cards or [])[:10]
    if not cards:
        raise ValueError("Study card requires at least one grounded flashcard")

    output = None
    for key in ("output_path", "path", "destination", "file_path", "png_path"):
        if values.get(key):
            output = Path(values[key])
            break
    if output is None:
        for candidate in reversed(args):
            if isinstance(candidate, (str, Path)) and str(candidate).lower().endswith(".png"):
                output = Path(candidate)
                break
    if output is None:
        raise ValueError("Study Card output path was not supplied")

    target_path = Path(output).resolve()
    tmp_path = AtomicFileWriter.temp_for(target_path)

    title = _title(next((values.get(k) for k in ("title", "topic", "document_title") if values.get(k)), "Study Card"))
    source = _clean(next((values.get(k) for k in ("source", "source_name", "source_ref", "filename") if values.get(k)), "Source unavailable"))
    raw_summary = next((values.get(k) for k in ("summary", "summary_markdown", "executive_summary", "markdown") if values.get(k)), "")
    match_sum = re.search(r"(?ims)^#{1,6}\s*Executive Summary\s*$\s*(.*?)(?=^#{1,6}\s+|\Z)", str(raw_summary))
    summary = _clean(match_sum.group(1) if match_sum else raw_summary) or "A grounded active-recall overview of the selected learning material."

    image = Image.new("RGB", (1920, 1080), "#071426")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((58, 44, 1862, 1040), radius=34, fill="#10213A", outline="#35699A", width=3)
    left, right = 105, 1815
    draw.text((left, 80), "AmbaAI STUDY CARD", font=_font_loader(29, True), fill="#38BDF8")

    title_font, title_lines, title_h = _fit_image_text(draw, title, 1710, 92, 48, 30, 2, bold=True, gap=4)
    curr_y = 132
    for l in title_lines:
        draw.text((left, curr_y), l, font=title_font, fill="#F8FAFC")
        bbox = draw.textbbox((left, curr_y), l, font=title_font)
        curr_y += (bbox[3] - bbox[1]) + 4

    summary_font, summary_lines, summary_h = _fit_image_text(draw, summary, 1710, 112, 28, 19, 3, bold=False, gap=5)
    curr_y += 6
    for l in summary_lines:
        draw.text((left, curr_y), l, font=summary_font, fill="#CBD5E1")
        bbox = draw.textbbox((left, curr_y), l, font=summary_font)
        curr_y += (bbox[3] - bbox[1]) + 5

    grid_top = max(286, curr_y + 16)
    footer_top, grid_bottom = 965, 945
    count = len(cards)
    columns = 1 if count == 1 else 2
    rows = ceil(count / columns)
    column_gap = 58
    row_gap = 12 if rows >= 4 else 18
    grid_width = right - left
    grid_height = grid_bottom - grid_top
    card_width = (grid_width - column_gap * (columns - 1)) // columns
    card_height = (grid_height - row_gap * (rows - 1)) // rows

    accents = ["#FFB000", "#38BDF8", "#34D399", "#A78BFA", "#FB7185", "#2DD4BF", "#F97316", "#60A5FA", "#4ADE80", "#C084FC"]
    for index, card in enumerate(cards):
        row, column = divmod(index, columns)
        if columns == 2 and count % 2 and index == count - 1:
            x1 = left + (grid_width - card_width) // 2
        else:
            x1 = left + column * (card_width + column_gap)
        y1 = grid_top + row * (card_height + row_gap)
        x2, y2 = x1 + card_width, y1 + card_height
        accent = accents[index % len(accents)]
        draw.rounded_rectangle((x1, y1, x2, y2), radius=16, fill="#1C3557", outline=accent, width=2)

        q = _clean(_get(card, "question", "front", "prompt", default="Question unavailable"))
        a = _clean(_get(card, "answer", "back", "response", default="Answer unavailable"))
        pad_x, pad_y = 18, max(12, min(22, card_height // 10))
        content_width = card_width - 2 * pad_x
        content_height = card_height - 2 * pad_y
        text_gap = max(6, min(12, content_height // 12))
        q_budget = int((content_height - text_gap) * 0.42)
        a_budget = content_height - text_gap - q_budget
        scale = max(0.75, min(1.45, card_height / 126.0))
        q_max, q_min = max(25, min(36, round(25 * scale))), max(18, min(25, round(18 * scale)))
        a_max, a_min = max(21, min(31, round(21 * scale))), max(15, min(22, round(15 * scale)))
        q_lines_limit = 3 if card_height >= 190 else 2
        a_lines_limit = 4 if card_height >= 190 else 3

        q_font, q_lines, q_h = _fit_image_text(draw, q, content_width, q_budget, q_max, q_min, q_lines_limit, bold=True, gap=3)
        a_font, a_lines, a_h = _fit_image_text(draw, a, content_width, a_budget + max(0, q_budget - q_h), a_max, a_min, a_lines_limit, bold=False, gap=4)
        total_h = q_h + text_gap + a_h
        y = y1 + pad_y + max(0, (content_height - total_h) // 2)

        for line in q_lines:
            draw.text((x1 + pad_x, y), line, font=q_font, fill=accent)
            bbox = draw.textbbox((x1 + pad_x, y), line, font=q_font)
            y += (bbox[3] - bbox[1]) + 3
        y += text_gap
        for line in a_lines:
            draw.text((x1 + pad_x, y), line, font=a_font, fill="#FFFFFF")
            bbox = draw.textbbox((x1 + pad_x, y), line, font=a_font)
            y += (bbox[3] - bbox[1]) + 4

    footer = f"Grounded in {source} | Generated locally | {count} revision card{'s' if count != 1 else ''}"
    draw.rounded_rectangle((left, footer_top, right, 1022), radius=14, fill="#1F9F9D")
    footer_font = _font_loader(18, True)
    draw.text((left + 30, footer_top + 16), footer, font=footer_font, fill="#FFFFFF")

    try:
        image.save(tmp_path, format="PNG", optimize=True)
        os.replace(tmp_path, target_path)
        return target_path
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_markdown(path: Path, title: str, source: str, summary: str, notes: str, flashcards: list[Any], mcqs: list[Any]) -> Path:
    p = [
        f"# {_clean(title)}",
        "",
        f"Source: {_clean(source)}",
        "",
        "## Executive Summary",
        _clean(summary),
        "",
        "## Structured Study Notes",
        _clean(notes),
        "",
        "## Flashcards",
    ]
    for i, c in enumerate(flashcards, 1):
        p.extend([f"### {i}. {_get(c, 'question')}", str(_get(c, "answer")), f"Source: {_get(c, 'source_ref', default=source)}", ""])
    p.append("## Knowledge Check Quiz")
    for i, q in enumerate(mcqs, 1):
        p.append(f"### {i}. {_get(q, 'question')}")
        p.extend(f"- {x}" for x in list(_get(q, "choices", default=[]))[:4])
        p.append("")
    content = "\n".join(p).strip() + "\n"
    return AtomicFileWriter.write_text(path, content)


def _write_flashcards_csv(path: Path, cards: list[Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = AtomicFileWriter.temp_for(target)
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Front", "Back", "Source"])
            for card in cards:
                writer.writerow([_get(card, "question"), _get(card, "answer"), _get(card, "source_ref")])
        os.replace(tmp_path, target)
        return target
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_quiz_csv(path: Path, mcqs: list[Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = AtomicFileWriter.temp_for(target)
    try:
        with tmp_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Question", "Choice A", "Choice B", "Choice C", "Choice D", "Correct Answer", "Explanation", "Source"])
            for mcq in mcqs:
                choices = (list(_get(mcq, "choices", default=[]))[:4] + [""] * 4)[:4]
                writer.writerow([_get(mcq, "question"), *choices, _get(mcq, "correct_answer"), _get(mcq, "explanation"), _get(mcq, "source_ref")])
        os.replace(tmp_path, target)
        return target
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def build_learning_bundle(
    output_dir: str | Path,
    *,
    document_id: int,
    title: str,
    source: str,
    summary: str,
    notes: str,
    flashcards: Iterable[Any],
    mcqs: Iterable[Any],
) -> LearningPackResult:
    start_time = time.perf_counter()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(title)

    v_title, v_summary, v_notes, cards, quiz = _validate_learning_inputs(
        title=title,
        summary=summary,
        notes=notes,
        flashcards=list(flashcards),
        mcqs=list(mcqs),
    )

    adapter = domain_registry.resolve(f"{v_title}\n{v_notes}") if domain_registry else None
    domain = adapter.name if adapter else None

    paths = {
        "study_guide_pdf": out / f"{stem}_study_guide.pdf",
        "structured_markdown": out / f"{stem}_study_guide.md",
        "study_card_png": out / f"{stem}_study_card.png",
        "flashcards_csv": out / f"{stem}_flashcards.csv",
        "quiz_csv": out / f"{stem}_quiz.csv",
        "quiz_pdf": out / f"{stem}_quiz.pdf",
        "answer_key_pdf": out / f"{stem}_answer_key.pdf",
    }

    create_study_guide_pdf(paths["study_guide_pdf"], v_title, source, v_summary, v_notes, cards, quiz, domain=domain)
    _write_markdown(paths["structured_markdown"], v_title, source, v_summary, v_notes, cards, quiz)
    create_study_card_png(paths["study_card_png"], v_title, source, v_summary, cards)
    _write_flashcards_csv(paths["flashcards_csv"], cards)
    _write_quiz_csv(paths["quiz_csv"], quiz)
    create_quiz_pdf(paths["quiz_pdf"], f"{v_title} - Knowledge Check", source, quiz, answer_key=False, domain=domain)
    create_quiz_pdf(paths["answer_key_pdf"], f"{v_title} - Answer Key", source, quiz, answer_key=True, domain=domain)

    artifacts = [_artifact(kind, path) for kind, path in paths.items()]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "document_id": int(document_id),
        "title": v_title,
        "source": source,
        "domain": domain or "general",
        "generated_locally": True,
        "grounded": True,
        "flashcards": len(cards),
        "quiz_questions": len(quiz),
        "artifacts": [asdict(item) for item in artifacts],
    }

    manifest_path = out / "manifest.json"
    AtomicFileWriter.write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))
    artifacts.append(_artifact("manifest", manifest_path))

    if len(artifacts) > MAX_ARTIFACTS:
        raise ValueError(f"Artifact count {len(artifacts)} exceeds limit {MAX_ARTIFACTS}")

    total_bytes = sum(a.size_bytes for a in artifacts)
    if total_bytes > MAX_BUNDLE_BYTES:
        raise ValueError(f"Total artifact payload {total_bytes} bytes exceeds security budget {MAX_BUNDLE_BYTES}")

    bundle_path = out / f"{stem}_offline_study_bundle.zip"
    tmp_bundle = AtomicFileWriter.temp_for(bundle_path)

    try:
        with zipfile.ZipFile(tmp_bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in artifacts:
                ap = Path(item.path)
                archive.write(ap, arcname=ap.name)
        os.replace(tmp_bundle, bundle_path)
    except Exception:
        try:
            os.unlink(tmp_bundle)
        except OSError:
            pass
        raise

    artifacts.append(_artifact("offline_bundle", bundle_path))
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    bundle_size = bundle_path.stat().st_size

    logger.info(
        "Learning bundle generated successfully",
        extra={
            "context": {
                "document_id": document_id,
                "domain": domain or "general",
                "artifact_count": len(artifacts),
                "bundle_size_bytes": bundle_size,
                "duration_ms": duration_ms,
            }
        },
    )

    return LearningPackResult(
        document_id=int(document_id),
        source=source,
        output_dir=str(out),
        bundle_path=str(bundle_path),
        artifacts=artifacts,
    )


def compile_document_agnostic_bundle(
    document: Any,
    *,
    flashcards: Iterable[Any] = (),
    mcqs: Iterable[Any] = (),
    output_dir: str | Path,
    metadata: Mapping[str, Any] | None = None,
    compiler: Any = None,
) -> Any:
    meta = dict(metadata or {})
    title = _title(_get(document, "title", default=meta.get("title", "Learning Pack")))
    source = resolve_source(document, meta)
    summary = _clean(_get(document, "executive_summary", "summary", default=""))
    notes = _clean(_get(document, "notes", "raw_text", default=""))
    doc_id = int(_get(document, "document_id", "id", default=meta.get("document_id", 0)) or 0)
    return build_learning_bundle(
        output_dir=output_dir,
        document_id=doc_id,
        title=title,
        source=source,
        summary=summary,
        notes=notes,
        flashcards=flashcards,
        mcqs=mcqs,
    )