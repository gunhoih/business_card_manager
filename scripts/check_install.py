"""Check repository completeness and Python imports before starting the app.

Usage:
    uv run --no-sync python scripts/check_install.py
    uv run --no-sync python scripts/check_install.py --source-only
"""

import argparse
import ast
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "app.py",
    "pyproject.toml",
    "backend/__init__.py",
    "backend/classifier/__init__.py",
    "backend/classifier/service.py",
    "frontend/__init__.py",
    "frontend/ocr_page.py",
    "frontend/classifier_page.py",
    "scripts/setup_ocr.py",
)
IMPORT_MODULES = (
    "backend.classifier.service",
    "backend.contact.field_parser",
    "backend.ocr.service",
    "frontend.ocr_page",
    "frontend.classifier_page",
    "app",
)


def find_unmerged_files(root=ROOT):
    """A pending merge/rebase must be resolved outside the installer."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_sources(root=ROOT):
    """Check missing files, unmerged files, and parse errors without dependencies."""
    problems = []

    unmerged = find_unmerged_files(root)
    if unmerged:
        problems.append("Unresolved Git conflicts: " + ", ".join(unmerged))

    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            problems.append("Missing source file: " + name)

    paths = [root / "app.py"]
    for directory in ("backend", "frontend", "scripts"):
        folder = root / directory
        if folder.is_dir():
            paths.extend(sorted(folder.rglob("*.py")))

    for path in paths:
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeError, OSError) as error:
            name = path.relative_to(root)
            problems.append(f"Invalid Python source ({name}): {error}")

    return problems


def check_imports(root=ROOT):
    """Import the actual app modules, without launching Streamlit or using an API key."""
    sys.path.insert(0, str(root))
    problems = []
    for module_name in IMPORT_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as error:
            problems.append(f"Import failed ({module_name}): {type(error).__name__}: {error}")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check app source and imports")
    parser.add_argument("--source-only", action="store_true", help="Do not import installed packages")
    args = parser.parse_args(argv)

    problems = check_sources()
    if not problems and not args.source_only:
        problems.extend(check_imports())

    if problems:
        print("[FAILED] Installation readiness check:", file=sys.stderr)
        for problem in problems:
            print("  - " + problem, file=sys.stderr)
        print("Source files are not restored by 'uv sync'.", file=sys.stderr)
        print("Check 'git status' and restore or update your repository safely.", file=sys.stderr)
        print("Do not run 'git reset --hard' if you need local changes.", file=sys.stderr)
        return 1

    if args.source_only:
        print("[OK] Source files, syntax and Git conflict checks passed.")
    else:
        print("[OK] Source files, Python syntax and app imports passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
