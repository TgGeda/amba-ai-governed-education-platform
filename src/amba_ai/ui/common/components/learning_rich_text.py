from __future__ import annotations

import html
import re
from typing import Any

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QFrame,
    QSizePolicy,
    QTextBrowser,
    QWidget,
)

_COMMENT_PATTERN = re.compile(
    r"(?:<!--|&lt;!--)\s*ambaai\.[\s\S]*?(?:-->|--&gt;)",
    re.IGNORECASE,
)

_INLINE_BULLET_PATTERN = re.compile(
    r"\s+-\s+(?=[A-Z0-9][^:\n]{1,80}:)",
)

_CODE_BLOCK_PATTERN = re.compile(
    r"```(\w*)\n([\s\S]*?)```",
)

_INLINE_CODE_PATTERN = re.compile(
    r"`([^`\n]+)`",
)

_BOLD_PATTERN = re.compile(
    r"(\*\*|__)(.*?)\1",
)

_ITALIC_PATTERN = re.compile(
    r"(\*|_)(.*?)\1",
)

_STRIKE_PATTERN = re.compile(
    r"~~(.*?)~~",
)

_HIGHLIGHT_PATTERN = re.compile(
    r"==(.*?)==",
)

_LINK_PATTERN = re.compile(
    r"\[([^\]]+)\]\(([^)]+)\)",
)

_HR_PATTERN = re.compile(
    r"^\s*([-*_]{3,})\s*$",
)

_TABLE_ROW_PATTERN = re.compile(
    r"^\s*\|(.+)\|\s*$",
)


def clean_learning_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\\n", "\n")
    text = _COMMENT_PATTERN.sub("", text)
    text = re.sub(r"(?im)^\s*(?:detected\s+topic|topic)\s*:\s*", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_embedded_bullets(text: str) -> str:
    normalized = clean_learning_text(text)
    if " - " not in normalized:
        return normalized
    return _INLINE_BULLET_PATTERN.sub("\n- ", normalized)


def _inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = _LINK_PATTERN.sub(r'<a href="\2" class="learningLink">\1</a>', escaped)
    escaped = _INLINE_CODE_PATTERN.sub(r'<code class="inlineCode">\1</code>', escaped)
    escaped = _HIGHLIGHT_PATTERN.sub(r'<mark class="learningHighlight">\1</mark>', escaped)
    escaped = _BOLD_PATTERN.sub(r"<strong>\2</strong>", escaped)
    escaped = _ITALIC_PATTERN.sub(r"<em>\2</em>", escaped)
    escaped = _STRIKE_PATTERN.sub(r"<del>\1</del>", escaped)
    return escaped


def learning_text_to_html(value: Any) -> str:
    text = normalize_embedded_bullets(clean_learning_text(value))
    if not text:
        return '<p class="emptyLearningText">No grounded explanation is available.</p>'

    css_styles = """
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 13.5px;
            line-height: 1.6;
            color: #1D3323;
            margin: 0;
            padding: 0;
            background-color: transparent;
        }
        p {
            margin: 0 0 6px 0;
            background: transparent;
            border: none;
        }
        h1, h2, h3, h4, h5, h6 {
            color: #C05C46;
            font-weight: 800;
            margin: 10px 0 4px 0;
            padding: 0;
        }
        ul, ol {
            margin: 0 0 8px 0;
            padding-left: 18px;
        }
        li {
            margin-bottom: 3px;
        }
        code.inlineCode {
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 11.5px;
            background-color: #F4E9D7;
            color: #8C3B2B;
            padding: 1px 4px;
            border-radius: 3px;
            border: 1px solid #DCC8A9;
        }
        pre.codeBlock {
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 12px;
            background-color: #1D3323;
            color: #FBF7EF;
            padding: 8px 10px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 6px 0;
            line-height: 1.4;
        }
    </style>
    """

    code_blocks: list[str] = []

    def save_code_block(match: re.Match) -> str:
        code_text = html.escape(match.group(2).strip())
        code_blocks.append(
            f'<pre class="codeBlock"><code>{code_text}</code></pre>'
        )
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    processed_text = _CODE_BLOCK_PATTERN.sub(save_code_block, text)

    lines = processed_text.splitlines()
    fragments: list[str] = [css_styles]

    paragraph_lines: list[str] = []
    bullet_items: list[str] = []
    numbered_items: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        content = " ".join(line.strip() for line in paragraph_lines if line.strip())
        if content:
            fragments.append(f"<p>{_inline_markup(content)}</p>")
        paragraph_lines.clear()

    def flush_bullets() -> None:
        if not bullet_items:
            return
        items = "".join(f"<li>{_inline_markup(item)}</li>" for item in bullet_items)
        fragments.append(f'<ul class="learningList">{items}</ul>')
        bullet_items.clear()

    def flush_numbered() -> None:
        if not numbered_items:
            return
        items = "".join(f"<li>{_inline_markup(item)}</li>" for item in numbered_items)
        fragments.append(f'<ol class="learningList">{items}</ol>')
        numbered_items.clear()

    def flush_all() -> None:
        flush_paragraph()
        flush_bullets()
        flush_numbered()

    for raw_line in lines:
        stripped = raw_line.strip()

        if stripped.startswith("__CODE_BLOCK_") and stripped.endswith("__"):
            flush_all()
            idx = int(stripped.replace("__CODE_BLOCK_", "").replace("__", ""))
            fragments.append(code_blocks[idx])
            continue

        if not stripped:
            flush_all()
            continue

        if stripped.startswith(("- ", "* ", "+ ", "• ")):
            flush_paragraph()
            flush_numbered()
            bullet_items.append(stripped[2:].strip())
            continue

        num_match = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if num_match:
            flush_paragraph()
            flush_bullets()
            numbered_items.append(num_match.group(1).strip())
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            flush_all()
            level = len(heading_match.group(1))
            heading_text = _inline_markup(heading_match.group(2).strip())
            fragments.append(f"<h{level}>{heading_text}</h{level}>")
            continue

        paragraph_lines.append(stripped)

    flush_all()
    return "\n".join(fragments)


class LearningCodeHighlighter(QSyntaxHighlighter):
    def __init__(self, parent: QTextDocument | None = None) -> None:
        super().__init__(parent)
        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []
        self._build_rules()

    def _build_rules(self) -> None:
        fmt_keyword = QTextCharFormat()
        fmt_keyword.setForeground(QColor("#C05C46"))
        fmt_keyword.setFontWeight(QFont.Weight.Bold)

        fmt_string = QTextCharFormat()
        fmt_string.setForeground(QColor("#315343"))

        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor("#8F846E"))
        fmt_comment.setFontItalic(True)

        keywords = [
            r"\bdef\b", r"\bclass\b", r"\bimport\b", r"\bfrom\b", r"\breturn\b",
            r"\bif\b", r"\belif\b", r"\belse\b", r"\bfor\b", r"\bwhile\b",
            r"\btry\b", r"\bexcept\b", r"\bwith\b", r"\bas\b", r"\byield\b",
            r"\blambda\b", r"\basync\b", r"\bawait\b"
        ]

        for kw in keywords:
            self._rules.append((re.compile(kw, re.IGNORECASE), fmt_keyword))

        self._rules.append((re.compile(r"(\".*?\"|\'.*?\')"), fmt_string))
        self._rules.append((re.compile(r"(#|//).*$"), fmt_comment))

    def highlightBlock(self, text: str) -> None:
        if not text:
            return

        fmt = self.format(0)
        font_families = fmt.fontFamilies()
        families_str = " ".join(str(f).lower() for f in font_families) if font_families else ""

        if not any(f in families_str for f in ("cascadia", "consolas", "courier", "monospace", "code")):
            return

        for pattern, rule_fmt in self._rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, rule_fmt)


class LearningRichText(QTextBrowser):
    linkClicked = Signal(str)

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._updating_height = False

        self.setObjectName("learningRichText")
        self.setAccessibleName("Learning content")

        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)

        # Force NoFrame & transparent background to permanently destroy rectangle outlines
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(0)
        self.setStyleSheet("QTextBrowser { border: none !important; background: transparent !important; padding: 0px; }")

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )

        self.document().setDocumentMargin(0)
        self.highlighter = LearningCodeHighlighter(self.document())

        document_layout = self.document().documentLayout()
        if document_layout is not None:
            document_layout.documentSizeChanged.connect(
                self._schedule_height_update
            )

        self.anchorClicked.connect(self._handle_anchor_clicked)

        if text:
            self.setLearningText(text)
        else:
            self._schedule_height_update()

    def setLearningText(self, text: str) -> None:
        self.setHtml(learning_text_to_html(text))
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)
        self._schedule_height_update()

    def learningText(self) -> str:
        return self.toPlainText()

    def clearLearningText(self) -> None:
        self.clear()
        self._schedule_height_update()

    def event(self, event: QEvent) -> bool:
        result = super().event(event)

        if event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ApplicationFontChange,
            QEvent.Type.PaletteChange,
        }:
            self._schedule_height_update()

        return result

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._updating_height:
            self._update_document_width()
            self._schedule_height_update()

    def sizeHint(self) -> QSize:
        document_height = int(self.document().size().height())
        return QSize(
            max(320, self.width()),
            max(16, document_height + 2),
        )

    def minimumSizeHint(self) -> QSize:
        return QSize(200, 16)

    def _handle_anchor_clicked(self, url: QUrl) -> None:
        url_str = url.toString()
        if url_str.startswith(("http://", "https://", "mailto:")):
            QDesktopServices.openUrl(url)
        self.linkClicked.emit(url_str)

    def _update_document_width(self) -> None:
        viewport_width = max(100, self.viewport().width())
        self.document().setTextWidth(viewport_width)

    def _schedule_height_update(self, *_args) -> None:
        QTimer.singleShot(0, self._update_height)

    def _update_height(self) -> None:
        if self._updating_height:
            return

        self._updating_height = True
        try:
            self._update_document_width()
            doc_height = int(self.document().size().height())
            content_height = max(16, doc_height + 2)

            if self.height() != content_height:
                self.setFixedHeight(content_height)
                self.updateGeometry()
        finally:
            self._updating_height = False