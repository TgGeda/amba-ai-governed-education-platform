from __future__ import annotations

from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]


def _requirements(path: Path) -> dict[str, Requirement]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        req = Requirement(value)
        result[canonicalize_name(req.name)] = req
    return result


def test_base_requirements_are_exact_and_contained_in_lock() -> None:
    base = _requirements(ROOT / "requirements.txt")
    lock = _requirements(ROOT / "requirements-lock.txt")
    assert base
    assert set(base) <= set(lock)
    assert "chardet" in base
    for req in [*base.values(), *lock.values()]:
        specs = list(req.specifier)
        assert len(specs) == 1
        assert specs[0].operator == "=="
        assert "*" not in specs[0].version


def test_windows_launcher_is_portable_and_uses_venv_directly() -> None:
    launcher = (ROOT / "run_amba.bat").read_text(encoding="utf-8")
    assert 'cd /d "%~dp0"' in launcher
    assert 'F:\\AmbaAI\\amba_ai_project' not in launcher
    assert 'set "QT_QPA_PLATFORM="' in launcher
    assert 'set "PYTHONPATH=%CD%\\src"' in launcher
    assert '".venv\\Scripts\\python.exe" -m amba_ai.main' in launcher
    assert "activate" not in launcher.lower()
