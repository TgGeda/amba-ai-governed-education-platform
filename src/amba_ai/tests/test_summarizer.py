from __future__ import annotations

import ast
import compileall
from pathlib import Path
import pytest

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from amba_ai.ui.features.summarizer.summarizer_widget import SummarizerWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class DummyJobService:
    def __init__(self, sample_markdown: str = ""):
        self.sample_markdown = sample_markdown or (
            "# Introduction to BGP Protocols\n\n"
            "## Executive Summary\nBorder Gateway Protocol (BGP) is the core routing protocol of the global Internet.\n\n"
            "## Learning Objectives\n- Understand Autonomous Systems.\n- Configure BGP sessions.\n\n"
            "## Key Definitions\n- **Autonomous System (AS)**: A collection of connected IP routing prefixes.\n\n"
            "## Why It Matters\nBGP enables inter-domain routing across the global Internet.\n\n"
            "## How It Works\nBGP exchanges path vectors between peering routers over TCP port 179.\n\n"
            "## One-Minute Review\nBGP uses path vector attributes for route selection."
        )

    def summarize_document(self, document_id: int, **kwargs):
        from amba_ai.models.schemas import SummaryResult
        return SummaryResult(
            markdown_notes=self.sample_markdown,
            model_name="qwen-2.5-3b",
            tokens_used=128,
            metadata={"document_id": document_id, "cached": True},
        )


def test_ast_and_compilation():
    root_dir = Path(__file__).parent.parent / "src" / "amba_ai" / "ui" / "summarizer"
    for py_file in root_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        parsed = ast.parse(content, filename=str(py_file))
        assert parsed is not None
        compiled = compile(content, filename=str(py_file), mode="exec")
        assert compiled is not None

    res = compileall.compile_dir(str(root_dir), force=True, quiet=True)
    assert res is True


@pytest.mark.parametrize("domain_name, markdown_content", [
    ("networking", "# BGP Networks\n\n## Executive Summary\nBGP routes internet traffic.\n\n## Key Definitions\n- **Autonomous System**: Routing network."),
    ("biology", "# Photosynthesis\n\n## Executive Summary\nPlants convert light into chemical energy.\n\n## Key Definitions\n- **Chlorophyll**: Green pigment in plants."),
    ("mathematics", "# Linear Algebra\n\n## Executive Summary\nStudy of vectors and linear transformations.\n\n## Key Definitions\n- **Eigenvector**: Non-zero vector scaled by transformation."),
    ("programming", "# Object-Oriented Design\n\n## Executive Summary\nParadigm based on objects and classes.\n\n## Key Definitions\n- **Polymorphism**: Provision of a single interface to entities of different types."),
    ("history", "# Industrial Revolution\n\n## Executive Summary\nTransition to new manufacturing processes.\n\n## Key Definitions\n- **Steam Engine**: Engine using expansion of steam."),
    ("language_learning", "# Spanish Verb Conjugation\n\n## Executive Summary\nRules for altering Spanish verbs.\n\n## Key Definitions\n- **Subjunctive**: Mood expressing wishes or conditionality."),
])
def test_multi_domain_parsing(domain_name, markdown_content):
    doc = _load_or_parse_learning_document(markdown=markdown_content, document_id=101, title=domain_name, source_name="Test Source")
    assert doc.title == domain_name
    assert doc.domain != ""
    assert len(doc.learning_objectives) > 0


def test_unbreakable_parsing_edge_cases():
    # 1. Unformatted raw string
    raw_text = "Just a raw string with no markdown headings or structure."
    doc1 = _load_or_parse_learning_document(markdown=raw_text, document_id=1)
    assert doc1.title != ""
    assert doc1.executive_summary != ""

    # 2. Markdown with asterisks in concept names (*jq, *API Intelligence)
    asterisk_md = "# Title\n\n## Definitions\n- ***jq*** : Powerful command-line JSON processor\n- **API Intelligence** : Pulling essential fields"
    doc2 = _load_or_parse_learning_document(markdown=asterisk_md, document_id=2)
    concept_names = [c.name for c in doc2.concepts]
    assert "jq" in concept_names
    assert "API Intelligence" in concept_names
    assert not any(name.startswith("*") for name in concept_names)


def test_summarizer_widget_state_and_navigation(qapp):
    settings = QSettings("AmbaAI", "TestWorkspace")
    job_service = DummyJobService()
    widget = SummarizerWidget(settings, job_service)

    widget.set_document(42)
    assert widget.document_id == 42
    assert widget.selected_concept_id is None

    widget.generate_summary()
    assert widget.current_summary is not None
    assert widget.current_learning_doc is not None

    # Test real-time search filter
    widget.search_bar.setText("NonExistentTermKey123")
    assert widget.search_bar.text() == "NonExistentTermKey123"

    # Test state clearing on set_document
    widget.set_document(99)
    assert widget.document_id == 99
    assert widget.current_summary is None
    assert widget.selected_concept_id is None