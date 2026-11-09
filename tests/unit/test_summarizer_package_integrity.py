from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "amba_ai" / "ui" / "features" / "summarizer"


def test_summarizer_package_python_sources_parse_and_compile() -> None:
    sources = sorted(PACKAGE.rglob("*.py"))
    assert sources, f"no Python sources found under {PACKAGE}"
    for source in sources:
        text = source.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source))
        assert tree is not None
        compile(text, filename=str(source), mode="exec")
