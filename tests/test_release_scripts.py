from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path


def _load_release_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "faigate-release"
    loader = SourceFileLoader("faigate_release", str(script_path))
    spec = importlib.util.spec_from_loader("faigate_release", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_release_script_rejects_invalid_versions():
    module = _load_release_module()

    assert module.validate_version("1.11.3") == "1.11.3"
    try:
        module.validate_version("v1.11.3")
    except ValueError as exc:
        assert "Expected x.y.z" in str(exc)
    else:
        raise AssertionError("Expected invalid version to raise")


def test_release_script_syncs_pyproject_and_package_version(tmp_path, monkeypatch):
    module = _load_release_module()
    pyproject = tmp_path / "pyproject.toml"
    package_init = tmp_path / "__init__.py"
    pyproject.write_text('[project]\nversion = "1.11.2"\n', encoding="utf-8")
    package_init.write_text('__version__ = "1.11.2"\n', encoding="utf-8")

    monkeypatch.setattr(module, "PYPROJECT", pyproject)
    monkeypatch.setattr(module, "PACKAGE_INIT", package_init)

    changed = module.sync_version_files("1.11.3")

    assert pyproject.read_text(encoding="utf-8") == '[project]\nversion = "1.11.3"\n'
    assert package_init.read_text(encoding="utf-8") == '__version__ = "1.11.3"\n'
    assert pyproject in changed
    assert package_init in changed


def test_release_script_updates_changelog_header(tmp_path, monkeypatch):
    module = _load_release_module()
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n\n- Keep going\n", encoding="utf-8")

    monkeypatch.setattr(module, "CHANGELOG", changelog)

    changed = module.update_changelog("1.11.3")

    content = changelog.read_text(encoding="utf-8")
    assert changed is True
    assert "## v1.11.3 -" in content
    assert "### Added" in content


def test_release_script_promotes_existing_version_unreleased_section(tmp_path, monkeypatch):
    module = _load_release_module()
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## v1.12.0 - Unreleased\n\n### Added\n\n- Keep going\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "CHANGELOG", changelog)

    changed = module.update_changelog("1.12.0")

    content = changelog.read_text(encoding="utf-8")
    assert changed is True
    assert "## v1.12.0 - Unreleased" not in content
    assert "## v1.12.0 -" in content
    assert content.count("## v1.12.0 -") == 1


def test_release_script_next_steps_reference_tap_repo():
    module = _load_release_module()

    steps = module.render_next_steps("1.11.3")

    assert 'git tag -a v1.11.3 -m "fusionAIze Gate v1.11.3"' in steps[2]
    assert "homebrew-tap" in steps[-1]
    assert "Formula/faigate.rb" not in steps[-1]
