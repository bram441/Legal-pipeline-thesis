# pipeline/kb/kb_lint.py
"""
Static checks on generated FO(.) **before** IDP.parse — catches common LLM mistakes
that waste repair cycles (stray `*`, `let`, undeclared symbols, duplicate vocab signatures).
"""

import re
from typing import Dict, List, Set

from pipeline.kb.schema import (
    _SIG_RE,
    _TYPE_RE,
    _VOCAB_RE,
    extract_schema_from_kb_fo,
)

# Calls in theory that are not user-declared symbols (IDP / FO built-ins).
_BUILTIN_CALLS = frozenset({"max", "min", "abs", "sqrt"})


class KBLintError(Exception):
    """Raised when KB text fails static lint (caller may map to KBCacheError)."""


def _vocab_body(kb_text: str) -> str | None:
    m = _VOCAB_RE.search(kb_text or "")
    return m.group(1) if m else None


def _theory_body(kb_text: str) -> str | None:
    m = re.search(r"\btheory\s+T\s*:\s*V\s*\{", kb_text or "", re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    start = kb_text.find("{", m.start())
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(kb_text)):
        if kb_text[i] == "{":
            depth += 1
        elif kb_text[i] == "}":
            depth -= 1
            if depth == 0:
                return kb_text[start + 1 : i]
    return None


def _lint_let_in_theory(theory: str) -> List[str]:
    issues = []
    if re.search(r"\blet\b", theory):
        issues.append(
            "Theory contains `let` — IDP FO(.) does not support let-bindings. "
            "Rewrite using quantifiers and separate rules."
        )
    return issues


def _lint_unicode_confusion(kb_text: str) -> List[str]:
    issues = []
    # Blackboard bold / exotic math letters often appear when LLMs paste Unicode
    for ch in kb_text or "":
        o = ord(ch)
        if 0x1D400 <= o <= 0x1D7FF:  # Mathematical Alphanumeric Symbols block
            issues.append(
                "Found mathematical Unicode letter U+%04X in KB — use ASCII identifiers only "
                "(e.g. Bool not blackboard bold)." % o
            )
            break
    return issues


def _lint_vocab_stray_asterisk(vocab_body: str) -> List[str]:
    issues = []
    for i, raw in enumerate(vocab_body.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("//"):
            continue
        # Markdown merge: Bool then * then identifier (not product Type * Type)
        if re.search(r":\s*Bool\s*\*\s*[A-Za-z_]", line) or re.search(r"->\s*Bool\s*\*\s*[A-Za-z_]", line):
            issues.append(
                "Vocabulary line %d looks like markdown merged into FO (`Bool*...` or `-> Bool*...`): %r"
                % (i, line.strip()[:120])
            )
        if re.search(r":\s*Int\s*\*\s*[A-Za-z_]", line) or re.search(r":\s*Real\s*\*\s*[A-Za-z_]", line):
            issues.append(
                "Vocabulary line %d: possible stray `*` after Int/Real: %r" % (i, line.strip()[:120])
            )
    return issues


def _lint_duplicate_vocab_signatures(vocab_body: str) -> List[str]:
    """Same symbol name declared twice with different signatures."""
    seen: Dict[str, str] = {}
    issues = []
    for raw in vocab_body.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        ms = _SIG_RE.match(line)
        if not ms:
            continue
        name = ms.group(1)
        arg_blob = (ms.group(2) or "").strip()
        ret = ms.group(3).strip()
        sig = (arg_blob + " -> " + ret) if arg_blob else ("() -> " + ret)
        if name in seen and seen[name] != sig:
            issues.append(
                "Duplicate vocabulary symbol %r with conflicting signatures: %r vs %r"
                % (name, seen[name], sig)
            )
        seen.setdefault(name, sig)
    return issues


def _lint_malformed_vocab_lines(vocab_body: str) -> List[str]:
    """Catch common malformed declaration lines before parser step."""
    issues: List[str] = []
    declared_types: Set[str] = set()
    for raw in vocab_body.splitlines():
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        mt = _TYPE_RE.match(line)
        if mt:
            declared_types.add(mt.group(1))

    for i, raw in enumerate(vocab_body.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        if _TYPE_RE.match(line) or _SIG_RE.match(line):
            continue

        # Bare type-like line: "Person"
        if re.match(r"^[A-Za-z_]\w*$", line):
            issues.append(
                "Vocabulary line %d looks like a bare type/symbol %r. Use `type %s` for types or "
                "`name: Type -> Bool` for predicates." % (i, line, line)
            )
            continue

        # Shorthand declaration without return type: "foo: Person"
        ms = re.match(r"^([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*$", line)
        if ms:
            sym, rhs = ms.group(1), ms.group(2)
            if rhs in declared_types:
                issues.append(
                    "Vocabulary line %d uses shorthand %r. Add explicit return type, e.g. `%s: %s -> Bool`."
                    % (i, line, sym, rhs)
                )
    return issues


def _collect_declared_names(vocab_body: str) -> Set[str]:
    names: Set[str] = set()
    for raw in vocab_body.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        mt = _TYPE_RE.match(line)
        if mt:
            names.add(mt.group(1))
            continue
        ms = _SIG_RE.match(line)
        if ms:
            names.add(ms.group(1))
    return names


def _lint_undeclared_theory_calls(kb_text: str, vocab_body: str) -> List[str]:
    theory = _theory_body(kb_text) or ""
    declared = _collect_declared_names(vocab_body)
    bad: Set[str] = set()
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", theory):
        name = m.group(1)
        if name in declared or name in _BUILTIN_CALLS:
            continue
        if name in ("not", "true", "false"):
            continue
        bad.add(name)
    issues = []
    for name in sorted(bad)[:20]:
        issues.append(
            "Theory calls undeclared symbol %r — declare it in vocabulary or fix typo." % name
        )
    if len(bad) > 20:
        issues.append("... and %d more undeclared call(s)." % (len(bad) - 20))
    return issues


def lint_kb_fo_text(kb_text: str) -> None:
    """
    Run all static lints. Raises KBLintError with combined message on failure.
    Caller should run after sanitization, before IDP.parse.
    """
    if not kb_text or not kb_text.strip():
        raise KBLintError("Empty KB text")

    issues: List[str] = []
    issues.extend(_lint_unicode_confusion(kb_text))

    vb = _vocab_body(kb_text)
    if vb is not None:
        issues.extend(_lint_vocab_stray_asterisk(vb))
        issues.extend(_lint_duplicate_vocab_signatures(vb))
        issues.extend(_lint_malformed_vocab_lines(vb))

    th = _theory_body(kb_text)
    if th is not None:
        issues.extend(_lint_let_in_theory(th))

    if vb is not None and th is not None:
        issues.extend(_lint_undeclared_theory_calls(kb_text, vb))

    if issues:
        raise KBLintError("KB lint failed:\n- " + "\n- ".join(issues))

    # Consistency pass (raises KBSchemaError if vocabulary is structurally unusable)
    try:
        extract_schema_from_kb_fo(kb_text)
    except Exception as e:
        raise KBLintError("Schema extraction failed (fix vocabulary layout): " + str(e)) from e
