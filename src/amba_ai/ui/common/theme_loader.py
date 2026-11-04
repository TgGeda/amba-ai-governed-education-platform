from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PySide6.QtWidgets import QApplication, QWidget

TOKENS: dict[str, str] = {
    "surface_base": "#F8F6F0",
    "surface_card": "#FFFFFF",
    "surface_muted": "#F1F5F9",
    "border_subtle": "#D8E0E8",
    "accent_primary": "#2F7F7A",
    "accent_secondary": "#B85C47",
    "text_primary": "#18212B",
    "text_secondary": "#536273",
    "focus": "#2563EB",
    "success": "#2F855A",
    "warning": "#B7791F",
    "danger": "#C53030",
    "code_surface": "#0D1B2A",
    "code_text": "#FFFFFF",
    "code_accent": "#38BDF8",
}


def render_qss(template: str, tokens: Mapping[str, str] | None = None) -> str:
    values = dict(TOKENS)
    if tokens:
        values.update(tokens)
    result = str(template or "")
    for name, value in values.items():
        result = result.replace("{{" + name + "}}", value)
    return result


def load_component_qss(component_name: str, tokens: Mapping[str, str] | None = None) -> str:
    root = Path(__file__).resolve().parents[1] / "styles" / "components"
    chunks: list[str] = []

    common_path = root / "learning_common.qss"
    if common_path.exists():
        chunks.append(common_path.read_text(encoding="utf-8"))

    comp_path = root / f"{component_name}.qss"
    if comp_path.exists():
        chunks.append(comp_path.read_text(encoding="utf-8"))

    return render_qss("\n\n".join(chunks), tokens)


def compose_learning_qss(root: Path | None = None, tokens: Mapping[str, str] | None = None) -> str:
    base = root or (Path(__file__).resolve().parents[1] / "styles" / "components")
    names = ["learning_common.qss", "summary.qss", "notes.qss", "study.qss", "quiz.qss", "tutor.qss"]
    chunks: list[str] = []
    for name in names:
        path = base / name
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return render_qss("\n\n".join(chunks), tokens)


def apply_learning_theme(target: QApplication | QWidget, root: Path | None = None) -> None:
    target.setStyleSheet(compose_learning_qss(root))