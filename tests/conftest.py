"""Shared test isolation.

Provider modules import ``httpx`` at module scope and call ``httpx.AsyncClient``
when a backend is constructed. Test modules used to install a minimal
``sys.modules["httpx"]`` stub so those imports worked offline. That global
mutation leaked: the stub lacks the private submodule attributes
``fastapi.testclient`` (via ``starlette.testclient``) and the real exception
hierarchy (``HTTPError``, ``ConnectError``), so any module collected afterwards
silently received a busted ``httpx``. Restoration happened once, before
collection, which only helped when no stub module followed — an accident of
ordering, not a guarantee.

No test module mutates ``sys.modules["httpx"]`` any more; they import the
genuine package directly. ``load_real_module`` and the autouse fixture below
keep the invariant honest: whatever a test imports, ``sys.modules["httpx"]``
is the genuine package for the whole session, in every collection order.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest

_REAL_MODULES: dict[str, ModuleType] = {}


# Provider API keys that ``faigate.wizard._load_env_values`` reads from
# ``os.environ`` before overlaying any ``.env`` file. When an operator has these
# exported in their shell, wizard candidate detection treats the corresponding
# providers as "ready now", which flips several wizard tests between pass and
# fail on the same commit. Remove them for the duration of every test so the
# suite reads only what the test itself (its ``.env`` file / fixtures) provides.
_WIZARD_PROVIDER_API_KEYS = (
    "ANTHROPIC_API_KEY",
    "BLACKBOX_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "KILOCODE_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
)


def load_real_module(name: str) -> ModuleType:
    """Import the genuine top-level module even if a test stub is installed.

    ``httpx`` and its private submodules share ``sys.modules`` keys with their
    parent, so a bare ``importlib.reload`` or ``importlib.import_module`` after
    the parent was popped returns an incompletely initialised module on Python
    3.14. Purging the whole ``<name>.*`` family forces a clean re-execution.
    """
    for key in [key for key in sys.modules if key == name or key.startswith(f"{name}.")]:
        sys.modules.pop(key, None)
    real = importlib.import_module(name)
    sys.modules[name] = real
    _REAL_MODULES[name] = real
    return real


def install_real_module(name: str, *, sentinel: str) -> ModuleType:
    """Restore the genuine module unless it is already live and complete.

    ``sentinel`` is an attribute only the genuine package exposes (for httpx:
    ``HTTPError``); a stub that lacks it is purged and re-imported.
    """
    real = sys.modules.get(name)
    if real is not None and hasattr(real, sentinel):
        _REAL_MODULES[name] = real
        return real
    return load_real_module(name)


@pytest.fixture(autouse=True)
def _keep_wizard_provider_keys_hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep wizard candidate detection independent of the operator's shell.

    ``faigate.wizard._load_env_values`` seeds from ``os.environ`` before
    overlaying the ``.env`` file, so any provider API key exported in the shell
    leaks into provider detection and flips tests that assert a provider still
    needs a key. Run every test with those keys absent; tests that need a key
    provide it explicitly via ``monkeypatch.setenv`` or their ``.env`` file.
    """
    for key in _WIZARD_PROVIDER_API_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _keep_httpx_genuine() -> None:
    """Guarantee the genuine ``httpx`` before every test.

    The stub modules are gone, but a future test module could reintroduce one.
    Restoring here means the invariant holds per test rather than per session
    import, so no collection order can leave a later module with a broken
    ``httpx``.
    """
    install_real_module("httpx", sentinel="HTTPError")


install_real_module("httpx", sentinel="HTTPError")
