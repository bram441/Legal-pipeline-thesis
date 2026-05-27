"""
Central prompt path registry for the legal pipeline (JSON-IR + LE + shared).
"""

from __future__ import annotations

# --- JSON IR KB ---
KB_JSON_IR_SYMBOLS = "kb/json_ir/generation/symbols.txt"
KB_JSON_IR_RULES = "kb/json_ir/generation/rules.txt"
KB_JSON_IR_SYMBOLS_REPAIR = "kb/json_ir/repair/symbols_repair.txt"
KB_JSON_IR_RULES_REPAIR = "kb/json_ir/repair/rules_repair.txt"

# --- JSON IR extraction ---
EXTRACTION_JSON_IR_CASE = "extraction/json_ir/generation/case_facts.txt"
EXTRACTION_JSON_IR_QUERY = "extraction/json_ir/generation/question_query.txt"
EXTRACTION_JSON_IR_CASE_REPAIR = "extraction/json_ir/repair/case_facts_repair.txt"
EXTRACTION_JSON_IR_QUERY_REPAIR = "extraction/json_ir/repair/question_query_repair.txt"

# --- LE (law → LE for le_json_ir_* strategies) ---
LE_LAW_TO_LE = "le/generation/law_to_le.txt"

# --- Shared / other ---
SHARED_JSON_IR_CONTRACT = "shared/json_ir_contract.txt"
TRANSLATION_TO_ENGLISH = "translation/translate_to_english.txt"
EXTRACTION_WORLD_KNOWLEDGE = "extraction/world_knowledge_lexical.txt"
EXTRACTION_DEBUG = "extraction/extraction_debug_prompt.txt"
NL_PARAPHRASE_SYSTEM = "nl/nl_paraphrase_system.txt"
NL_PARAPHRASE_USER = "nl/nl_paraphrase_user.txt"
NL_PARAPHRASE_RANGE = "nl/nl_paraphrase_range.txt"

# Historical path aliases → canonical paths.
PROMPT_ALIASES: dict[str, str] = {
    "kb/kb_compilation_json_ir_symbols.txt": KB_JSON_IR_SYMBOLS,
    "kb/kb_compilation_json_ir_rules.txt": KB_JSON_IR_RULES,
    "kb/kb_compilation_json_ir_symbols_repair.txt": KB_JSON_IR_SYMBOLS_REPAIR,
    "kb/kb_compilation_json_ir_rules_repair.txt": KB_JSON_IR_RULES_REPAIR,
    "extraction/openai_extract_case_json_ir_prompt.txt": EXTRACTION_JSON_IR_CASE,
    "extraction/openai_extract_query_json_ir_prompt.txt": EXTRACTION_JSON_IR_QUERY,
    "extraction/openai_extract_case_json_ir_repair.txt": EXTRACTION_JSON_IR_CASE_REPAIR,
    "extraction/openai_extract_query_json_ir_repair.txt": EXTRACTION_JSON_IR_QUERY_REPAIR,
    "le/law_to_le.txt": LE_LAW_TO_LE,
}

REQUIRED_PROMPT_PATHS: tuple[str, ...] = (
    KB_JSON_IR_SYMBOLS,
    KB_JSON_IR_RULES,
    KB_JSON_IR_SYMBOLS_REPAIR,
    KB_JSON_IR_RULES_REPAIR,
    EXTRACTION_JSON_IR_CASE,
    EXTRACTION_JSON_IR_QUERY,
    EXTRACTION_JSON_IR_CASE_REPAIR,
    EXTRACTION_JSON_IR_QUERY_REPAIR,
    LE_LAW_TO_LE,
    SHARED_JSON_IR_CONTRACT,
    TRANSLATION_TO_ENGLISH,
    EXTRACTION_WORLD_KNOWLEDGE,
    EXTRACTION_DEBUG,
    NL_PARAPHRASE_SYSTEM,
    NL_PARAPHRASE_USER,
    NL_PARAPHRASE_RANGE,
)


def resolve_prompt_path(relative_path: str) -> str:
    rel = (relative_path or "").replace("\\", "/").strip()
    return PROMPT_ALIASES.get(rel, rel)


def json_ir_generation_prompts() -> tuple[str, str]:
    """Return canonical JSON-IR symbol and rule generation prompt paths."""
    return KB_JSON_IR_SYMBOLS, KB_JSON_IR_RULES
