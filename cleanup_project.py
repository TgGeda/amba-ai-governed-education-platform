#!/usr/bin/env python3
"""
cleanup_project.py
------------------
Autonomous cleanup and sanitation utility for the AmbaAI codebase.
Detects and archives/removes:
  - Root patch, install, and repair scripts (45+ files)
  - Temporary dump manifests, inventories, and zip packages
  - Backup files (*.bak), copy duplicates (* - Copy*), and scratch directories
  - Python bytecode cache (__pycache__, *.pyc, *.pyo)

Usage:
  python cleanup_project.py           # Safe mode: moves clutter into _debris_archive_<timestamp>/
  python cleanup_project.py --dry-run # Preview what would be removed without making changes
  python cleanup_project.py --purge   # Permanently delete instead of archiving
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import sys

# Whitelist: Essential project files and folders that MUST NEVER be touched
PROTECTED_ROOT_ITEMS = {
    "src",
    "data",
    "tests",
    "assets",
    "backup",
    "scripts",
    "requirements.txt",
    "requirements-dev.txt",
    "run_amba.bat",
    "amba_ai.spec",
    "README.md",
    "cleanup_project.py",
}

# Prefixes of root scripts that were one-off patches or installers
ROOT_SCRIPT_PREFIXES = (
    "patch_",
    "install_",
    "repair_",
    "collect_",
    "inspect_",
    "integrate_",
    "update_",
)

# Root-level temporary debug/manifest dump patterns
ROOT_FILE_GLOBS = [
    "ambaai_content_delivery_*.json",
    "ambaai_content_delivery_*.txt",
    "ambaai_content_delivery_*.zip",
    "ambaai_rag_integration_inventory.json",
]


class ProjectCleaner:
    def __init__(self, root_dir: Path, dry_run: bool = False, purge: bool = False) -> None:
        self.root = root_dir.resolve()
        self.dry_run = dry_run
        self.purge = purge
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.archive_dir = self.root / f"_debris_archive_{self.timestamp}"

        self.to_remove_files: list[Path] = []
        self.to_remove_dirs: list[Path] = []
        self.total_bytes = 0

    def scan(self) -> None:
        """Scan the project tree for all unnecessary files and directories."""
        self._scan_root_debris()
        self._scan_tree_debris(self.root / "src")
        self._scan_tree_debris(self.root / "tests")

    def _scan_root_debris(self) -> None:
        for item in self.root.iterdir():
            if item.name in PROTECTED_ROOT_ITEMS or item.name.startswith(".git"):
                continue

            # Root-level patch scripts
            if item.is_file() and item.suffix == ".py":
                if item.name.startswith(ROOT_SCRIPT_PREFIXES):
                    self._add_file(item)
                    continue

            # Root manifest dumps and inventories
            if item.is_file():
                for pattern in ROOT_FILE_GLOBS:
                    if item.match(pattern):
                        self._add_file(item)
                        break

            # Scratch folders (e.g. 'test document')
            if item.is_dir() and item.name.lower() in {"test document", "test_document"}:
                self._add_dir(item)

    def _scan_tree_debris(self, base_dir: Path) -> None:
        if not base_dir.exists():
            return

        for path in base_dir.rglob("*"):
            # Bytecode directories
            if path.is_dir() and path.name == "__pycache__":
                if path not in self.to_remove_dirs:
                    self._add_dir(path)
                continue

            # Bytecode files outside __pycache__
            if path.is_file() and path.suffix in {".pyc", ".pyo"}:
                self._add_file(path)
                continue

            # Backup files (*.bak, *.bak.*)
            if path.is_file() and (".bak" in path.name.lower() or path.suffix == ".bak"):
                self._add_file(path)
                continue

            # Duplicate copy files (* - Copy*)
            if path.is_file() and (" - copy" in path.stem.lower() or " - copy" in path.name.lower()):
                self._add_file(path)
                continue

    def _add_file(self, path: Path) -> None:
        if path not in self.to_remove_files:
            try:
                self.total_bytes += path.stat().st_size
            except OSError:
                pass
            self.to_remove_files.append(path)

    def _add_dir(self, path: Path) -> None:
        if path not in self.to_remove_dirs:
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        self.total_bytes += f.stat().st_size
                    except OSError:
                        pass
            self.to_remove_dirs.append(path)

    def execute(self) -> None:
        print(f"\n{'='*70}")
        print(f"AmbaAI Codebase Sanitizer — {'DRY RUN' if self.dry_run else 'EXECUTING'}")
        print(f"Project Root: {self.root}")
        print(f"Files flagged: {len(self.to_remove_files)}")
        print(f"Directories flagged: {len(self.to_remove_dirs)}")
        print(f"Space to reclaim: {self.total_bytes / (1024 * 1024):.2f} MB")
        print(f"{'='*70}\n")

        if not self.to_remove_files and not self.to_remove_dirs:
            print("✨ Codebase is already clean! No debris found.")
            return

        if self.dry_run:
            print("--- Flagged Files ---")
            for f in sorted(self.to_remove_files):
                print(f"  [FILE] {f.relative_to(self.root)}")
            print("\n--- Flagged Directories ---")
            for d in sorted(self.to_remove_dirs):
                print(f"  [DIR]  {d.relative_to(self.root)}")
            print("\n[Dry Run Completed] No files were modified.")
            return

        manifest: list[dict[str, str]] = []

        if not self.purge:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"📦 Staging clutter into: {self.archive_dir.name}\n")

        # 1. Process Files
        for f in self.to_remove_files:
            rel = f.relative_to(self.root)
            manifest.append({"type": "file", "original_path": str(rel)})

            if self.purge:
                try:
                    f.unlink(missing_ok=True)
                    print(f"  [DELETED] {rel}")
                except OSError as e:
                    print(f"  [ERROR] Could not delete {rel}: {e}")
            else:
                target = self.archive_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(f), str(target))
                    print(f"  [ARCHIVED] {rel}")
                except OSError as e:
                    print(f"  [ERROR] Could not move {rel}: {e}")

        # 2. Process Directories
        for d in self.to_remove_dirs:
            if not d.exists():
                continue
            rel = d.relative_to(self.root)
            manifest.append({"type": "directory", "original_path": str(rel)})

            if self.purge:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                    print(f"  [DELETED DIR] {rel}")
                except OSError as e:
                    print(f"  [ERROR] Could not delete directory {rel}: {e}")
            else:
                target = self.archive_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(d), str(target))
                    print(f"  [ARCHIVED DIR] {rel}")
                except OSError as e:
                    print(f"  [ERROR] Could not move directory {rel}: {e}")

        # 3. Write Rollback Manifest if archived
        if not self.purge:
            manifest_file = self.archive_dir / "manifest_rollback.json"
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            print(f"\n✅ Done! Archived {len(manifest)} items.")
            print(f"📄 Rollback manifest written to: {manifest_file.name}")
        else:
            print(f"\n✅ Done! Purged {len(manifest)} items.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up debris and temporary patch scripts.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the cleanup without modifying any files.",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Permanently delete debris instead of moving to an archive directory.",
    )
    args = parser.parse_args()

    cleaner = ProjectCleaner(root_dir=Path.cwd(), dry_run=args.dry_run, purge=args.purge)
    cleaner.scan()
    cleaner.execute()


if __name__ == "__main__":
    main()
