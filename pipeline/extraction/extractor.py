import json
import os
import re
from contextlib import contextmanager

from debug import status_log
from pipeline.extraction.openai_extractor import (
    extract_case_ir_only_openai,
    extract_query_ir_only_openai,
    LLMExtractionError,
)
from pipeline.extraction.json_ir import (
    ExtractionIRValidationError,
    _PLACEHOLDERS as _EXTRACTION_PLACEHOLDERS,
    normalize_case_ir,
    normalize_query_ir,
)
from pipeline.extraction.case_entity_seed import seed_person_entities_from_case_text
from pipeline.extraction.case_fact_validation import (
    CASE_EXTRACTION_REPAIR_ARTIFACT,
    CaseFactAssertionRejected,
    CaseFactRejectionDiagnostics,
    build_case_fact_rejection_repair_hint,
    build_factual_case_input_diagnostics,
    build_rejection_diagnostics,
    case_fact_validation_error_matches,
    parse_rejected_predicate_from_error,
    parse_rejection_code_from_error,
    validate_decomposition_repair_or_raise,
)
from pipeline.extraction.query_role_resolve import apply_role_arg_consistency
from pipeline.validation.fo_validation import (
    normalize_and_validate_case,
    normalize_and_validate_query,
    _entities_from_case,
)


class ExtractionError(Exception):
    pass


EXTRACTION_BACKEND_CHOICES = ("json_ir",)

# Default individuals when a predicate needs a sort the case did not list under entities.
# Aligns with prompts/shared/json_ir_contract.txt (single undifferentiated estate / goods).
_DEFAULT_ENTITY_BY_SCHEMA_TYPE = {
    "Estate": "estate_main",
    "Good": "goods_main",
    "Property": "property_main",
    "RealEstate": "residence_main",
    "HouseholdFurniture": "furniture_main",
}


def _default_entity_for_schema_type(typ: str) -> str | None:
    t = str(typ or "").strip()
    return _DEFAULT_ENTITY_BY_SCHEMA_TYPE.get(t)


def _entity_values_for_other_types(case: dict, skip_type: str) -> set[str]:
    """Lowercase names already assigned to another KB type in case.entities."""
    out: set[str] = set()
    for t2, vs in (case.get("entities") or {}).items():
        if t2 == skip_type:
            continue
        if not isinstance(vs, list):
            continue
        for v in vs:
            s = str(v).strip().lower()
            if s:
                out.add(s)
    return out


def _merge_entity_under_type(case: dict, typ: str, name: str) -> None:
    if not typ or not name:
        return
    n = str(name).strip().lower()
    if not n:
        return
    ents = case.setdefault("entities", {})
    if typ not in ents or not isinstance(ents[typ], list):
        ents[typ] = []
    if n not in {str(v).strip().lower() for v in ents[typ]}:
        ents[typ].append(n)
        ents[typ] = sorted(set(str(v).strip().lower() for v in ents[typ] if str(v).strip()))


# Words that are not entity names when they appear in "Is X ..." patterns
_QUESTION_STOPWORDS = frozenset({
    "the", "what", "who", "which", "how", "why", "when", "where", "does", "did",
    "is", "are", "was", "were", "can", "could", "article", "art", "belgian",
    "law", "case", "facts", "sentence", "minimum", "maximum", "prison", "fine",
})


def _symbol_tokens(name):
    s = str(name or "").strip()
    if not s:
        return []
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ")
    toks = [t.lower() for t in s.split() if t.strip()]
    stop = {"the", "a", "an", "of", "to", "on", "in", "and", "or", "for", "has", "have", "is"}
    return [t for t in toks if t not in stop]


def _question_tokens(text):
    s = str(text or "").strip().lower()
    if not s:
        return set()
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
        "does", "did", "what", "which", "when", "where", "why", "who", "according",
        "article", "under", "into", "onto", "about", "your", "their",
    }
    out = set()
    for t in toks:
        if t in stop:
            continue
        out.add(t)
        if t.endswith("s") and len(t) > 3:
            out.add(t[:-1])
    return out


def _best_schema_predicate_match(pred_name, kb_schema, user_question=None):
    """Return best canonical predicate name for pred_name, or None."""
    if not pred_name or not kb_schema:
        return None

    def _norm_name(s):
        return (s or "").lower().replace("_", "")

    candidates = [p.get("name") for p in (kb_schema.get("predicates") or []) if p.get("name")]
    if not candidates:
        return None

    for n in candidates:
        if n == pred_name or _norm_name(n) == _norm_name(pred_name):
            return n

    q = set(_symbol_tokens(pred_name))
    q_question = _question_tokens(user_question)
    if not q:
        return None
    best_name = None
    best_score = 0.0
    for n in candidates:
        t = set(_symbol_tokens(n))
        if not t:
            continue
        inter = len(q & t)
        if inter == 0:
            continue
        score_name = (2.0 * inter) / float(len(q) + len(t))
        score = score_name
        if q_question:
            inter_q = len(q_question & t)
            score_q = inter_q / float(max(1, len(t)))
            # Keep predicted-name similarity primary; use question grounding as tie-breaker.
            score = (0.75 * score_name) + (0.25 * score_q)
        if score > best_score:
            best_score = score
            best_name = n

    if best_name and best_score >= 0.60:
        return best_name
    return None


def _predicate_question_score(pred_name, user_question):
    t = set(_symbol_tokens(pred_name))
    q = _question_tokens(user_question)
    if not t or not q:
        return 0.0
    score = len(t & q) / float(len(t))

    # Reward predicates that encode the legal effect words the question asks about.
    if "usufruct" in q and "usufruct" in t:
        score += 0.18
    if "estate" in q and "estate" in t:
        score += 0.12
    if "entire" in q and "entire" in t:
        score += 0.08
    if "right" in q and "right" in t:
        score += 0.06

    # Penalize overly generic status predicates when the question targets an entitlement.
    if pred_name.startswith("Is") and ("usufruct" in q or "estate" in q):
        score -= 0.20

    return score


def _entity_asked_about_in_question(question):
    """Extract the person/entity the question asks about (e.g. 'Is Karel liable?' -> karel)."""
    if not question or not isinstance(question, str):
        return None
    q = question.strip()
    # Patterns: "Is X liable?", "for X", "about X", "X is liable", "sentence for X"
    patterns = [
        r"\b(?:Is|Are|Does|Did|Was|Were)\s+([A-Z][a-zA-Z]+)\b",
        r"\b(?:for|about)\s+([A-Z][a-zA-Z]+)\b",
        r"\b([A-Z][a-zA-Z]+)\s+(?:liable|punishable|eligible|qualifies)\b",
    ]
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            name = m.group(1).strip().lower()
            if name and name not in _QUESTION_STOPWORDS and len(name) >= 2:
                return name
    return None


def _case_entity_set(case):
    """All entity names (lowercase) that appear in the case: from facts and from case.entities."""
    out = set(_entities_from_case(case))
    for key, vals in (case.get("entities") or {}).items():
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
    return out


def _name_in_text(name_lower, text):
    """True if name appears in text (case-insensitive or capitalized)."""
    if not text or not isinstance(text, str):
        return False
    return name_lower in text.lower() or (name_lower.capitalize() in text and len(name_lower) >= 2)


def _ensure_entity_in_case(asked, case, kb_schema=None):
    """Ensure asked is listed in case['entities'] so downstream validation sees it."""
    if not isinstance(case, dict):
        return
    ents = case.get("entities")
    if isinstance(ents, dict):
        for _t, vals in ents.items():
            if isinstance(vals, list) and asked not in [str(v).strip().lower() for v in vals]:
                vals.append(asked)
                return
    types = (kb_schema or {}).get("types") or []
    primary = types[0] if types else "Person"
    case["entities"] = case.get("entities") or {}
    if not isinstance(case["entities"], dict):
        case["entities"] = {}
    case["entities"].setdefault(primary, []).append(asked)


def _check_entity_consistency(user_question, query_obj, case, case_text=None, kb_schema=None):
    """Raise ValueError if the question asks about an entity but query args/entity use a different one.
    When the question clearly asks about E and E is in the case (or in case_text), fix args/entity to [E]."""
    asked = _entity_asked_about_in_question(user_question)
    if not asked:
        return

    case_entities = set(_case_entity_set(case))
    if asked not in case_entities and case_text and _name_in_text(asked, case_text):
        case_entities.add(asked)
        _ensure_entity_in_case(asked, case, kb_schema)
    if asked not in case_entities:
        return

    q_type = str(query_obj.get("type") or "").strip().lower()
    if q_type == "intent":
        entity = str(query_obj.get("entity") or "").strip().lower()
        if entity and entity != asked:
            query_obj["entity"] = asked
            status_log("Query", "Entity overwrite: question asks about '{}', using entity '{}'".format(asked, asked))
        return

    if q_type == "predicate":
        args = query_obj.get("args") or []
        if not isinstance(args, list):
            return
        args_lower = [str(a).strip().lower() for a in args if a]
        if args_lower and asked not in args_lower:
            # Keep arity-safe behavior: force unary predicates to [asked], but for n-ary
            # predicates only replace the first slot and preserve/pad remaining slots.
            pred_name = str(query_obj.get("predicate") or "").strip()
            expected = None
            if kb_schema and pred_name:
                matched = _best_schema_predicate_match(pred_name, kb_schema, user_question=user_question)
                if matched:
                    query_obj["predicate"] = matched
                    for p in (kb_schema.get("predicates") or []):
                        if p.get("name") == matched:
                            expected = len(p.get("args") or [])
                            break

            if expected == 1:
                query_obj["args"] = [asked]
                status_log("Query", "Entity overwrite: question asks about '{}', using args ['{}']".format(asked, asked))
            elif expected and expected > 1:
                kept = [str(a).strip().lower() for a in args if str(a).strip()]
                if not kept:
                    kept = [asked]
                else:
                    kept[0] = asked
                # Do not force-fill non-primary argument positions with the asked entity;
                # those positions may require non-Person types (Estate, Date, ...).
                query_obj["args"] = kept[:expected]
                status_log("Query", "Entity overwrite: aligned args to arity {} with primary entity '{}'".format(expected, asked))


def _coerce_query_args_to_schema(query_obj, case, kb_schema, user_question=None):
    """Deterministic fallback: make predicate boolean args arity/schema consistent."""
    if not isinstance(query_obj, dict) or not kb_schema:
        return False
    if str(query_obj.get("type") or "").strip().lower() != "predicate":
        return False

    mode = str(query_obj.get("mode") or "").strip().lower()
    pred_name = str(query_obj.get("predicate") or "").strip()
    if not pred_name:
        return False

    sig = None
    canonical = pred_name
    matched = _best_schema_predicate_match(pred_name, kb_schema, user_question=user_question)
    if matched:
        canonical = matched
        for p in (kb_schema.get("predicates") or []):
            if p.get("name") == matched:
                sig = p
                break
    # If we already have a valid canonical symbol but question semantics clearly prefer
    # another schema predicate, switch to the better-matching one.
    if user_question and sig and (kb_schema.get("predicates") or []):
        cur_q_score = _predicate_question_score(canonical, user_question)
        best_q_name = None
        best_q_score = cur_q_score
        for p in (kb_schema.get("predicates") or []):
            n = p.get("name")
            if not n:
                continue
            s = _predicate_question_score(n, user_question)
            if s > best_q_score:
                best_q_score = s
                best_q_name = n
        if best_q_name and best_q_score >= 0.45 and (best_q_score - cur_q_score) >= 0.20:
            canonical = best_q_name
            for p in (kb_schema.get("predicates") or []):
                if p.get("name") == best_q_name:
                    sig = p
                    break
    if not sig:
        return False
    if mode != "boolean":
        if canonical != pred_name:
            query_obj["predicate"] = canonical
            return True
        return False

    expected_types = list(sig.get("args") or [])
    expected = len(expected_types)
    if expected == 0:
        if query_obj.get("args") != []:
            query_obj["args"] = []
            query_obj["predicate"] = canonical
            return True
        return False

    current = []
    for a in (query_obj.get("args") or []):
        s = str(a).strip().lower()
        if s:
            current.append(s)

    fact_entities = set(_entities_from_case(case))
    typed_entities = {}
    for t, vals in (case.get("entities") or {}).items():
        if isinstance(t, str) and isinstance(vals, list):
            cleaned = [str(v).strip().lower() for v in vals if isinstance(v, str) and str(v).strip()]
            # Prefer constants that are grounded in facts.
            grounded = [v for v in cleaned if v in fact_entities]
            fallback = [v for v in cleaned if v not in fact_entities]
            typed_entities[t] = grounded + fallback
    out: list[str] = []
    for i in range(expected):
        t_key = str(expected_types[i]).strip() if i < len(expected_types) else ""
        candidates = list(typed_entities.get(t_key, []))
        cur_s = str(current[i]).strip().lower() if i < len(current) else ""
        is_ph = (not cur_s) or (cur_s in _EXTRACTION_PLACEHOLDERS)

        if candidates:
            norm_c = [str(c).strip().lower() for c in candidates]
            if cur_s and not is_ph and cur_s not in fact_entities:
                # typed_entities orders grounded-in-facts first; prefer that bucket when cur is not grounded.
                chosen = str(candidates[0]).strip().lower()
            elif cur_s and not is_ph and cur_s in norm_c:
                chosen = cur_s
            else:
                chosen = str(candidates[0]).strip().lower()
        else:
            blocked = _entity_values_for_other_types(case, t_key)
            if cur_s and not is_ph and cur_s not in blocked:
                chosen = cur_s
                _merge_entity_under_type(case, t_key, chosen)
            elif cur_s and not is_ph and cur_s in blocked:
                d = _default_entity_for_schema_type(t_key)
                if d:
                    chosen = d
                    _merge_entity_under_type(case, t_key, d)
                else:
                    chosen = "?"
            else:
                d = _default_entity_for_schema_type(t_key)
                if d:
                    chosen = d
                    _merge_entity_under_type(case, t_key, d)
                else:
                    chosen = "?"
        out.append(chosen)

    if len(out) != expected:
        return False
    if any((not str(x or "").strip()) or str(x).strip().lower() in _EXTRACTION_PLACEHOLDERS for x in out):
        return False

    changed = (out != current) or (canonical != pred_name)
    if changed:
        query_obj["predicate"] = canonical
        query_obj["args"] = out
    return changed


def _arity_mismatch_repair_hint(error_msg, previous_output, kb_schema):
    """Extra guidance when boolean query.args length does not match predicate arity."""
    if not kb_schema or "Predicate arity mismatch" not in error_msg:
        return ""

    m = re.search(r"Predicate arity mismatch for ([^:]+): expected (\d+)", error_msg)
    if not m:
        return ""

    pred_raw = m.group(1).strip()
    expected = int(m.group(2))

    def _norm_name(s):
        return (s or "").lower().replace("_", "")

    sig = None
    canonical = pred_raw
    for p in kb_schema.get("predicates", []) or []:
        n = p.get("name")
        if not n:
            continue
        if n == pred_raw or _norm_name(n) == _norm_name(pred_raw):
            sig = p
            canonical = n
            break
    if not sig:
        return ""

    types = sig.get("args") or []
    got = []
    if isinstance(previous_output, dict):
        q = previous_output.get("query")
        if isinstance(q, dict) and isinstance(q.get("args"), list):
            got = q.get("args")

    lines = [
        "",
        "REMEDIATION (predicate arity):",
        "- In KB_SCHEMA, `" + canonical + "` has " + str(expected) + " domain argument(s): " + ", ".join(types) + ".",
        "- For type=\"predicate\" and mode=\"boolean\", query.args must be a JSON array of exactly "
        + str(expected)
        + " string(s), each a lowercase entity name that already appears in case.facts or case.entities.",
        "- Your previous query.args was: " + json.dumps(got, ensure_ascii=False) + " (length " + str(len(got)) + ").",
        "- Do not use schema type names (Person, Company) as args. Prefer the named person from the case (e.g. ahmed, anna).",
    ]
    return "\n".join(lines)


def _write_case_extraction_repair_artifact(
    path: str | None,
    records: list[dict],
    *,
    factual_input_summary: dict | None = None,
) -> None:
    if not path:
        return
    if not records and not factual_input_summary:
        return
    payload: dict = {}
    if records:
        payload["attempts"] = records
    if factual_input_summary:
        payload.update(factual_input_summary)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError:
        pass


def _case_rejection_diagnostics_from_error(
    error: Exception,
    kb_schema: dict | None,
    *,
    case_text: str | None,
    repair_attempt: int,
) -> CaseFactRejectionDiagnostics | None:
    if not kb_schema:
        return None
    pred = getattr(error, "pred", None) or parse_rejected_predicate_from_error(str(error))
    code = getattr(error, "rejection_code", None) or parse_rejection_code_from_error(str(error))
    if not pred and not case_fact_validation_error_matches(str(error)):
        return None
    return build_rejection_diagnostics(
        pred or "INVALID_PREDICATE",
        code or "invalid_case_fact",
        kb_schema,
        case_text=case_text,
        repair_attempt=repair_attempt,
    )


def _schema_feedback_message(
    error,
    previous_output,
    kb_schema=None,
    *,
    case_text: str | None = None,
    rejection_diag: CaseFactRejectionDiagnostics | None = None,
):
    """Build schema-aware feedback for LLM repair."""
    err_s = str(error)
    msg = (
        "Your previous output did not pass schema validation.\n"
        "Error: " + err_s + "\n"
        "Previous output: " + json.dumps(previous_output, ensure_ascii=False, indent=2)
    )
    if kb_schema and "Unknown symbol" in err_s:
        preds = [p.get("name") for p in kb_schema.get("predicates", []) if p.get("name")]
        funs = [f.get("name") for f in kb_schema.get("functions", []) if f.get("name")]
        valid = sorted(set(preds + funs))
        if valid:
            msg += "\n\nValid symbols (use EXACT names, case-sensitive): " + ", ".join(valid)
    if kb_schema:
        msg += _arity_mismatch_repair_hint(err_s, previous_output, kb_schema)
    el = err_s.lower()
    if "derived predicate" in el or "must not assert derived" in el:
        msg += (
            "\n\nREMEDIATION (derived/conclusion predicates): remove those assertions from case IR. "
            "Assert only observable/input facts and numeric value_assertions; let the KB derive legal conclusions."
        )
    if kb_schema:
        if case_fact_validation_error_matches(err_s):
            rejected_pred = parse_rejected_predicate_from_error(err_s) or "INVALID_PREDICATE"
            rejection_code = parse_rejection_code_from_error(err_s)
            diag = rejection_diag or build_rejection_diagnostics(
                rejected_pred,
                rejection_code or "invalid_case_fact",
                kb_schema,
                case_text=case_text,
            )
            msg += build_case_fact_rejection_repair_hint(
                rejected_pred,
                kb_schema,
                rejection_code=rejection_code,
                case_text=case_text,
                rejection_diag=diag,
            )
    if "query argument type mismatch" in el:
        msg += (
            "\n\nREMEDIATION (query arg sort): each args[i] must be a constant listed under case.entities "
            "for the sort KB_SCHEMA expects at position i (Person, Company, Estate, Good, FinancialYear, etc.)."
        )
    if "unresolved placeholder" in el:
        msg += (
            "\n\nREMEDIATION (placeholders): replace ? with a concrete constant from case.entities for that sort, "
            "or ensure the case IR declares an entity for the required sort first."
        )
    if "observable predicate" in el and "legal-conclusion" in el:
        derived = [
            p
            for p in (kb_schema or {}).get("predicates") or []
            if isinstance(p, dict)
            and str(p.get("kind") or "").lower() in {"derived", "conclusion"}
        ]
        msg += (
            "\n\nREMEDIATION (query target): The previous query selected an observable case-input predicate. "
            "The question asks for a legal conclusion. Select a derived predicate instead."
        )
        if derived:
            msg += "\n\nAvailable derived predicates:\n"
            for p in derived[:25]:
                args = ", ".join(p.get("args") or [])
                msg += f"- {p.get('name')}({args}): {p.get('description', '')}\n"
    if "unconstrained consequent variable" in el or "same variable twice" in el:
        from pipeline.semantic.legal_question import witness_modeling_hint

        msg += "\n\nREMEDIATION (rule design):" + witness_modeling_hint()
    return msg


def _auto_provider():
    from pipeline.config import config_section

    forced = str(config_section("extraction").get("provider") or "").strip().lower()
    if forced and forced != "auto":
        return forced

    return "openai"


def get_extraction_backend_from_env() -> str:
    """Extraction is always JSON-IR."""
    return "json_ir"


def get_extraction_max_retries() -> int:
    from pipeline.config import config_section

    try:
        return max(1, int(config_section("extraction").get("max_retries") or 6))
    except (TypeError, ValueError):
        return 6


def _extraction_backend():
    return get_extraction_backend_from_env()


@contextmanager
def extraction_backend_env_override(backend: str | None):
    if backend is None:
        yield
        return
    if backend not in EXTRACTION_BACKEND_CHOICES:
        raise ValueError("Unknown extraction backend: " + str(backend))
    key = "PIPELINE_EXTRACTION_BACKEND"
    saved = os.environ.get(key)
    try:
        os.environ[key] = backend
        yield
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved


def _run_case_extraction_loop(
    case_text: str,
    *,
    kb_schema: dict | None,
    schema_environment: dict | None = None,
    provider: str,
    model: str,
    max_retries: int,
    repair_artifact_path: str | None = None,
) -> dict:
    case_feedback = None
    case_obj = None
    last_case_error = None
    pending_rejection_diag: CaseFactRejectionDiagnostics | None = None
    repair_records: list[dict] = []

    for case_attempt in range(max_retries):
        if case_attempt == 0:
            status_log("Case", "Extracting")
        else:
            status_log("Case", "Repair attempt {}".format(case_attempt))
        try:
            case_ir = extract_case_ir_only_openai(
                case_text,
                model=model,
                kb_schema=kb_schema,
                feedback=case_feedback,
                schema_environment=schema_environment,
            )
            case_obj = normalize_case_ir(
                case_ir,
                kb_schema=kb_schema,
                case_text=case_text,
            )
            seed_person_entities_from_case_text(case_text, case_obj, kb_schema)
        except LLMExtractionError as e:
            raise ExtractionError(str(e))
        except (ExtractionIRValidationError, CaseFactAssertionRejected) as e:
            last_case_error = e
            pending_rejection_diag = _case_rejection_diagnostics_from_error(
                e,
                kb_schema,
                case_text=case_text,
                repair_attempt=case_attempt,
            )
            if pending_rejection_diag:
                repair_records.append(pending_rejection_diag.to_dict())
            case_feedback = _schema_feedback_message(
                e,
                case_obj or {},
                kb_schema,
                case_text=case_text,
                rejection_diag=pending_rejection_diag,
            )
            continue

        try:
            validate_decomposition_repair_or_raise(case_obj, pending_rejection_diag)
            pending_rejection_diag = None
        except CaseFactAssertionRejected as e:
            last_case_error = e
            if pending_rejection_diag:
                pending_rejection_diag.empty_facts_after_repair = True
                repair_records.append(pending_rejection_diag.to_dict())
            case_feedback = _schema_feedback_message(
                e,
                case_obj or {},
                kb_schema,
                case_text=case_text,
                rejection_diag=pending_rejection_diag,
            )
            continue

        try:
            status_log("Case", "Validating")
            work_schema = kb_schema
            if (
                isinstance(case_obj, dict)
                and case_obj.get("case_given_factual_inputs")
                and kb_schema
            ):
                from pipeline.kb.case_given_bridge import (
                    build_case_given_inputs_from_assertions,
                    extend_kb_schema_with_case_given,
                )

                bridges = build_case_given_inputs_from_assertions(
                    case_obj["case_given_factual_inputs"],
                    kb_schema,
                )
                work_schema = extend_kb_schema_with_case_given(kb_schema, bridges)
            case = normalize_and_validate_case(case_obj, kb_schema=work_schema)
            if isinstance(case_obj, dict) and case_obj.get("case_given_factual_inputs"):
                case["case_given_factual_inputs"] = list(case_obj["case_given_factual_inputs"])
            factual_summary = build_factual_case_input_diagnostics(
                case,
                case_text=case_text,
                kb_schema=work_schema or kb_schema,
            )
            if pending_rejection_diag:
                final_record = pending_rejection_diag.to_dict()
                final_record["repair_succeeded"] = case_object_has_facts(case)
                repair_records.append(final_record)
            _write_case_extraction_repair_artifact(
                repair_artifact_path,
                repair_records,
                factual_input_summary=factual_summary,
            )
            return case
        except ValueError as e:
            last_case_error = e
            case_feedback = _schema_feedback_message(
                e,
                case_obj,
                kb_schema,
                case_text=case_text,
                rejection_diag=pending_rejection_diag,
            )

    _write_case_extraction_repair_artifact(repair_artifact_path, repair_records)
    raise ExtractionError(
        "Case extraction failed after {} repair attempts: {}".format(max_retries, last_case_error)
    )


def case_object_has_facts(case_obj: dict) -> bool:
    from pipeline.extraction.case_fact_validation import case_object_has_non_entity_facts

    return case_object_has_non_entity_facts(case_obj)


def extract_case_and_query(
    case_text,
    user_question,
    kb_schema=None,
    schema_environment=None,
    provider="auto",
    model=None,
    max_retries=6,
    run_artifact_dir=None,
):
    """Extract raw {case, query} JSON using the configured provider.

    Uses schema-aware feedback loops: case and query are extracted and validated
    separately. Each component retries up to max_retries times with validation
    feedback (IDP-Z3 / schema errors) sent back to the LLM.
    """
    if provider == "auto":
        provider = _auto_provider()

    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

    case = _run_case_extraction_loop(
        case_text,
        kb_schema=kb_schema,
        schema_environment=schema_environment,
        provider=provider,
        model=chosen_model,
        max_retries=max_retries,
        repair_artifact_path=(
            os.path.join(run_artifact_dir, CASE_EXTRACTION_REPAIR_ARTIFACT)
            if run_artifact_dir
            else None
        ),
    )

    # --- Phase 2: Query extraction with feedback loop ---
    query_feedback = None
    query_obj = None
    last_query_error = None
    for query_attempt in range(max_retries):
        if query_attempt == 0:
            status_log("Query", "Extracting")
        else:
            status_log("Query", "Repair attempt {}".format(query_attempt))
        try:
            query_ir = extract_query_ir_only_openai(
                user_question,
                model=chosen_model,
                kb_schema=kb_schema,
                case=case,
                feedback=query_feedback,
                schema_environment=schema_environment,
            )
            query_obj = normalize_query_ir(query_ir, case, kb_schema, user_question)
        except LLMExtractionError as e:
            raise ExtractionError(str(e))
        except ExtractionIRValidationError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj or {}, kb_schema)
            continue

        try:
            status_log("Query", "Validating")
            if apply_role_arg_consistency(user_question, query_obj, case, kb_schema=kb_schema):
                status_log(
                    "Query",
                    "Adjusted query.args using case facts for role-based question (see query_role_resolve)",
                )
            _check_entity_consistency(user_question, query_obj, case, case_text=case_text, kb_schema=kb_schema)
            _coerce_query_args_to_schema(query_obj, case, kb_schema, user_question=user_question)
            query = normalize_and_validate_query(query_obj, case, kb_schema=kb_schema)
            from pipeline.extraction.case_fact_validation import validate_case_facts_not_query_target

            validate_case_facts_not_query_target(case, query, kb_schema=kb_schema)
            break
        except ValueError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj, kb_schema)
    else:
        raise ExtractionError("Query extraction failed after {} repair attempts: {}".format(max_retries, last_query_error))

    return {"case": case, "query": query}


def extract_case_only(
    case_text,
    kb_schema=None,
    schema_environment=None,
    provider="auto",
    model=None,
    max_retries=6,
    repair_artifact_path: str | None = None,
):
    """Extract and validate case facts only. Use for shared case across multiple questions."""
    if provider == "auto":
        provider = _auto_provider()
    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    return _run_case_extraction_loop(
        case_text,
        kb_schema=kb_schema,
        schema_environment=schema_environment,
        provider=provider,
        model=chosen_model,
        max_retries=max_retries,
        repair_artifact_path=repair_artifact_path,
    )


def extract_query_only(
    user_question,
    case,
    kb_schema=None,
    schema_environment=None,
    provider="auto",
    model=None,
    max_retries=6,
    case_text=None,
):
    """Extract and validate query only, given an already-validated case."""
    if provider == "auto":
        provider = _auto_provider()
    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    query_feedback = None
    query_obj = None
    last_query_error = None
    for query_attempt in range(max_retries):
        if query_attempt == 0:
            status_log("Query", "Extracting")
        else:
            status_log("Query", "Repair attempt {}".format(query_attempt))
        try:
            query_ir = extract_query_ir_only_openai(
                user_question,
                model=chosen_model,
                kb_schema=kb_schema,
                case=case,
                feedback=query_feedback,
                schema_environment=schema_environment,
            )
            query_obj = normalize_query_ir(query_ir, case, kb_schema, user_question)
        except LLMExtractionError as e:
            raise ExtractionError(str(e))
        except ExtractionIRValidationError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj or {}, kb_schema)
            continue

        try:
            status_log("Query", "Validating")
            if apply_role_arg_consistency(user_question, query_obj, case, kb_schema=kb_schema):
                status_log(
                    "Query",
                    "Adjusted query.args using case facts for role-based question (see query_role_resolve)",
                )
            _check_entity_consistency(user_question, query_obj, case, case_text=case_text, kb_schema=kb_schema)
            _coerce_query_args_to_schema(query_obj, case, kb_schema, user_question=user_question)
            query = normalize_and_validate_query(query_obj, case, kb_schema=kb_schema)
            return query
        except ValueError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj, kb_schema)
    raise ExtractionError(
        "Query extraction failed after {} repair attempts: {}".format(max_retries, last_query_error)
    )
