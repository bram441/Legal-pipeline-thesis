"""Shared exceptions for KB compilation."""


class LawCompilationError(Exception):
    """LLM or validation failure while compiling law text to FO(.)."""

    def __init__(
        self,
        message,
        *,
        repair_snapshot=None,
        error_kind: str | None = None,
        repair_summary: dict | None = None,
    ):
        super().__init__(message)
        self.repair_snapshot = repair_snapshot
        self.error_kind = error_kind
        self.repair_summary = repair_summary
