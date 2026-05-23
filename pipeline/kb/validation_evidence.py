"""Collect validation diagnostics for repair prompts (primary error may block later validators)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.kb.law_numeric_literals import format_law_numbers_for_message
from pipeline.kb.numeric_threshold_provenance import collect_numeric_threshold_provenance_issues
from pipeline.kb.threshold_cardinality import collect_threshold_cardinality_violations


@dataclass
class ValidationRepairEvidence:
    cardinality_violations: list[str] = field(default_factory=list)
    numeric_provenance_issues: list[dict[str, Any]] = field(default_factory=list)
    law_thresholds: list[float] = field(default_factory=list)

    @property
    def threshold_cardinality_violation_count(self) -> int:
        return len(self.cardinality_violations)

    def primary_error_path(self) -> str | None:
        if not self.cardinality_violations:
            return None
        return _extract_rule_path(self.cardinality_violations[0])

    def format_secondary_diagnostics(self) -> str:
        lines: list[str] = []
        if self.numeric_provenance_issues:
            lines.append("numeric_threshold_not_in_law_text (secondary — fix even if cardinality is primary):")
            for issue in self.numeric_provenance_issues:
                val = issue.get("threshold")
                path = issue.get("path", "?")
                lines.append(
                    "  - Rule %s uses numeric threshold %s, not in scoped law text."
                    % (path, val)
                )
            if self.law_thresholds:
                lines.append(
                    "  Allowed law-text thresholds: %s"
                    % format_law_numbers_for_message(set(self.law_thresholds))
                )
            lines.append("Also fix these numeric threshold provenance issues.")
        if len(self.cardinality_violations) > 1:
            lines.append(
                "Additional threshold_cardinality violations (%d total):"
                % len(self.cardinality_violations)
            )
            for v in self.cardinality_violations[1:4]:
                lines.append("  - " + v[:200])
        return "\n".join(lines)


def _extract_rule_path(message: str) -> str | None:
    m = re.search(r"(rules\[\d+\](?:\.[a-zA-Z0-9_\[\]]+)*)", message or "")
    return m.group(1) if m else None


def collect_validation_repair_evidence(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    law_text_for_lints: str | None,
) -> ValidationRepairEvidence:
    """Non-blocking collection of cardinality + numeric provenance issues."""
    from pipeline.kb.law_numeric_literals import extract_numeric_values_from_law_text

    law_text = (law_text_for_lints or "").strip()
    law_vals = sorted(extract_numeric_values_from_law_text(law_text)) if law_text else []
    cardinality = collect_threshold_cardinality_violations(
        ir, pred_kinds, law_text_for_lints=law_text_for_lints
    )
    numeric = collect_numeric_threshold_provenance_issues(
        ir, law_text_for_lints=law_text_for_lints
    )
    return ValidationRepairEvidence(
        cardinality_violations=cardinality,
        numeric_provenance_issues=numeric,
        law_thresholds=law_vals,
    )


def extract_error_path_from_message(message: str) -> str | None:
    return _extract_rule_path(message)
