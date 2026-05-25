"""Typed schema environment built from validated JSON-IR KB symbols."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pipeline.extraction.case_fact_validation import (
    case_function_may_be_asserted,
    case_predicate_may_be_asserted,
)
from pipeline.kb.factual_case_input import (
    case_given_predicate_name,
    is_factual_case_input_candidate,
)
from pipeline.kb.factual_criteria import (
    is_factual_criteria_input_candidate,
    pragmatic_factual_criteria_mode_enabled,
    symbol_marked_factual_criteria_input,
)
from pipeline.kb.temporal_support import temporal_support_exempt_from_helper_definition

SCHEMA_ENVIRONMENT_FILENAME = "schema_environment.json"

_PERIOD_TYPE_TOKENS = frozenset(
    {
        "year",
        "period",
        "financialyear",
        "financial_year",
        "boekjaar",
        "fiscal",
        "fy",
        "date",
        "time",
    }
)


class SchemaEnvironmentError(Exception):
    """Invalid or incomplete schema environment."""


def _norm_tokens(name: str) -> set[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name or ""))
    s = s.replace("_", " ").replace("-", " ")
    return {t.lower() for t in s.split() if t.strip()}


def infer_type_kind(type_name: str) -> str:
    toks = _norm_tokens(type_name)
    if toks & _PERIOD_TYPE_TOKENS:
        return "period"
    if toks & {"int", "integer", "real", "float", "number", "amount", "euro"}:
        return "number"
    if toks & {"string", "text", "label"}:
        return "string"
    if toks & {"bool", "boolean"}:
        return "boolean"
    return "entity"


def _sym_dict(sym: dict[str, Any], *, kb_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    name = str(sym.get("name") or "").strip()
    if not name:
        return {}
    kind = str(sym.get("kind") or "unknown").strip().lower()
    args = list(sym.get("args") or [])
    returns = str(sym.get("returns") or "Bool").strip()
    legal_output = sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None
    output_category = sym.get("output_category")
    directly_observable = bool(sym.get("directly_observable") is True)
    background = bool(sym.get("background") is True)
    case_input = bool(sym.get("case_input") is True)
    temporal_support = temporal_support_exempt_from_helper_definition(sym)
    allowed, _ = case_predicate_may_be_asserted(sym) if returns.lower() == "bool" else (True, None)
    if returns.lower() != "bool":
        allowed, _ = case_function_may_be_asserted(sym)
    assertable = bool(allowed)
    factual_case_input = is_factual_case_input_candidate(sym, kb_schema)
    factual_criteria = symbol_marked_factual_criteria_input(sym) or (
        pragmatic_factual_criteria_mode_enabled()
        and is_factual_criteria_input_candidate(sym, kb_schema=kb_schema)
    )
    case_given_input_predicate = case_given_predicate_name(name) if factual_case_input else None
    if factual_criteria and not factual_case_input:
        assertable = True
    query_target = False
    if returns.lower() == "bool":
        from pipeline.kb.legal_effect import predicate_represents_legal_effect_output

        query_target = predicate_represents_legal_effect_output(
            name,
            description=str(sym.get("description") or ""),
            kind=kind,
            legal_output=legal_output,
            output_category=str(output_category or ""),
        )
    return {
        "name": name,
        "args": args,
        "returns": returns,
        "kind": kind,
        "description": sym.get("description") or "",
        "legal_output": legal_output,
        "output_category": output_category,
        "directly_observable": directly_observable,
        "background": background,
        "case_input": case_input,
        "assertable_in_case": assertable,
        "factual_case_input": factual_case_input,
        "factual_criteria_input": factual_criteria,
        "case_given_input_predicate": case_given_input_predicate,
        "query_target_candidate": query_target,
        "temporal_support": temporal_support,
    }


def build_schema_environment(kb_schema: dict[str, Any]) -> dict[str, Any]:
    """Build JSON-serializable typed environment from kb_schema."""
    if not isinstance(kb_schema, dict):
        raise SchemaEnvironmentError("kb_schema must be a dict")

    types: dict[str, dict[str, Any]] = {}
    for t in kb_schema.get("types") or []:
        t_name = str(t).strip() if not isinstance(t, dict) else str(t.get("name") or "").strip()
        if not t_name:
            continue
        types[t_name] = {
            "name": t_name,
            "kind": infer_type_kind(t_name),
            "aliases": [],
            "source": "kb_symbol_table",
        }

    predicates: dict[str, dict[str, Any]] = {}
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            entry = _sym_dict(p, kb_schema=kb_schema)
            if entry:
                predicates[entry["name"]] = entry
                for arg_t in entry["args"]:
                    if arg_t and arg_t not in types:
                        types[str(arg_t)] = {
                            "name": str(arg_t),
                            "kind": infer_type_kind(str(arg_t)),
                            "aliases": [],
                            "source": "kb_symbol_table",
                        }

    functions: dict[str, dict[str, Any]] = {}
    for f in kb_schema.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            entry = _sym_dict(f, kb_schema=kb_schema)
            if entry:
                functions[entry["name"]] = entry
                for arg_t in entry["args"]:
                    if arg_t and arg_t not in types:
                        types[str(arg_t)] = {
                            "name": str(arg_t),
                            "kind": infer_type_kind(str(arg_t)),
                            "aliases": [],
                            "source": "kb_symbol_table",
                        }

    assertable_preds = sorted(
        n for n, s in predicates.items() if s.get("assertable_in_case")
    )
    assertable_funs = sorted(n for n, s in functions.items() if s.get("assertable_in_case"))
    legal_outputs = sorted(n for n, s in predicates.items() if s.get("query_target_candidate"))
    temporal_syms = sorted(n for n, s in predicates.items() if s.get("temporal_support"))

    factual_inputs = sorted(
        n for n, s in predicates.items() if s.get("factual_case_input")
    )
    factual_criteria_inputs = sorted(
        n for n, s in predicates.items() if s.get("factual_criteria_input")
    )

    return {
        "types": types,
        "predicates": predicates,
        "functions": functions,
        "assertable_case_symbols": {
            "predicates": assertable_preds,
            "functions": assertable_funs,
        },
        "factual_case_input_predicates": factual_inputs,
        "factual_criteria_input_predicates": factual_criteria_inputs,
        "legal_output_query_targets": legal_outputs,
        "temporal_support_symbols": temporal_syms,
    }


def save_schema_environment(run_dir: str, kb_schema: dict[str, Any]) -> dict[str, Any]:
    env = build_schema_environment(kb_schema)
    path = os.path.join(run_dir, SCHEMA_ENVIRONMENT_FILENAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(env, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return env


def load_schema_environment(run_dir: str, *, kb_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    path = os.path.join(run_dir, SCHEMA_ENVIRONMENT_FILENAME)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("types"):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    if kb_schema:
        return build_schema_environment(kb_schema)
    raise SchemaEnvironmentError("schema_environment.json missing and no kb_schema to build from")


def schema_environment_prompt_view(env: dict[str, Any]) -> str:
    """Compact text block for extraction prompts."""
    lines: list[str] = []
    type_names = sorted((env.get("types") or {}).keys())
    lines.append("ALLOWED ENTITY TYPES (use only these as entities keys):")
    for t in type_names:
        meta = (env.get("types") or {}).get(t) or {}
        lines.append(f"- {t} ({meta.get('kind', 'entity')})")

    lines.append("")
    lines.append("ASSERTABLE CASE SYMBOLS (only these may appear in case assertions/value_assertions):")
    acs = env.get("assertable_case_symbols") or {}
    for pname in acs.get("predicates") or []:
        p = (env.get("predicates") or {}).get(pname) or {}
        args = ", ".join(p.get("args") or [])
        lines.append(f"- predicate {pname}({args})")
    for fname in acs.get("functions") or []:
        f = (env.get("functions") or {}).get(fname) or {}
        args = ", ".join(f.get("args") or [])
        lines.append(f"- function {fname}({args}) -> {f.get('returns', 'Int')}")

    lines.append("")
    lines.append(
        "FACTUAL CRITERIA INPUT (externally checkable legal/factual conditions — assert only when case "
        "text explicitly supports them; include evidence_text as a verbatim substring; never invent "
        "numeric values):"
    )
    for pname in env.get("factual_criteria_input_predicates") or []:
        p = (env.get("predicates") or {}).get(pname) or {}
        args = ", ".join(p.get("args") or [])
        lines.append(f"- {pname}({args})")

    lines.append("")
    lines.append(
        "FACTUAL CASE INPUT (threshold/criterion satisfaction — assert only when case text explicitly "
        "states the condition; include evidence_text; never invent numeric values):"
    )
    for pname in env.get("factual_case_input_predicates") or []:
        p = (env.get("predicates") or {}).get(pname) or {}
        args = ", ".join(p.get("args") or [])
        cgp = p.get("case_given_input_predicate") or ("case_given_" + pname)
        lines.append(f"- {pname}({args}) -> rendered as {cgp}({args}) when explicitly supported")

    lines.append("")
    lines.append("NON-ASSERTABLE (do NOT use as case facts):")
    for pname, p in sorted((env.get("predicates") or {}).items()):
        if not p.get("assertable_in_case"):
            reason = []
            if p.get("query_target_candidate"):
                reason.append("legal_output/query_target")
            elif p.get("temporal_support"):
                reason.append("temporal_support")
            elif p.get("kind") in {"helper", "derived", "conclusion"}:
                reason.append(p.get("kind"))
            else:
                reason.append("not_assertable")
            lines.append(f"- predicate {pname}: {', '.join(reason) or 'forbidden'}")

    lines.append("")
    lines.append("LEGAL-OUTPUT QUERY TARGET CANDIDATES (boolean query predicates):")
    for pname in env.get("legal_output_query_targets") or []:
        p = (env.get("predicates") or {}).get(pname) or {}
        args = ", ".join(p.get("args") or [])
        lines.append(f"- {pname}({args})")

    lines.append("")
    lines.append("TEMPORAL/BACKGROUND SUPPORT (not final legal-effect answers when legal-output exists):")
    for pname in env.get("temporal_support_symbols") or []:
        p = (env.get("predicates") or {}).get(pname) or {}
        args = ", ".join(p.get("args") or [])
        note = "assertable_in_case" if p.get("assertable_in_case") else "not_assertable_in_case"
        lines.append(f"- {pname}({args}) [{note}]")

    lines.append("")
    lines.append(
        "RULES: Use only listed types and symbol names. Case facts only from assertable symbols "
        "or factual case input predicates when explicitly supported by case text with evidence_text. "
        "Prefer numeric value_assertions when explicit numbers are present; never invent numbers. "
        "Query targets must be legal-output candidates when the question asks for a legal effect. "
        "Never assert legal-output or query-target predicates as case facts. "
        "Do not invent entity types."
    )
    return "\n".join(lines)
