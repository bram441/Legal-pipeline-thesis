# Logical English layer: law text -> LE -> JSON-IR (when PIPELINE_USE_LE=1).

from pipeline.le.layer import use_le_enabled, law_text_to_le

__all__ = ["use_le_enabled", "law_text_to_le"]
