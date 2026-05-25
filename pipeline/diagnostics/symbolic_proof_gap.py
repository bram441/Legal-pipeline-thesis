"""Generic symbolic proof-gap diagnostics for Boolean derived queries."""

from __future__ import annotations

import json
import os
import re
from collections import deque
from typing import Any

from pipeline.kb.json_ir import (
    _collect_helper_symbol_usage,
    _iter_function_refs,
    _iter_pred_atoms_with_args,
    _rule_expr_sides,
)
from pipeline.kb.schema_environment import build_schema_environment
from pipeline.symbolic.antecedent_coverage import (
    _bind_query_to_rule,
    _index_case_facts,
    compute_antecedent_coverage,
)

SYMBOLIC_PROOF_GAP_ARTIFACT = "symbolic_proof_gap.json"

_FUNC = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(.+?)\s*\.\s*$")
_ENTITY_YEAR = re.compile(r"(?:19|20)\d{2}")
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_FOLLOWING = re.compile(r"\bfollowing\b|\bfollows\b|\bafter\b", re.IGNORECASE)


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def _split_args(blob: str) -> list[str]:
    return [_norm(x.strip()) for x in (blob or "").split(",") if x.strip()]


def _index_function_assignments(facts: list[str]) -> set[tuple[str, tuple[str, ...]]]:
    out: set[tuple[str, tuple[str, ...]]] = set()
    for ln in facts or []:
        if not isinstance(ln, str):
            continue
        m = _FUNC.match(ln.strip())
        if m:
            out.add((_norm(m.group(1)), tuple(_split_args(m.group(2)))))
    return out


def _schema_maps(kb_schema: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, dict]]:
    pred_kinds: dict[str, str] = {}
    fun_kinds: dict[str, str] = {}
    sym_meta: dict[str, dict] = {}
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            name = str(p["name"])
            pred_kinds[name] = str(p.get("kind") or "unknown").strip().lower()
            sym_meta[name] = dict(p)
    for f in kb_schema.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            name = str(f["name"])
            fun_kinds[name] = str(f.get("kind") or "unknown").strip().lower()
            sym_meta[name] = dict(f)
    return pred_kinds, fun_kinds, sym_meta


def _rules_defining_predicate(rules: list[dict], pred_name: str) -> list[int]:
    target = _norm(pred_name)
    out: list[int] = []
    for idx, rule in enumerate(rules or []):
        if not isinstance(rule, dict):
            continue
        _, then_side = _rule_expr_sides(rule)
        for atom in _iter_pred_atoms_with_args(then_side):
            pn = _norm(atom.get("pred") or atom.get("symbol") or "")
            if pn == target:
                out.append(idx)
    return out


def _rule_if_requirements(rule: dict) -> dict[str, Any]:
    if_side, _ = _rule_expr_sides(rule)
    preds: list[dict[str, Any]] = []
    compares: list[dict[str, Any]] = []
    for atom in _iter_pred_atoms_with_args(if_side):
        pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
        if pn:
            preds.append({"predicate": pn, "args": list(atom.get("args") or [])})
    for fn in _iter_function_refs(if_side):
        compares.append({"function": fn})
    return {"predicates": preds, "function_compares": compares}


def _collect_derivation_rules(kb_schema: dict, query_pred: str) -> list[dict[str, Any]]:
    rules = kb_schema.get("rules") or []
    pred_kinds, fun_kinds, _ = _schema_maps(kb_schema)
    _, _, def_then_p, _ = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)

    seen: set[str] = set()
    queue: deque[str] = deque([query_pred])
    rule_indices: set[int] = set()
    while queue:
        cur = queue.popleft()
        if cur in seen:
            continue
        seen.add(cur)
        for idx in _rules_defining_predicate(rules, cur):
            rule_indices.add(idx)
            rule = rules[idx]
            reqs = _rule_if_requirements(rule)
            for p in reqs["predicates"]:
                pname = p["predicate"]
                pk = pred_kinds.get(pname, "unknown")
                if pk in {"helper", "derived", "conclusion"} and pname in def_then_p:
                    queue.append(pname)
    ordered = sorted(rule_indices)
    return [
        {
            "rule_index": idx,
            "requirements": _rule_if_requirements(rules[idx]),
            "then_predicates": [
                str(a.get("pred") or a.get("symbol") or "")
                for a in _iter_pred_atoms_with_args(_rule_expr_sides(rules[idx])[1])
            ],
        }
        for idx in ordered
    ]


def _assertability(env: dict[str, Any] | None, symbol: str, *, is_function: bool = False) -> bool | None:
    if not env:
        return None
    bucket = (env.get("functions") if is_function else env.get("predicates")) or {}
    entry = bucket.get(symbol) or {}
    return entry.get("assertable_in_case")


def _temporal_support(env: dict[str, Any] | None, symbol: str) -> bool:
    if not env:
        return False
    entry = ((env.get("predicates") or {}).get(symbol)) or {}
    return bool(entry.get("temporal_support"))


def _case_text_snippets(case_text: str | None, symbol: str, sym_meta: dict) -> list[str]:
    if not case_text:
        return []
    text = case_text.strip()
    if not text:
        return []
    snippets: list[str] = []
    desc = str((sym_meta.get(symbol) or {}).get("description") or "")
    keywords: set[str] = set()
    for token in re.split(r"[^A-Za-z0-9_]+", symbol):
        if len(token) >= 4:
            keywords.add(token.lower())
    for token in re.split(r"[^A-Za-z0-9_]+", desc):
        if len(token) >= 5:
            keywords.add(token.lower())
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sent in sentences:
        low = sent.lower()
        if any(k in low for k in keywords):
            snippets.append(sent.strip())
    if not snippets and _YEAR.search(text):
        for sent in sentences:
            if _YEAR.search(sent):
                snippets.append(sent.strip())
    return snippets[:5]


def _has_explicit_numeric_evidence(case_text: str | None) -> bool:
    if not case_text:
        return False
    for m in re.finditer(r"\b\d+(?:[.,]\d+)?\b", case_text):
        token = m.group(0)
        if re.fullmatch(r"(?:19|20)\d{2}", token):
            continue
        if re.fullmatch(r"\d{1,2}", token):
            continue
        if re.search(r"\d:\d", case_text[max(0, m.start() - 2): m.end() + 2]):
            continue
        return True
    return False


def _entity_year_hints(entities: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    if not isinstance(entities, dict):
        return hints
    for vals in entities.values():
        if not isinstance(vals, list):
            continue
        for ent in vals:
            if not isinstance(ent, str):
                continue
            m = _ENTITY_YEAR.search(ent)
            if m:
                hints[_norm(ent)] = m.group(0)
    return hints


def _temporal_query_issues(
    *,
    case_facts: list[str],
    query: dict[str, Any],
    user_question: str | None,
    case_entities: dict[str, Any] | None = None,
    kb_schema: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    from pipeline.extraction.query_period_binding import analyze_query_period_binding

    issues: list[dict[str, Any]] = []
    if not user_question:
        return issues

    pred = str(query.get("predicate") or "")
    sig = None
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == pred:
            sig = p
            break

    case = {"facts": case_facts, "entities": case_entities or {}}
    diag = analyze_query_period_binding(
        query=query,
        case=case,
        kb_schema=kb_schema or {},
        user_question=user_question,
        predicate_sig=sig,
    )
    for msg in diag.get("query_argument_binding_warnings") or []:
        kind = "query_fy_matches_anchor_not_successor"
        if "predecessor" in msg.lower():
            kind = "query_fy_is_predecessor_not_successor"
        elif "not the successor" in msg.lower():
            kind = "query_fy_not_in_successor_chain"
        elif diag.get("query_period_role") == "unknown":
            kind = "query_period_role_ambiguous"
        issues.append({"kind": kind, "detail": msg, "query_period_binding": diag})

    return issues


def _classify_gap(
    *,
    antecedents: list[dict[str, Any]],
    temporal_issues: list[dict[str, Any]],
    symbolic_result: dict[str, Any] | None,
    case_text: str | None,
) -> dict[str, Any]:
    statuses = {a.get("gap_status") for a in antecedents}
    sym_status = str((symbolic_result or {}).get("status") or "").lower()
    sym_label = str((symbolic_result or {}).get("label") or "").lower()

    if sym_status == "error":
        return {
            "primary": "renderer_solver_issue",
            "secondary": [],
            "rationale": "Symbolic engine returned an error before a conclusive proof could be evaluated.",
        }

    secondary: list[str] = []
    if temporal_issues:
        secondary.append("query_argument_issue")

    missing_obs = "missing_entirely" in statuses or "blocked_by_missing_numeric" in statuses
    missing_numeric = "blocked_by_missing_numeric" in statuses
    has_numeric_evidence = _has_explicit_numeric_evidence(case_text)

    if missing_numeric and not has_numeric_evidence:
        if any(a.get("gap_status") == "derivable_from_rules" for a in antecedents):
            primary = "extraction_gap"
            rationale = (
                "Case text states threshold exceedance and consecutive financial years qualitatively, "
                "but extraction did not produce the assertable numeric observables or full temporal "
                "grounding needed to derive the legal-effect antecedent chain."
            )
            secondary.append("genuinely_under_specified_case")
        else:
            primary = "genuinely_under_specified_case"
            rationale = (
                "Case text provides no numeric observables required by KB threshold rules; "
                "asserting numeric facts would require hallucination."
            )
    elif missing_obs:
        primary = "extraction_gap"
        rationale = (
            "Assertable observables or temporal facts required by the derivation chain were not extracted "
            "from the case although the case text contains relevant qualitative evidence."
        )
    elif any(a.get("gap_status") == "blocked_by_rule_linkage" for a in antecedents):
        primary = "kb_rule_linkage_gap"
        rationale = "Required helper or derived symbols are not reachable through KB rules."
    elif temporal_issues:
        primary = "query_argument_issue"
        rationale = "Query arguments appear misaligned with temporal wording in the question/case."
    elif sym_label in {"unknown", ""} and (symbolic_result or {}).get("certain") is False:
        primary = "extraction_gap"
        rationale = "Symbolic result is inconclusive and antecedents are not fully grounded in case facts."
    else:
        primary = "genuinely_under_specified_case"
        rationale = "No single blocking category identified; case may lack explicit observables for a decisive proof."

    if primary == "genuinely_under_specified_case" and "extraction_gap" not in secondary:
        if any(a.get("gap_status") == "missing_entirely" for a in antecedents):
            secondary.append("extraction_gap")

    return {"primary": primary, "secondary": sorted(set(secondary)), "rationale": rationale}


def build_symbolic_proof_gap_report(
    *,
    case: dict[str, Any],
    query: dict[str, Any],
    kb_schema: dict[str, Any],
    schema_environment: dict[str, Any] | None = None,
    symbolic_result: dict[str, Any] | None = None,
    case_text: str | None = None,
    user_question: str | None = None,
) -> dict[str, Any]:
    env = schema_environment or build_schema_environment(kb_schema)
    pred_kinds, fun_kinds, sym_meta = _schema_maps(kb_schema)
    _, _, def_then_p, def_then_f = _collect_helper_symbol_usage(
        kb_schema.get("rules") or [], pred_kinds, fun_kinds
    )

    facts = list(case.get("facts") or [])
    pos_facts, neg_facts = _index_case_facts(facts)
    func_facts = _index_function_assignments(facts)

    q_pred = str(query.get("predicate") or "").strip()
    q_args = list(query.get("args") or [])

    coverage = compute_antecedent_coverage(case, query, kb_schema, symbolic_result=symbolic_result)
    deriving_rules = _collect_derivation_rules(kb_schema, q_pred)

    antecedent_rows: list[dict[str, Any]] = []
    seen_atoms: set[str] = set()

    def _add_row(
        symbol: str,
        *,
        symbol_type: str,
        atom: str,
        gap_status: str,
        kind: str,
        assertable: bool | None,
        case_text_evidence: list[str],
        explicit_case_evidence: bool,
        via_rules: list[int],
    ) -> None:
        if atom in seen_atoms:
            return
        seen_atoms.add(atom)
        antecedent_rows.append(
            {
                "symbol": symbol,
                "symbol_type": symbol_type,
                "atom": atom,
                "kind": kind,
                "gap_status": gap_status,
                "assertable_in_case": assertable,
                "explicit_case_text_evidence": explicit_case_evidence,
                "case_text_snippets": case_text_evidence,
                "deriving_rule_indices": via_rules,
            }
        )

    for block in coverage:
        for cond in block.get("conditions") or []:
            atom = str(cond.get("atom") or "")
            status = str(cond.get("status") or "")
            if not atom:
                continue
            sym = atom.split("(", 1)[0]
            kind = pred_kinds.get(sym, "unknown")
            assertable = _assertability(env, sym, is_function=False)
            snippets = _case_text_snippets(case_text, sym, sym_meta)
            explicit = bool(snippets)
            if status == "present":
                gap_status = "directly_present"
            elif status == "helper_defined":
                gap_status = "derivable_from_rules"
            elif status == "helper_floating":
                gap_status = "blocked_by_rule_linkage"
            elif kind == "observable" or _temporal_support(env, sym):
                gap_status = "missing_entirely" if _temporal_support(env, sym) else "missing_entirely"
            else:
                gap_status = "derivable_from_rules"
            _add_row(
                sym,
                symbol_type="predicate",
                atom=atom,
                gap_status=gap_status,
                kind=kind,
                assertable=assertable,
                case_text_evidence=snippets,
                explicit_case_evidence=explicit,
                via_rules=_rules_defining_predicate(kb_schema.get("rules") or [], sym),
            )

    observable_funcs = {
        str(f.get("name"))
        for f in kb_schema.get("functions") or []
        if isinstance(f, dict) and f.get("name") and fun_kinds.get(str(f["name"])) == "observable"
    }
    for fn in sorted(observable_funcs):
        assertable = _assertability(env, fn, is_function=True)
        snippets = _case_text_snippets(case_text, fn, sym_meta)
        present = any(f[0] == _norm(fn) for f in func_facts)
        gap_status = "directly_present" if present else "blocked_by_missing_numeric"
        _add_row(
            fn,
            symbol_type="function",
            atom=fn + "(...)",
            gap_status=gap_status,
            kind=fun_kinds.get(fn, "unknown"),
            assertable=assertable,
            case_text_evidence=snippets,
            explicit_case_evidence=bool(snippets) and _has_explicit_numeric_evidence(case_text),
            via_rules=[
                idx
                for idx, rule in enumerate(kb_schema.get("rules") or [])
                if fn in list(_iter_function_refs(_rule_expr_sides(rule)[0]))
            ],
        )

    temporal_issues = _temporal_query_issues(
        case_facts=facts,
        query=query,
        user_question=user_question,
        case_entities=case.get("entities") or {},
        kb_schema=kb_schema,
    )

    classification = _classify_gap(
        antecedents=antecedent_rows,
        temporal_issues=temporal_issues,
        symbolic_result=symbolic_result,
        case_text=case_text,
    )

    return {
        "query": {
            "predicate": q_pred,
            "args": q_args,
            "mode": query.get("mode"),
            "type": query.get("type"),
        },
        "symbolic_outcome": {
            "status": (symbolic_result or {}).get("status"),
            "label": (symbolic_result or {}).get("label"),
            "certain": (symbolic_result or {}).get("certain"),
            "possible": (symbolic_result or {}).get("possible"),
            "certainty_class": (symbolic_result or {}).get("certainty_class"),
        },
        "extracted_case": {
            "facts": facts,
            "value_assertions": [
                ln for ln in facts if isinstance(ln, str) and _FUNC.match(ln.strip())
            ],
            "entities": case.get("entities") or {},
        },
        "deriving_rules": deriving_rules,
        "antecedent_coverage": coverage,
        "antecedents": antecedent_rows,
        "temporal_query_issues": temporal_issues,
        "query_period_binding": query.get("query_period_binding"),
        "classification": classification,
    }


def save_symbolic_proof_gap_report(directory: str, report: dict[str, Any]) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, SYMBOLIC_PROOF_GAP_ARTIFACT)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def _find_kb_schema_near_results(results_path: str) -> dict[str, Any] | None:
    run_dir = os.path.dirname(os.path.abspath(results_path))
    candidates = [
        os.path.join(run_dir, "translated", "json_ir", "kb_schema.json"),
        os.path.join(run_dir, "json_ir", "kb_schema.json"),
        os.path.join(run_dir, "kb_schema.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError):
                continue
    return None


def _find_schema_environment_near_results(results_path: str) -> dict[str, Any] | None:
    run_dir = os.path.dirname(os.path.abspath(results_path))
    candidates = [
        os.path.join(run_dir, "translated", "json_ir", "schema_environment.json"),
        os.path.join(run_dir, "json_ir_compile", "schema_environment.json"),
        os.path.join(run_dir, "schema_environment.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("types"):
                    return data
            except (OSError, json.JSONDecodeError):
                continue
    return None


def build_from_results_json(
    results_path: str,
    *,
    question_index: int = 0,
    kb_schema: dict[str, Any] | None = None,
    schema_environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with open(results_path, encoding="utf-8") as f:
        payload = json.load(f)
    questions = payload.get("questions") or []
    if not questions:
        raise ValueError("results.json has no questions")
    qitem = questions[question_index]
    pipeline = qitem.get("pipeline") or {}
    case = pipeline.get("case") or {}
    query = pipeline.get("query") or {}
    symbolic_result = pipeline.get("symbolic_result") or {}

    env = schema_environment
    if env is None and isinstance(case.get("schema_environment"), dict):
        env = case["schema_environment"]
    if env is None:
        env = _find_schema_environment_near_results(results_path)

    schema = kb_schema
    if schema is None:
        schema = _kb_schema_from_extraction_prompt(pipeline.get("extraction_prompt") or "")
    if schema is None:
        schema = _find_kb_schema_near_results(results_path)
    if schema is None:
        raise ValueError("Could not recover kb_schema from results artifact")

    if env is None:
        env = build_schema_environment(schema)

    return build_symbolic_proof_gap_report(
        case=case,
        query=query,
        kb_schema=schema,
        schema_environment=env,
        symbolic_result=symbolic_result,
        case_text=(payload.get("case") or {}).get("text"),
        user_question=qitem.get("text"),
    )


def _kb_schema_from_extraction_prompt(prompt: str) -> dict[str, Any] | None:
    marker = "KB_SCHEMA:\n"
    if marker not in prompt:
        return None
    chunk = prompt.split(marker, 1)[1]
    end = chunk.find("\n\nCASE:")
    if end == -1:
        end = chunk.find("\n\nQUESTION:")
    if end == -1:
        return None
    try:
        data = json.loads(chunk[:end].strip())
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None

