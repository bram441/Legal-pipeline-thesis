# pipeline/debug.py

import os


def debug_enabled():
    v = os.getenv("PIPELINE_DEBUG", "").strip().lower()
    return v in ["1", "true", "yes", "on"]


def debug_log(where, message):
    """Print debug traces when PIPELINE_DEBUG is enabled."""
    if not debug_enabled():
        return
    print("[DEBUG] " + str(where) + ": " + str(message))
