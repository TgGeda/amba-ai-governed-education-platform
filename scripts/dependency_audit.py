from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

DEPRECATED_MODULES = (
    "amba_ai.core.content_delivery_v2",
    "amba_ai.core.content_delivery_v3",
    "amba_ai.core.summary_fast_path",
    "amba_ai.core.professional_learning_pack_v4",
    "amba_ai.core.document_agnostic_learning_pack_v6_4",
    "amba_ai.core.rag_engine",
)

SHORT_TO_FULL = {
    "content_delivery_v2": "amba_ai.core.content_delivery_v2",
    "content_delivery_v3": "amba_ai.core.content_delivery_v3",
    "summary_fast_path": "amba_ai.core.summary_fast_path",
    "professional_learning_pack_v4": "amba_ai.core.professional_learning_pack_v4",
    "document_agnostic_learning_pack_v6_4": "amba_ai.core.document_agnostic_learning_pack_v6_4",
    "rag_engine": "amba_ai.core.rag_engine",
}

MIGRATION_MAP = {
    "amba_ai.core.content_delivery_v2": "amba_ai.services.content_delivery_service",
    "amba_ai.core.content_delivery_v3": "amba_ai.services.content_delivery_service",
    "amba_ai.core.summary_fast_path": "amba_ai.services.content_delivery_service",
    "amba_ai.core.professional_learning_pack_v4": "amba_ai.services.content_delivery_service",
    "amba_ai.core.document_agnostic_learning_pack_v6_4": "amba_ai.services.content_delivery_service",
    "amba_ai.core.rag_engine": "amba_ai.rag.engine",
}

KIND_SEVERITY_MAP = {
    "dynamic-import": "CRITICAL",
    "import": "HIGH",
    "from-import": "HIGH",
    "relative-import": "HIGH",
    "attribute-access": "HIGH",
    "string-ref": "LOW",
}

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".idea",
    ".vscode",
}

SCANNABLE_TEXT_EXTENSIONS = {
    ".py",
    ".json",
    ".qss",
    ".spec",
    ".bat",
    ".cmd",
    ".sh",
    ".txt",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
}


@dataclass(frozen=True, slots=True)
class Reference:
    file: Path
    line: int
    kind: str
    symbol: str
    severity: str
    replacement: str
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": str(self.file),
            "line": self.line,
            "kind": self.kind,
            "severity": self.severity,
            "symbol": self.symbol,
            "replacement": self.replacement,
            "snippet": self.snippet,
        }


@dataclass
class Report:
    references: dict[str, list[Reference]] = field(default_factory=dict)
    seen: set[tuple[str, int, str, str]] = field(default_factory=set)

    def add(self, module: str, ref: Reference) -> None:
        key = (str(ref.file), ref.line, module, ref.kind)
        if key in self.seen:
            return
        self.seen.add(key)
        self.references.setdefault(module, []).append(ref)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total_issues": sum(len(refs) for refs in self.references.values()),
                "deprecated_modules_scanned": len(DEPRECATED_MODULES),
            },
            "findings": {
                module: [ref.to_dict() for ref in refs]
                for module, refs in self.references.items()
            },
        }

    def print_text(self) -> int:
        print("\n" + "=" * 90)
        print("AMBA-AI ENTERPRISE DEPRECATION AUDIT REPORT")
        print("=" * 90)

        total = 0
        for module in DEPRECATED_MODULES:
            refs = self.references.get(module, [])
            replacement = MIGRATION_MAP.get(module, "None")
            print(f"\nTarget: {module}")
            print(f"Target Replacement: {replacement}")
            print("-" * (8 + len(module)))

            if not refs:
                print("  [OK] No usages found.")
                continue

            total += len(refs)
            for ref in sorted(refs, key=lambda r: (str(r.file), r.line)):
                snip = f" -> {ref.snippet}" if ref.snippet else ""
                print(f"  {ref.file}:{ref.line:<5} [{ref.severity}] [{ref.kind}] {ref.symbol}{snip}")

        print("\n" + "=" * 90)
        print(f"AUDIT SUMMARY: {total} reference(s) detected across the repository.")
        print("=" * 90 + "\n")
        return total


def resolve_package_for_file(file_path: Path, repo_root: Path) -> list[str]:
    try:
        rel = file_path.relative_to(repo_root)
    except ValueError:
        return []

    parts = list(rel.parts)
    if "src" in parts:
        src_idx = parts.index("src")
        parts = parts[src_idx + 1 :]

    if not parts:
        return []

    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]

    if parts[-1] == "__init__":
        parts.pop()

    return parts[:-1]


class DynamicAndStaticImportVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, repo_root: Path, report: Report) -> None:
        self.file_path = file_path
        self.repo_root = repo_root
        self.report = report
        self.current_package = resolve_package_for_file(file_path, repo_root)
        self._aliases: dict[str, str] = {}

    def _resolve_relative(self, level: int, module: str | None) -> str:
        if level <= 0:
            return module or ""

        if level > len(self.current_package) + 1:
            return module or ""

        base = self.current_package[: len(self.current_package) - (level - 1)]
        if module:
            return ".".join(base + [module])
        return ".".join(base)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name
            self._aliases[asname] = name

            for target in DEPRECATED_MODULES:
                if name == target or name.startswith(f"{target}."):
                    kind = "import"
                    self.report.add(
                        target,
                        Reference(
                            file=self.file_path,
                            line=node.lineno,
                            kind=kind,
                            symbol=name,
                            severity=KIND_SEVERITY_MAP[kind],
                            replacement=MIGRATION_MAP.get(target, "None"),
                        ),
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        resolved_module = self._resolve_relative(node.level, node.module)

        for alias in node.names:
            imported_symbol = alias.name
            local_name = alias.asname or imported_symbol
            full_imported = f"{resolved_module}.{imported_symbol}" if resolved_module else imported_symbol
            self._aliases[local_name] = full_imported

        for target in DEPRECATED_MODULES:
            if resolved_module == target or resolved_module.startswith(f"{target}."):
                symbols = ", ".join(a.name for a in node.names)
                kind = "relative-import" if node.level > 0 else "from-import"
                self.report.add(
                    target,
                    Reference(
                        file=self.file_path,
                        line=node.lineno,
                        kind=kind,
                        symbol=f"from {resolved_module} import {symbols}",
                        severity=KIND_SEVERITY_MAP[kind],
                        replacement=MIGRATION_MAP.get(target, "None"),
                    ),
                )

        if resolved_module in {"amba_ai.core", "core"}:
            for alias in node.names:
                if alias.name in SHORT_TO_FULL:
                    target = SHORT_TO_FULL[alias.name]
                    kind = "relative-import" if node.level > 0 else "from-import"
                    self.report.add(
                        target,
                        Reference(
                            file=self.file_path,
                            line=node.lineno,
                            kind=kind,
                            symbol=f"from {resolved_module} import {alias.name}",
                            severity=KIND_SEVERITY_MAP[kind],
                            replacement=MIGRATION_MAP.get(target, "None"),
                        ),
                    )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        chain: list[str] = [node.attr]
        curr: ast.AST = node.value
        while isinstance(curr, ast.Attribute):
            chain.append(curr.attr)
            curr = curr.value

        if isinstance(curr, ast.Name):
            chain.append(curr.id)
            chain.reverse()
            root = chain[0]
            resolved_root = self._aliases.get(root, root)
            full_attr_path = ".".join([resolved_root] + chain[1:])

            for target in DEPRECATED_MODULES:
                if full_attr_path == target or full_attr_path.startswith(f"{target}."):
                    kind = "attribute-access"
                    self.report.add(
                        target,
                        Reference(
                            file=self.file_path,
                            line=node.lineno,
                            kind=kind,
                            symbol=full_attr_path,
                            severity=KIND_SEVERITY_MAP[kind],
                            replacement=MIGRATION_MAP.get(target, "None"),
                        ),
                    )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        is_importlib = False
        is_dunder_import = False

        if isinstance(func, ast.Attribute) and func.attr == "import_module":
            is_importlib = True
        elif isinstance(func, ast.Name):
            if func.id == "import_module":
                is_importlib = True
            elif func.id == "__import__":
                is_dunder_import = True

        if (is_importlib or is_dunder_import) and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                mod_str = first_arg.value.strip()

                pkg_str = None
                for kw in node.keywords:
                    if kw.arg == "package" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        pkg_str = kw.value.value.strip()

                resolved = mod_str
                if mod_str.startswith("."):
                    level = len(mod_str) - len(mod_str.lstrip("."))
                    sub = mod_str.lstrip(".")
                    if pkg_str:
                        base = pkg_str.split(".")
                        resolved = ".".join(base[: len(base) - (level - 1)] + ([sub] if sub else []))
                    else:
                        resolved = self._resolve_relative(level, sub if sub else None)

                for target in DEPRECATED_MODULES:
                    if resolved == target or resolved.startswith(f"{target}."):
                        kind = "dynamic-import"
                        self.report.add(
                            target,
                            Reference(
                                file=self.file_path,
                                line=node.lineno,
                                kind=kind,
                                symbol=resolved,
                                severity=KIND_SEVERITY_MAP[kind],
                                replacement=MIGRATION_MAP.get(target, "None"),
                            ),
                        )

        self.generic_visit(node)


def find_files(root: Path) -> Iterable[Path]:
    for entry in root.iterdir():
        if entry.name in IGNORED_DIRS or entry.name.startswith("_debris_archive"):
            continue

        if entry.is_dir():
            yield from find_files(entry)
        elif entry.is_file():
            yield entry


def scan_source_ast(file_path: Path, repo_root: Path, report: Report) -> None:
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(file_path))
        visitor = DynamicAndStaticImportVisitor(file_path, repo_root, report)
        visitor.visit(tree)
    except Exception:
        pass


def scan_raw_text(file_path: Path, report: Report, this_script: Path) -> None:
    if file_path.resolve() == this_script.resolve():
        return

    ext = file_path.suffix.lower()
    if ext not in SCANNABLE_TEXT_EXTENSIONS and not file_path.name.startswith("amba_ai.spec"):
        return

    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return

    for line_idx, line in enumerate(lines, start=1):
        for target in DEPRECATED_MODULES:
            if target in line:
                kind = "string-ref"
                report.add(
                    target,
                    Reference(
                        file=file_path,
                        line=line_idx,
                        kind=kind,
                        symbol=target,
                        severity=KIND_SEVERITY_MAP[kind],
                        replacement=MIGRATION_MAP.get(target, "None"),
                        snippet=line.strip()[:100],
                    ),
                )

        for short_name, target in SHORT_TO_FULL.items():
            if short_name in line:
                if any(delim + short_name in line for delim in ("'", '"', "/", "\\", ".")):
                    kind = "string-ref"
                    report.add(
                        target,
                        Reference(
                            file=file_path,
                            line=line_idx,
                            kind=kind,
                            symbol=short_name,
                            severity=KIND_SEVERITY_MAP[kind],
                            replacement=MIGRATION_MAP.get(target, "None"),
                            snippet=line.strip()[:100],
                        ),
                    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AmbaAI Deprecation Dependency Auditor")
    parser.add_argument("repo_root", nargs="?", default=None, help="Root path of repository")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    args = parser.parse_args()

    this_file = Path(__file__).resolve()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else this_file.parent.parent

    if not repo_root.exists() or not repo_root.is_dir():
        if args.json:
            print(json.dumps({"error": f"Target repository directory does not exist: {repo_root}"}))
        else:
            print(f"[ERROR] Target repository directory does not exist: {repo_root}")
        sys.exit(2)

    report = Report()
    all_files = list(find_files(repo_root))

    for path in all_files:
        if path.suffix.lower() == ".py":
            scan_source_ast(path, repo_root, report)
        scan_raw_text(path, report, this_file)

    total_issues = sum(len(refs) for refs in report.references.values())

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_text()

    sys.exit(1 if total_issues > 0 else 0)


if __name__ == "__main__":
    main()