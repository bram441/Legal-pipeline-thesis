import os
import re

from debug import status_log
from pipeline.kb.compile_backend import get_kb_backend_from_env
from pipeline.kb.compiler import compile_law_to_kb_fo
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.schema import _VOCAB_RE, extract_schema_from_kb_fo, load_kb_schema, save_kb_schema
from pipeline.kb.semantic_check import check_kb_semantic, KBSemanticError
from pipeline.utils.run_trace import trace_enabled, RunTraceWriter


class KBCacheError(Exception):
    pass


def _validate_kb_fo_text(kb_text):
    s = kb_text.strip()

    if "vocabulary V" not in s:
        raise KBCacheError("KB FO text missing 'vocabulary V'")
    if "theory T:V" not in s:
        raise KBCacheError("KB FO text missing 'theory T:V'")
    if "structure" in s:
        raise KBCacheError("KB FO text must not contain 'structure' blocks")

    return s


def _fix_vocab_markdown_bullet_merges(kb_text):
    """
    LLMs often paste markdown bullets into FO: `pred1: Bool   *pred2: ...` on one line.
    IDP then parses `*` as a type constructor and fails (Expected '->' at ... *pred2).
    Split into two declarations. Repeat to unwrap chains.
    """
    lines = kb_text.splitlines()
    out = []
    # After Bool / Int / Real, spurious `* nextName` (LLM often omits space: `Bool*foo`)
    pat_simple = re.compile(
        r"^(\s*)([A-Za-z_]\w*)\s*:\s*(Bool|Int|Real)\s*\*\s*([A-Za-z_]\w*)(.*)$"
    )
    # After `... -> Bool`, same bullet mistake
    pat_arrow_bool = re.compile(
        r"^(\s*)([A-Za-z_]\w*)\s*:\s*"
        r"((?:[A-Za-z_]\w*(?:\s*\*\s*[A-Za-z_]\w*)*)\s*->\s*Bool)\s*\*\s*"
        r"([A-Za-z_]\w*)(.*)$"
    )
    for line in lines:
        m = pat_simple.match(line)
        if not m:
            m = pat_arrow_bool.match(line)
        if m:
            indent, first, typ_or_sig, second, rest = (
                m.group(1),
                m.group(2),
                m.group(3),
                m.group(4),
                m.group(5),
            )
            rest = rest.strip()
            out.append(indent + first + ": " + typ_or_sig)
            if rest.startswith(":"):
                out.append(indent + "  " + second + rest)
            else:
                out.append(indent + "  " + second + ": Bool" + ((" " + rest) if rest else ""))
        else:
            out.append(line)
    return "\n".join(out)


_CO_DOMAIN_TYPES = frozenset({"Bool", "Int", "Real"})
_BUILTIN_TYPE_NAMES = frozenset({"Bool", "Int", "Real"})
_RESERVED_SYMBOL_NAMES = frozenset({"true", "false", "not"})


def _normalize_vocab_declaration_shape(kb_text: str) -> str:
    """
    Fix common malformed vocabulary declaration lines:
    - bare type names: `Person` -> `type Person`
    - shorthand unary bool predicates: `foo: Person` -> `foo: Person -> Bool`
    """
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    lines = inner.splitlines()

    declared_types = set()
    for raw in lines:
        mt = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s*$", raw.strip(), re.IGNORECASE)
        if mt:
            declared_types.add(mt.group(1))

    out_lines: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if re.match(r"^\s*type\s+[A-Za-z_]\w*\s*$", stripped, re.IGNORECASE):
            out_lines.append(raw)
            continue

        # Bare type line (e.g. "Person") inside vocab block.
        mbare = re.match(r"^(\s*)([A-Za-z_]\w*)\s*$", raw)
        if mbare:
            indent, name = mbare.group(1), mbare.group(2)
            # Conservative: only auto-promote PascalCase-ish names as types.
            if name[:1].isupper():
                out_lines.append(indent + "type " + name)
                declared_types.add(name)
                continue

        # Shorthand declaration "pred: Type" (often intended Bool predicate).
        msh = re.match(r"^(\s*)([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)\s*$", raw)
        if msh:
            indent, sym, rhs = msh.group(1), msh.group(2), msh.group(3)
            if rhs in declared_types or rhs in ("Bool", "Int", "Real"):
                out_lines.append(indent + sym + ": " + rhs + " -> Bool")
                continue

        out_lines.append(raw)

    new_inner = "\n".join(out_lines)
    start, end = m.span(1)
    return kb_text[:start] + new_inner + kb_text[end:]


def _normalize_vocab_curried_domain(kb_text: str) -> str:
    """
    LLMs often declare binary (or n-ary) predicates as curried arrows:
      foo: Person -> Goods -> Bool
    IDP FO(.) expects a product domain:
      foo: Person * Goods -> Bool
    """
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    out_lines: list[str] = []
    for raw in inner.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if re.match(r"^\s*type\s+", raw, re.IGNORECASE):
            out_lines.append(raw)
            continue
        sm = re.match(r"^(\s*)([A-Za-z_]\w*)\s*:\s*(.+)$", raw.rstrip())
        if not sm:
            out_lines.append(raw)
            continue
        indent, sym, rhs = sm.group(1), sm.group(2), sm.group(3).strip()
        parts = re.split(r"\s*->\s*", rhs)
        if len(parts) >= 3 and parts[-1] in _CO_DOMAIN_TYPES:
            domain = " * ".join(parts[:-1])
            out_lines.append(indent + sym + ": " + domain + " -> " + parts[-1])
        else:
            out_lines.append(raw)
    new_inner = "\n".join(out_lines)
    start, end = m.span(1)
    return kb_text[:start] + new_inner + kb_text[end:]


def _drop_builtin_type_declarations(kb_text: str) -> str:
    """Remove invalid user-declared built-in types (Bool/Int/Real)."""
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    out_lines: list[str] = []
    for raw in inner.splitlines():
        mt = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s*$", raw.strip(), re.IGNORECASE)
        if mt and mt.group(1) in _BUILTIN_TYPE_NAMES:
            continue
        out_lines.append(raw)
    start, end = m.span(1)
    return kb_text[:start] + "\n".join(out_lines) + kb_text[end:]


def _dedupe_vocab_declarations(kb_text: str) -> str:
    """Drop exact duplicate type/signature lines in vocabulary."""
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    seen_types = set()
    seen_sigs = set()
    out_lines: list[str] = []
    for raw in inner.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        mt = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s*$", stripped, re.IGNORECASE)
        if mt:
            t = mt.group(1)
            if t in seen_types:
                continue
            seen_types.add(t)
            out_lines.append(raw)
            continue
        ms = re.match(r"^\s*([A-Za-z_]\w*)\s*:\s*(.+?)\s*$", stripped)
        if ms:
            sig = ms.group(1) + ":" + ms.group(2)
            if sig in seen_sigs:
                continue
            seen_sigs.add(sig)
            out_lines.append(raw)
            continue
        out_lines.append(raw)
    start, end = m.span(1)
    return kb_text[:start] + "\n".join(out_lines) + kb_text[end:]


def _drop_reserved_symbol_declarations(kb_text: str) -> str:
    """Remove declarations that collide with FO reserved literals/operators."""
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    out_lines: list[str] = []
    for raw in inner.splitlines():
        stripped = raw.strip()
        ms = re.match(r"^([A-Za-z_]\w*)\s*:\s*", stripped)
        if ms and ms.group(1).lower() in _RESERVED_SYMBOL_NAMES:
            continue
        out_lines.append(raw)
    start, end = m.span(1)
    return kb_text[:start] + "\n".join(out_lines) + kb_text[end:]


def _resolve_type_symbol_name_collisions(kb_text: str) -> str:
    """
    If a type name is also declared as predicate/function, rename the symbol and rewrite calls.
    Example: type Judgment + Judgment: LegalAction -> Bool  => JudgmentPred.
    """
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    lines = inner.splitlines()
    type_names = set()
    for raw in lines:
        mt = re.match(r"^\s*type\s+([A-Za-z_]\w*)\s*$", raw.strip(), re.IGNORECASE)
        if mt:
            type_names.add(mt.group(1))
    rewrites = {}
    out_lines = []
    for raw in lines:
        ms = re.match(r"^(\s*)([A-Za-z_]\w*)\s*:\s*(.+)$", raw.rstrip())
        if not ms:
            out_lines.append(raw)
            continue
        indent, name, sig = ms.group(1), ms.group(2), ms.group(3)
        if name in type_names:
            new_name = name + "Pred"
            k = 2
            while new_name in type_names or new_name in rewrites.values():
                new_name = name + "Pred" + str(k)
                k += 1
            rewrites[name] = new_name
            out_lines.append(indent + new_name + ": " + sig)
        else:
            out_lines.append(raw)
    if not rewrites:
        return kb_text
    start, end = m.span(1)
    s = kb_text[:start] + "\n".join(out_lines) + kb_text[end:]
    for old, new in rewrites.items():
        s = re.sub(r"\b" + re.escape(old) + r"\s*\(", new + "(", s)
    return s


def _coerce_numeric_calls_in_boolean_context(kb_text: str) -> str:
    """
    Rewrite bare Int/Real function calls used as booleans in rule conditions.
    Example: (... & NumberOfYears(x)) => ...  -> (... & (NumberOfYears(x) ~= 0)) => ...
    """
    vm = _VOCAB_RE.search(kb_text or "")
    tm = re.search(r"\btheory\s+T\s*:\s*V\s*\{", kb_text or "", re.IGNORECASE | re.DOTALL)
    if not vm or not tm:
        return kb_text
    vocab_inner = vm.group(1)
    start = kb_text.find("{", tm.start())
    if start < 0:
        return kb_text
    depth = 0
    end = -1
    for i in range(start, len(kb_text)):
        ch = kb_text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return kb_text
    theory_inner = kb_text[start + 1 : end]

    numeric_funcs = set()
    for raw in vocab_inner.splitlines():
        ms = re.match(r"^\s*([A-Za-z_]\w*)\s*:\s*(.+?)\s*->\s*([A-Za-z_]\w*)\s*$", raw.strip())
        if not ms:
            continue
        name = ms.group(1)
        ret = ms.group(3)
        if ret in ("Int", "Real"):
            numeric_funcs.add(name)

    for name in sorted(numeric_funcs, key=len, reverse=True):
        # ... & name(x)      => ... & (name(x) ~= 0)
        theory_inner = re.sub(
            r"([&\|\(]\s*)" + re.escape(name) + r"\(([^()]*)\)(?!\s*(?:=|~=|=<|>=|<|>))",
            r"\1(" + name + r"(\2) ~= 0)",
            theory_inner,
        )
        # ... & ~name(x)     => ... & (name(x) = 0)
        theory_inner = re.sub(
            r"([&\|\(]\s*)~\s*" + re.escape(name) + r"\(([^()]*)\)(?!\s*(?:=|~=|=<|>=|<|>))",
            r"\1(" + name + r"(\2) = 0)",
            theory_inner,
        )

    return kb_text[: start + 1] + theory_inner + kb_text[end:]


def _auto_declare_undeclared_theory_calls(kb_text: str) -> str:
    """Add missing predicate declarations for symbols called in theory but absent from vocabulary."""
    vm = _VOCAB_RE.search(kb_text or "")
    tm = re.search(r"\btheory\s+T\s*:\s*V\s*\{(.*?)\}\s*$", kb_text or "", re.IGNORECASE | re.DOTALL)
    if not vm or not tm:
        return kb_text

    vocab_inner = vm.group(1)
    theory_inner = tm.group(1)

    decl_names = set()
    for raw in vocab_inner.splitlines():
        m = re.match(r"^\s*([A-Za-z_]\w*)\s*:\s*", raw.strip())
        if m:
            decl_names.add(m.group(1))

    # Collect variable typing from quantifier headers: !x in Person, y in Good:
    var_types: dict[str, str] = {}
    for qh in re.finditer(r"[!?]\s*([^:\n]+):", theory_inner):
        header = qh.group(1)
        for v, t in re.findall(r"([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)", header):
            var_types[v] = t

    def _iter_calls(text: str):
        i = 0
        n = len(text)
        while i < n:
            m = re.search(r"\b([A-Za-z_]\w*)\s*\(", text[i:])
            if not m:
                break
            name = m.group(1)
            open_i = i + m.end() - 1
            j = open_i + 1
            depth = 1
            in_str = False
            esc = False
            while j < n:
                ch = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            if j >= n:
                i = open_i + 1
                continue
            arg_blob = text[open_i + 1 : j]
            # Split by top-level commas only.
            args = []
            buf = []
            dep2 = 0
            in_s2 = False
            esc2 = False
            for ch in arg_blob:
                if in_s2:
                    buf.append(ch)
                    if esc2:
                        esc2 = False
                    elif ch == "\\":
                        esc2 = True
                    elif ch == '"':
                        in_s2 = False
                    continue
                if ch == '"':
                    in_s2 = True
                    buf.append(ch)
                    continue
                if ch == "(":
                    dep2 += 1
                    buf.append(ch)
                    continue
                if ch == ")":
                    dep2 = max(0, dep2 - 1)
                    buf.append(ch)
                    continue
                if ch == "," and dep2 == 0:
                    a = "".join(buf).strip()
                    if a:
                        args.append(a)
                    buf = []
                    continue
                buf.append(ch)
            tail = "".join(buf).strip()
            if tail:
                args.append(tail)
            yield name, args
            i = j + 1

    new_decls: list[str] = []
    seen_new = set()
    for name, args_raw in _iter_calls(theory_inner):
        if name in decl_names or name in seen_new:
            continue
        if not args_raw:
            continue
        arg_types = []
        for a in args_raw:
            arg_types.append(var_types.get(a, "Person"))
        new_decls.append("  " + name + ": " + " * ".join(arg_types) + " -> Bool")
        seen_new.add(name)

    # Fallback: symbol-like bare identifiers in theory that may not appear as name(...)
    # but still trigger undeclared-symbol lint downstream.
    type_names = set(re.findall(r"^\s*type\s+([A-Za-z_]\w*)\s*$", vocab_inner, flags=re.MULTILINE))
    reserved = {
        "vocabulary", "theory", "type", "true", "false", "and", "or", "not",
        "in", "forall", "exists", "Bool", "Int", "Real"
    }
    token_candidates = set(re.findall(r"\b([A-Za-z_]\w*)\b", theory_inner))
    for tok in sorted(token_candidates):
        if tok in reserved or tok in type_names or tok in decl_names or tok in seen_new:
            continue
        if tok in var_types:
            continue
        # Heuristic: prefer predicate-like names (Pascal/camel-ish), skip tiny tokens.
        if len(tok) < 3:
            continue
        if not (tok[0].isupper() or any(c.isupper() for c in tok[1:])):
            continue
        new_decls.append("  " + tok + ": Person -> Bool")
        seen_new.add(tok)

    if not new_decls:
        return kb_text

    start, end = vm.span(1)
    new_inner = vocab_inner.rstrip() + ("\n" if vocab_inner.strip() else "") + "\n".join(new_decls) + "\n"
    return kb_text[:start] + new_inner + kb_text[end:]


def _sanitize_common_llm_syntax(kb_text):
    s = kb_text
    # Common non-FO operators from JSON/Prolog-like output.
    s = s.replace("&&", " & ")
    s = s.replace("||", " | ")
    s = s.replace("!=", " ~= ")
    # Typed quantifiers in many generated theories: "forall x:Person, y:Type (body)."
    def _rewrite_forall(m):
        vars_part = m.group(1)
        body = m.group(2).strip()
        pairs = re.findall(r"([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)", vars_part)
        if not pairs:
            pairs = re.findall(r"([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)", vars_part)
        if not pairs:
            return m.group(0)
        q = ", ".join(v + " in " + t for v, t in pairs)
        return "! " + q + ": " + body + "."

    def _rewrite_exists(m):
        vars_part = m.group(1)
        body = m.group(2).strip()
        pairs = re.findall(r"([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*)", vars_part)
        if not pairs:
            pairs = re.findall(r"([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)", vars_part)
        if not pairs:
            return m.group(0)
        q = ", ".join(v + " in " + t for v, t in pairs)
        return "? " + q + ": " + body

    s = re.sub(
        r"\bforall\s+([A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*)*)\s*\(\s*(.*?)\s*\)\s*\.",
        _rewrite_forall,
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )
    s = re.sub(
        r"\bexists\s+([A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*\s*:\s*[A-Za-z_]\w*)*)\s*\(\s*(.*?)\s*\)",
        _rewrite_exists,
        s,
        flags=re.IGNORECASE | re.DOTALL,
    )
    # Handle FO-like quantifier keyword variants used by LLMs: "Exists x in T:"
    s = re.sub(r"\bexists\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    # Corrupted quantifier tokenization like: exists(d *in Person:
    s = re.sub(r"\bexists\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    # Expand grouped quantifier heads: "!x,y in Person" -> "! x in Person, y in Person"
    def _expand_grouped_quant(m):
        q = m.group(1)
        vars_blob = m.group(2)
        typ = m.group(3)
        vars_ = [v.strip() for v in vars_blob.split(",") if v.strip()]
        if len(vars_) <= 1:
            return m.group(0)
        expanded = ", ".join(v + " in " + typ for v in vars_)
        return q + " " + expanded

    s = re.sub(r"([!?])\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)\s+in\s+([A-Za-z_]\w*)", _expand_grouped_quant, s)
    # Negation token from C-style formulas: "!P(x)" -> "~P(x)" (keep quantifier ! intact).
    s = re.sub(r"!\s*([A-Za-z_]\w*\s*\()", r"~\1", s)
    # Corrupted implication tokens occasionally produced by models.
    s = re.sub(r"[-–—]\s*\*+\s*>", " => ", s)
    s = s.replace("->>", " => ")
    s = s.replace("==>", " => ")
    s = re.sub(r'!\s*([A-Za-z_]\w*)\s*\[\s*Party\s*\]\s*:', r'! \1 in Party:', s)
    s = re.sub(r'\bforall\s+([A-Za-z_]\w*)\s+in\s+Party\s*:', r'! \1 in Party:', s, flags=re.IGNORECASE)
    # LLM often outputs "theory T: V" (space after colon); IDP expects "theory T:V"
    s = re.sub(r'theory\s+T\s*:\s*V\b', 'theory T:V', s, flags=re.IGNORECASE)
    # FO(.) requires capitalized built-in types: Bool, Int, Real
    s = re.sub(r'\b->\s*bool\b', ' -> Bool', s)
    s = re.sub(r'\b->\s*int\b', ' -> Int', s)
    s = re.sub(r'\b->\s*real\b', ' -> Real', s)
    # Equivalence: IDP expects <=> , not <-> (Prolog/math style)
    s = re.sub(r'<->', '<=>', s)
    # IDP uses =< for "less or equal"; many LLMs emit <=.
    s = re.sub(r'(?<![<>=!])<=', '=<', s)
    # Guard against common tautology artifacts in non-ordered custom types.
    # Example seen in generated KBs: (LegalActionFilingDate(x) =< LegalActionFilingDate(x))
    # which can trigger parse/type failures when Date is not comparable.
    s = re.sub(
        r"\(\s*([A-Za-z_]\w*\([^()]*\))\s*(=<|>=|<|>)\s*\1\s*\)",
        "true",
        s,
    )
    # Markdown bullets merged between vocabulary lines (see _fix_vocab_markdown_bullet_merges)
    prev = None
    while prev != s:
        prev = s
        s = _fix_vocab_markdown_bullet_merges(s)
    s = _drop_builtin_type_declarations(s)
    s = _drop_reserved_symbol_declarations(s)
    s = _normalize_vocab_declaration_shape(s)
    s = _normalize_vocab_curried_domain(s)
    s = _dedupe_vocab_declarations(s)
    s = _resolve_type_symbol_name_collisions(s)
    s = _coerce_numeric_calls_in_boolean_context(s)
    s = _auto_declare_undeclared_theory_calls(s)
    return s


def _fix_sentence_equivalence(kb_text):
    """
    Convert function-assignment rules from <=> to => to avoid UNSAT.
    Rules like 'imprisonmentMinDays(p) = 180 <=> cond' create conflicts when
    multiple rules constrain the same function for the same person; use => instead.
    """
    def repl(m):
        lhs, val, cond = m.group(1), m.group(2), m.group(3)
        cond = cond.strip().rstrip(".")
        return "(" + cond + ") => " + lhs + " = " + val + "."

    return re.sub(
        r"(\w+\([^)]+\))\s*=\s*(-?\d+)\s*<=>\s*(.+?)\.\s*$",
        repl,
        kb_text,
        flags=re.MULTILINE,
    )


def _idp_parse_check(kb_text):
    try:
        from idp_engine import IDP
        IDP.from_str(kb_text)
    except Exception as e:
        raise KBCacheError("IDP failed to parse compiled KB: " + str(e))


def _use_le_enabled():
    try:
        from pipeline.le import use_le_enabled
        return use_le_enabled()
    except ImportError:
        return False


def json_ir_outer_cache_retries_enabled() -> bool:
    """When true, outer ``get_or_compile_kb`` may rerun the full JSON_IR compile loop (legacy)."""
    v = (os.getenv("JSON_IR_ALLOW_OUTER_CACHE_RETRIES") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def resolve_max_repair_attempts(kb_backend: str, default: int = 8, *, log_warnings: bool = True) -> int:
    """
    Outer cache repair attempts. JSON_IR defaults to 1 (structured loop handles repair).
    ``PIPELINE_KB_MAX_REPAIR_ATTEMPTS`` applies to legacy FO only unless
    ``JSON_IR_ALLOW_OUTER_CACHE_RETRIES=1``.
    """
    env_attempts = (os.getenv("PIPELINE_KB_MAX_REPAIR_ATTEMPTS") or "").strip()
    if kb_backend == "json_ir":
        if json_ir_outer_cache_retries_enabled():
            n = default
            if env_attempts:
                try:
                    n = max(1, int(env_attempts))
                except ValueError:
                    pass
            if log_warnings:
                status_log(
                    "KB",
                    "WARNING: JSON_IR outer cache retries enabled (JSON_IR_ALLOW_OUTER_CACHE_RETRIES=1); "
                    "structured compile loop may run up to {} outer time(s)".format(n),
                )
            return n
        if env_attempts and log_warnings:
            status_log(
                "KB",
                "Ignoring PIPELINE_KB_MAX_REPAIR_ATTEMPTS={} for json_ir backend "
                "(inner structured loop handles repair; set JSON_IR_ALLOW_OUTER_CACHE_RETRIES=1 to enable outer retries)".format(
                    env_attempts
                ),
            )
        return 1
    n = default
    if env_attempts:
        try:
            n = max(1, int(env_attempts))
        except ValueError:
            pass
    return n


def _format_json_ir_cache_error(exc: LawCompilationError) -> str:
    """Single concise failure line for cache layer (no recursive outer wraps)."""
    msg = str(exc).strip()
    rs = getattr(exc, "repair_summary", None) or {}
    if rs:
        extra = (
            "structured_repair: symbol_versions={symbol_version_count}, "
            "rules_attempts={rules_attempt_count}, total_kb_llm_calls={total_kb_llm_calls}, "
            "final_error={final_normalized_error_code}".format(
                symbol_version_count=rs.get("symbol_version_count", "?"),
                rules_attempt_count=rs.get("rules_attempt_count", "?"),
                total_kb_llm_calls=rs.get("total_kb_llm_calls", "?"),
                final_normalized_error_code=rs.get("final_normalized_error_code", "?"),
            )
        )
        if extra not in msg:
            msg = msg + "\n" + extra
    return "Law compilation failed: " + msg if not msg.lower().startswith("law compilation failed") else msg


def get_or_compile_kb(
    run_dir,
    law_text,
    model=None,
    log_filename="kb_compile.log",
    max_repair_attempts=8,
    cache_subdir=None,
    question_text=None,
    case_text=None,
):
    """Compile or load KB. When cache_subdir is set (e.g. 'translated'), use run_dir/cache_subdir/ for cache.
    When PIPELINE_USE_LE=1, appends 'le' to cache path so LE and non-LE KBs are cached separately.
    When PIPELINE_TRACE=1, writes all steps to run_dir/run_trace.txt for debugging.
    Outer repair: legacy FO uses ``PIPELINE_KB_MAX_REPAIR_ATTEMPTS`` (default 8).
    JSON_IR uses a single outer attempt; repair is handled in ``json_ir_compile_loop``."""
    base_run_dir = run_dir
    trace_path = os.path.join(base_run_dir, "run_trace.txt") if trace_enabled() else None

    kb_backend = get_kb_backend_from_env()
    max_repair_attempts = resolve_max_repair_attempts(kb_backend, default=max_repair_attempts)
    parts = []
    if cache_subdir:
        parts.append(cache_subdir)
    if kb_backend != "legacy_fo":
        parts.append(kb_backend)
    if _use_le_enabled():
        parts.append("le")
    if parts:
        run_dir = os.path.join(run_dir, *parts)
        os.makedirs(run_dir, exist_ok=True)
    kb_path = os.path.join(run_dir, "kb.fo")
    schema_path = os.path.join(run_dir, "kb_schema.json")
    log_path = os.path.join(run_dir, log_filename)

    repair_feedback = None
    last_raw = None

    trace = RunTraceWriter(trace_path) if trace_path else None
    if trace:
        trace.section("RUN TRACE")
        trace.log("Run dir", base_run_dir)
        trace.log("Cache subdir (effective)", run_dir)
        trace.log("KB compiler backend", kb_backend)

    if os.path.exists(kb_path):
        status_log("KB", "Loading from cache")
        with open(kb_path, "r", encoding="utf-8") as f:
            cached_kb = f.read()
        try:
            kb_text = _sanitize_common_llm_syntax(cached_kb)
            kb_text = _fix_sentence_equivalence(kb_text)
            if kb_text != cached_kb:
                with open(kb_path, "w", encoding="utf-8") as f:
                    f.write(kb_text.strip() + "\n")
            kb_text = _validate_kb_fo_text(kb_text)
            try:
                from pipeline.kb.kb_lint import lint_kb_fo_text

                lint_kb_fo_text(kb_text)
                with open(kb_path, "w", encoding="utf-8") as f:
                    f.write(kb_text.strip() + "\n")
            except Exception as lint_exc:
                raise KBCacheError("KB lint: " + str(lint_exc)) from lint_exc
            _idp_parse_check(kb_text)
            check_kb_semantic(kb_text)
            if os.path.exists(schema_path):
                kb_schema = load_kb_schema(run_dir)
            else:
                kb_schema = extract_schema_from_kb_fo(kb_text)
                save_kb_schema(run_dir, kb_schema)
            if trace:
                trace.section("KB LOADED FROM CACHE")
                trace.log("Status", "OK (syntax and semantic checks passed)")
                trace.close()
            return kb_text, kb_schema
        except Exception as e:
            status_log("KB", "Cached KB invalid, recompiling with repair")
            if trace:
                trace.section("CACHED KB INVALID - RECOMPILING")
                trace.log_error("Validation failed", e)
                trace.log("Cached KB (that failed)", cached_kb.strip())
            try:
                os.remove(kb_path)
            except OSError:
                pass
            if os.path.exists(schema_path):
                try:
                    os.remove(schema_path)
                except OSError:
                    pass
            repair_feedback = {
                "error_message": str(e),
                "previous_output": cached_kb.strip(),
            }
            last_raw = cached_kb

    for attempt in range(max_repair_attempts):
        if trace:
            trace.section("KB COMPILATION - Attempt {}".format(attempt + 1))
            trace.log("Law text", law_text)
            if repair_feedback:
                trace.log("Repair feedback (from previous attempt)", repair_feedback.get("error_message", ""))
                trace.log("Previous output (sent to repair prompt)", repair_feedback.get("previous_output", "")[:3000] + ("..." if len(repair_feedback.get("previous_output", "")) > 3000 else ""))

        if attempt == 0:
            if kb_backend == "json_ir":
                status_log(
                    "KB",
                    "JSON_IR structured compile loop handles repair internally (see repair_history.json)",
                )
            else:
                status_log(
                    "KB",
                    "Generating from law text (Logical English)" if _use_le_enabled() else "Generating from law text",
                )
        elif kb_backend != "json_ir":
            status_log("KB", "Repair attempt {}".format(attempt))

        try:
            json_ir_artifacts = (
                os.path.join(base_run_dir, "json_ir_compile")
                if kb_backend == "json_ir"
                else None
            )
            raw_kb_text, ir_kb_schema = compile_law_to_kb_fo(
                law_text,
                model=model,
                repair_feedback=repair_feedback,
                question_text=question_text,
                case_text=case_text,
                artifact_dir=json_ir_artifacts,
            )
        except LawCompilationError as e:
            msg = str(e)
            kb_b = get_kb_backend_from_env()
            non_retryable = (
                "Missing OPENAI_API_KEY" in msg
                or "PIPELINE_KB_COMPILER must" in msg
                or "OpenAI SDK not installed" in msg
            )
            snap = getattr(e, "repair_snapshot", None) or {}
            prev_out = snap.get("previous_output") or ""
            # Legacy FO: outer cache may retry compile with repair_feedback.
            # JSON_IR: structured loop handles repair; outer rerun only when
            # JSON_IR_ALLOW_OUTER_CACHE_RETRIES=1 (see resolve_max_repair_attempts).
            outer_retry_ok = kb_b != "json_ir" or json_ir_outer_cache_retries_enabled()
            if outer_retry_ok and not non_retryable and attempt < max_repair_attempts - 1:
                repair_feedback = {
                    "error_message": msg,
                    "previous_output": prev_out,
                }
                if trace:
                    label = "json_ir outer cache retry" if kb_b == "json_ir" else "legacy outer repair"
                    trace.log_error("LawCompilationError ({})".format(label), e)
                if kb_b == "json_ir":
                    status_log(
                        "KB",
                        "Outer cache retry {}/{} (JSON_IR_ALLOW_OUTER_CACHE_RETRIES=1)".format(
                            attempt + 2, max_repair_attempts
                        ),
                    )
                continue
            if trace:
                trace.log_error("LawCompilationError", e)
                rs = getattr(e, "repair_summary", None)
                if rs:
                    trace.log("JSON_IR repair_summary", rs)
                trace.close()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (LLM call).\n")
                f.write(str(e) + "\n")
                if getattr(e, "repair_summary", None):
                    f.write("\n=== REPAIR SUMMARY ===\n")
                    f.write(repr(e.repair_summary) + "\n")
                if last_raw:
                    f.write("\n=== LAST RAW KB ===\n" + last_raw.strip() + "\n")
            if kb_b == "json_ir":
                raise KBCacheError(_format_json_ir_cache_error(e)) from e
            raise KBCacheError("Law compilation failed: " + str(e)) from e

        last_raw = raw_kb_text
        if trace:
            trace.log("LLM response (raw)", raw_kb_text)

        try:
            status_log("KB", "Checking syntax validity")
            if get_kb_backend_from_env() == "json_ir":
                kb_text = raw_kb_text.strip()
                if not kb_text.endswith("\n"):
                    kb_text = kb_text + "\n"
            else:
                kb_text = _sanitize_common_llm_syntax(raw_kb_text)
                kb_text = _fix_sentence_equivalence(kb_text)
            if trace:
                trace.log("After sanitization", kb_text[:2000] + ("..." if len(kb_text) > 2000 else ""))
            try:
                from pipeline.kb.kb_lint import lint_kb_fo_text

                lint_kb_fo_text(kb_text)
            except Exception as lint_exc:
                raise KBCacheError("KB lint: " + str(lint_exc)) from lint_exc
            kb_text = _validate_kb_fo_text(kb_text)
            _idp_parse_check(kb_text)
            if trace:
                trace.log("Syntax validation", "OK (vocabulary+theory present, IDP parse OK)")
            if ir_kb_schema is not None:
                kb_schema = ir_kb_schema
            else:
                kb_schema = extract_schema_from_kb_fo(kb_text)
            status_log("KB", "Checking semantic validity (satisfiability)")
            check_kb_semantic(kb_text)
            if trace:
                trace.log("Semantic validation", "OK (theory satisfiable)")
        except (KBCacheError, KBSemanticError, Exception) as e:
            if trace:
                trace.log_error("Validation failed", e)
            repair_feedback = {
                "error_message": str(e),
                "previous_output": raw_kb_text.strip(),
            }
            if attempt < max_repair_attempts - 1:
                continue
            if trace:
                trace.section("KB COMPILATION FAILED")
                trace.log("Final error", str(e))
                trace.close()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (invalid FO syntax after {} repair attempts).\n\n".format(max_repair_attempts))
                f.write("Error:\n" + str(e) + "\n\n")
                f.write("=== LAST RAW KB ===\n")
                f.write(raw_kb_text.strip() + "\n")
            raise KBCacheError("KB compilation failed after {} repair attempts: {}".format(max_repair_attempts, e))

        break

    if trace:
        trace.section("KB COMPILATION SUCCESS")
        trace.log("Final KB", kb_text)
        trace.close()

    with open(kb_path, "w", encoding="utf-8") as f:
        f.write(kb_text.strip() + "\n")

    save_kb_schema(run_dir, kb_schema)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("KB compiled successfully.\n")

    status_log("KB", "Compilation successful")
    return kb_text, kb_schema
