# pipeline/eval/scoring.py

import os
import re

from pipeline.eval.boolean_belief import summarize_boolean_symbolic, symbolic_result_is_inconclusive
from pipeline.semantic.legal_question import question_asks_legal_conclusion


def belief_scoring_enabled() -> bool:
    """True only when open-world belief scoring is explicitly requested (e.g. eval --belief-scoring)."""
    from pipeline.config import config_section

    return bool(config_section("evaluation").get("belief_scoring"))


def _normalize_range_for_compare(range_str, entity=None):
    """Extract a single numeric value from get_range output for comparison."""
    if range_str is None:
        return None
    s = str(range_str).strip()
    if not s or "no model" in s.lower() or "unsatisfiable" in s.lower() or "not found" in s.lower():
        return None
    m = re.search(r"^(-?\d+)", s)
    if m:
        return m.group(1)
    if entity:
        entity_clean = str(entity).strip().lower().replace("'", "")
        for pattern in [
            r"['\"]?" + re.escape(entity_clean) + r"['\"]?\s*->\s*(-?\d+)",
            r"->\s*(-?\d+)",
        ]:
            m = re.search(pattern, s, re.IGNORECASE)
            if m:
                return m.group(1)
    return None


def _belief_threshold_from_env_or_expected(expected: dict) -> float | None:
    if not belief_scoring_enabled():
        return None
    thr_raw = expected.get("belief_match_threshold")
    if thr_raw is None:
        from pipeline.config import config_section

        thr_raw = config_section("evaluation").get("boolean_belief_threshold")
    if thr_raw in (None, ""):
        return 0.5
    try:
        return max(0.0, min(1.0, float(thr_raw)))
    except (TypeError, ValueError):
        return None


def _inconclusive_warning(exp_val: bool, label: str) -> str | None:
    if exp_val is True and label == "unknown":
        return (
            "Expected true, but symbolic result is only possible, not certain. "
            "This is an underconstrained or missing-fact result and is counted as inconclusive, not correct."
        )
    if exp_val is False and label == "unknown":
        return (
            "Expected false, but symbolic result is not decisively false. "
            "Unknown/open results are counted as inconclusive, not correct."
        )
    return None


def _predicate_kind_from_schema(kb_schema: dict | None, pred_name: str) -> str | None:
    if not kb_schema or not pred_name:
        return None
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == pred_name:
            return str(p.get("kind") or "unknown").strip().lower()
    return None


def _query_target_warnings(
    expected: dict,
    query: dict | None,
    kb_schema: dict | None,
    user_question: str | None,
) -> list[str]:
    warnings: list[str] = []
    if not query or not isinstance(expected, dict):
        return warnings
    if expected.get("mode") != "boolean":
        return warnings
    pred = str(query.get("predicate") or "").strip()
    if not pred:
        return warnings
    pk = query.get("predicate_kind") or _predicate_kind_from_schema(kb_schema, pred)
    if not question_asks_legal_conclusion(user_question or ""):
        return warnings
    from pipeline.extraction.query_target_selection import is_temporal_support_background_target
    from pipeline.kb.legal_effect import question_has_legal_effect_language

    sig = None
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == pred:
            sig = p
            break
    if sig and question_has_legal_effect_language(user_question or ""):
        if is_temporal_support_background_target(sig):
            warnings.append(
                "Query target '"
                + pred
                + "' is a temporal support/background relation, not a legal-effect answer predicate."
            )
            return warnings
    if pk != "observable":
        return warnings
    warnings.append(
        "Expected legal Boolean answer was evaluated using observable predicate '"
        + pred
        + "'. This may be a query-target error because observable predicates are case facts, not legal conclusions."
    )
    return warnings


def _target_in_atom_list(atoms: list, pred: str | None, args: list) -> bool:
    if not pred:
        return False
    want_args = [str(a).strip().lower() for a in (args or [])]
    for item in atoms:
        if not isinstance(item, dict):
            continue
        if str(item.get("predicate") or "") != str(pred):
            continue
        got_args = [str(a).strip().lower() for a in (item.get("args") or [])]
        if got_args == want_args:
            return True
    return False


def _finalize_boolean_score(
    out: dict,
    expected: dict,
    query: dict | None,
    kb_schema: dict | None,
    user_question: str | None,
    symbolic_result: dict | None = None,
) -> dict:
    if query:
        pred = str(query.get("predicate") or "")
        out["query_predicate"] = pred or None
        out["query_predicate_kind"] = query.get("predicate_kind") or _predicate_kind_from_schema(kb_schema, pred)
        qts = query.get("query_target_selection")
        if isinstance(qts, dict):
            out["query_target_selection"] = qts
    warns = _query_target_warnings(expected, query, kb_schema, user_question)
    if symbolic_result and isinstance(symbolic_result, dict):
        cov = symbolic_result.get("antecedent_coverage")
        if cov:
            from pipeline.symbolic.antecedent_coverage import missing_observable_symbols

            missing = missing_observable_symbols(cov)
            if missing:
                warns = list(warns)
                warns.append(
                    "Antecedent diagnostics: missing observable case facts for "
                    + ", ".join(missing)
                    + " (blocking rule paths only)."
                )
        label = str(symbolic_result.get("label") or symbolic_result.get("epistemic_label") or "").lower()
        inconclusive = label == "unknown" or (
            symbolic_result.get("possible") and not symbolic_result.get("certain")
        )
        if inconclusive:
            hint = symbolic_result.get("extraction_repair_hint")
            if hint:
                warns = list(warns)
                warns.append(str(hint))
    if warns:
        out["warnings"] = warns
    return out


def score_question(expected, symbolic_result, *, query=None, kb_schema=None, user_question=None):
    """
    Compares an expected answer object against the pipeline symbolic_result.

    Boolean mode (default): decisive entailment/contradiction only.
    Open/unknown (possible but not certain) is inconclusive and not correct.

  Belief scoring: only when SCORE_TREAT_OPEN_WITH_BELIEF=1 (set by eval --belief-scoring).
    """
    if expected is None:
        return {"match": None, "reason": "no expected provided"}

    if not isinstance(expected, dict):
        return {"match": False, "reason": "expected must be an object"}

    pred = symbolic_result or {}

    sym_intent = str(pred.get("intent") or "").strip().lower()
    certainty_class = pred.get("certainty_class")

    if expected.get("intent"):
        intent = str(expected.get("intent")).strip().lower()
        if intent == "satisfiable":
            exp_val = bool(expected.get("value"))
            got_val = bool(pred.get("satisfiable") if "satisfiable" in pred else pred.get("sat"))
            return {
                "match": exp_val == got_val,
                "expected": exp_val,
                "got": got_val,
                "scoring_mode": "decisive",
                "certainty_class": "consistency",
                "internal_intent": sym_intent or "satisfiable",
            }
        if intent == "get_range":
            exp_val = expected.get("value")
            got_raw = pred.get("range") or (pred.get("values") or [None])[0]
            got_val = _normalize_range_for_compare(got_raw, pred.get("entity"))
            exp_norm = str(exp_val).strip() if exp_val is not None else None
            tolerance = int(expected.get("tolerance_days", 5))
            try:
                exp_int = int(exp_norm) if exp_norm is not None else None
                got_int = int(got_val) if got_val is not None else None
                match = (
                    exp_int is not None
                    and got_int is not None
                    and abs(exp_int - got_int) <= tolerance
                )
            except (ValueError, TypeError):
                match = exp_norm is not None and got_val is not None and exp_norm == got_val
            return {
                "match": match,
                "expected": exp_val,
                "got": got_val,
                "raw_range": got_raw,
                "scoring_mode": "decisive",
                "certainty_class": "range",
                "internal_intent": sym_intent or "get_range",
            }
        return {"match": False, "reason": "unsupported intent: " + str(intent), "scoring_mode": "manual"}

    if sym_intent == "propagation" and expected.get("mode") == "boolean":
        exp_val = bool(expected.get("value"))
        target_pred = expected.get("target_predicate") or (query or {}).get("predicate")
        target_args = expected.get("target_args") or (query or {}).get("args") or []
        in_true = _target_in_atom_list(pred.get("certain_true") or [], target_pred, target_args)
        in_false = _target_in_atom_list(pred.get("certain_false") or [], target_pred, target_args)
        if exp_val is True:
            match = in_true
            got = True if in_true else (False if in_false else None)
        else:
            match = in_false
            got = False if in_false else (True if in_true else None)
        inconclusive = got is None
        return {
            "match": match if not inconclusive else False,
            "got": got,
            "decisive": not inconclusive,
            "inconclusive": inconclusive,
            "scoring_mode": "decisive",
            "certainty_class": "decisive",
            "internal_intent": "propagation",
        }

    if sym_intent == "model_expansion":
        return {
            "match": False,
            "decisive": False,
            "inconclusive": True,
            "reason": "model_expansion yields possible models, not decisive legal truth",
            "scoring_mode": "manual",
            "certainty_class": "possible_model",
            "internal_intent": "model_expansion",
        }

    if sym_intent in ("relevance", "explain"):
        return {
            "match": None,
            "decisive": False,
            "inconclusive": True,
            "scoring_mode": "manual",
            "certainty_class": "manual",
            "internal_intent": sym_intent,
            "reason": "manual scoring required",
        }

    mode = expected.get("mode")

    if mode == "set":
        exp_set = sorted(str(x).strip().lower() for x in (expected.get("value") or []))
        got_set = sorted(
            str(x).strip().lower()
            for x in (pred.get("entailed") or pred.get("certain") or pred.get("certain_set") or [])
        )
        return {
            "match": exp_set == got_set,
            "expected": exp_set,
            "got": got_set,
            "scoring_mode": "decisive",
            "certainty_class": pred.get("certainty_class") or "decisive",
            "internal_intent": sym_intent or "deduction_set",
        }

    if mode == "boolean":
        if symbolic_result_is_inconclusive(pred):
            exp_val = bool(expected.get("value"))
            base = {
                "expected": exp_val,
                "epistemic_label": "unknown",
                "scoring_mode": "decisive",
                "match": False,
                "got": None,
                "decisive": False,
                "inconclusive": True,
                "reason": "symbolic failure or non-decisive symbolic output",
                "symbolic_inconclusive": True,
            }
            status = str(pred.get("status") or "").strip().lower()
            if status:
                base["symbolic_status"] = status
            return _finalize_boolean_score(
                base, expected, query, kb_schema, user_question, pred
            )

        exp_val = bool(expected.get("value"))
        target = expected.get("target")
        if target and pred.get("target") and str(target).lower() != str(pred.get("target")).lower():
            return {
                "match": False,
                "decisive": True,
                "inconclusive": False,
                "reason": "target mismatch",
                "expected_target": target,
                "got_target": pred.get("target"),
            }

        summ = summarize_boolean_symbolic(pred)
        p_yes = float(summ["p_yes"])
        label = summ["label"]
        belief_threshold = _belief_threshold_from_env_or_expected(expected)
        use_belief = belief_threshold is not None

        base = {
            "expected": exp_val,
            "belief_yes": p_yes,
            "credence_yes_pct": summ["credence_yes_pct"],
            "verdict_strength_pct": summ["verdict_strength_pct"],
            "epistemic_label": label,
            "scoring_mode": "belief" if use_belief else "decisive",
        }

        if label == "entailed":
            got = True
            match = exp_val is True
            return _finalize_boolean_score(
                {**base, "match": match, "got": got, "decisive": True, "inconclusive": False},
                expected,
                query,
                kb_schema,
                user_question,
                pred,
            )

        if label == "contradicted":
            got = False
            match = exp_val is False
            return _finalize_boolean_score(
                {**base, "match": match, "got": got, "decisive": True, "inconclusive": False},
                expected,
                query,
                kb_schema,
                user_question,
                pred,
            )

        out = {
            **base,
            "match": False,
            "got": None,
            "decisive": False,
            "inconclusive": True,
            "reason": "open: neither entailed nor contradicted",
        }
        warn = _inconclusive_warning(exp_val, label)
        if warn:
            out["warning"] = warn

        if use_belief:
            if exp_val is True:
                belief_match = p_yes >= belief_threshold
                out["match"] = belief_match
                out["got"] = p_yes >= 0.5
            else:
                belief_match = (1.0 - p_yes) >= belief_threshold
                out["match"] = belief_match
                out["got"] = p_yes < 0.5
            out["belief_match_threshold"] = belief_threshold
            out["belief_scored"] = True
            out.pop("reason", None)
            out["decisive"] = False
            out["inconclusive"] = not belief_match

        return _finalize_boolean_score(out, expected, query, kb_schema, user_question, pred)

    return {"match": False, "reason": "unsupported mode: " + str(mode)}
