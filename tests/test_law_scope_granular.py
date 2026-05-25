"""Granular law scoping: citations, chunking, legal-effect false-positive guard."""

from __future__ import annotations

import os

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError
from pipeline.kb.law_citation import extract_citations
from pipeline.kb.law_scope import select_law_text_for_compilation
from pipeline.kb.legal_effect import (
    should_require_legal_effect_output,
    validate_legal_effect_output_presence,
)

LAW_ART_124 = """
Article 1:24.

§ 1. A small company is a company that, on the balance sheet date, does not exceed more than one of the criteria.

§ 2. The consequences apply from the financial year following the year in which the criteria mentioned in paragraph 1 were exceeded.
""".strip()

LAW_ART_124_BELGIAN = """
Art. 1:24. par. 1. Small companies are companies with legal personality that do not exceed more than one criterion.

par. 2. When more than one of the criteria referred to in paragraph 1 are exceeded, the consequences then take effect from the financial year following the financial year during which more than one of the criteria were exceeded for the second time.
""".strip()

LAW_ART_1_POINTS = """
Article 1.

Paragraph 1.

1° First point about alpha classification.

2° Second point about beta.

3° Third point about gamma.

4° Fourth point specific rule about delta eligibility.

5° Fifth point about epsilon.
""".strip()

LAW_MULTI = """
Article 1:24.

§ 1. Small company definition.

§ 2. Consequences timing.

Article 3.
Unrelated text about something else entirely.
""".strip()


def _classify_only_predicates() -> list[dict]:
    return [
        {
            "name": "reports_for_year",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "kind": "observable",
            "description": "Case input",
        },
        {
            "name": "is_small_company",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "kind": "derived",
            "description": "Small company classification",
        },
    ]


@pytest.fixture(autouse=True)
def _scope_cited(monkeypatch):
    monkeypatch.setenv("JSON_IR_SCOPE_MODE", "cited")


def test_a_paragraph_1_excludes_paragraph_2_effect_text():
    q = "Is BV Vega a small company according to Article 1:24 paragraph 1?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124, question_text=q)
    assert "§ 1" in scoped or "small company" in scoped.lower()
    assert "consequences apply" not in scoped.lower()
    assert meta["scope_mode"] == "exact_citation"
    assert meta["cited_paragraph"] == 1
    assert meta["contains_effect_language"] is False


def test_b_paragraph_2_includes_effect_and_may_pull_paragraph_1_dependency():
    q = "Do the consequences under Article 1:24 paragraph 2 apply from 2026?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124, question_text=q)
    assert "consequences apply" in scoped.lower()
    assert meta["contains_effect_language"] is True
    assert meta["cited_paragraph"] == 2
    if meta.get("included_dependency_chunks"):
        assert "§ 1" in scoped or "criteria" in scoped.lower()


def test_c_point_4_only():
    q = "Under Article 1, paragraph 1, point 4, does delta eligibility apply?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_1_POINTS, question_text=q)
    assert "Fourth point" in scoped or "delta" in scoped.lower()
    assert "First point" not in scoped
    assert "Second point" not in scoped
    assert meta["cited_point"] == 4
    assert meta["selected_granularity"] in {"point", "mixed"}


def test_d_article_level_includes_all_paragraphs():
    q = "According to Article 1:24, what applies?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124, question_text=q)
    assert "§ 1" in scoped
    assert "§ 2" in scoped
    assert meta["scope_mode"] == "article_level"
    assert meta["selected_granularity"] == "article"


def test_e_keyword_retrieval_without_citation(monkeypatch):
    monkeypatch.setenv("JSON_IR_SCOPE_MODE", "retrieve")
    q = "Does the unrelated provision about something else apply?"
    scoped, meta = select_law_text_for_compilation(
        LAW_MULTI, question_text=q, case_text=""
    )
    assert meta["scope_mode"] in {"keyword_retrieval", "fallback_full_law"}
    assert "Unrelated" in scoped or len(scoped) > 0


def test_f_dutch_citation_forms():
    cases = [
        ("artikel 1:24, § 1", "1:24", 1, None),
        ("artikel 1, paragraaf 1, punt 4", "1", 1, 4),
        ("art. 1:24, tweede lid", "1:24", 2, None),
    ]
    for q, art, para, pt in cases:
        refs = extract_citations(q)
        assert refs, f"no citation for {q!r}"
        r = refs[0]
        assert art.replace(":", ".") in r.article.replace(":", ".")
        assert r.effective_paragraph() == para
        if pt is not None:
            assert r.point == pt


def test_g_legal_effect_validator_skips_when_scoped_text_has_no_effect():
    q = "Is Company X a small company under Article 1:24 paragraph 1?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124, question_text=q)
    assert meta["contains_effect_language"] is False
    assert should_require_legal_effect_output(scoped, scope_metadata=meta) is False
    validate_legal_effect_output_presence(
        _classify_only_predicates(),
        law_text_for_lints=scoped,
        scope_metadata=meta,
    )


def test_h_legal_effect_validator_still_fires_for_paragraph_2_question():
    q = "From when do the consequences under Article 1:24 paragraph 2 apply?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124, question_text=q)
    assert meta["contains_effect_language"] is True
    assert should_require_legal_effect_output(scoped, scope_metadata=meta) is True
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_legal_effect_output_presence(
            _classify_only_predicates(),
            law_text_for_lints=scoped,
            scope_metadata=meta,
        )
    assert "legal-output" in str(exc.value).lower() or "legal-effect" in str(exc.value).lower()


def test_belgian_par_format_paragraph_1_excludes_paragraph_2():
    q = "Is BV Vega a small company according to Article 1:24, paragraph 1?"
    scoped, meta = select_law_text_for_compilation(LAW_ART_124_BELGIAN, question_text=q)
    assert "par. 1" in scoped or "Small companies" in scoped
    assert "take effect from" not in scoped.lower()
    assert meta["scope_mode"] == "exact_citation"
    assert meta["contains_effect_language"] is False


def test_legacy_article_scoping_still_works():
    law = LAW_MULTI
    scoped, meta = select_law_text_for_compilation(
        law, question_text="Under Article 3?"
    )
    assert "Article 3" in scoped
    assert "Article 1:24" not in scoped
    assert meta.get("citations")
