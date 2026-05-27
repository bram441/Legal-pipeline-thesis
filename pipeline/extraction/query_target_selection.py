"""Generic query-target selection with semantic question-category preference."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from pipeline.kb.composite_predicate_heuristics import (
    symbol_background_or_case_input,
    symbol_directly_observable,
)
from pipeline.kb.legal_effect import (
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
    question_has_legal_effect_language,
    schema_has_legal_effect_output_predicate,
)
from pipeline.kb.temporal_support import temporal_support_exempt_from_helper_definition
from pipeline.semantic.legal_question import (
    question_asks_legal_conclusion,
    question_asks_legal_definition,
)


def _bool_predicates(kb_schema: dict) -> list[dict]:
    out: list[dict] = []
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            if str(p.get("returns") or "Bool").strip().lower() == "bool":
                out.append(p)
    return out


def is_temporal_support_background_target(sym: dict[str, Any]) -> bool:
    """
    Temporal period/year relations usable in rule antecedents but not as final answers.
    """
    if temporal_support_exempt_from_helper_definition(sym):
        return True
    if symbol_background_or_case_input(sym):
        return True
    if sym.get("case_input") is True:
        return True
    if symbol_directly_observable(sym) and temporal_support_exempt_from_helper_definition(sym):
        return True
    return False


def is_legal_output_query_target(sym: dict[str, Any]) -> bool:
    lo = sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None
    return predicate_represents_legal_effect_output(
        str(sym.get("name") or ""),
        description=str(sym.get("description") or ""),
        kind=str(sym.get("kind") or ""),
        legal_output=lo,
        output_category=str(sym.get("output_category") or ""),
    )


@dataclass
class QueryTargetSelectionDiagnostics:
    chosen_predicate: str = ""
    chosen_reason: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen_predicate": self.chosen_predicate,
            "chosen_reason": self.chosen_reason,
            "candidates": self.candidates,
            "rejected": self.rejected,
            "warning": self.warning,
        }


def _score_candidate(
    sym: dict[str, Any],
    user_question: str,
    *,
    pred_hint: str,
    prefer_effect: bool,
    prefer_classification: bool,
) -> tuple[float, list[str]]:
    from pipeline.extraction.json_ir import (
        _derived_predicate_specificity_score,
        _lexical_overlap_score,
        _norm_name,
        _symbol_tokens,
    )

    reasons: list[str] = []
    name = str(sym.get("name") or "")
    score = _derived_predicate_specificity_score(sym, user_question)
    if is_legal_output_query_target(sym):
        score += 0.4
        reasons.append("legal_output_target")
    cat = str(sym.get("output_category") or "").strip().lower()
    if prefer_classification:
        if predicate_looks_like_classification_output(
            name,
            description=str(sym.get("description") or ""),
            kind=str(sym.get("kind") or ""),
            legal_output=sym.get("legal_output")
            if isinstance(sym.get("legal_output"), bool)
            else None,
            output_category=cat,
        ) or cat in {"classification", "status"}:
            score += 1.0
            reasons.append("classification_question_match")
        elif is_legal_output_query_target(sym):
            score -= 1.0
            reasons.append("deprioritized_non_classification_for_classification_question")
    if prefer_effect and is_legal_output_query_target(sym):
        score += 0.25
        reasons.append("effect_question_match")
    hint = str(pred_hint or "").strip()
    if hint and (_norm_name(hint) == _norm_name(name) or hint == name):
        score += 0.15
        reasons.append("predicate_hint_match")
    if _lexical_overlap_score(sym, user_question) > 0.35:
        reasons.append("lexical_overlap_with_question")
    return score, reasons


def _looks_like_classification_question(question: str) -> bool:
    qtxt = (question or "").strip()
    if question_asks_legal_definition(qtxt):
        return True
    return bool(
        re.search(
            r"(?i)\b(?:is|does)\b.+\b(?:a|an|as|qualif(?:y|ies)\s+as|status|classification|category)\b",
            qtxt,
        )
    )


def select_boolean_query_predicate(
    *,
    pred_hint: str,
    user_question: str,
    kb_schema: dict,
    current_pred: str | None = None,
) -> QueryTargetSelectionDiagnostics:
    """
    Choose the final boolean query predicate for legal-effect/conclusion questions.
    """
    from pipeline.extraction.json_ir import (
        _derived_bool_predicates,
        _pick_most_specific_derived_predicate,
        _symbol_sig,
    )

    diag = QueryTargetSelectionDiagnostics()
    preds = _bool_predicates(kb_schema)
    effect_q = question_has_legal_effect_language(user_question)
    classification_q = _looks_like_classification_question(user_question) and not effect_q
    conclusion_q = question_asks_legal_conclusion(user_question)

    scored_all: list[tuple[float, dict, list[str]]] = []
    for sym in preds:
        sc, reasons = _score_candidate(
            sym,
            user_question,
            pred_hint=pred_hint,
            prefer_effect=effect_q,
            prefer_classification=classification_q,
        )
        scored_all.append((sc, sym, reasons))

    for sc, sym, reasons in sorted(scored_all, key=lambda x: -x[0]):
        name = str(sym.get("name") or "")
        entry = {
            "name": name,
            "kind": sym.get("kind"),
            "score": round(sc, 4),
            "reasons": reasons,
            "legal_output": sym.get("legal_output"),
            "output_category": sym.get("output_category"),
            "directly_observable": symbol_directly_observable(sym),
            "background": symbol_background_or_case_input(sym),
        }
        if is_temporal_support_background_target(sym):
            entry["rejected"] = True
            entry["rejection_reason"] = "temporal_support_not_final_answer"
            diag.rejected.append(entry)
            continue
        diag.candidates.append(entry)

    legal_outputs = [p for p in preds if is_legal_output_query_target(p)]
    derived = _derived_bool_predicates(kb_schema)

    if effect_q:
        if legal_outputs:
            scored_lo = []
            for sym in legal_outputs:
                sc, reasons = _score_candidate(
                    sym,
                    user_question,
                    pred_hint=pred_hint,
                    prefer_effect=effect_q,
                    prefer_classification=classification_q,
                )
                scored_lo.append((sc, sym, reasons))
            scored_lo.sort(key=lambda x: -x[0])
            best_sc, best_sym, best_reasons = scored_lo[0]
            chosen = str(best_sym["name"])
            diag.chosen_predicate = chosen
            if current_pred and current_pred != chosen:
                if is_temporal_support_background_target(_symbol_sig(kb_schema, current_pred) or {}):
                    diag.chosen_reason = (
                        "preferred_legal_output_over_temporal_support "
                        "(rejected '%s' as temporal_support_not_final_answer)" % current_pred
                    )
                else:
                    diag.chosen_reason = "preferred_legal_output_predicate"
            else:
                diag.chosen_reason = "legal_output_best_match"
            diag.chosen_predicate = chosen
            if best_reasons:
                diag.chosen_reason += ": " + ",".join(best_reasons)
            return diag

        refined = _pick_most_specific_derived_predicate(user_question, kb_schema, current_pred)
        if refined:
            diag.chosen_predicate = refined
            diag.chosen_reason = "fallback_derived_no_legal_output_flag"
            diag.warning = "no_legal_output_predicate_available"
            return diag
        diag.chosen_predicate = current_pred or ""
        diag.chosen_reason = "fallback_no_legal_output_target"
        diag.warning = "no_legal_output_predicate_available"
        return diag

    if classification_q:
        scored_cl = [x for x in scored_all if x[1] in [p for p in preds]]
        scored_cl.sort(key=lambda x: -x[0])
        if scored_cl:
            best_sc, best_sym, best_reasons = scored_cl[0]
            diag.chosen_predicate = str(best_sym.get("name") or current_pred or "")
            diag.chosen_reason = "classification_best_match"
            if best_reasons:
                diag.chosen_reason += ": " + ",".join(best_reasons)
            return diag

    if current_pred:
        diag.chosen_predicate = current_pred
        diag.chosen_reason = "unchanged_non_effect_question"
        return diag

    refined = _pick_most_specific_derived_predicate(user_question, kb_schema, None)
    if refined:
        diag.chosen_predicate = refined
        diag.chosen_reason = "fallback_derived_pick"
    return diag


def apply_query_target_selection(
    *,
    pred_hint: str,
    user_question: str,
    kb_schema: dict,
    current_pred: str | None,
) -> tuple[str | None, dict[str, Any]]:
    """Return (predicate_name, diagnostics). Applies semantic predicate-category selection."""
    if not current_pred:
        return current_pred, {}
    if not (
        question_asks_legal_conclusion(user_question)
        or _looks_like_classification_question(user_question)
    ):
        return current_pred, {"chosen_predicate": current_pred, "chosen_reason": "not_legal_effect_question"}

    diag = select_boolean_query_predicate(
        pred_hint=pred_hint,
        user_question=user_question,
        kb_schema=kb_schema,
        current_pred=current_pred,
    )
    chosen = diag.chosen_predicate or current_pred
    return chosen, diag.to_dict()
