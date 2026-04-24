# pipeline/utils/prompt_loader.py
from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Subfolders under prompts/ (paths are relative to PROMPTS_DIR, use forward slashes):
#   kb/           — law → FO compilation and repair (syntax, UNSAT, etc.)
#   le/           — Logical English: law_to_le, le_to_fo
#   extraction/   — case/query extraction, world_knowledge_lexical.txt, debug templates
#   translation/  — e.g. translate_to_english
#   nl/           — natural-language paraphrase for explanations
#
# Call sites use paths like render_prompt("kb/kb_compilation.txt", ...).


class PromptError(Exception):
    pass


def load_prompt(relative_path: str) -> str:
    """Load a prompt file. ``relative_path`` may include subdirs, e.g. ``kb/kb_compilation.txt``."""
    path = PROMPTS_DIR / relative_path.replace("\\", "/")
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


_PLACEHOLDER_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


def render_prompt(relative_path: str, **kwargs) -> str:
    """
    Safe prompt rendering:
    - Only replaces placeholders of the form {identifier} (e.g., {law_text})
    - Leaves all other braces alone (e.g., FO(.) blocks like 'vocabulary V { ... }')
    """
    template = load_prompt(relative_path)

    # Replace only known keys
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))

    # Detect unreplaced placeholders that look like {identifier}
    missing = sorted(set(_PLACEHOLDER_RE.findall(template)))
    if missing:
        raise PromptError(f"Prompt template missing placeholder(s): {', '.join(missing)}")

    return template
