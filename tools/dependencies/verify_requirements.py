from __future__ import annotations

from importlib import import_module, metadata
from pathlib import Path
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
CRITICAL_IMPORTS = (
    "PySide6",
    "faiss",
    "transformers",
    "yaml",
    "reportlab",
    "docx",
    "pypdf",
    "chardet",
)


def parse(path: Path) -> dict[str, Requirement]:
    result: dict[str, Requirement] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        name = canonicalize_name(req.name)
        if name in result:
            raise AssertionError(f"duplicate dependency at {path}:{number}: {req.name}")
        specs = list(req.specifier)
        assert len(specs) == 1 and specs[0].operator == "==" and "*" not in specs[0].version, line
        result[name] = req
    return result


def main() -> int:
    base = parse(ROOT / "requirements.txt")
    lock = parse(ROOT / "requirements-lock.txt")
    assert set(base) <= set(lock), sorted(set(base) - set(lock))

    installed = {
        canonicalize_name(dist.metadata["Name"]): dist.version
        for dist in metadata.distributions()
        if dist.metadata.get("Name")
    }
    missing = sorted(set(lock) - set(installed))
    mismatched = sorted(
        f"{req.name}: lock {req.specifier}, installed {installed.get(name)}"
        for name, req in lock.items()
        if name in installed and installed[name] not in req.specifier
    )
    assert not missing, f"missing locked distributions: {missing}"
    assert not mismatched, f"version mismatches: {mismatched}"

    for module in CRITICAL_IMPORTS:
        import_module(module)

    check = subprocess.run([sys.executable, "-m", "pip", "check"], cwd=ROOT, text=True, capture_output=True)
    print(check.stdout, end="")
    print(check.stderr, end="", file=sys.stderr)
    assert check.returncode == 0, "pip check failed"

    print(f"PASS: {len(base)} declared dependencies are contained in {len(lock)} exact locked distributions")
    print("PASS: critical UI, vector, transformer, YAML, report, Word, PDF, and charset imports resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
