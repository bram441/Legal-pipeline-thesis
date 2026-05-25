"""
Error-specific repair cards for JSON IR KB compilation (law-agnostic).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairCard:
    card_id: str
    title: str
    layer: str  # symbols | rules | either
    do_items: tuple[str, ...]
    do_not_items: tuple[str, ...]
    preferred_pattern: str = ""


_CARDS: dict[str, RepairCard] = {
    "missing_helper_definition": RepairCard(
        card_id="missing_helper_definition",
        title="Missing helper definition",
        layer="rules",
        do_items=(
            "The repair card names the exact missing helper and its signature from the symbol table.",
            "Define the helper with one or more rules where it appears in THEN (from observables, compares, or simpler helpers).",
            "Or reclassify as observable/case_input/background only when the fact is directly case-given and safe.",
            "For threshold/counting helpers, prefer pairwise/conjunctive THEN definitions (A&B, A&C, B&C).",
            "Temporal support relations marked background/case_input do not need a THEN definition.",
        ),
        do_not_items=(
            "Delete the helper condition from the rule IF.",
            "Rename the helper without defining it in THEN.",
            "Introduce another undefined helper to replace the missing one.",
            "Mark computed threshold helpers observable without case-level justification.",
        ),
        preferred_pattern=(
            "missing_helper(C,FY) in THEN from compare(metric(C,FY), >, threshold); "
            "more_than_one(C,FY) in THEN from pairwise exceeded OR of (A&B)|(A&C)|(B&C)."
        ),
    ),
    "missing_helper_definition_for_legal_effect": RepairCard(
        card_id="missing_helper_definition_for_legal_effect",
        title="Missing helper definition (legal-effect rule)",
        layer="rules",
        do_items=(
            "The legal-effect derived predicate already exists; keep it in THEN.",
            "Define every helper used in IF to derive that legal-effect predicate.",
            "Threshold helpers: define from numeric compares on observable functions.",
            "Temporal/consecutive helpers: define from period/year facts or inline per-year conditions.",
            "If a helper cannot be defined, inline lower-level conditions; do not delete the legal-effect rule.",
        ),
        do_not_items=(
            "Create new symbols during rules repair.",
            "Delete the legal-effect rule or remove its THEN conclusion.",
            "Turn the legal-effect predicate into a classification predicate.",
            "Leave helpers undefined while they remain in the legal-effect rule IF.",
        ),
        preferred_pattern=(
            "exceeds_A(X,Y) :- compare(metric(X,Y), >, threshold_A). "
            "exceeds_two_consecutive(X,Y) :- exceeds_more_than_one(X,Y), exceeds_more_than_one(X, prior_year(Y)). "
            "legal_effect(X,Y) :- exceeds_two_consecutive(X,Y)."
        ),
    ),
    "missing_helper_definition_for_composite_temporal_threshold": RepairCard(
        card_id="missing_helper_definition_for_composite_temporal_threshold",
        title="Missing composite threshold/temporal helper (legal-effect)",
        layer="rules",
        do_items=(
            "You are repairing rules only; do not create new symbols.",
            "Do not delete the legal-effect rule.",
            "Define per-criterion exceeded helpers from numeric comparisons on observables.",
            "Define more_than_one_criterion as pairwise exceeded: (A&B) OR (A&C) OR (B&C).",
            "Define two-consecutive-years from per-year conditions plus an existing prior-year relation.",
            "Define following-period linkage only if the symbol table already has such a relation.",
            "Keep the legal-effect output predicate in THEN.",
        ),
        do_not_items=(
            "Create new symbols during rules repair.",
            "Delete the legal-effect rule or remove its THEN conclusion.",
            "Invent prior/following year functions not declared in the symbol table.",
            "Leave composite helpers undefined while they remain in the legal-effect rule IF.",
        ),
        preferred_pattern=(
            "exceeds_A(C,FY):-compare(...); exceeds_more_than_one(C,FY):-pairwise exceeded; "
            "two_consecutive(C,FY):-exceeds_more_than_one(C,FY),exceeds_more_than_one(C,prior_year(FY)); "
            "legal_effect(C,FY):-two_consecutive(C,FY)."
        ),
    ),
    "computed_observable_unsafe": RepairCard(
        card_id="computed_observable_unsafe",
        title="Computed condition marked observable",
        layer="symbols",
        do_items=(
            "Change threshold/count/consolidation predicates to helper or derived with defining rules.",
            "Keep documentary/status facts (passport, travel document, comply/unwillingness with measure) "
            "as kind=observable with directly_observable=true and/or case_input=true.",
            "Keep legal conclusions/effects as derived (or helper+rules), not observable.",
            "Use directly_observable=true only when a case can state the composite fact verbatim.",
        ),
        do_not_items=(
            "Use observable kind merely to avoid defining rules for threshold helpers.",
            "Mark legal-output/effect predicates as observable.",
            "Force passport/compliance behavior facts into helper/derived unless they are rule-derived.",
        ),
    ),
    "computed_observable_unsafe_for_legal_effect": RepairCard(
        card_id="computed_observable_unsafe_for_legal_effect",
        title="Computed threshold helper blocks legal-effect KB",
        layer="symbols",
        do_items=(
            "This KB derives a legal effect; threshold/consecutive helpers must not stay observable.",
            "Change computed exceeds/threshold/criteria predicates to kind=helper (or derived).",
            "Keep numeric amount/count functions as observable; define threshold helpers in rules via compares.",
            "Preserve the legal-effect derived predicate and its rule in THEN.",
            "After symbols validate, define every helper used in the legal-effect rule IF.",
        ),
        do_not_items=(
            "Leave threshold helpers as observable to avoid rules.",
            "Delete the legal-effect predicate or replace it with classification only.",
            "Use directly_observable=true on threshold compares without case-level justification.",
            "Remove helpers from the legal-effect rule without defining them.",
        ),
        preferred_pattern=(
            "Symbols: exceeds_employee_threshold kind=helper. "
            "Rules: exceeds_employee_threshold(C,FY) in THEN from compare(employees(C,FY), >, 50); "
            "legal_effect(C,FY) in THEN when consecutive conditions hold."
        ),
    ),
    "missing_threshold_classification_exclusion": RepairCard(
        card_id="missing_threshold_classification_exclusion",
        title="Missing threshold classification exclusion",
        layer="rules",
        do_items=(
            "The KB may already have positive qualification rules; that is not enough for false-case reasoning.",
            "For 'not more than one criterion is exceeded', add a negative/exclusion rule with pairwise exceeded logic.",
            "Let A/B/C = criterion 1/2/3 exceeded. Correct exclusion: "
            "((A AND B) OR (A AND C) OR (B AND C)) => NOT classification (negated predicate in THEN).",
            "If positive rules already exist, preserve them and add the missing exclusion rule.",
            "Preserve exact numeric thresholds from scoped law text in every compare literal.",
            "Optional helper: define at_least_two_exceeded, then at_least_two_exceeded => not classification.",
        ),
        do_not_items=(
            "A OR B OR C => NOT classification (simple OR of single exceeded compares).",
            "within_A OR within_B OR within_C => classification (one within-threshold check is too weak).",
            "Only positive pairwise within-threshold rules without an exclusion rule.",
            "Rely on open-world absence of proof to answer false legal questions.",
            "Remove or replace existing positive qualification rules when adding exclusion.",
        ),
        preferred_pattern=(
            "((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR (B_exceeded AND C_exceeded)) "
            "=> NOT classification (negated: true in THEN)."
        ),
    ),
    "numeric_threshold_not_in_law_text": RepairCard(
        card_id="numeric_threshold_not_in_law_text",
        title="Numeric threshold not in law text",
        layer="rules",
        do_items=(
            "Preserve numeric thresholds exactly from scoped law text.",
            "Replace invented thresholds with matching law-text numbers.",
        ),
        do_not_items=(
            "Infer new thresholds (e.g. change 900,000 into 1,900,000).",
            "Round or rescale legal constants during repair.",
            "Add 1,000,000 unless the law text contains it.",
        ),
    ),
    "threshold_cardinality_or_singleton": RepairCard(
        card_id="threshold_cardinality_or_singleton",
        title="Threshold cardinality / polarity",
        layer="rules",
        do_items=(
            "When the law says 'not more than one criterion is exceeded', define exceeded: "
            "A = criterion 1 exceeded, B = criterion 2 exceeded, C = criterion 3 exceeded.",
            "Correct positive qualification: NOT ((A AND B) OR (A AND C) OR (B AND C)) => classification.",
            "Correct negative/exclusion/disqualification: "
            "((A AND B) OR (A AND C) OR (B AND C)) => NOT classification (negated predicate in THEN).",
            "If the failing rule has negated THEN, repair its IF to pairwise exceeded AND combinations; "
            "do not remove the exclusion rule or the positive rule.",
            "Preserve exact numeric thresholds from scoped law text.",
            "If using within-threshold conditions for qualification, use pairwise within: "
            "(within_A AND within_B) OR (within_A AND within_C) OR (within_B AND within_C).",
            "Exclusion/disqualification must still use pairwise exceeded combinations, not within-OR.",
        ),
        do_not_items=(
            "A OR B OR C => classification.",
            "A OR B OR C => NOT classification.",
            "within_A OR within_B OR within_C => classification.",
            "Remove the exclusion rule when fixing cardinality.",
            "Remove the positive rule when fixing exclusion.",
            "Invent or alter legal threshold numbers during repair.",
        ),
        preferred_pattern=(
            "Positive: NOT ((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR "
            "(B_exceeded AND C_exceeded)) => classification. "
            "Exclusion: ((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR "
            "(B_exceeded AND C_exceeded)) => NOT classification."
        ),
    ),
    "status_as_type": RepairCard(
        card_id="status_as_type",
        title="Status modeled as primitive type",
        layer="symbols",
        do_items=(
            "Replace narrow legal-status types with broader entity types.",
            "Model the status/classification as a derived predicate over the broader type.",
        ),
        do_not_items=(
            "Keep type X and predicate is_x(X).",
            "Make ordinary case entities impossible to classify.",
        ),
    ),
    "missing_temporal_support_symbol": RepairCard(
        card_id="missing_temporal_support_symbol",
        title="Missing temporal support symbol",
        layer="symbols",
        do_items=(
            "The symbol table is INVALID: the scoped law/question requires temporal reasoning "
            "(previous, following, consecutive periods/years) but no temporal support relation/function exists.",
            "You MUST add at least one temporal support predicate/function using existing period/year types.",
            "Choose names from the law text and schema. Generic examples: "
            "previous_period(Period, Period), next_period(Period, Period), "
            "immediately_precedes(Period, Period), immediately_follows(Period, Period), "
            "consecutive_periods(Period, Period), previous_year(Year, Year), next_year(Year, Year), "
            "previous_financial_year(FinancialYear, FinancialYear), "
            "next_financial_year(FinancialYear, FinancialYear), "
            "consecutive_financial_years(FinancialYear, FinancialYear).",
            "Temporal support must be a SEPARATE relation/function between period arguments — "
            "not merely the words following/consecutive inside a legal-effect predicate name.",
            "Mark temporal support as directly_observable=true and/or background=true / case_input=true; "
            "use kind=observable (preferred) or helper — not derived/legal_output unless rule-definable.",
            "Keep legal-effect output predicates separate from classification predicates.",
            "Preserve existing classification/support predicates unless directly wrong.",
            "Rules repair cannot define consecutive/following-period helpers until these symbols exist.",
        ),
        do_not_items=(
            "Rename only the legal-effect predicate to embed following/previous/consecutive without adding "
            "a separate period relation (that does NOT satisfy this requirement).",
            "Hardcode case-specific constants, article numbers, or benchmark-specific shortcuts.",
            "Encode temporal ordering only in a predicate name without period/year arguments.",
            "Remove the legal-effect predicate.",
            "Replace the legal-effect question with a broad classification predicate only.",
        ),
        preferred_pattern=(
            "next_financial_year(FinancialYear, FinancialYear); "
            "previous_financial_year(FinancialYear, FinancialYear); "
            "legal_effect(Entity, Year) :- trigger(Entity, Year), next_financial_year(Year, Following)."
        ),
    ),
    "missing_legal_effect_output": RepairCard(
        card_id="missing_legal_effect_output",
        title="Missing legal-effect output predicate",
        layer="symbols",
        do_items=(
            "The symbol table may already include positive classification predicates; that is not enough for effect questions.",
            "Add a derived legal-output predicate for consequence/effect/timing/applicability from scoped law text.",
            "Set kind=derived, legal_output=true, output_category=legal_effect or timing.",
            "When scope has classification + effect paragraphs: keep is_* classification predicates as support; "
            "add a separate legal-effect predicate for the effect paragraph.",
            "Name the predicate from law wording (e.g. consequences_apply_from_following_financial_year).",
            "Rules repair will later define this predicate from effect antecedents — symbols phase only adds the declaration.",
        ),
        do_not_items=(
            "Answer effect/timing questions with is_small_company / is_micro_company / classification alone.",
            "Rely on open-world absence of proof for a legal-effect answer.",
            "Remove classification predicates when adding the legal-effect symbol.",
            "Use only threshold/helper predicates without a legal_output derived predicate.",
        ),
        preferred_pattern=(
            "consequences_apply_from_following_financial_year(company, period) "
            "kind=derived legal_output=true output_category=legal_effect"
        ),
    ),
    "derived_predicate_not_defined": RepairCard(
        card_id="derived_predicate_not_defined",
        title="Derived predicate not defined in rules",
        layer="rules",
        do_items=(
            "Add at least one rule with the derived predicate in THEN.",
            "Define legal-output predicates from the law's antecedents.",
        ),
        do_not_items=(
            "Remove the derived predicate if it is legally necessary.",
        ),
    ),
    "ungrounded_variable": RepairCard(
        card_id="ungrounded_variable",
        title="Ungrounded consequent variable",
        layer="rules",
        do_items=(
            "Ensure every variable in THEN appears in IF or is safely quantified.",
            "Add missing relational antecedents.",
        ),
        do_not_items=(
            "Invent constants.",
            "Leave conclusion variables unconstrained.",
        ),
    ),
    "invalid_signature": RepairCard(
        card_id="invalid_signature",
        title="Invalid symbol signature",
        layer="symbols",
        do_items=(
            "Align predicate/function signatures with how the law and rules use them.",
            "Prefer broader entity types for legal statuses.",
        ),
        do_not_items=(
            "Patch rules by changing legal meaning when the symbol table is wrong.",
        ),
    ),
    "unknown_symbol": RepairCard(
        card_id="unknown_symbol",
        title="Unknown or undeclared symbol",
        layer="either",
        do_items=(
            "If the symbol expresses a legally required concept, add it to symbols and use it consistently.",
            "If it is a typo, replace it with the correct existing symbol.",
        ),
        do_not_items=(
            "Silently drop the condition.",
        ),
    ),
    "type_mismatch": RepairCard(
        card_id="type_mismatch",
        title="Type mismatch in rule",
        layer="either",
        do_items=(
            "Align quantifier types and argument types with vocabulary signatures.",
            "Prefer broader entity types for status predicates.",
        ),
        do_not_items=(
            "Force incompatible types without fixing signatures.",
        ),
    ),
    "idp_render_error": RepairCard(
        card_id="idp_render_error",
        title="FO render / IDP error",
        layer="either",
        do_items=(
            "Fix the JSON IR shape and symbol usage that caused the render failure.",
        ),
        do_not_items=(
            "Delete legal conditions to satisfy the renderer.",
        ),
    ),
    "json_parse_error": RepairCard(
        card_id="json_parse_error",
        title="Invalid JSON output",
        layer="either",
        do_items=(
            "Return valid JSON only.",
            "Preserve semantics from the previous valid attempt if available.",
        ),
        do_not_items=(
            "Include prose outside JSON.",
            "Use markdown fences.",
        ),
    ),
    "unknown_validation_error": RepairCard(
        card_id="unknown_validation_error",
        title="Validation error (generic)",
        layer="either",
        do_items=(
            "Fix the validation error without deleting legal conditions.",
            "Preserve valid symbols/rules unless implicated by the error.",
        ),
        do_not_items=(
            "Rename predicates without preserving semantics.",
            "Turn legal-output predicates into observables.",
        ),
    ),
    "suspicious_self_relation": RepairCard(
        card_id="suspicious_self_relation",
        title="Suspicious self-relation R(x,x)",
        layer="rules",
        do_items=(
            "Do not use R(c,c) to express existence of another related entity.",
            "Introduce a distinct quantified variable: exists other != c and R(c, other).",
            "Or model existence as an observable Boolean on the main subject (has_related_entities(c)).",
            "Only use R(x,x) when the predicate is explicitly reflexive by name, description, or metadata.",
        ),
        do_not_items=(
            "Keep affiliated_with(c,c) or forms_consortium_with(c,c) style self-applications.",
            "Delete the legal condition instead of fixing the relation pattern.",
        ),
        preferred_pattern="has_affiliated_companies(c) observable OR affiliated_with(c, other) with other != c.",
    ),
    "no_helper_definition_progress": RepairCard(
        card_id="no_helper_definition_progress",
        title="No helper-definition progress",
        layer="rules",
        do_items=(
            "Add a new rule with the missing helper in THEN, not only in IF.",
            "Define from observables/compares or simpler helpers already in the symbol table.",
            "For threshold helpers use pairwise/conjunctive THEN definitions.",
        ),
        do_not_items=(
            "Resubmit identical rules without a THEN definition for the missing helper.",
            "Rename the helper without defining it.",
        ),
    ),
    "predicate_used_as_function": RepairCard(
        card_id="predicate_used_as_function",
        title="Predicate used as function",
        layer="rules",
        do_items=(
            "Use predicates as P(args) or negated P(args) in IF/THEN.",
            "Use numeric functions only inside compare left/right terms.",
        ),
        do_not_items=(
            "Use a predicate name as a function term.",
            "Write P(args) = value — predicates are not functions.",
        ),
    ),
    "function_used_as_predicate": RepairCard(
        card_id="function_used_as_predicate",
        title="Function used as predicate",
        layer="rules",
        do_items=(
            "Use numeric functions only inside compare left/right: F(args) op N.",
            "For legal NO conclusions, use negated predicate in THEN.",
        ),
        do_not_items=(
            "Use a function name as a Bool predicate atom.",
            "Write F(args) = false — functions are not predicates.",
        ),
        preferred_pattern=(
            'compare({"func": "F", "args": [...]}, "<=", {"func": "threshold", ...}) in IF; '
            'THEN compare equality to define threshold helper from law literal.'
        ),
    ),
    "repeated_missing_numeric_helper_definition": RepairCard(
        card_id="repeated_missing_numeric_helper_definition",
        title="Repeated missing numeric helper definition",
        layer="rules",
        do_items=(
            "Define the threshold helper function in THEN with compare equality to a law-text literal.",
            "Use the numeric threshold helper scaffold pattern.",
        ),
        do_not_items=(
            "Reuse the function only in IF without a THEN equality definition.",
            "Define case-value observables from law thresholds.",
        ),
    ),
    "numeric_threshold_ambiguous": RepairCard(
        card_id="numeric_threshold_ambiguous",
        title="Ambiguous law threshold for numeric helper",
        layer="rules",
        do_items=(
            "Pick the law literal matching the function name/description and scoped article.",
            "Define with THEN compare equality using that single literal.",
        ),
        do_not_items=(
            "Guess among multiple plausible thresholds silently.",
            "Invent thresholds not present in scoped law text.",
        ),
    ),
    "repeated_missing_helper_definition": RepairCard(
        card_id="repeated_missing_helper_definition",
        title="Repeated missing helper definition",
        layer="rules",
        do_items=(
            "Two repair attempts failed to add a THEN rule for the same helper.",
            "Use the threshold pairwise scaffold: define exceeded helpers, then counting helper H in THEN.",
            "If symbols cannot express the helper, escalate to symbols repair with new helpers/functions.",
        ),
        do_not_items=(
            "Rename the helper again without defining it.",
            "Delete IF conditions that use the helper.",
        ),
    ),
}


def get_repair_card(error_code: str) -> RepairCard:
    return _CARDS.get(error_code) or _CARDS["unknown_validation_error"]


def format_repair_card(error_code: str) -> str:
    card = get_repair_card(error_code)
    lines = [
        "REPAIR CARD: %s" % card.title,
        "Intended layer: %s" % card.layer,
        "Do:",
    ]
    for item in card.do_items:
        lines.append("- " + item)
    lines.append("Do not:")
    for item in card.do_not_items:
        lines.append("- " + item)
    if card.preferred_pattern:
        lines.append("Preferred pattern: " + card.preferred_pattern)
    return "\n".join(lines)
