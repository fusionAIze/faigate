#!/usr/bin/env python3
"""Refuse a second release writer and a release title that breaks the convention.

Two properties of this repository's release path, checked by one command so a
single exit status proves both:

1. **One writer.** No workflow under ``.forgejo/workflows`` or
   ``.github/workflows`` executes a release-creating call. The ops-engine
   creates the release on ``tag_push``; a repo-local writer aims at the same
   release object, the first create wins and the second returns 409/422.
   Comment-only lines and quoted strings are ignored: ``notify-tap.yml`` prints
   a suggested ``gh release edit`` repair line, and that is advice for an
   operator, not a call.

2. **One title.** ``.ops.yaml`` declares ``release.name_template``, and it
   renders the title the rest of the release path expects. ops-engine 3.6.2
   (P36-021) reads the template from the repository's ``.ops.yaml`` release
   block before falling back to the layover; ``notify-tap.yml`` gates the
   resulting title against ``.release-title-prefix``. The engine default
   renders ``faigate vX.Y.Z``, which the title gate refuses, so the Homebrew
   formula update never dispatches. The two values are compared against each
   other here instead of being restated.

Usage:
    check-release-path.py [--root DIR]

Exit 0 when both properties hold; exit 1 naming every failure otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

WORKFLOW_DIRS = (".forgejo/workflows", ".github/workflows")
CANONICAL_REPO = "fusionaize/faigate"
SAMPLE_TAG = "v1.2.3"

_RELEASE_CALL_PATTERNS = (
    re.compile(r"\bpublish_release\s*\("),
    re.compile(r"\bcreate_release\s*\("),
    re.compile(r"\bgh\s+release\s+(?:create|edit|delete)\b"),
    re.compile(r"\bgh\s+api\b[^\n]*\breleases\b[^\n]*\b(?:-X|--method)\s*(?:POST|PATCH|PUT|DELETE)\b"),
    re.compile(r"\bsoftprops/action-gh-release\b"),
    # A write to the releases endpoint, never a download: the method flag is on
    # the same line, so `curl ... /releases/latest` to fetch a tool is not a call.
    re.compile(
        r"\bcurl\b[^\n]*\b(?:-X|--request)\s*(?:POST|PATCH|PUT|DELETE)\b[^\n]*/releases\b"
        r"|\bcurl\b[^\n]*/releases\b[^\n]*\b(?:-X|--request)\s*(?:POST|PATCH|PUT|DELETE)\b"
    ),
)

# A double- or single-quoted span on one line. Stripping these keeps an echoed
# repair instruction out of the match while leaving a real command — whose
# arguments are the quoted parts — intact.
_QUOTED_SPAN = re.compile(r'"(?:\\.|[^"\\])*"' + r"|'(?:\\.|[^'\\])*'")

_PLACEHOLDER = re.compile(r"\{(repo|repo_name|tag_name)\}")


def _executable_text(line: str) -> str:
    """Return the part of ``line`` that can execute, or ``""``.

    Leading-``#`` lines are comments and cannot run. Inline comments are left
    in place: a comment that mentions a release call is still preceded by the
    code that does the work, so it changes no verdict.
    """
    if line.lstrip().startswith("#"):
        return ""
    return _QUOTED_SPAN.sub("", line)


def find_release_calls(root: Path) -> list[str]:
    """Name every executable release-creating call in this repository's workflows."""
    failures: list[str] = []
    for rel in WORKFLOW_DIRS:
        workflow_dir = root / rel
        if not workflow_dir.is_dir():
            continue
        paths = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for lineno, raw in enumerate(text.splitlines(), start=1):
                candidate = _executable_text(raw)
                if not candidate:
                    continue
                if any(pattern.search(candidate) for pattern in _RELEASE_CALL_PATTERNS):
                    failures.append(
                        f"ReleaseWriterError: {path.relative_to(root)}:{lineno} "
                        f"executes a release-creating call ({raw.strip()}). The "
                        "ops-engine is the single writer; remove the call or make "
                        "it skip when the engine writes."
                    )
    return failures


def render_template(template: str, repo: str, tag_name: str) -> str:
    """Render the three placeholders ops-engine supports, leaving others visible."""
    values = {
        "repo": repo,
        "repo_name": repo.split("/")[-1],
        "tag_name": tag_name,
    }
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def find_title_failures(root: Path) -> list[str]:
    """Name every way the rendered release title breaks the convention."""
    prefix_path = root / ".release-title-prefix"
    if not prefix_path.is_file():
        return [
            "ReleaseTitleTemplateError: .release-title-prefix is missing. The "
            "title convention has one source and both the Forgejo title gate and "
            "notify-tap read it; a release path without it cannot be checked."
        ]
    prefix = prefix_path.read_text(encoding="utf-8").strip()

    ops_path = root / ".ops.yaml"
    if not ops_path.is_file():
        return [
            "ReleaseTitleTemplateError: .ops.yaml is missing. Until the title "
            "template is declared in the repository's release block, ops-engine "
            "3.6.2 renders the default '{repo_name} {tag_name}' -> "
            f"'faigate {SAMPLE_TAG}', which the title convention refuses."
        ]
    data = yaml.safe_load(ops_path.read_text(encoding="utf-8")) or {}
    release = data.get("release") or {}
    template = release.get("name_template")
    if not template:
        return [
            "ReleaseTitleTemplateError: .ops.yaml declares no "
            "release.name_template. ops-engine 3.6.2 (P36-021) then falls back "
            f"to '{{repo_name}} {{tag_name}}' -> 'faigate {SAMPLE_TAG}', and "
            f"notify-tap's gate ^{prefix} vX.Y.Z$ refuses, so the Homebrew "
            "dispatch never fires."
        ]

    rendered = render_template(template, CANONICAL_REPO, SAMPLE_TAG)
    expected = f"{prefix} {SAMPLE_TAG}"
    if rendered != expected:
        return [
            "ReleaseTitleTemplateError: .ops.yaml release.name_template "
            f"{template!r} renders {rendered!r}, but .release-title-prefix "
            f"requires {expected!r}. The engine creates the release under the "
            "rendered name and notify-tap refuses anything else."
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refuse a second release writer or a non-conforming release title.")
    parser.add_argument(
        "--root",
        default=None,
        metavar="DIR",
        help="repository root to check (default: the root holding this script)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root is not None else Path(__file__).resolve().parents[2]

    failures = find_release_calls(root) + find_title_failures(root)
    if failures:
        for failure in failures:
            sys.stderr.write(failure + "\n")
        return 1

    template = (
        (yaml.safe_load((root / ".ops.yaml").read_text(encoding="utf-8")) or {}).get("release", {}).get("name_template")
    )
    prefix = (root / ".release-title-prefix").read_text(encoding="utf-8").strip()
    expected = f"{prefix} {SAMPLE_TAG}"
    sys.stdout.write(
        "release path check: PASS - one writer (the ops-engine) and the title "
        f"template {template!r} renders {expected!r}.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
