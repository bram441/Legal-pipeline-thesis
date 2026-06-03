"""Unit tests for structured JSON IR compile loop (mocked LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError
from pipeline.kb.json_ir_repair import RULE_DESIGN_TAG, SCHEMA_DESIGN_TAG, normalize_error_code
from pipeline.kb.json_ir_compile_loop import (
    CompileLoopLimits,
    compile_json_ir_structured,
)

LAW_EFFECT = (
    "The consequences apply from the financial year following the year in which "
    "the criteria were exceeded for the second consecutive time."
)

LAW_CLASS = "A micro-company is a company that does not exceed more than one criterion."

GOOD_SYMBOLS = {
    "types": ["Company", "FinancialYear"],
    "predicates": [
        {
            "name": "reports_for_year",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "kind": "observable",
        },
        {
            "name": "consequences_apply_from_following_financial_year",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "kind": "derived",
            "legal_output": True,
            "description": "Legal consequences apply from the following financial year",
        },
    ],
    "functions": [
        {
            "name": "next_financial_year",
            "kind": "helper",
            "args": ["FinancialYear"],
            "returns": "FinancialYear",
            "description": "The financial year immediately following the given year.",
        },
    ],
}

RULES_WITH_HELPER_USE = {
    "rules": [
        {
            "forall": [{"var": "c", "type": "Company"}],
            "if": [{"pred": "undefined_helper", "args": ["c"]}],
            "then": [{"pred": "consequences_apply_from_following_financial_year", "args": ["c", "y"]}],
        }
    ]
}

RULES_DEFINES_HELPER = {
    "rules": [
        {
            "forall": [
                {"var": "c", "type": "Company"},
                {"var": "y", "type": "FinancialYear"},
            ],
            "if": [{"pred": "reports_for_year", "args": ["c", "y"]}],
            "then": [{"pred": "consequences_apply_from_following_financial_year", "args": ["c", "y"]}],
            "operator": "implies",
        }
    ]
}

STATUS_AS_TYPE_SYMBOLS = {
    "types": ["MicroCompany"],
    "predicates": [
        {
            "name": "is_micro_company",
            "args": ["MicroCompany"],
            "returns": "Bool",
            "kind": "derived",
        },
    ],
    "functions": [],
}

FIXED_SYMBOLS = {
    "types": ["Company"],
    "predicates": [
        {"name": "fact", "args": ["Company"], "returns": "Bool", "kind": "observable"},
        {"name": "is_micro_company", "args": ["Company"], "returns": "Bool", "kind": "derived"},
    ],
    "functions": [],
}


def _render_validate_or_fail(merged_ir, *, law_text_for_lints=None, scope_metadata=None, **_kw):
    preds = {p.get("name") for p in merged_ir.get("predicates") or []}
    rules = merged_ir.get("rules") or []
    for r in rules:
        then = r.get("then") or []
        for atom in then:
            if isinstance(atom, dict):
                args = atom.get("args") or []
                if "y" in args and not any(
                    isinstance(x, dict) and x.get("pred") == "reports_for_year" for x in (r.get("if") or [])
                ):
                    raise JSONIRCompilationError(
                        RULE_DESIGN_TAG
                        + ": Helper predicate 'undefined_helper' has no defining rule. Repair layer: rules."
                    )
    if law_text_for_lints and LAW_EFFECT in (law_text_for_lints or ""):
        if "consequences_apply_from_following_financial_year" not in preds:
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + ": The scoped law text contains legal-effect or timing language, but the JSON IR "
                "has no derived legal-output predicate representing that effect. Repair layer: symbols."
            )
    from pipeline.kb.json_ir import validate_json_ir_symbols

    validate_json_ir_symbols(merged_ir)
    return "vocabulary V { type Company; } theory T:V { ! x in Company: true. }", merged_ir


@pytest.fixture(autouse=True)
def _patch_render(monkeypatch):
    monkeypatch.setattr(
        "pipeline.kb.json_ir_compile_loop.render_json_ir_to_fo_and_schema",
        _render_validate_or_fail,
    )


def test_rules_repair_success_same_symbol_version(tmp_path: Path) -> None:
    calls = {"rules": 0}

    def symbols_llm(*_a, **_k):
        return dict(GOOD_SYMBOLS), "{}"

    def rules_llm(_law, _st, *, repair=False, **_k):
        calls["rules"] += 1
        if calls["rules"] == 1:
            return dict(RULES_WITH_HELPER_USE), "{}"
        return dict(RULES_DEFINES_HELPER), "{}"

    fo, schema = compile_json_ir_structured(
        LAW_EFFECT,
        symbols_llm=symbols_llm,
        rules_llm=rules_llm,
        repair_context_fn=lambda **_kw: "",
        artifact_dir=tmp_path,
        limits=CompileLoopLimits(2, 3, 10, 3, 2),
    )
    assert "vocabulary" in fo.lower()
    assert calls["rules"] == 2
    assert (tmp_path / "repair_history.json").is_file()


def test_symbols_repair_status_as_type(tmp_path: Path) -> None:
    sym_calls = {"n": 0}

    def symbols_llm(*_a, **_k):
        sym_calls["n"] += 1
        if sym_calls["n"] == 1:
            return dict(STATUS_AS_TYPE_SYMBOLS), "{}"
        return dict(FIXED_SYMBOLS), "{}"

    def rules_llm(_law, _st, **_k):
        return {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "fact", "args": ["c"]}],
                    "then": [{"pred": "is_micro_company", "args": ["c"]}],
                }
            ]
        }, "{}"

    compile_json_ir_structured(
        LAW_CLASS,
        symbols_llm=symbols_llm,
        rules_llm=rules_llm,
        repair_context_fn=lambda **_kw: "",
        artifact_dir=tmp_path,
        limits=CompileLoopLimits(3, 2, 10, 3, 2),
    )


def test_missing_legal_effect_routes_symbols(tmp_path: Path) -> None:
    sym_calls = {"n": 0}

    def symbols_llm(*_a, **_k):
        sym_calls["n"] += 1
        if sym_calls["n"] == 1:
            bad = dict(GOOD_SYMBOLS)
            bad["predicates"] = [p for p in bad["predicates"] if p["name"] != "consequences_apply_from_following_financial_year"]
            bad["predicates"].append(
                {
                    "name": "is_small_company",
                    "args": ["Company", "FinancialYear"],
                    "returns": "Bool",
                    "kind": "derived",
                }
            )
            return bad, "{}"
        return dict(GOOD_SYMBOLS), "{}"

    def rules_llm(_law, _st, **_k):
        return dict(RULES_DEFINES_HELPER), "{}"

    compile_json_ir_structured(
        LAW_EFFECT,
        symbols_llm=symbols_llm,
        rules_llm=rules_llm,
        repair_context_fn=lambda **_kw: "",
        artifact_dir=tmp_path,
        limits=CompileLoopLimits(2, 2, 8, 3, 2),
    )
    hist = json.loads((tmp_path / "repair_history.json").read_text(encoding="utf-8"))
    routes = [e.get("repair_route") for e in hist["events"]]
    assert "symbols_repair_required" in routes


def test_budget_exhausted(tmp_path: Path) -> None:
    def symbols_llm(*_a, **_k):
        return dict(GOOD_SYMBOLS), "{}"

    def rules_llm(_law, _st, **_k):
        return dict(RULES_WITH_HELPER_USE), "{}"

    with pytest.raises(LawCompilationError) as exc:
        compile_json_ir_structured(
            LAW_EFFECT,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **_kw: "",
            artifact_dir=tmp_path,
            limits=CompileLoopLimits(1, 5, 2, 3, 2),
        )
    summary = (exc.value.repair_summary or {}) if exc.value.repair_summary else {}
    assert (
        summary.get("budget_exhausted")
        or summary.get("repair_stalled")
        or summary.get("repeated_error_detected")
        or "budget" in str(exc.value).lower()
    )


def test_concise_failure_message_no_recursion() -> None:
    def symbols_llm(*_a, **_k):
        return dict(STATUS_AS_TYPE_SYMBOLS), "{}"

    def rules_llm(*_a, **_k):
        return {"rules": []}, "{}"

    with pytest.raises(LawCompilationError) as exc:
        compile_json_ir_structured(
            LAW_CLASS,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **_kw: "",
            limits=CompileLoopLimits(1, 1, 2, 2, 1),
        )
    msg = str(exc.value)
    assert msg.count("JSON IR compilation failed after") == 0
    assert "symbol_versions=" in msg
    assert "repair_snapshot" not in msg


def test_normalize_error_code_helper() -> None:
    msg = RULE_DESIGN_TAG + ": Helper predicate 'exceeds_x' has no defining rule."
    assert normalize_error_code(msg) == "missing_helper_definition"


def test_repeated_error_stalls(tmp_path: Path) -> None:
    def symbols_llm(*_a, **_k):
        return dict(GOOD_SYMBOLS), "{}"

    def rules_llm(_law, _st, **_k):
        return dict(RULES_WITH_HELPER_USE), "{}"

    with pytest.raises(LawCompilationError) as exc:
        compile_json_ir_structured(
            LAW_EFFECT,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **_kw: "",
            artifact_dir=tmp_path,
            limits=CompileLoopLimits(1, 5, 10, 2, 2),
        )
    snap = exc.value.repair_snapshot or {}
    summary = snap.get("repair_summary") or exc.value.repair_summary or {}
    assert summary.get("repair_stalled") or summary.get("repeated_error_detected")
