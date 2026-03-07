"""
Legal reasoning pipeline – web UI.

Run from project root:
  streamlit run ui/app.py
"""

import hashlib
import os
import sys

# Ensure project root is on path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

from debug import status_log
from pipeline.app.pipeline import answer_legal_prompt
from pipeline.io.text_runs import write_text_run
from pipeline.kb.cache import get_or_compile_kb
from pipeline.translation.translator import translate_to_english, TranslationError
from pipeline.rendering.explanations import explain_on_demand
from pipeline.utils.unicode_sanitize import sanitize_for_output


def _get_run_dir(law_text, translate):
    """Same run-folder structure as CLI: ui/run/<hash>/ with translated/ subdir for KB cache."""
    h = hashlib.sha256(law_text.strip().encode("utf-8")).hexdigest()[:16]
    return os.path.join(_root, "ui", "run", h)


def _normalize_text(s):
    """Match CLI: same normalization as load_text_run (strip, normalize newlines)."""
    if not s:
        return ""
    return "\n".join(ln.strip() for ln in s.strip().splitlines()).strip()


def run_pipeline(law_text, case_text, questions, translate, provider="auto", force_recompile=False):
    law_text = _normalize_text(law_text)
    case_text = _normalize_text(case_text)
    questions = [q.strip() for q in questions if q and q.strip()]

    if not law_text:
        return None, None, "Please enter law text."
    if not case_text:
        return None, None, "Please enter case text."
    if not questions:
        return None, None, "Please enter at least one question."

    try:
        if translate:
            status_log("Translation", "Translating law, case, and questions to English")
            law_text = translate_to_english(law_text)
            case_text = translate_to_english(case_text)
            questions = [translate_to_english(q) for q in questions]
    except TranslationError as e:
        return None, None, f"Translation failed: {e}"

    run_path = _get_run_dir(law_text, translate)
    write_text_run(run_path, law_text, case_text, questions)

    if force_recompile:
        cache_dir = os.path.join(run_path, "translated") if translate else run_path
        for f in ("kb.fo", "kb_schema.json"):
            p = os.path.join(cache_dir, f)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    status_log("KB", "Loading or compiling knowledge base")
    try:
        kb_text, kb_schema = get_or_compile_kb(
            run_path, law_text, cache_subdir="translated" if translate else None
        )
    except Exception as e:
        return None, None, f"KB compilation failed: {e}"

    results = []
    for i, q in enumerate(questions):
        status_log("Question", f"Processing {i + 1} of {len(questions)}")
        result = answer_legal_prompt(
            case_text,
            q,
            base_kb_text=kb_text,
            extractor_provider=provider,
            kb_schema=kb_schema,
        )
        results.append({"question": q, "result": result})

    return results, kb_text, None


def main():
    st.set_page_config(page_title="Legal Reasoning Pipeline", layout="wide")
    st.title("Legal Reasoning Pipeline")
    st.markdown(
        "Enter law text, a case description, and one or more questions. "
        "The system compiles the law to first-order logic, extracts structured case facts and queries, "
        "and runs symbolic reasoning (IDP-Z3) to produce answers."
    )

    with st.sidebar:
        st.header("Settings")
        translate = st.checkbox("Translate to English", value=True)
        provider = st.selectbox("LLM provider", ["auto", "openai"], index=0)
        force_recompile = st.checkbox(
            "Force recompile KB",
            value=False,
            help="Ignore cached KB and recompile (use if you get IDP/compilation errors).",
        )

    law_text = st.text_area(
        "Law text",
        placeholder="Paste the relevant legal articles here...",
        height=120,
    )
    case_text = st.text_area(
        "Case",
        placeholder="Describe the facts of the case...",
        height=100,
    )
    questions_text = st.text_area(
        "Questions (one per line)",
        placeholder="Is the defendant liable?\nWhat is the maximum penalty?",
        height=100,
    )
    questions = [q.strip() for q in (questions_text or "").strip().splitlines() if q.strip()]

    if st.button("Run pipeline", type="primary"):
        with st.spinner("Running pipeline..."):
            results, kb_text, err = run_pipeline(
                law_text, case_text, questions,
                translate=translate, provider=provider, force_recompile=force_recompile
            )

        if err:
            st.error(err)
            return

        st.session_state["pipeline_results"] = results
        st.session_state["pipeline_kb_text"] = kb_text
        for k in list(st.session_state.keys()):
            if k.startswith("explanation_"):
                del st.session_state[k]
        st.success("Done!")

    results = st.session_state.get("pipeline_results", [])
    kb_text = st.session_state.get("pipeline_kb_text", "")

    if results:
        st.divider()
        for i, item in enumerate(results):
            q = item["question"]
            r = item["result"]

            with st.expander(f"**Q{i + 1}:** {q[:80]}{'...' if len(q) > 80 else ''}", expanded=True):
                if r.get("error_stage"):
                    st.error(f"**Error ({r.get('error_stage')}):** {sanitize_for_output(str(r.get('error', '')))}")
                else:
                    st.markdown(f"**Answer:** {sanitize_for_output(r.get('natural_language', '—'))}")
                    if r.get("explanation"):
                        st.markdown("**Explanation:**")
                        st.markdown(sanitize_for_output(r["explanation"]))

                    expl_key = f"explanation_{i}"
                    if expl_key in st.session_state:
                        st.markdown("**Explanation:**")
                        st.markdown(sanitize_for_output(st.session_state[expl_key]))
                    elif st.button("Explain", key=f"btn_explain_{i}", help="Generate explanation from KB, facts, and result"):
                        with st.spinner("Generating explanation..."):
                            expl = explain_on_demand(
                                r.get("case"),
                                r.get("query"),
                                r.get("symbolic_result"),
                                base_kb_text=kb_text,
                            )
                            st.session_state[expl_key] = expl
                        st.rerun()

                    with st.expander("Details (case & query)"):
                        st.text(f"Case: {r.get('case')}")
                        st.text(f"Query: {r.get('query')}")
                        st.text(f"SAT: {r.get('sat')}")


if __name__ == "__main__":
    main()
