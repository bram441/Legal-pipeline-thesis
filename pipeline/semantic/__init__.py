"""Law-agnostic semantic helpers for legal pipeline validation."""

from pipeline.semantic.legal_question import (
    domain_heuristics_enabled,
    is_reflexive_predicate_name,
    question_asks_factual_only,
    question_asks_legal_conclusion,
    question_asks_legal_effect_timing,
    witness_modeling_hint,
)

__all__ = [
    "domain_heuristics_enabled",
    "is_reflexive_predicate_name",
    "question_asks_factual_only",
    "question_asks_legal_conclusion",
    "question_asks_legal_effect_timing",
    "witness_modeling_hint",
]
