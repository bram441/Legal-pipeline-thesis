# pipeline/debug.py

import os


def debug_enabled():
    v = os.getenv("PIPELINE_DEBUG", "").strip().lower()
    return v in ["1", "true", "yes", "on"]


def status_log(stage, message):
    """Print status updates (always on, unless PIPELINE_QUIET=1)."""
    if os.getenv("PIPELINE_QUIET", "").strip().lower() in ["1", "true", "yes", "on"]:
        return
    print("[{}] {}".format(stage, message))


def debug_log(where, message):
    """Print debug traces when PIPELINE_DEBUG is enabled."""
    if not debug_enabled():
        return
    print("[DEBUG] " + str(where) + ": " + str(message))
