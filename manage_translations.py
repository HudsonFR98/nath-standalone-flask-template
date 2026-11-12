#!/usr/bin/env python3
"""
Translation management script for Nath Standalone Flask Template application.

This script helps with:
1. Extracting translatable strings from the codebase
2. Updating existing translation files
3. Adding new languages
4. Compiling translation files

Usage:
    python manage_translations.py extract          # Extract strings to messages.pot
    python manage_translations.py update          # Update existing translation files
    python manage_translations.py compile         # Compile all translation files
    python manage_translations.py init <lang>     # Initialize new language
    python manage_translations.py all             # Run extract, update, and compile
"""

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TRANSLATIONS = ROOT / "nath_standalone_flask_template" / "translations"
BABEL_CFG = ROOT / "babel.cfg"


def _pybabel_argv(*args: str) -> list[str]:
    """Use pybabel from the same venv as this interpreter (Docker dev, CI, host venv)."""
    pybabel = Path(sys.executable).with_name("pybabel")
    if pybabel.is_file():
        return [str(pybabel), *args]
    return [sys.executable, "-m", "babel.messages.frontend", *args]


def run_command(argv: list[str], description: str) -> bool:
    """Run a command and handle errors"""
    print(f"Running: {description}")
    try:
        subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed:")
        print(f"  Error: {e.stderr or e.stdout}")
        return False


def extract_strings() -> bool:
    """Extract translatable strings from the codebase"""
    return run_command(
        _pybabel_argv(
            "extract",
            "-F",
            str(BABEL_CFG.relative_to(ROOT)),
            "-k",
            "_",
            "-o",
            str(TRANSLATIONS / "messages.pot"),
            "nath_standalone_flask_template",
        ),
        "Extracting translatable strings",
    )


def update_translations() -> bool:
    """Update existing translation files with new strings"""
    success = True
    pot = TRANSLATIONS / "messages.pot"
    for lang in ("en", "fr"):
        lang_dir = TRANSLATIONS / lang / "LC_MESSAGES"
        if lang_dir.is_dir():
            success &= run_command(
                _pybabel_argv(
                    "update",
                    "-i",
                    str(pot),
                    "-d",
                    str(TRANSLATIONS),
                    "-l",
                    lang,
                ),
                f"Updating {lang} translations",
            )
    return success


def compile_translations() -> bool:
    """Compile all translation files"""
    return run_command(
        _pybabel_argv("compile", "-d", str(TRANSLATIONS)),
        "Compiling translation files",
    )


def init_language(lang: str) -> bool:
    """Initialize a new language"""
    if not lang:
        print("Error: Language code required (e.g., 'es' for Spanish)")
        return False

    lang_dir = TRANSLATIONS / lang / "LC_MESSAGES"
    lang_dir.mkdir(parents=True, exist_ok=True)

    return run_command(
        _pybabel_argv(
            "init",
            "-i",
            str(TRANSLATIONS / "messages.pot"),
            "-d",
            str(TRANSLATIONS),
            "-l",
            lang,
        ),
        f"Initializing {lang} translation file",
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == "extract":
        extract_strings()
    elif command == "update":
        update_translations()
    elif command == "compile":
        compile_translations()
    elif command == "init":
        if len(sys.argv) < 3:
            print("Error: Language code required for init command")
            return
        init_language(sys.argv[2])
    elif command == "all":
        extract_strings()
        update_translations()
        compile_translations()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
