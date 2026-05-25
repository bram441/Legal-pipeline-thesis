"""Pre-solver validation against typed schema environment."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pipeline.extraction.json_ir import _safe_entity
from pipeline.validation.entity_type_mapping import (
    apply_resolved_entities_to_case,
    resolve_entity_type_mapping,
)

CASE_ENTITY_MAPPING_ARTIFACT = "case_entity_type_mapping.json"
PRE_SOLVER_DIAGNOSTICS_ARTIFACT = "pre_solver_domain_validation.json"

_ATOM = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_FUNC = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(.+?)\s*\.\s*$")


class PreSolverDomainValidationError(ValueError):
    """Case/query cannot be rendered into FO domains before IDP-Z3."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class CaseSchemaValidationError(ValueError):
    """Case facts/entities violate schema environment."""


def _split_args(blob: str) -> list[str]:
    return [_safe_entity(x) for x in (blob or "").split(",") if _safe_entity(x)]


def _validate_fact_signatures(case: dict[str, Any], env: dict[str, Any], mapping: dict[str, Any]) -> None:
    preds = env.get("predicates") or {}
    funs = env.get("functions") or {}
    entities = mapping.get("entities") or {}

    for ln in (case or {}).get("facts") or []:
        if not isinstance(ln, str):
            continue
        s = ln.strip()
        mf = _FUNC.match(s)
        if mf:
            name = mf.group(1)
            args = _split_args(mf.group(2))
            sym = funs.get(name)
            if not sym:
                raise CaseSchemaValidationError("Unknown function in case facts: " + name)
            if not sym.get("assertable_in_case"):
                raise CaseSchemaValidationError(
                    "Function " + name + " is not assertable as a case fact."
                )
            expected = list(sym.get("args") or [])
            if len(args) != len(expected):
                raise CaseSchemaValidationError(
                    f"Function {name} expects {len(expected)} args, got {len(args)}."
                )
            for i, (arg, typ) in enumerate(zip(args, expected)):
                ent_info = entities.get(arg) or {}
                if ent_info.get("resolved_type") != typ:
                    raise CaseSchemaValidationError(
                        f"Function {name} arg{i} '{arg}' has resolved type "
                        f"{ent_info.get('resolved_type')}, expected {typ}."
                    )
            continue

        m = _ATOM.match(s)
        if not m:
            continue
        name = m.group(1)
        args = _split_args(m.group(2))
        sym = preds.get(name)
        if not sym:
            raise CaseSchemaValidationError("Unknown predicate in case facts: " + name)
        if not sym.get("assertable_in_case"):
            raise CaseSchemaValidationError(
                "Predicate " + name + " is not assertable as a case fact."
            )
        expected = list(sym.get("args") or [])
        if len(args) != len(expected):
            raise CaseSchemaValidationError(
                f"Predicate {name} expects {len(expected)} args, got {len(args)}."
            )
        for i, (arg, typ) in enumerate(zip(args, expected)):
            ent_info = entities.get(arg) or {}
            if ent_info.get("resolved_type") != typ:
                raise CaseSchemaValidationError(
                    f"Predicate {name} arg{i} '{arg}' has resolved type "
                    f"{ent_info.get('resolved_type')}, expected {typ}."
                )


def _validate_query_against_environment(
    query: dict[str, Any],
    env: dict[str, Any],
    mapping: dict[str, Any],
) -> None:
    if not isinstance(query, dict):
        return
    if str(query.get("type") or "") != "predicate":
        return
    pred = str(query.get("predicate") or "").strip()
    sig = (env.get("predicates") or {}).get(pred) or {}
    if not sig:
        raise CaseSchemaValidationError("Query predicate not in schema environment: " + pred)
    expected = list(sig.get("args") or [])
    args = [_safe_entity(x) for x in (query.get("args") or [])]
    if len(args) != len(expected):
        raise CaseSchemaValidationError(
            f"Query predicate {pred} expects {len(expected)} args, got {len(args)}."
        )
    entities = mapping.get("entities") or {}
    for i, (arg, typ) in enumerate(zip(args, expected)):
        if not arg:
            raise CaseSchemaValidationError(f"Query arg{i} for {pred} is empty.")
        ent_info = entities.get(arg) or {}
        if ent_info.get("resolved_type") != typ:
            raise CaseSchemaValidationError(
                f"Query arg{i} '{arg}' resolved as {ent_info.get('resolved_type')}, expected {typ}."
            )


def prepare_case_for_symbolic(
    case: dict[str, Any],
    query: dict[str, Any] | None,
    env: dict[str, Any],
    *,
    artifact_dir: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Validate case/query, resolve entity types, rewrite case.entities, return diagnostics.

    Raises PreSolverDomainValidationError on conflicts/unmapped entities.
    """
    mapping = resolve_entity_type_mapping(case, query, env)
    if mapping.get("conflicts"):
        diag = {
            "pre_solver_domain_validation_errors": [
                "entity_type_conflicts: " + json.dumps(mapping["conflicts"], ensure_ascii=False)
            ],
            "case_entity_type_mapping": mapping,
            "unmapped_case_entities": mapping.get("unmapped_entities") or [],
        }
        if artifact_dir:
            _write_json(artifact_dir, CASE_ENTITY_MAPPING_ARTIFACT, mapping)
            _write_json(artifact_dir, PRE_SOLVER_DIAGNOSTICS_ARTIFACT, diag)
        raise PreSolverDomainValidationError(
            "Conflicting inferred types for case entities: "
            + json.dumps(mapping["conflicts"], ensure_ascii=False),
            diagnostics=diag,
        )

    unmapped = list(mapping.get("unmapped_entities") or [])
    # Entities only in case.entities without facts/query usage and wrong type
    for ent, info in (mapping.get("entities") or {}).items():
        if not info.get("resolved_type"):
            if ent not in unmapped:
                unmapped.append(ent)

    if unmapped:
        diag = {
            "pre_solver_domain_validation_errors": [
                "unmapped_case_entities: " + ", ".join(sorted(unmapped))
            ],
            "case_entity_type_mapping": mapping,
            "unmapped_case_entities": sorted(unmapped),
        }
        if artifact_dir:
            _write_json(artifact_dir, CASE_ENTITY_MAPPING_ARTIFACT, mapping)
            _write_json(artifact_dir, PRE_SOLVER_DIAGNOSTICS_ARTIFACT, diag)
        raise PreSolverDomainValidationError(
            "Case entities could not be mapped to KB types: " + ", ".join(sorted(unmapped)),
            diagnostics=diag,
        )

    _validate_fact_signatures(case, env, mapping)
    _validate_query_against_environment(query, env, mapping)

    domain_map = apply_resolved_entities_to_case(case, mapping)

    rendered_entities = {t: list(ids) for t, ids in domain_map.items()}
    diag = {
        "case_entities_rendered_to_domains": rendered_entities,
        "query_arguments_with_inferred_types": mapping.get("query_arguments_with_inferred_types") or [],
        "unmapped_case_entities": [],
        "pre_solver_domain_validation_errors": [],
    }

    if artifact_dir:
        _write_json(artifact_dir, CASE_ENTITY_MAPPING_ARTIFACT, mapping)
        _write_json(artifact_dir, PRE_SOLVER_DIAGNOSTICS_ARTIFACT, diag)

    case["schema_environment"] = env
    case["entity_type_mapping"] = mapping
    case["resolved_entity_domains"] = domain_map
    return case, mapping, diag


def _write_json(directory: str, filename: str, payload: dict[str, Any]) -> None:
    try:
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError:
        pass
