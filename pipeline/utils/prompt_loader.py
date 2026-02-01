# pipeline/utils/prompt_loader.py
from __future__ import annotations

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


class PromptError(Exception):
    pass


def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise PromptError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


_PLACEHOLDER_RE = re.compile(r"{([a-zA-Z_][a-zA-Z0-9_]*)}")


def render_prompt(filename: str, **kwargs) -> str:
    """
    Safe prompt rendering:
    - Only replaces placeholders of the form {identifier} (e.g., {law_text})
    - Leaves all other braces alone (e.g., FO(.) blocks like 'vocabulary V { ... }')
    """
    template = load_prompt(filename)

    # Replace only known keys
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))

    # Detect unreplaced placeholders that look like {identifier}
    missing = sorted(set(_PLACEHOLDER_RE.findall(template)))
    if missing:
        raise PromptError(f"Prompt template missing placeholder(s): {', '.join(missing)}")

    return template
