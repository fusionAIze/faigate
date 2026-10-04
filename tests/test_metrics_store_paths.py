"""The metrics store opens on a machine the installer has never touched.

``faigate.config._safe_db_path`` deliberately refuses the repo-relative value in
``config.yaml`` and falls back to ``~/.local/share/faigate/faigate.db``. Nothing
creates that directory, so every surface that builds the module-level app -
``/livez``, ``/readyz``, ``/health``, the catalog sync route - failed with
``sqlite3.OperationalError: unable to open database file`` on a container, a CI
runner or a fresh checkout, while passing on any machine where the installer had
already made the directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faigate.metrics import MetricsStore


def test_init_creates_a_missing_parent_directory(tmp_path: Path) -> None:
    """init() must create the directory its path names, not assume it exists."""
    target = tmp_path / "never" / "created" / "faigate.db"
    assert not target.parent.exists(), "the fixture must start without the directory"

    store = MetricsStore(db_path=str(target))
    store.init()

    assert target.parent.is_dir(), "init() left its parent directory uncreated"
    assert target.exists(), "init() did not create the database file"


def test_init_does_not_create_a_directory_for_an_in_memory_store(tmp_path: Path) -> None:
    """The counter-example: ``:memory:`` is not a path and must not be made one."""
    store = MetricsStore(db_path=":memory:")
    store.init()

    assert not (Path.cwd() / ":memory:").exists(), "an in-memory store created a file named ':memory:'"


def test_a_relative_path_resolves_without_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A relative path is resolved against the working directory, not rejected."""
    monkeypatch.chdir(tmp_path)
    store = MetricsStore(db_path="nested/relative.db")
    store.init()

    assert (tmp_path / "nested" / "relative.db").exists()
