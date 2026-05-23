"""
Central prompt path registry for the legal pipeline.

Canonical paths use the reorganized prompts/ tree. Legacy relative paths resolve
through PROMPT_ALIASES so existing call sites keep working.
"""

from __future__ import annotations

# --- JSON IR KB ---
KB_JSON_IR_SYMBOLS = "kb/json_ir/generation/symbols.txt"
KB_JSON_IR_RULES = "kb/json_ir/generation/rules.txt"
KB_JSON_IR_SYMBOLS_REPAIR = "kb/json_ir/repair/symbols_repair.txt"
KB_JSON_IR_RULES_REPAIR = "kb/json_ir/repair/rules_repair.txt"

# --- Legacy direct-FO KB ---
KB_LEGACY_COMPILATION = "kb/legacy/kb_compilation.txt"
KB_LEGACY_VOCAB_ONLY = "kb/legacy/kb_vocab_only.txt"
KB_LEGACY_THEORY_ONLY = "kb/legacy/kb_theory_only.txt"
KB_LEGACY_REPAIR_SYNTAX = "kb/legacy/kb_compilation_repair_syntax.txt"
KB_LEGACY_REPAIR_SEMANTIC = "kb/legacy/kb_compilation_repair_semantic.txt"
KB_LEGACY_REPAIR_SYMBOLIC = "kb/legacy/kb_compilation_repair_symbolic.txt"

# --- JSON IR extraction ---
EXTRACTION_JSON_IR_CASE = "extraction/json_ir/generation/case_facts.txt"
EXTRACTION_JSON_IR_QUERY = "extraction/json_ir/generation/question_query.txt"
EXTRACTION_JSON_IR_CASE_REPAIR = "extraction/json_ir/repair/case_facts_repair.txt"
EXTRACTION_JSON_IR_QUERY_REPAIR = "extraction/json_ir/repair/question_query_repair.txt"

# --- Legacy extraction ---
EXTRACTION_LEGACY_CASE = "extraction/legacy/openai_extract_case_prompt.txt"
EXTRACTION_LEGACY_QUERY = "extraction/legacy/openai_extract_query_prompt.txt"
EXTRACTION_LEGACY_CASE_REPAIR = "extraction/legacy/openai_extract_case_prompt_repair.txt"
EXTRACTION_LEGACY_QUERY_REPAIR = "extraction/legacy/openai_extract_query_prompt_repair.txt"

# --- LE ---
LE_LAW_TO_LE = "le/generation/law_to_le.txt"
LE_TO_FO = "le/generation/le_to_fo.txt"
LE_VOCAB_ONLY = "le/generation/le_vocab_only.txt"
LE_THEORY_ONLY = "le/generation/le_theory_only.txt"

# --- Shared / other (unchanged locations) ---
SHARED_JSON_IR_CONTRACT = "shared/json_ir_contract.txt"
TRANSLATION_TO_ENGLISH = "translation/translate_to_english.txt"
EXTRACTION_WORLD_KNOWLEDGE = "extraction/world_knowledge_lexical.txt"
EXTRACTION_DEBUG = "extraction/extraction_debug_prompt.txt"
NL_PARAPHRASE_SYSTEM = "nl/nl_paraphrase_system.txt"
NL_PARAPHRASE_USER = "nl/nl_paraphrase_user.txt"
NL_PARAPHRASE_RANGE = "nl/nl_paraphrase_range.txt"

# Old path -> canonical path (backwards compatibility).
PROMPT_ALIASES: dict[str, str] = {
    "kb/kb_compilation_json_ir_symbols.txt": KB_JSON_IR_SYMBOLS,
    "kb/kb_compilation_json_ir_rules.txt": KB_JSON_IR_RULES,
    "kb/kb_compilation_json_ir_symbols_repair.txt": KB_JSON_IR_SYMBOLS_REPAIR,
    "kb/kb_compilation_json_ir_rules_repair.txt": KB_JSON_IR_RULES_REPAIR,
    "kb/kb_compilation.txt": KB_LEGACY_COMPILATION,
    "kb/kb_vocab_only.txt": KB_LEGACY_VOCAB_ONLY,
    "kb/kb_theory_only.txt": KB_LEGACY_THEORY_ONLY,
    "kb/kb_compilation_repair_syntax.txt": KB_LEGACY_REPAIR_SYNTAX,
    "kb/kb_compilation_repair_semantic.txt": KB_LEGACY_REPAIR_SEMANTIC,
    "kb/kb_compilation_repair_symbolic.txt": KB_LEGACY_REPAIR_SYMBOLIC,
    "extraction/openai_extract_case_json_ir_prompt.txt": EXTRACTION_JSON_IR_CASE,
    "extraction/openai_extract_query_json_ir_prompt.txt": EXTRACTION_JSON_IR_QUERY,
    "extraction/openai_extract_case_json_ir_repair.txt": EXTRACTION_JSON_IR_CASE_REPAIR,
    "extraction/openai_extract_query_json_ir_repair.txt": EXTRACTION_JSON_IR_QUERY_REPAIR,
    "extraction/openai_extract_case_prompt.txt": EXTRACTION_LEGACY_CASE,
    "extraction/openai_extract_query_prompt.txt": EXTRACTION_LEGACY_QUERY,
    "extraction/openai_extract_case_prompt_repair.txt": EXTRACTION_LEGACY_CASE_REPAIR,
    "extraction/openai_extract_query_prompt_repair.txt": EXTRACTION_LEGACY_QUERY_REPAIR,
    "le/law_to_le.txt": LE_LAW_TO_LE,
    "le/le_to_fo.txt": LE_TO_FO,
    "le/le_vocab_only.txt": LE_VOCAB_ONLY,
    "le/le_theory_only.txt": LE_THEORY_ONLY,
}

# All canonical paths that must exist on disk (for tests).
REQUIRED_PROMPT_PATHS: tuple[str, ...] = (
    KB_JSON_IR_SYMBOLS,
    KB_JSON_IR_RULES,
    KB_JSON_IR_SYMBOLS_REPAIR,
    KB_JSON_IR_RULES_REPAIR,
    KB_LEGACY_COMPILATION,
    KB_LEGACY_VOCAB_ONLY,
    KB_LEGACY_THEORY_ONLY,
    KB_LEGACY_REPAIR_SYNTAX,
    KB_LEGACY_REPAIR_SEMANTIC,
    KB_LEGACY_REPAIR_SYMBOLIC,
    EXTRACTION_JSON_IR_CASE,
    EXTRACTION_JSON_IR_QUERY,
    EXTRACTION_JSON_IR_CASE_REPAIR,
    EXTRACTION_JSON_IR_QUERY_REPAIR,
    EXTRACTION_LEGACY_CASE,
    EXTRACTION_LEGACY_QUERY,
    EXTRACTION_LEGACY_CASE_REPAIR,
    EXTRACTION_LEGACY_QUERY_REPAIR,
    LE_LAW_TO_LE,
    LE_TO_FO,
    LE_VOCAB_ONLY,
    LE_THEORY_ONLY,
    SHARED_JSON_IR_CONTRACT,
    TRANSLATION_TO_ENGLISH,
    EXTRACTION_WORLD_KNOWLEDGE,
    EXTRACTION_DEBUG,
    NL_PARAPHRASE_SYSTEM,
    NL_PARAPHRASE_USER,
    NL_PARAPHRASE_RANGE,
)


def resolve_prompt_path(relative_path: str) -> str:
    """Return canonical prompt path; accepts legacy aliases."""
    rel = (relative_path or "").replace("\\", "/").strip()
    return PROMPT_ALIASES.get(rel, rel)
