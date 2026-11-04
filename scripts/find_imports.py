from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import sys

FILE_MOVES: list[tuple[str, str]] = [
    (
        "src/amba_ai/ui/views/library/document_store.py",
        "src/amba_ai/db/document_store.py",
    ),
    (
        "src/amba_ai/ui/views/library/sync_service.py",
        "src/amba_ai/db/sync_service.py",
    ),
    (
        "src/amba_ai/ui/views/library/autotag_service.py",
        "src/amba_ai/services/autotag_service.py",
    ),
    (
        "src/amba_ai/ui/views/library/semantic_search.py",
        "src/amba_ai/services/semantic_search.py",
    ),
    (
        "src/amba_ai/ui/views/library/heatmap_widgets.py",
        "src/amba_ai/ui/components/heatmap_widgets.py",
    ),
    (
        "src/amba_ai/ui/views/library/permissions_context.py",
        "src/amba_ai/models/permissions_context.py",
    ),
]

FULL_MODULE_REPLACEMENTS: list[tuple[str, str]] = [
    (
        "amba_ai.ui.views.library.document_store",
        "amba_ai.db.document_store",
    ),
    (
        "amba_ai.ui.views.library.sync_service",
        "amba_ai.db.sync_service",
    ),
    (
        "amba_ai.ui.views.library.autotag_service",
        "amba_ai.services.autotag_service",
    ),
    (
        "amba_ai.ui.views.library.semantic_search",
        "amba_ai.services.semantic_search",
    ),
    (
        "amba_ai.ui.views.library.heatmap_widgets",
        "amba_ai.ui.components.heatmap_widgets",
    ),
    (
        "amba_ai.ui.views.library.permissions_context",
        "amba_ai.models.permissions_context",
    ),
]

RELATIVE_IMPORT_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\bfrom\s+\.document_store\b", "from amba_ai.db.document_store"),
    (r"\bfrom\s+\.sync_service\b", "from amba_ai.db.sync_service"),
    (r"\bfrom\s+\.autotag_service\b", "from amba_ai.services.autotag_service"),
    (r"\bfrom\s+\.semantic_search\b", "from amba_ai.services.semantic_search"),
    (r"\bfrom\s+\.heatmap_widgets\b", "from amba_ai.ui.components.heatmap_widgets"),
    (r"\bfrom\s+\.permissions_context\b", "from amba_ai.models.permissions_context"),
]

IGNORED_DIRS: set[str] = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "build",
    "dist",
}


class RepositoryMigrator:
    def __init__(self, repo_root: Path, dry_run: bool = False, leave_shims: bool = False) -> None:
        self.root = repo_root.resolve()
        self.dry_run = dry_run
        self.leave_shims = leave_shims
        self.moved_count = 0
        self.modified_files: set[Path] = set()

    def run(self) -> None:
        print(f"\nStarting repository realignment at: {self.root}")
        print(f"Mode: {'DRY RUN' if self.dry_run else 'EXECUTE'}\n")

        self.move_files()
        self.rewrite_imports()
        self.clean_empty_directories()

        print(f"\nMigration finished:")
        print(f"  Files moved: {self.moved_count}")
        print(f"  Files updated with new imports: {len(self.modified_files)}")

    def move_files(self) -> None:
        for src_rel, dst_rel in FILE_MOVES:
            src_path = self.root / src_rel
            dst_path = self.root / dst_rel

            if not src_path.exists():
                continue

            print(f"[MOVE] {src_rel} -> {dst_rel}")
            if not self.dry_run:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                init_file = dst_path.parent / "__init__.py"
                if not init_file.exists():
                    init_file.touch()

                if self.leave_shims:
                    content = src_path.read_text(encoding="utf-8", errors="ignore")
                    shutil.move(str(src_path), str(dst_path))
                    mod_target = dst_rel.replace("src/", "").replace(".py", "").replace("/", ".")
                    src_path.write_text(f"from {mod_target} import *\n", encoding="utf-8")
                else:
                    shutil.move(str(src_path), str(dst_path))

            self.moved_count += 1

    def rewrite_imports(self) -> None:
        for py_path in self.find_python_files(self.root / "src"):
            self.process_file(py_path)

        tests_dir = self.root / "tests"
        if tests_dir.exists():
            for py_path in self.find_python_files(tests_dir):
                self.process_file(py_path)

    def process_file(self, file_path: Path) -> None:
        try:
            original_text = file_path.read_text(encoding="utf-8")
        except Exception:
            return

        modified_text = original_text

        for old_mod, new_mod in FULL_MODULE_REPLACEMENTS:
            pattern_from = rf"\bfrom\s+{re.escape(old_mod)}\b"
            modified_text = re.sub(pattern_from, f"from {new_mod}", modified_text)

            pattern_import = rf"\bimport\s+{re.escape(old_mod)}\b"
            modified_text = re.sub(pattern_import, f"import {new_mod}", modified_text)

        for rel_pattern, replacement in RELATIVE_IMPORT_REPLACEMENTS:
            modified_text = re.sub(rel_pattern, replacement, modified_text)

        if modified_text != original_text:
            try:
                ast.parse(modified_text, filename=str(file_path))
            except SyntaxError as e:
                print(f"[ERROR] Import rewrite caused syntax error in {file_path}: {e}")
                return

            if not self.dry_run:
                file_path.write_text(modified_text, encoding="utf-8")

            rel = file_path.relative_to(self.root)
            print(f"[REWRITE] Updated imports in {rel}")
            self.modified_files.add(file_path)

    def find_python_files(self, directory: Path) -> list[Path]:
        results: list[Path] = []
        if not directory.exists():
            return results

        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith("_debris")]
            for file in files:
                if file.endswith(".py"):
                    results.append(Path(root) / file)
        return results

    def clean_empty_directories(self) -> None:
        if self.dry_run:
            return

        target_dir = self.root / "src" / "amba_ai" / "ui" / "views" / "library"
        if target_dir.exists():
            remaining = list(target_dir.iterdir())
            if not remaining or all(f.name == "__pycache__" for f in remaining):
                shutil.rmtree(target_dir, ignore_errors=True)
                print(f"[CLEANUP] Removed empty directory: {target_dir.relative_to(self.root)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Relocate backend services out of UI layer and fix imports.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate moves and import rewrites without modifying files.")
    parser.add_argument("--leave-shims", action="store_true", help="Leave backwards-compatible re-export shims at old paths.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    if not (repo_root / "src").exists():
        repo_root = Path.cwd().resolve()

    migrator = RepositoryMigrator(repo_root=repo_root, dry_run=args.dry_run, leave_shims=args.leave_shims)
    migrator.run()


if __name__ == "__main__":
    main()