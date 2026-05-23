"""Structured repair history for JSON IR KB compilation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RepairEvent:
    event_index: int
    phase: str  # symbols | rules | validation | render
    symbol_version: int
    rules_attempt: int
    total_llm_calls: int
    action: str
    status: str  # ok | validation_failed | llm_failed | stalled | budget_exhausted | success
    error_kind: str | None = None
    normalized_error_signature: str | None = None
    normalized_error_code: str | None = None
    repair_route: str | None = None
    repair_card_id: str | None = None
    short_error_message: str | None = None
    artifact_paths: list[str] = field(default_factory=list)
    progress_detected: bool | None = None
    progress_reason: str | None = None
    previous_error_path: str | None = None
    current_error_path: str | None = None
    threshold_cardinality_violation_count: int | None = None


@dataclass
class RepairHistory:
    events: list[RepairEvent] = field(default_factory=list)
    symbol_version_count: int = 0
    rules_attempt_count: int = 0
    total_kb_llm_calls: int = 0
    repair_layers_used: list[str] = field(default_factory=list)
    final_failure_category: str | None = None
    final_normalized_error_code: str | None = None
    final_normalized_error_signature: str | None = None
    repeated_error_detected: bool = False
    repair_stalled: bool = False
    budget_exhausted: bool = False
    distinct_errors: list[str] = field(default_factory=list)

    def record(self, event: RepairEvent) -> None:
        self.events.append(event)
        self.symbol_version_count = max(self.symbol_version_count, event.symbol_version)
        self.rules_attempt_count = max(self.rules_attempt_count, event.rules_attempt)
        self.total_kb_llm_calls = event.total_llm_calls
        if event.repair_route and event.repair_route not in self.repair_layers_used:
            self.repair_layers_used.append(event.repair_route)

    def write(self, artifact_dir: Path | str | None) -> None:
        if not artifact_dir:
            return
        root = Path(artifact_dir)
        root.mkdir(parents=True, exist_ok=True)
        payload = {
            "events": [asdict(e) for e in self.events],
            "summary": {
                "symbol_version_count": self.symbol_version_count,
                "rules_attempt_count": self.rules_attempt_count,
                "total_kb_llm_calls": self.total_kb_llm_calls,
                "repair_layers_used": self.repair_layers_used,
                "final_failure_category": self.final_failure_category,
                "final_normalized_error_code": self.final_normalized_error_code,
                "final_normalized_error_signature": self.final_normalized_error_signature,
                "repeated_error_detected": self.repeated_error_detected,
                "repair_stalled": self.repair_stalled,
                "budget_exhausted": self.budget_exhausted,
                "distinct_errors": self.distinct_errors,
            },
        }
        (root / "repair_history.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (root / "repair_summary.json").write_text(
            json.dumps(payload["summary"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "repair_history": [asdict(e) for e in self.events],
            "repair_summary": {
                "symbol_version_count": self.symbol_version_count,
                "rules_attempt_count": self.rules_attempt_count,
                "total_kb_llm_calls": self.total_kb_llm_calls,
                "repair_layers_used": self.repair_layers_used,
                "final_failure_category": self.final_failure_category,
                "final_normalized_error_code": self.final_normalized_error_code,
                "final_normalized_error_signature": self.final_normalized_error_signature,
                "repeated_error_detected": self.repeated_error_detected,
                "repair_stalled": self.repair_stalled,
                "budget_exhausted": self.budget_exhausted,
                "distinct_errors": self.distinct_errors,
            },
        }
