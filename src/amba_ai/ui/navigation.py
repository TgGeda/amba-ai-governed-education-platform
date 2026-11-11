from __future__ import annotations

from enum import Enum
from typing import Any


class WorkspaceTab(str, Enum):
    INGEST = "view_ingest"
    LIBRARY = "view_library"
    SUMMARIZER = "view_summarizer"
    NOTES = "view_notes"
    STUDY = "view_study"
    TUTOR = "view_tutor"
    EQUITY = "view_equity_switch"
    GOVERNANCE_REVIEW = "view_governance_review"


def resolve_tab_index(tab_widget: Any, target_tab: WorkspaceTab | str) -> int | None:
    target = target_tab.value if isinstance(target_tab, WorkspaceTab) else str(target_tab).strip()
    aliases = {
        "ingest": "view_ingest",
        "library": "view_library",
        "summarizer": "view_summarizer",
        "summary": "view_summarizer",
        "notes": "view_notes",
        "study": "view_study",
        "tutor": "view_tutor",
        "chat": "view_tutor",
        "equity": "view_equity_switch",
        "equity_switch": "view_equity_switch",
        "review": "view_governance_review",
        "teacher_review": "view_governance_review",
        "governance_review": "view_governance_review",
    }
    resolved = aliases.get(target, target)
    class_tokens = {
        "view_ingest": "Ingest",
        "view_library": "Library",
        "view_summarizer": "Summarizer",
        "view_notes": "Notes",
        "view_study": "Study",
        "view_tutor": "Tutor",
        "view_equity_switch": "Equity",
        "view_governance_review": "GovernanceReview",
    }
    token = class_tokens.get(resolved)
    if token is None:
        return None
    for index in range(tab_widget.count()):
        if token in type(tab_widget.widget(index)).__name__:
            return index
    return None
