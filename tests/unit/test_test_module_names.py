from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_test_module_basenames_are_unique() -> None:
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in sorted((ROOT / "tests").rglob("test_*.py")):
        by_name[path.name].append(path.relative_to(ROOT).as_posix())
    duplicates = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    assert not duplicates, f"duplicate pytest module basenames: {duplicates}"
