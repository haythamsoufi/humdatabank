from __future__ import annotations

import argparse
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable

EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".html": "html",
    ".dart": "dart",
}

LANGUAGES: Iterable[str] = ("python", "javascript", "html", "dart")

EXCLUDED_DIRS = {
    "node_modules",
    ".next",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    "out",
    "build",
    "dist",
    "venv",
    ".venv",
}


def is_comment_line(line: str, language: str, in_multiline_comment: bool) -> tuple[bool, bool]:
    """
    Check if a line is a comment line.
    
    Returns:
        tuple[bool, bool]: (is_comment, new_multiline_state)
    """
    stripped = line.strip()
    
    # Empty lines are not comments
    if not stripped:
        return False, in_multiline_comment
    
    if language == "python":
        # Python: # for single-line comments
        # Check if line starts with # (after stripping)
        if stripped.startswith("#"):
            return True, False
        # Check for inline comments (but don't count the line as comment if it has code)
        # For counting purposes, if the line has code before #, it's not a comment line
        return False, False
    
    elif language in ("javascript", "dart"):
        # JavaScript/Dart: // for single-line, /* */ for multi-line
        if in_multiline_comment:
            # Check if multiline comment ends on this line
            if "*/" in stripped:
                # This line is part of the comment
                return True, False
            return True, True
        
        # Check for single-line comment
        if "//" in stripped:
            # Check if it's a full-line comment (starts with //)
            if stripped.startswith("//"):
                return True, False
            # Inline comment - line has code, so not a comment line
            return False, False
        
        # Check for start of multiline comment
        if "/*" in stripped:
            # Check if it ends on the same line
            if "*/" in stripped:
                # Check if line is only comment
                before_comment = stripped.split("/*")[0].strip()
                if not before_comment:
                    return True, False
                return False, False
            # Multiline comment starts
            # Check if there's code before the comment
            before_comment = stripped.split("/*")[0].strip()
            if not before_comment:
                return True, True
            return False, True
        
        return False, False
    
    elif language == "html":
        # HTML: <!-- --> for comments
        if in_multiline_comment:
            # Check if comment ends
            if "-->" in stripped:
                return True, False
            return True, True
        
        # Check for HTML comment
        if "<!--" in stripped:
            # Check if it ends on the same line
            if "-->" in stripped:
                # Check if line is only comment
                before_comment = stripped.split("<!--")[0].strip()
                if not before_comment:
                    return True, False
                return False, False
            # Multiline comment starts
            before_comment = stripped.split("<!--")[0].strip()
            if not before_comment:
                return True, True
            return False, True
        
        return False, False
    
    elif language == "yaml":
        # YAML: # for comments
        if stripped.startswith("#"):
            return True, False
        return False, False
    
    return False, False


def count_code_lines(file_path: Path, language: str) -> int:
    """
    Count non-comment lines in a file.
    """
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            count = 0
            in_multiline_comment = False
            
            for line in handle:
                is_comment, in_multiline_comment = is_comment_line(
                    line, language, in_multiline_comment
                )
                if not is_comment:
                    count += 1
            
            return count
    except OSError:
        return 0


def count_lines(target_dir: Path, excluded_dirs: Iterable[str]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)

    excluded = {name.lower() for name in excluded_dirs}

    for root, dirnames, filenames in os.walk(target_dir):
        if excluded:
            dirnames[:] = [d for d in dirnames if d.lower() not in excluded]

        for filename in filenames:
            path = Path(root, filename)
            language = EXTENSION_MAP.get(path.suffix.lower())
            if language is None:
                continue

            code_lines = count_code_lines(path, language)
            counts[language] += code_lines

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count code lines (excluding comments) for Python, JavaScript, HTML, and Dart files."
    )
    parser.add_argument(
        "directories",
        nargs="*",
        help="Directories to scan. Defaults to Backoffice, Website, and MobileApp when omitted.",
    )
    parser.add_argument(
        "--include-deps",
        action="store_true",
        help="Include third-party folders such as node_modules and .next.",
    )
    args = parser.parse_args()

    directory_args = args.directories or ["Backoffice", "Website", "MobileApp"]
    excluded_dirs = [] if args.include_deps else sorted(EXCLUDED_DIRS)

    project_total_counts: Dict[str, int] = defaultdict(int)

    for directory in directory_args:
        target_dir = Path(directory).resolve()
        if not target_dir.exists():
            print(f"[skip] Directory not found: {target_dir}")
            continue

        print(f"\nScanning {target_dir} ...")
        counts = count_lines(target_dir, excluded_dirs)
        total_lines = sum(counts.get(language, 0) for language in LANGUAGES)

        print(f"{target_dir.name}:")
        if total_lines == 0:
            print("  No matching files found.")
            continue

        printed_any = False
        for language in LANGUAGES:
            language_count = counts.get(language, 0)
            if language_count == 0:
                continue

            printed_any = True
            percentage = (language_count / total_lines) * 100
            print(
                f"  {language.capitalize():>10}: "
                f"{language_count:>12,}  ({percentage:6.2f}%)"
            )
            project_total_counts[language] += language_count

        if not printed_any:
            print("  No matching files found.")

        print(f"  {'Total':>10}: {total_lines:>12,}  (100.00%)")

    # Print project overall totals
    project_total_lines = sum(project_total_counts.get(language, 0) for language in LANGUAGES)
    if project_total_lines > 0:
        print(f"\n{'=' * 60}")
        print("Project Overall Total:")
        printed_any = False
        for language in LANGUAGES:
            language_count = project_total_counts.get(language, 0)
            if language_count == 0:
                continue

            printed_any = True
            percentage = (language_count / project_total_lines) * 100
            print(
                f"  {language.capitalize():>10}: "
                f"{language_count:>12,}  ({percentage:6.2f}%)"
            )

        if printed_any:
            print(f"  {'Total':>10}: {project_total_lines:>12,}  (100.00%)")


if __name__ == "__main__":
    main()

