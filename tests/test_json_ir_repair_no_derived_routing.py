"""Route generic 'no derived legal outputs' schema errors to legal-effect symbols repair."""

from __future__ import annotations

from pipeline.kb.json_ir import SCHEMA_DESIGN_TAG
from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    normalize_error_code,
    normalize_error_signature,
)

_NO_DERIVED_MSG = (
    SCHEMA_DESIGN_TAG
    + ": Symbol table contains no derived legal outputs. A reusable legal KB must expose "
    "at least one derived predicate/function representing legal classifications, consequences, "
    "rights, obligations, permissions, prohibitions, exceptions, sanctions, validity results, "
    "entitlements, or exclusions."
)

_NO_OBSERVABLE_MSG = (
    SCHEMA_DESIGN_TAG
    + ": Symbol table contains no observable case-input symbols. A reusable legal KB must "
    "include observable predicates/functions that can be populated from case descriptions."
)

_STATUS_AS_TYPE_MSG = (
    SCHEMA_DESIGN_TAG
    + ": Type 'SmallCompanyStatus' is semantically identical to the status or classification "
    "encoded as a primitive type."
)

_TEMPORAL_MSG = (
    SCHEMA_DESIGN_TAG
    + ": The scoped law/question requires reasoning over previous, following, or consecutive "
    "periods, but the symbol table has no temporal support relation/function."
)

_THRESHOLD_MSG = (
    SCHEMA_DESIGN_TAG
    + ": Cannot prove disqualification; add an exclusion rule such as not_qualified when criteria fail."
)


def test_normalize_no_derived_legal_outputs_to_missing_legal_effect():
    assert normalize_error_code(_NO_DERIVED_MSG) == "missing_legal_effect_output"
    assert normalize_error_signature(_NO_DERIVED_MSG) == "schema::missing_legal_effect"


def test_repair_hints_include_legal_effect_supplement_for_no_derived():
    hints = _build_repair_hints(
        _NO_DERIVED_MSG,
        "",
        error_code=normalize_error_code(_NO_DERIVED_MSG),
        layer="symbols",
        law_text="Legal consequences apply from the following financial year.",
        question_text="When do legal consequences apply?",
        scope_metadata={
            "contains_effect_language": True,
            "question_asks_legal_effect": True,
        },
        symbol_table={
            "types": ["Company"],
            "predicates": [
                {
                    "name": "revenue_known",
                    "kind": "observable",
                    "args": ["Company"],
                    "returns": "Bool",
                },
            ],
            "functions": [],
        },
    )
    assert "MISSING LEGAL-EFFECT OUTPUT" in hints
    assert "derived" in hints.lower()
    assert "legal_output" in hints.lower() or "legal-effect" in hints.lower()
    assert "MISSING TEMPORAL SUPPORT SYMBOL" not in hints


def test_no_derived_classifies_as_symbols_repair():
    assert (
        classify_json_ir_validation_error(_NO_DERIVED_MSG)
        == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    )


def test_no_observable_not_mapped_to_missing_legal_effect():
    assert normalize_error_code(_NO_OBSERVABLE_MSG) != "missing_legal_effect_output"
    assert normalize_error_signature(_NO_OBSERVABLE_MSG) == "schema::no_observable"


def test_status_as_type_precedence_over_no_derived_phrase():
    assert normalize_error_code(_STATUS_AS_TYPE_MSG) == "status_as_type"


def test_temporal_support_precedence_when_message_is_temporal_specific():
    assert normalize_error_code(_TEMPORAL_MSG) == "missing_temporal_support_symbol"


def test_threshold_errors_unchanged():
    assert normalize_error_code(_THRESHOLD_MSG) == "missing_threshold_classification_exclusion"
