"""
Stable, document-agnostic learning UI components.

These widgets consume Learning Core objects but never parse lesson content.
Presentation lives in QSS; Python owns structure, behavior, accessibility, and state.
"""

from .accessibility import repolish, set_state
from .accordion_card import AccordionCard
from .command_block import TechnicalBlockView
from .concept_explorer import ConceptExplorer
from .empty_state import EmptyState
from .figure_view import LearningFigureView, ZoomableLabel
from .learning_header import LearningHeader
from .mastery_banner import MasteryBanner, MasterySnapshot
from .reading_canvas import ReadingCanvas
from .search_bar import LearningSearchBar
from .source_chip import SourceChip
from .table_view import LearningTableView
from .outline_panel import DocumentOutlinePanel
from .flow_layout import FlowLayout, configure_flow_widget
from .learning_rich_text import (
    LearningRichText,
    LearningCodeHighlighter,   # NEW: syntax highlighting backend
    clean_learning_text,
    learning_text_to_html,
    normalize_embedded_bullets,
)

__all__ = [
    "AccordionCard",
    "ConceptExplorer",
    DocumentOutlinePanel,
    "EmptyState",
    "LearningFigureView",
    "ZoomableLabel",            # NEW: zoom/drag/scroll figure label
    "LearningHeader",
    "LearningSearchBar",
    "LearningTableView",
    "MasteryBanner",
    "MasterySnapshot",
    "ReadingCanvas",
    "SourceChip",
    "TechnicalBlockView",
    "repolish",
    "set_state",
    "LearningRichText",
    "LearningCodeHighlighter",  # NEW: syntax highlighting backend
    "clean_learning_text",
    "learning_text_to_html",
    "normalize_embedded_bullets",
    "FlowLayout",
    "configure_flow_widget",
]
