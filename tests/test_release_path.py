"""The repository's release path has one writer and one title template.

The ops-engine creates the release on ``tag_push``. Two repo-local facts decide
whether that release reaches the Homebrew tap, and both are checked here so a
regression fails in CI rather than on the next tag:

* no workflow executes a release-creating call (a second writer races the
  engine on the same release object), and
* ``.ops.yaml`` declares a ``release.name_template`` that renders the title
  ``.release-title-prefix`` requires (ops-engine 3.6.2 reads the template from
  the repository's own release block; the default renders ``faigate vX.Y.Z``,
  which ``notify-tap.yml`` refuses).

RED PROOF: both tests fail against base 764d4e1 — the ``gh release create`` and
``gh release edit`` calls were live in ``.github/workflows/prerelease.yml`` and
``.ops.yaml`` had no ``release:`` block.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_check_module():
    script_path = REPO_ROOT / ".github" / "scripts" / "check-release-path.py"
    spec = importlib.util.spec_from_file_location("check_release_path", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_no_workflow_executes_a_release_creating_call():
    module = _load_check_module()

    assert module.find_release_calls(REPO_ROOT) == []


def test_ops_yaml_declares_the_release_title_the_convention_requires():
    module = _load_check_module()

    assert module.find_title_failures(REPO_ROOT) == []


def test_release_creating_calls_are_detected_and_echoed_advice_is_not(tmp_path):
    """The checker must see a real command and must not see an echoed one."""
    module = _load_check_module()

    base = tmp_path / ".github" / "workflows"
    base.mkdir(parents=True)
    (base / "writer.yml").write_text(
        "jobs:\n"
        "  release:\n"
        "    steps:\n"
        "      - run: |\n"
        '          gh release create "$TAG" --title x --notes-file notes.md\n',
        encoding="utf-8",
    )
    assert module.find_release_calls(tmp_path)

    (base / "writer.yml").write_text(
        "jobs:\n"
        "  gate:\n"
        "    steps:\n"
        "      - run: |\n"
        "          # gh release create is what this workflow used to do\n"
        "          echo \"::error::Fix: gh release edit $TAG --title 'x'\"\n"
        "          curl -fsSL https://example.invalid/releases/latest -o tool\n",
        encoding="utf-8",
    )
    assert module.find_release_calls(tmp_path) == []


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("fusionAIze Gate {tag_name}", "fusionAIze Gate v1.2.3"),
        ("{repo_name} {tag_name}", "faigate v1.2.3"),
        ("{repo} {tag_name}", "fusionaize/faigate v1.2.3"),
        ("x {unknown}", "x {unknown}"),
    ],
)
def test_render_template_matches_the_engine_placeholders(template, expected):
    module = _load_check_module()

    assert module.render_template(template, "fusionaize/faigate", "v1.2.3") == expected
