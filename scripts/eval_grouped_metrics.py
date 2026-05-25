"""
Grouped evaluation metrics for tiered test sets (manifest-driven).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_test_set_manifest(runs_dir: Path) -> dict[str, Any] | None:
    path = runs_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    by_id: dict[str, dict[str, Any]] = {}
    for entry in data.get("runs") or []:
        if isinstance(entry, dict) and entry.get("id"):
            by_id[str(entry["id"])] = entry
    data["runs_by_id"] = by_id
    return data


def _cell_decisive_counts(cell: dict[str, Any]) -> dict[str, int | float | None]:
    total = cell.get("total")
    correct_dec = cell.get("correct_decisive")
    incorrect_dec = cell.get("incorrect_decisive")
    inconclusive = cell.get("inconclusive")
    scored = bool(cell.get("scored"))
    decisive_answers = None
    if isinstance(correct_dec, int) and isinstance(incorrect_dec, int):
        decisive_answers = correct_dec + incorrect_dec
    strict_accuracy = None
    decisive_precision = None
    coverage = None
    decisive_coverage = None
    if isinstance(total, int) and total > 0 and isinstance(correct_dec, int):
        strict_accuracy = correct_dec / total
    if (
        isinstance(decisive_answers, int)
        and decisive_answers > 0
        and isinstance(correct_dec, int)
    ):
        decisive_precision = correct_dec / decisive_answers
    if scored:
        coverage = 1.0
    elif cell.get("ok") is False or cell.get("failure_category"):
        coverage = 0.0
    if isinstance(total, int) and total > 0 and isinstance(decisive_answers, int):
        decisive_coverage = decisive_answers / total
    return {
        "total_questions": total,
        "correct_decisive": correct_dec,
        "incorrect_decisive": incorrect_dec,
        "inconclusive": inconclusive,
        "decisive_answers": decisive_answers,
        "strict_accuracy": strict_accuracy,
        "decisive_precision": decisive_precision,
        "coverage": coverage,
        "decisive_coverage": decisive_coverage,
        "scored": scored,
        "failure_category": cell.get("failure_category"),
    }


def _failure_bucket(category: str | None) -> str:
    cat = (category or "").strip()
    if cat == "law_compilation":
        return "law_compilation"
    if cat in ("case_extraction", "translation"):
        return "extraction"
    if cat in (
        "reasoning_symbol_mismatch",
        "case_query_validation",
        "kb_compile_validation",
        "kb_idp_parse",
        "kb_semantic",
        "kb_lint",
    ):
        return "symbolic"
    if cat in ("completed", "completed_with_symbolic_errors"):
        return "completed"
    if cat:
        return "other"
    return "unknown"


def compute_grouped_metrics(
    matrix: dict[str, Any],
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Aggregate matrix cells by strategy, evaluation_group, difficulty, law_domain, phenomenon.
    """
    strategies = matrix.get("strategies") or []
    cells = matrix.get("cells") or {}
    runs_by_id = (manifest or {}).get("runs_by_id") or {}

    def _meta(run_id: str) -> dict[str, Any]:
        return runs_by_id.get(run_id) or {}

    def _aggregate_bucket(cells_in_bucket: list[dict[str, Any]]) -> dict[str, Any]:
        total_cells = len(cells_in_bucket)
        scored_cells = sum(1 for c in cells_in_bucket if c.get("scored"))
        correct_dec = sum(int(c.get("correct_decisive") or 0) for c in cells_in_bucket if c.get("scored"))
        incorrect_dec = sum(
            int(c.get("incorrect_decisive") or 0) for c in cells_in_bucket if c.get("scored")
        )
        inconclusive = sum(int(c.get("inconclusive") or 0) for c in cells_in_bucket if c.get("scored"))
        total_q = sum(int(c.get("total") or 0) for c in cells_in_bucket if c.get("scored"))
        law_compilation = sum(
            1 for c in cells_in_bucket if c.get("failure_category") == "law_compilation"
        )
        extraction_fail = sum(
            1
            for c in cells_in_bucket
            if _failure_bucket(c.get("failure_category")) == "extraction"
        )
        symbolic_fail = sum(
            1
            for c in cells_in_bucket
            if _failure_bucket(c.get("failure_category")) == "symbolic"
        )
        decisive_answers = correct_dec + incorrect_dec
        total_questions = total_q
        strict_accuracy_over_cells = (correct_dec / total_cells) if total_cells else None
        strict_scored_accuracy = (correct_dec / total_questions) if total_questions else None
        return {
            "total_cells": total_cells,
            "scored_cells": scored_cells,
            "total_questions": total_questions,
            "decisive_correct": correct_dec,
            "decisive_wrong": incorrect_dec,
            "inconclusive": inconclusive,
            "decisive_answers": decisive_answers,
            "law_compilation_failures": law_compilation,
            "extraction_failures": extraction_fail,
            "symbolic_failures": symbolic_fail,
            "compile_failure_rate": (law_compilation / total_cells) if total_cells else None,
            "inconclusive_rate": (inconclusive / total_questions) if total_questions else None,
            "decisive_wrong_rate": (incorrect_dec / decisive_answers) if decisive_answers else None,
            "strict_accuracy": strict_accuracy_over_cells,
            "strict_scored_accuracy": strict_scored_accuracy,
            "decisive_precision": (correct_dec / decisive_answers) if decisive_answers else None,
            "coverage": (scored_cells / total_cells) if total_cells else None,
            "decisive_coverage": (decisive_answers / total_questions) if total_questions else None,
        }

    flat_cells: list[tuple[str, str, dict[str, Any]]] = []
    for run_id, row in cells.items():
        if not isinstance(row, dict):
            continue
        for strategy, cell in row.items():
            if isinstance(cell, dict):
                flat_cells.append((run_id, strategy, cell))

    out: dict[str, Any] = {
        "manifest_present": manifest is not None,
        "by_strategy": {},
        "by_evaluation_group": {},
        "by_difficulty": {},
        "by_law_domain": {},
        "by_phenomenon": {},
    }

    for strategy in strategies:
        bucket = [c for _, s, c in flat_cells if s == strategy]
        out["by_strategy"][strategy] = _aggregate_bucket(bucket)

    for key_name, field in (
        ("by_evaluation_group", "evaluation_group"),
        ("by_difficulty", "difficulty"),
        ("by_law_domain", "law_domain"),
    ):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run_id, strategy, cell in flat_cells:
            val = _meta(run_id).get(field) or "unknown"
            groups[str(val)].append(cell)
        out[key_name] = {k: _aggregate_bucket(v) for k, v in sorted(groups.items())}

    phen_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run_id, strategy, cell in flat_cells:
        tags = _meta(run_id).get("phenomena") or ["unknown"]
        for tag in tags:
            phen_groups[str(tag)].append(cell)
    out["by_phenomenon"] = {k: _aggregate_bucket(v) for k, v in sorted(phen_groups.items())}

    return out


def format_grouped_report_md(grouped: dict[str, Any]) -> str:
    lines = [
        "## Grouped metrics (manifest tiers)",
        "",
        "Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; "
        "``decisive_precision`` = decisive_correct / decisive_answers; "
        "``coverage`` = scored_cells / total_cells.",
        "",
    ]

    def _table(title: str, section: dict[str, dict[str, Any]]) -> None:
        if not section:
            return
        lines.extend([f"### {title}", ""])
        lines.append(
            "| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | "
            "strict_acc | scored_acc | dec.prec | coverage |"
        )
        lines.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
        for name, m in section.items():
            sa = m.get("strict_accuracy")
            ssa = m.get("strict_scored_accuracy")
            dp = m.get("decisive_precision")
            cov = m.get("coverage")
            cfr = m.get("compile_failure_rate")
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    name,
                    m.get("total_cells"),
                    m.get("scored_cells"),
                    m.get("decisive_correct"),
                    m.get("decisive_wrong"),
                    m.get("inconclusive"),
                    "%.0f%%" % (cfr * 100) if isinstance(cfr, float) else "—",
                    "%.2f" % sa if isinstance(sa, float) else "—",
                    "%.2f" % ssa if isinstance(ssa, float) else "—",
                    "%.2f" % dp if isinstance(dp, float) else "—",
                    "%.2f" % cov if isinstance(cov, float) else "—",
                )
            )
        lines.append("")

    _table("By strategy", grouped.get("by_strategy") or {})
    _table("By evaluation_group", grouped.get("by_evaluation_group") or {})
    _table("By difficulty", grouped.get("by_difficulty") or {})
    _table("By law_domain", grouped.get("by_law_domain") or {})
    _table("By phenomenon", grouped.get("by_phenomenon") or {})
    return "\n".join(lines)
