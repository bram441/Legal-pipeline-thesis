# pipeline/kb/repair_hints.py
"""Deterministic hints bundled into KB repair prompts so the model addresses known patterns."""

import re


def build_machine_repair_hints(error_message: str, previous_output: str) -> str:
    """
    Short, imperative bullets derived from the IDP error and the previous FO string.
    When nothing matches, return a neutral line so the template always has content.
    """
    hints = []
    em = error_message or ""
    eml = em.lower()
    prev = previous_output or ""

    if "*" in em or "expected '[*⨯]'" in eml or "expected ',' or ':'" in eml:
        hints.append(
            "The parser message mentions `*` or a comma/colon error: in `vocabulary V {`, "
            "never use markdown bullets. Each declaration is ONE line; there must be NO `*` "
            "between `Bool`/`Int`/`Real` and the next symbol unless it is a real product type "
            "`A * B` inside a signature (spaces around `*`)."
        )

    if re.search(r":\s*Bool\s*\*[A-Za-z_]", prev) or re.search(r"->\s*Bool\s*\*[A-Za-z_]", prev):
        hints.append(
            "AUTOCHECK on your previous output: found `Bool` or `-> Bool` immediately followed by `*` "
            "and an identifier — that is invalid. Split into two lines (two declarations); delete the stray `*`."
        )

    if re.search(r"\bin\s+[A-Za-z_][A-Za-z0-9_]*\*\s*[,;]", prev) or " in person*" in eml:
        hints.append(
            "AUTOCHECK: quantifiers must be `! x in Type:` or `? x in Type:` with a single type name — "
            "not `in Person*` (the `*` is a parse error). Remove `*` after the type in quantifiers."
        )

    if "structure" in eml and "must not contain" in eml:
        hints.append("Do not output `structure S:V` in the KB — only vocabulary + theory.")

    if "kb lint" in eml:
        hints.append(
            "KB static lint failed — fix every issue listed in the error report (undeclared symbols, "
            "`let`, stray `*`, duplicate signatures). Do not resubmit the same broken patterns."
        )

    if re.search(r"\blet\b", prev, re.IGNORECASE):
        hints.append(
            "AUTOCHECK: previous output contains `let` — IDP FO has no let-bindings. "
            "Rewrite using `!` / `?` quantifiers and separate formulas."
        )

    if "undeclared symbol" in eml or "theory calls undeclared" in eml:
        hints.append(
            "Every identifier used as Predicate(...) or function(...) in the theory MUST be declared "
            "in `vocabulary V` with identical spelling (case-sensitive)."
        )

    if "duplicate vocabulary symbol" in eml or "conflicting signatures" in eml:
        hints.append("Use exactly ONE signature line per symbol name in the vocabulary.")

    if "𝔹" in em or "blackboard" in eml or "mathematical unicode" in eml:
        hints.append("Replace Unicode mathematical letters with ASCII (e.g. Bool, Real).")

    if not hints:
        return "(none — follow the ERROR REPORT below exactly; do not repeat the same malformed pattern.)"

    return "You MUST fix all of the following (in addition to the error report):\n" + "\n".join(
        "- " + h for h in hints
    )
