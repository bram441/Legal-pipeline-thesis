from __future__ import annotations

import inspect
from pathlib import Path

from pipeline.kb.json_ir import render_json_ir_to_fo_and_schema
from pipeline.kb.json_ir_compile_loop import compile_json_ir_structured
from pipeline.utils.prompt_paths import (
    KB_JSON_IR_RULES,
    KB_JSON_IR_SYMBOLS,
    REQUIRED_PROMPT_PATHS,
    json_ir_generation_prompts,
)


def test_json_ir_generation_prompts_are_canonical() -> None:
    symbols, rules = json_ir_generation_prompts()
    assert symbols == KB_JSON_IR_SYMBOLS
    assert rules == KB_JSON_IR_RULES


def test_no_rule_plan_in_required_prompt_paths() -> None:
    joined = "\n".join(REQUIRED_PROMPT_PATHS)
    assert "rule_plan" not in joined


def test_canonical_prompts_include_guidance_and_examples_appendix() -> None:
    root = Path(__file__).resolve().parents[1]
    symbols = (root / "prompts" / "kb" / "json_ir" / "generation" / "symbols.txt").read_text(encoding="utf-8")
    rules = (root / "prompts" / "kb" / "json_ir" / "generation" / "rules.txt").read_text(encoding="utf-8")
    assert "Controlled directly-observable exception:" in symbols
    assert "Directly assertable status/classification facts" in symbols
    assert "Prerequisite status/classification closure:" in rules
    assert "# ILLUSTRATIVE EXAMPLES APPENDIX" in symbols
    assert "# ILLUSTRATIVE EXAMPLES APPENDIX" in rules


def test_rule_metadata_keys_survive_schema_and_not_semantics() -> None:
    ir = {
        "types": ["Company"],
        "predicates": [
            {"name": "fact", "args": ["Company"], "returns": "Bool", "kind": "observable"},
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "legal_output": True,
                "output_category": "classification",
            },
        ],
        "functions": [],
        "rules": [
            {
                "id": "rule_small_company_positive",
                "description": "Positive classification",
                "source_ref": "Art 1:24",
                "rule_kind": "classification_positive",
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "fact", "args": ["c"]}],
                "then": [{"pred": "is_small_company", "args": ["c"]}],
                "operator": "implies",
            }
        ],
    }
    fo, schema = render_json_ir_to_fo_and_schema(ir)
    assert "is_small_company" in fo
    assert schema["rules"][0]["id"] == "rule_small_company_positive"
    assert schema["rules"][0]["rule_kind"] == "classification_positive"


def test_compile_loop_does_not_accept_rule_plan_llm() -> None:
    assert "rule_plan_llm" not in inspect.signature(compile_json_ir_structured).parameters
