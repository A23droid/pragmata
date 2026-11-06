import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_EXCLUDES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".DS_Store",
}


@dataclass
class CodeSymbol:
    name: str
    kind: str  # class, function, method
    line_start: int
    line_end: int
    docstring: Optional[str] = None


@dataclass
class SearchMatch:
    file_path: str
    line_number: int
    line_content: str


@dataclass
class ProjectInspectionSummary:
    file_tree: List[Dict[str, Any]]
    total_files: int
    detected_languages: List[str]
    detected_frameworks: List[str]
    test_commands: List[str]
    readme_snippet: Optional[str] = None
    config_files: List[str] = field(default_factory=list)


class RepoInspector:
    """
    Syntax-aware repository inspector.
    Safely navigates file hierarchies, identifies frameworks, extracts symbols,
    and runs targeted code searches without executing untrusted code on the host.
    """

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path.resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """Prevent directory traversal attacks by validating path is strictly inside workspace."""
        clean_path = (self.workspace_path / relative_path).resolve()
        if not str(clean_path).startswith(str(self.workspace_path)):
            raise ValueError(f"Security error: Path '{relative_path}' traverses outside workspace boundary.")
        return clean_path

    def get_file_tree(
        self,
        max_depth: int = 4,
        max_files: int = 500,
        exclude_dirs: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        """Return structured file list up to max_depth."""
        excludes = exclude_dirs or DEFAULT_EXCLUDES
        tree = []
        files_count = 0

        for root, dirs, files in os.walk(self.workspace_path):
            rel_root = os.path.relpath(root, self.workspace_path)
            depth = 0 if rel_root == "." else len(Path(rel_root).parts)

            if depth >= max_depth:
                dirs.clear()
                continue

            # In-place filter directories
            dirs[:] = [d for d in dirs if d not in excludes and not d.startswith(".")]

            for f in sorted(files):
                if f.startswith(".") or f in excludes:
                    continue
                file_rel = os.path.normpath(os.path.join(rel_root, f)) if rel_root != "." else f
                full_p = Path(root) / f
                try:
                    size = full_p.stat().st_size
                except OSError:
                    size = 0

                tree.append({
                    "path": file_rel,
                    "name": f,
                    "extension": full_p.suffix,
                    "size_bytes": size,
                    "depth": depth + 1,
                })
                files_count += 1
                if files_count >= max_files:
                    logger.info(f"File tree exploration capped at {max_files} files.")
                    return tree

        return tree

    def detect_languages_and_frameworks(self) -> Dict[str, List[str]]:
        """Identify primary languages and frameworks based on manifest files."""
        languages = set()
        frameworks = set()
        config_files = []

        # Check for Python
        if (self.workspace_path / "pyproject.toml").exists() or (self.workspace_path / "requirements.txt").exists() or (self.workspace_path / "setup.py").exists():
            languages.add("Python")
            if (self.workspace_path / "pyproject.toml").exists():
                config_files.append("pyproject.toml")
                try:
                    content = (self.workspace_path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
                    if "fastapi" in content.lower():
                        frameworks.add("FastAPI")
                    if "django" in content.lower():
                        frameworks.add("Django")
                    if "flask" in content.lower():
                        frameworks.add("Flask")
                except Exception:
                    pass

        # Check for JavaScript / TypeScript
        pkg_json = self.workspace_path / "package.json"
        if pkg_json.exists():
            config_files.append("package.json")
            if (self.workspace_path / "tsconfig.json").exists():
                languages.add("TypeScript")
                config_files.append("tsconfig.json")
            else:
                languages.add("JavaScript")
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "next" in deps:
                    frameworks.add("Next.js")
                if "react" in deps:
                    frameworks.add("React")
                if "vue" in deps:
                    frameworks.add("Vue")
                if "express" in deps:
                    frameworks.add("Express")
            except Exception:
                pass

        # Check for Rust
        if (self.workspace_path / "Cargo.toml").exists():
            languages.add("Rust")
            config_files.append("Cargo.toml")

        # Check for Go
        if (self.workspace_path / "go.mod").exists():
            languages.add("Go")
            config_files.append("go.mod")

        return {
            "languages": sorted(list(languages)),
            "frameworks": sorted(list(frameworks)),
            "config_files": sorted(config_files),
        }

    def detect_test_commands(self) -> List[str]:
        """Detect available test runners and command recipes."""
        commands = []

        # Python test commands
        if (self.workspace_path / "pytest.ini").exists() or (self.workspace_path / "pyproject.toml").exists():
            commands.append("pytest")
            commands.append("python -m unittest")

        # JS/TS npm test
        pkg_json = self.workspace_path / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                scripts = data.get("scripts", {})
                if "test" in scripts:
                    commands.append("npm test")
                if "test:unit" in scripts:
                    commands.append("npm run test:unit")
            except Exception:
                pass

        # Makefile
        makefile = self.workspace_path / "Makefile"
        if makefile.exists():
            try:
                text = makefile.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"^test\s*:", text, re.MULTILINE):
                    commands.append("make test")
            except Exception:
                pass

        # Cargo test
        if (self.workspace_path / "Cargo.toml").exists():
            commands.append("cargo test")

        # Go test
        if (self.workspace_path / "go.mod").exists():
            commands.append("go test ./...")

        return sorted(list(set(commands)))

    def get_readme_snippet(self, max_lines: int = 60) -> Optional[str]:
        """Extract snippet of the README file if present."""
        for name in ["README.md", "README", "readme.md", "README.rst", "README.txt"]:
            readme_path = self.workspace_path / name
            if readme_path.exists():
                try:
                    lines = readme_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                    return "\n".join(lines[:max_lines])
                except Exception:
                    return None
        return None

    def search_code(
        self,
        query: str,
        max_matches: int = 25,
        file_extensions: Optional[List[str]] = None,
    ) -> List[SearchMatch]:
        """Search text/regex in source files with boundary guards."""
        matches = []
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            # Fallback to literal search if regex is invalid
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        for root, dirs, files in os.walk(self.workspace_path):
            dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES and not d.startswith(".")]

            for f in sorted(files):
                ext = Path(f).suffix.lower()
                if file_extensions and ext not in file_extensions:
                    continue
                if ext in {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".zip", ".tar", ".gz", ".pyc"}:
                    continue

                full_p = Path(root) / f
                rel_p = os.path.relpath(full_p, self.workspace_path)
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as fh:
                        for idx, line in enumerate(fh, start=1):
                            if pattern.search(line):
                                matches.append(SearchMatch(
                                    file_path=rel_p,
                                    line_number=idx,
                                    line_content=line.strip()[:200],
                                ))
                                if len(matches) >= max_matches:
                                    return matches
                except Exception:
                    continue

        return matches

    def read_file_content(
        self,
        relative_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        max_lines: int = 300,
    ) -> str:
        """Safely read lines from a file inside the workspace."""
        path = self._resolve_safe_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: '{relative_path}'")

        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()

        start = max(1, start_line) if start_line else 1
        end = min(len(lines), end_line) if end_line else min(len(lines), start + max_lines - 1)

        selected = lines[start - 1 : end]
        return "".join(selected)

    def extract_symbols(self, relative_path: str) -> List[CodeSymbol]:
        """Extract classes, functions, and methods using AST for Python and regex for other code."""
        path = self._resolve_safe_path(relative_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: '{relative_path}'")

        symbols: List[CodeSymbol] = []
        content = path.read_text(encoding="utf-8", errors="ignore")

        if path.suffix == ".py":
            try:
                tree = ast.parse(content, filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        doc = ast.get_docstring(node)
                        end_lineno = getattr(node, "end_lineno", node.lineno)
                        symbols.append(CodeSymbol(
                            name=node.name,
                            kind="class",
                            line_start=node.lineno,
                            line_end=end_lineno,
                            docstring=doc[:150] if doc else None,
                        ))
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(node)
                        end_lineno = getattr(node, "end_lineno", node.lineno)
                        symbols.append(CodeSymbol(
                            name=node.name,
                            kind="function",
                            line_start=node.lineno,
                            line_end=end_lineno,
                            docstring=doc[:150] if doc else None,
                        ))
            except SyntaxError as ex:
                logger.warning(f"Could not parse AST for {relative_path}: {ex}")

        # Regex symbol extraction for JS/TS/Go/Rust
        elif path.suffix in {".js", ".ts", ".jsx", ".tsx", ".go", ".rs"}:
            lines = content.splitlines()
            fn_pattern = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)")
            class_pattern = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)")
            const_fn_pattern = re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(")

            for idx, line in enumerate(lines, start=1):
                m_fn = fn_pattern.search(line) or const_fn_pattern.search(line)
                if m_fn:
                    symbols.append(CodeSymbol(
                        name=m_fn.group(1),
                        kind="function",
                        line_start=idx,
                        line_end=idx,
                    ))
                m_cls = class_pattern.search(line)
                if m_cls:
                    symbols.append(CodeSymbol(
                        name=m_cls.group(1),
                        kind="class",
                        line_start=idx,
                        line_end=idx,
                    ))

        return symbols

    def summarize(self) -> ProjectInspectionSummary:
        """Produce a consolidated project inspection summary."""
        tree = self.get_file_tree(max_depth=3)
        tech = self.detect_languages_and_frameworks()
        test_cmds = self.detect_test_commands()
        readme = self.get_readme_snippet()

        return ProjectInspectionSummary(
            file_tree=tree,
            total_files=len(tree),
            detected_languages=tech["languages"],
            detected_frameworks=tech["frameworks"],
            test_commands=test_cmds,
            readme_snippet=readme,
            config_files=tech["config_files"],
        )
