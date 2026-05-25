"""
Run trace: write all pipeline steps to a text file for debugging.
Enable with PIPELINE_TRACE=1 (or true/yes). Writes to run_dir/run_trace.txt.
"""

import os


def trace_enabled():
    """True if run tracing should be written."""
    from pipeline.config import config_section

    return bool(config_section("debug").get("trace"))


class RunTraceWriter:
    """Append pipeline steps to a trace file. Use section() and log() to structure output."""

    def __init__(self, filepath, append=False):
        self.filepath = filepath
        self._file = None
        if filepath:
            d = os.path.dirname(filepath)
            if d:
                os.makedirs(d, exist_ok=True)
            self._file = open(filepath, "a" if append else "w", encoding="utf-8")

    def section(self, title):
        if self._file:
            self._file.write("\n" + "=" * 70 + "\n")
            self._file.write("  " + title + "\n")
            self._file.write("=" * 70 + "\n\n")

    def log(self, label, content):
        if self._file:
            self._file.write("--- " + label + " ---\n")
            self._file.write((str(content).strip() if content else "(empty)") + "\n\n")

    def log_error(self, label, error):
        if self._file:
            self._file.write("--- " + label + " (ERROR) ---\n")
            self._file.write(str(error) + "\n\n")

    def close(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
