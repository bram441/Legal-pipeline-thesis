from idp_z3.case_structure import build_structure_block_from_facts
from pipeline.kb.schema_environment import build_schema_environment
from pipeline.validation.pre_solver_validation import prepare_case_for_symbolic


def _kb_schema():
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "company_marker",
                "kind": "observable",
                "args": ["Company"],
                "returns": "Bool",
                "directly_observable": True,
            },
            {
                "name": "legal_consequences_apply_from_following_financial_year",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
                "output_category": "legal_effect",
            },
        ],
        "functions": [],
    }


def test_query_only_entity_seeded_into_domain():
    kb_schema = _kb_schema()
    env = build_schema_environment(kb_schema)
    case = {"facts": ["company_marker(bv_horizon)."], "entities": {}}
    query = {
        "type": "predicate",
        "predicate": "legal_consequences_apply_from_following_financial_year",
        "args": ["bv_horizon", "financial_year_2025"],
    }
    prepared, _mapping, _diag = prepare_case_for_symbolic(case, query, env)
    structure = build_structure_block_from_facts(
        prepared["facts"],
        entities=prepared["entities"],
        kb_schema=kb_schema,
        kb_primary_type="Company",
    )
    assert "FinancialYear := {'financial_year_2025'}." in structure


def test_case_entities_only_seeded_into_domain():
    kb_schema = _kb_schema()
    env = build_schema_environment(kb_schema)
    case = {
        "facts": ["company_marker(acme)."],
        "entities": {"Company": ["acme"], "FinancialYear": ["financial_year_2024"]},
    }
    prepared, _mapping, _diag = prepare_case_for_symbolic(case, None, env)
    structure = build_structure_block_from_facts(
        prepared["facts"],
        entities=prepared["entities"],
        kb_schema=kb_schema,
        kb_primary_type="Company",
    )
    assert "FinancialYear := {'financial_year_2024'}." in structure
