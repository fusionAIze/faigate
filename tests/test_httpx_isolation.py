"""Regression test for the httpx isolation mechanism.

Test modules used to install a minimal ``sys.modules["httpx"]`` stub at import
time and never restore it. The restoration in ``tests/conftest.py`` ran once,
before collection, so it only protected modules that happened to be collected
before the last stub module — an ordering accident, not a guarantee.

This single test pins the invariant directly: the genuine ``httpx`` is in
``sys.modules`` no matter how many modules are (re)imported, in any order, and
``conftest.install_real_module`` repairs ``sys.modules`` even if a stub is
injected mid-session.
"""

from __future__ import annotations

import importlib
import sys
import types

import conftest
import httpx

_HTTPX_MARKERS = ("HTTPError", "TimeoutException", "ConnectError", "AsyncClient")


def _assert_genuine_httpx() -> None:
    live = sys.modules["httpx"]
    assert getattr(live, "__file__", None), "httpx in sys.modules is not the genuine package"
    for marker in _HTTPX_MARKERS:
        assert hasattr(live, marker), f"genuine httpx lacks {marker}"


def test_genuine_httpx_holds_across_repeated_module_switches_and_stub_injection():
    """The real httpx survives repeated switches and a late stub override."""
    cycles = [
        "faigate.providers",
        "faigate.main",
        "faigate.updates",
        "faigate.metadata_catalog_sync",
    ]
    for _ in range(3):
        for name in cycles:
            sys.modules.pop(name, None)
            importlib.import_module(name)
            _assert_genuine_httpx()
            assert httpx is sys.modules["httpx"]

    stub = types.ModuleType("httpx")
    sys.modules["httpx"] = stub
    assert not hasattr(sys.modules["httpx"], "HTTPError")

    repaired = conftest.install_real_module("httpx", sentinel="HTTPError")
    assert repaired is sys.modules["httpx"]
    _assert_genuine_httpx()
