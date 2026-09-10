"""Shared test isolation.

Several sibling test modules install a minimal ``sys.modules["httpx"]`` stub at
import time so provider code can be imported without a real network client.
The stub lacks the private submodule attributes ``fastapi.testclient`` (via
``starlette.testclient``) needs, so a module that re-imports the genuine
package after such a stub has already been collected silently receives a
busted ``httpx``. Any later module that needs the real package must restore it
from the genuine source, not from ``sys.modules``.

``_load_real_httpx`` is the single place that does this; per-file fixtures keep
mirroring the real package onto the module objects under test.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

_HYGIENE_MODULES = ("httpx",)
_REAL_MODULES: dict[str, ModuleType] = {}


def load_real_module(name: str) -> ModuleType:
    """Import the genuine top-level module even if a test stub is installed.

    ``httpx`` and its private submodules share ``sys.modules`` keys with their
    parent, so a bare ``importlib.reload`` or ``importlib.import_module`` after
    the parent was popped returns an incompletely initialised module on Python
    3.14. Purging the whole ``<name>.*`` family and any importer that bound the
    old object forces a clean re-execution.
    """
    for key in [key for key in sys.modules if key == name or key.startswith(f"{name}.")]:
        sys.modules.pop(key, None)
    real = importlib.import_module(name)
    sys.modules[name] = real
    _REAL_MODULES[name] = real
    return real


def _install_httpx_hygiene() -> None:
    """Restore the genuine httpx for every test in the session.

    The provider tests knowingly swap in a stub so ``faigate.providers`` can be
    imported offline. That stub must end before any module that needs the real
    exception hierarchy or ``starlette.testclient``. Doing it globally rather
    than per-file removes the import-order coupling between sibling modules.
    """
    httpx = load_real_module("httpx")

    from fastapi import testclient as _fastapi_testclient

    _fastapi_testclient.httpx = httpx


_install_httpx_hygiene()
