from __future__ import annotations

import re
from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication,
    QTextCharFormat, QSyntaxHighlighter
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QVBoxLayout, QWidget
)


class MultiLangHighlighter(QSyntaxHighlighter):
    def __init__(self, parent, language: str = "python"):
        super().__init__(parent)
        self.language = language.lower()
        self.rules: list[tuple[str, QTextCharFormat]] = []
        self._setup_rules()

    def _setup_rules(self):
        self.rules.clear()

        if self.language == "python":
            kw_fmt = QTextCharFormat()
            kw_fmt.setForeground(QColor("#007acc"))
            kw_fmt.setFontWeight(QFont.Weight.Bold)
            keywords = ["def", "class", "import", "return", "if", "else", "for", "while", "try", "except", "with", "as"]
            self.rules += [(r"\b" + kw + r"\b", kw_fmt) for kw in keywords]

            str_fmt = QTextCharFormat()
            str_fmt.setForeground(QColor("#ce9178"))
            self.rules.append((r"\".*?\"|'.*?'", str_fmt))

            num_fmt = QTextCharFormat()
            num_fmt.setForeground(QColor("#b5cea8"))
            self.rules.append((r"\b[0-9]+\b", num_fmt))

            com_fmt = QTextCharFormat()
            com_fmt.setForeground(QColor("#6a9955"))
            self.rules.append((r"#.*", com_fmt))

        elif self.language == "sql":
            kw_fmt = QTextCharFormat()
            kw_fmt.setForeground(QColor("#569cd6"))
            kw_fmt.setFontWeight(QFont.Weight.Bold)
            keywords = ["SELECT", "FROM", "WHERE", "JOIN", "INSERT", "UPDATE", "DELETE", "CREATE", "TABLE", "DROP"]
            self.rules += [(r"\b" + kw + r"\b", kw_fmt) for kw in keywords]

            str_fmt = QTextCharFormat()
            str_fmt.setForeground(QColor("#d69d85"))
            self.rules.append((r"'[^']*'", str_fmt))

            num_fmt = QTextCharFormat()
            num_fmt.setForeground(QColor("#b5cea8"))
            self.rules.append((r"\b[0-9]+\b", num_fmt))

            com_fmt = QTextCharFormat()
            com_fmt.setForeground(QColor("#6a9955"))
            self.rules.append((r"--.*", com_fmt))

        elif self.language == "latex":
            cmd_fmt = QTextCharFormat()
            cmd_fmt.setForeground(QColor("#c586c0"))
            cmd_fmt.setFontWeight(QFont.Weight.Bold)
            self.rules.append((r"\\[a-zA-Z]+", cmd_fmt))

            math_fmt = QTextCharFormat()
            math_fmt.setForeground(QColor("#569cd6"))
            self.rules.append((r"\$[^$]+\$", math_fmt))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)

    def setLanguage(self, language: str):
        self.language = language.lower()
        self._setup_rules()
        self.rehighlight()


class TechnicalBlockView(QFrame):
    copied = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("learningTechnicalBlock")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.label = QLabel("Technical Content")
        self.label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.copy = QPushButton("Copy")
        self.copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy.setToolTip("Copy block content to clipboard")
        top.addWidget(self.label, 1)
        top.addWidget(self.copy)

        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        self.content.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.content.setFont(QFont("Consolas", 10))
        self.highlighter = MultiLangHighlighter(self.content.document(), "python")

        self.explanation = QLabel("")
        self.explanation.setWordWrap(True)
        self.explanation.setVisible(False)

        root.addLayout(top)
        root.addWidget(self.content)
        root.addWidget(self.explanation)

        self.copy.clicked.connect(self._copy)

    def setBlock(self, block: object) -> None:
        block_type = getattr(getattr(block, "block_type", None), "value", None) or getattr(block, "block_type", "technical")
        label = getattr(block, "label", "") or str(block_type).replace("_", " ").title()
        content = str(getattr(block, "content", "") or "")
        explanation = str(getattr(block, "explanation", "") or "")

        self.label.setText(label)
        self.content.setPlainText(content)
        self.explanation.setText(explanation)
        self.explanation.setVisible(bool(explanation))

        lang_map = {"python": "python", "sql": "sql", "latex": "latex", "formula": "latex"}
        self.highlighter.setLanguage(lang_map.get(str(block_type).lower(), "python"))

        self.setAccessibleName(f"{label} technical block")

    def _copy(self) -> None:
        value = self.content.toPlainText()
        QGuiApplication.clipboard().setText(value)
        self.copied.emit(value)

        self.copy.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy.setText("Copy"))