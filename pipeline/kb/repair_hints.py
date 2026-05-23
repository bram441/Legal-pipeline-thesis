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
    if "bare type/symbol" in eml or "shorthand" in eml:
        hints.append(
            "Vocabulary declaration shape is invalid. Use `type T` for types and `p: T -> Bool` for "
            "unary predicates (never `p: T` alone)."
        )
    if "missing 'vocabulary v'" in eml or "missing 'theory t:v'" in eml:
        hints.append(
            "Output exactly two blocks in order: `vocabulary V { ... }` then `theory T:V { ... }`."
        )

    if re.search(r"\blet\b", prev, re.IGNORECASE):
        hints.append(
            "AUTOCHECK: previous output contains `let` — IDP FO has no let-bindings. "
            "Rewrite using `!` / `?` quantifiers and separate formulas."
        )
    if re.search(r"^\s*[A-Za-z_]\w*\s*$", prev, re.MULTILINE):
        hints.append(
            "AUTOCHECK: found bare identifier line(s) in vocabulary. Prefix type lines with `type`."
        )
    if re.search(r"^\s*[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*\s*$", prev, re.MULTILINE):
        hints.append(
            "AUTOCHECK: found shorthand declaration `name: Type`. Expand to `name: Type -> Bool` "
            "or declare a proper function return type."
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

    if "date found" in eml or "integer expected" in eml or "ℤ value expected" in em:
        hints.append(
            "A variable typed as Date (or another sort) is used where Int/Real is required, or two sorts are mixed "
            "in `=` / arithmetic. Align quantifier sorts (`! d in Date:`) with each symbol's declared argument types; "
            "use a different variable for Int-typed parameters."
        )

    if "wrong arguments" in eml or "expected argument of type" in eml:
        hints.append(
            "Predicate/function argument sorts must match the vocabulary signatures exactly. "
            "Fix the rule call argument order and variable sorts, or adjust the symbol table if the law model is wrong."
        )

    if not hints:
        return "(none — follow the ERROR REPORT below exactly; do not repeat the same malformed pattern.)"

    return "You MUST fix all of the following (in addition to the error report):\n" + "\n".join(
        "- " + h for h in hints
    )


def build_json_ir_compile_hints(error_message: str) -> str:
    """Short bullets for JSON IR normalization/typecheck failures (rules phase repair)."""
    em = (error_message or "").strip()
    if not em:
        return ""
    el = em.lower()
    out: list[str] = []

    if "json_ir_schema_design_error" in el:
        if "observable predicate" in el and ("consequent" in el or "then" in el):
            out.append(
                "The rule consequent uses an observable predicate. Observables are case-input facts — move them to "
                "`if`, or add/use a derived predicate for the legal consequence and repair the symbol table if needed."
            )
        if "no derived legal outputs" in el:
            out.append(
                "Add derived predicates/functions for legal statuses, rights, obligations, permissions, prohibitions, "
                "sanctions, validity results, entitlements, exclusions, exceptions, or legal effects described by the law."
            )
        if "no observable case-input" in el:
            out.append(
                "Add observable predicates/functions that case extraction can populate from factual case descriptions."
            )
        if "boolean predicate atom" in el or "bool predicate atom" in el:
            out.append(
                "A function was used as a Boolean atom. If yes/no, declare a predicate with returns Bool; "
                "if numeric, use the function only inside compare/terms."
            )
        if "computed-looking observable" in el or "looks computed/composite" in el:
            out.append(
                "Threshold/count/exceeds/meets-style conditions must be helper/derived with defining rules, "
                "or numeric comparisons on observable functions—not observable unless directly_observable=true."
            )
        if "semantically identical to the status" in el or "classification encoded as a primitive type" in el:
            out.append(
                "Status-as-type error: do not declare a narrow type matching a same-name is_* predicate. "
                "Use a broader entity type and a derived status predicate over it; use binary relations for "
                "roles between entities when the law links two parties."
            )
        if "legal-effect or timing language" in el or "no derived legal-output predicate" in el:
            out.append(
                "Add a derived legal-output predicate for consequences/effects/timing/rights/obligations "
                "stated in the law—not only is_* classifications or threshold helpers. Optionally set "
                "legal_output=true or output_category=legal_effect on that symbol."
            )
        if "helper predicate" in el and ("defining rule" in el or "never defined" in el):
            out.append(
                "Define the helper with rules (THEN derives it from observables/comparisons), or replace with "
                "direct numeric comparisons. Do not delete negated conditions or rename without fixing definitions."
            )
        if "helper predicate" in el and "never defined" in el:
            out.append(
                "Every helper used in a rule condition must be defined by some rule, or it must be reclassified "
                "as observable with directly_observable=true. Either add a rule whose THEN derives "
                "the helper from observables, or change the symbol kind."
            )
        if "helper function" in el and "never defined" in el:
            out.append(
                "Every helper used in a rule condition must be defined by some rule, or it must be reclassified "
                "as observable. Do not leave helper predicates/functions open."
            )
    if "json_ir_rule_design_error" in el and "circular" in el:
        out.append(
            "Break circular derived-only rules by adding observable/helper conditions in `if`, or repair the symbol table."
        )
    if "at-most-one" in el or "more-than-one criteria" in el or "simple or over individual threshold" in el:
        out.append(
            "Cardinality error: for 'not more than one criterion exceeded', never use a plain OR over single "
            "threshold compares for a favorable derived conclusion. Use pairwise (A and B) or (A and C) or "
            "(B and C), or NOT at_least_two_exceeded helper."
        )
    if "incompatible unary subject roles" in el:
        out.append(
            "Do not quantify a single variable over both deceased-style and surviving-style unary observables. "
            "Introduce separate variables (e.g. subject, other) and a binary relation linking them, then rewrite rules."
        )

    if "unsupported expression object" in el or "func and op/right at the same object level" in el:
        out.append(
            "In `if` / `then` / nested `and`/`or`, each expression object must be ONLY one of: "
            "atom `{\"pred\":\"P\",\"args\":[...],\"negated\":false}`, "
            "`{\"and\":[ ... ]}`, `{\"or\":[ ... ]}`, `{\"not\": ... }`, "
            "or comparison `{\"left\":...,\"op\":\"=<\",\"right\":...}`. "
            "Remove keys such as `implies`, `when`, `forall`, `exists`, `iff` from inside `if`/`then` trees."
        )
    if "placeholder identifier" in el:
        out.append(
            "Do not invent identifiers starting with `_` (e.g. `_descendant`). "
            "Declare every variable in `forall` and use those names in atoms and terms."
        )
    if "predicate must return bool" in el:
        out.append(
            "Every name used with `pred`/`symbol` in rules must be declared in SYMBOL_TABLE as a predicate "
            "with `\"returns\":\"Bool\"`. If you meant a numeric value, use a `functions` entry and a `func` term instead."
        )
    if "unbound identifier" in el and "object rule" in el:
        out.append(
            "Every variable used inside an object rule must appear in the rule's `forall` (or nested quantifiers the renderer supports). "
            "Either add `{\"var\":\"x\",\"type\":\"SomeType\"}` to `forall`, or use a string FO rule instead."
        )
    if "expects type" in el and "got" in el:
        out.append(
            "Predicate/function argument sorts must match SYMBOL_TABLE exactly. JSON_IR has no subtyping: "
            "use the broader declared type for variables and represent roles with predicates, or repair the symbol signature."
        )
    if "unsupported term" in el or ("term object" in el and "func" in el):
        out.append(
            "Non-Boolean terms must be strings (vars/constants), numbers, or `{\"func\":\"F\",\"args\":[...]}` with `F` declared as a function."
        )
    if "must match right type" in el and "compare" in el:
        out.append(
            "In `compare` objects, `left` and `right` must have the same sort (including Int vs Real — pick one). "
            "Do not compare a Date variable to an Int expression without converting or using the correct variable."
        )
    if "lists it only under functions" in el or "bool predicate atom" in el:
        out.append(
            "A name used as {\"pred\":\"X\",...} must be under predicates with returns Bool in SYMBOL_TABLE. "
            "If X is numeric or a threshold, move it to functions and use {\"func\":\"X\",\"args\":[...]} inside compare only."
        )
    if "integer expected" in el or "date found" in el or "expects sort" in el:
        out.append(
            "String rules: every `v in T` quantifier must match how `v` is passed into predicates/functions "
            "(e.g. do not pass a Date-quantified `d1` into a parameter declared as Int)."
        )

    if not out:
        return ""
    return "\n".join("- " + h for h in out)
