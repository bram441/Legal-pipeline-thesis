"""Shared exceptions for KB compilation."""


class LawCompilationError(Exception):
    """LLM or validation failure while compiling law text to FO(.)."""

    def __init__(self, message, *, repair_snapshot=None):
        super().__init__(message)
        self.repair_snapshot = repair_snapshot
