#!/usr/bin/env python
"""Audit prompts and optionally remove separator-line bloat safely.

The optional rewrite is deliberately mechanical: it only replaces blocks of
long repeated '='/'-' separator lines around a title with a Markdown header.
It does not rewrite instructions, schemas, examples, or wording.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SEP_RE = re.compile(r"^\s*([=\-_*#])\1{19,}\s*$")


def rough_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


def compact_separators(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    changes = 0
    while i < len(lines):
        if i + 2 < len(lines) and SEP_RE.match(lines[i]) and lines[i + 1].strip() and SEP_RE.match(lines[i + 2]):
            title = lines[i + 1].strip().strip("#:=*-_ ")
            if title:
                out.append(f"## {title}")
                changes += 1
                i += 3
                continue
        # Also remove standalone separator lines if they are purely decorative.
        if SEP_RE.match(lines[i]):
            changes += 1
            i += 1
            continue
        out.append(lines[i])
        i += 1
    new = "\n".join(out)
    if text.endswith("\n"):
        new += "\n"
    return new, changes


def audit_file(path: Path, apply: bool) -> dict:
    text = path.read_text(encoding="utf-8")
    new, changes = compact_separators(text)
    before = len(text)
    after = len(new)
    sep_chars = sum(1 for c in text if c in "=-_*#")
    long_sep_lines = sum(1 for line in text.splitlines() if SEP_RE.match(line))
    if apply and new != text:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        path.write_text(new, encoding="utf-8")
    return {
        "path": str(path),
        "chars_before": before,
        "chars_after": after,
        "rough_tokens_before": rough_tokens(text),
        "rough_tokens_after": rough_tokens(new),
        "separator_chars_before": sep_chars,
        "long_separator_lines": long_sep_lines,
        "mechanical_changes": changes,
        "changed": new != text,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit and optionally compact prompt separator formatting.")
    ap.add_argument("--prompts-dir", default="prompts")
    ap.add_argument("--apply", action="store_true", help="Apply mechanical separator cleanup. Creates .bak once per changed file.")
    ap.add_argument("--report", default="results/reports/prompt_format_audit.json")
    args = ap.parse_args()

    prompts_dir = Path(args.prompts_dir)
    files = sorted([p for p in prompts_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md", ".prompt"}])
    rows = [audit_file(p, args.apply) for p in files]
    total_before = sum(r["chars_before"] for r in rows)
    total_after = sum(r["chars_after"] for r in rows)
    summary = {
        "apply": args.apply,
        "file_count": len(rows),
        "total_chars_before": total_before,
        "total_chars_after": total_after,
        "total_rough_tokens_before": sum(r["rough_tokens_before"] for r in rows),
        "total_rough_tokens_after": sum(r["rough_tokens_after"] for r in rows),
        "estimated_token_savings": sum(r["rough_tokens_before"] - r["rough_tokens_after"] for r in rows),
        "changed_files": [r for r in rows if r["changed"]],
        "largest_files": sorted(rows, key=lambda r: r["chars_before"], reverse=True)[:15],
        "files": rows,
    }
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prompt files: {len(rows)}")
    print(f"Chars: {total_before} -> {total_after} ({total_before - total_after} saved)")
    print(f"Rough tokens: {summary['total_rough_tokens_before']} -> {summary['total_rough_tokens_after']} ({summary['estimated_token_savings']} saved)")
    print(f"Changed files: {len(summary['changed_files'])}")
    print(f"Report: {report_path}")
    if not args.apply:
        print("Dry run only. Re-run with --apply to make mechanical changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
