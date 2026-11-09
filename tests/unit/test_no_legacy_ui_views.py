from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "amba_ai"


def test_legacy_ui_views_package_is_absent() -> None:
    assert not (SRC / "ui" / "views").exists()


def test_production_source_does_not_import_legacy_ui_views() -> None:
    offenders: list[str] = []
    for source in sorted(SRC.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            if any(name == "amba_ai.ui.views" or name.startswith("amba_ai.ui.views.") for name in modules):
                offenders.append(f"{source.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}")
    assert offenders == []


def test_main_window_uses_feature_widgets() -> None:
    text = (SRC / "ui" / "main_window.py").read_text(encoding="utf-8")
    expected = {
        "amba_ai.ui.features.ingest",
        "amba_ai.ui.features.library",
        "amba_ai.ui.features.notes",
        "amba_ai.ui.features.study",
        "amba_ai.ui.features.summarizer",
        "amba_ai.ui.features.tutor",
    }
    assert all(module in text for module in expected)
