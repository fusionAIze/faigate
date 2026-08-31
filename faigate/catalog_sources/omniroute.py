"""OmniRoute catalog source adapter.

OmniRoute publishes its provider and model configuration as TypeScript under
``open-sse/config/**``, not as a machine-readable JSON artifact. There is no
``npm run build``-free JSON to download, so this adapter evaluates those
configs to JSON on demand via ``tsx`` (transpile-and-run, no full Next.js
build) and normalizes the result into
:class:`~faigate.catalog_sources.base.NormalizedEntry` objects.

To keep the evaluation deterministic and script-free, ``tsx`` is resolved from
a locked, ``--ignore-scripts`` install (pinned to :data:`TSX_VERSION`), and the
Node runtime is pinned to OmniRoute's own ``.node-version`` / ``.nvmrc`` rather
than whatever ``node`` happens to be first on ``PATH``. A runtime whose major
version does not match that pin is a hard error, not a silent fallback.

The canonical source is **exclusively** ``diegosouzapw/OmniRoute``. Several
near-identical forks exist with one or two stars; wiring one by accident
would silently pull a divergent provider catalog. To make that mistake loud,
the repository URL is hard-wired as :data:`OMNIROUTE_REPO_URL` and the test
suite asserts it stays that value.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from faigate.catalog_sources.base import FreeTier, NormalizedEntry

#: Hard-wired canonical upstream. Do not change without a deliberate,
#: reviewed decision: several lookalike forks exist and a fork mix-up must
#: be caught by ``tests/test_catalog_sources.py``, not silently accepted.
OMNIROUTE_REPO_URL = "https://github.com/diegosouzapw/OmniRoute.git"

#: Node version files, in precedence order, that pin the runtime OmniRoute
#: itself targets. The first one found in the checkout wins; both pin ``24``.
_NODE_VERSION_FILES = (".node-version", ".nvmrc")

#: Default pinned Node major used when the checkout carries neither pin file.
_DEFAULT_NODE_MAJOR = "24"

#: Locked ``tsx`` version. Exact (not a range) so the install is reproducible;
#: bumped deliberately, never pulled at runtime like ``npx --yes`` does.
TSX_VERSION = "4.23.13"

#: The ``tsx`` loader is installed under its own directory inside the checkout
#: (``node_modules`` and ``package.json`` are otherwise untouched), so the
#: checkout stays a clean clone of upstream while the loader stays locked.
_TSX_INSTALL_DIR = ".faigate-tsx-runtime"

#: Path, relative to the checkout root, of the TypeScript module whose
#: evaluation produces the normalized JSON payload (providers, free tiers).
_DUMP_SCRIPT_RELATIVE = "open-sse/config/omniroute_dump.ts"

#: Registry fields carried onto a normalized entry's context window.
_CONTEXT_KEYS = ("contextLength", "maxInputTokens")

#: Registry capability flags mapped onto free-form capability tokens.
_CAPABILITY_FLAGS = ("toolCalling", "supportsReasoning", "supportsXHighEffort")

#: Registry modality flags mapped onto interchange modality tokens.
_MODALITY_FLAGS = {
    "supportsVision": "image",
    "supportsAudio": "audio",
    "supportsVideo": "video",
}

#: Free-tier free types that grant recurring, uncapped access (no published
#: token budget), surfaced as a free tier with no numeric cap.
_UNCAPPED_FREE_TYPES = {"recurring-uncapped", "keyless"}


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _derive_context_length(raw: dict[str, Any]) -> int | None:
    """Derive a context window from the registry's context/max-input fields."""
    for key in _CONTEXT_KEYS:
        value = _as_int(raw.get(key))
        if value is not None:
            return value
    return None


def _derive_modalities(raw: dict[str, Any]) -> list[str]:
    return sorted({token for flag, token in _MODALITY_FLAGS.items() if raw.get(flag)})


def _derive_capabilities(raw: dict[str, Any]) -> list[str]:
    capabilities: list[str] = []
    for flag in _CAPABILITY_FLAGS:
        if raw.get(flag):
            capabilities.append(flag)
    if raw.get("supportedThinkingEfforts"):
        capabilities.append("thinking_efforts")
    return capabilities


def _build_entry(provider_id: str, model: dict[str, Any]) -> NormalizedEntry:
    model_id = str(model.get("id") or "")
    max_output = _as_int(model.get("maxOutputTokens"))
    max_input = _as_int(model.get("maxInputTokens"))
    context_window = _as_int(model.get("contextLength"))
    if context_window is None:
        context_window = max_input
    if context_window is None:
        context_window = _derive_context_length(model)

    return NormalizedEntry(
        provider_id=provider_id,
        model_id=model_id,
        display_name=str(model.get("name")) if model.get("name") else None,
        context_window=context_window,
        max_input_tokens=max_input,
        max_output_tokens=max_output,
        modalities=_derive_modalities(model),
        capabilities=_derive_capabilities(model),
        source_url=OMNIROUTE_REPO_URL,
    )


def _free_tier_from_budget(budget: dict[str, Any]) -> FreeTier:
    """Map one OmniRoute free-model budget onto a :class:`FreeTier`.

    OmniRoute stores monthly/credit token figures on each free-model record.
    ``monthlyTokens`` maps to ``tokens_per_month``; a raw RPD figure is not
    stored there, so ``tokens_per_day`` stays ``None`` unless derivable.
    """
    monthly = _as_int(budget.get("monthlyTokens"))
    credit = _as_int(budget.get("creditTokens"))
    free_type = str(budget.get("freeType") or "")

    if free_type in _UNCAPPED_FREE_TYPES:
        return FreeTier(tokens_per_month=None, expires_at=None)

    tokens_per_month = monthly if monthly and monthly > 0 else None
    if tokens_per_month is None and credit and credit > 0:
        tokens_per_month = credit
    return FreeTier(tokens_per_month=tokens_per_month)


def _index_free_tiers(payload: dict[str, Any]) -> dict[tuple[str, str], FreeTier]:
    """Index free-tier facts from the free-model budgets, scoped per model.

    Each OmniRoute free-model budget is keyed by ``provider`` and ``modelId``,
    and -- matching upstream's own ``computeFreeModelTotals`` / ``perModel`` --
    a free tier is attributed strictly to the ``(provider, modelId)`` pair that
    carries a budget. A provider-level budget with no matching model id never
    exists upstream (every ``FREE_MODEL_BUDGETS`` entry has a ``modelId``), and
    must not be treated as evidence that *every* model of that provider is
    free. Budgets without a usable model id are dropped rather than fanning out
    to provider scope.
    """
    free_tiers: dict[tuple[str, str], FreeTier] = {}
    for budget in payload.get("free_model_budgets") or []:
        if not isinstance(budget, dict):
            continue
        provider = str(budget.get("provider") or "").strip()
        model_id = budget.get("modelId")
        model_id = str(model_id).strip() if model_id else ""
        if not provider or not model_id:
            continue
        free_tiers.setdefault((provider, model_id), _free_tier_from_budget(budget))
    return free_tiers


def _resolve_free_tier(
    free_tiers: dict[tuple[str, str], FreeTier],
    provider_id: str,
    model_id: str,
) -> FreeTier | None:
    return free_tiers.get((provider_id, model_id))


def _walk_providers(payload: dict[str, Any]) -> list[NormalizedEntry]:
    """Flatten provider -> models into normalized entries, keyed by provider.

    ``provider_id`` is the canonical registry id (e.g. ``deepseek``), while
    the public alias (``ds``) is irrelevant to the catalog.
    """
    free_tiers = _index_free_tiers(payload)
    entries: list[NormalizedEntry] = []
    providers = payload.get("providers") or {}

    for provider_id, provider in providers.items():
        if not isinstance(provider, dict):
            continue
        models = provider.get("models") or []
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict):
                continue
            model_id = str(model.get("id") or "")
            entry = _build_entry(str(provider_id), model)
            entry.free_tier = _resolve_free_tier(free_tiers, str(provider_id), model_id)
            entries.append(entry)
    return entries


_DUMP_TS_TEMPLATE = """\
// Auto-evaluated by faigate.catalog_sources.omniroute. Mirrors the shape the
// adapter's normalize() consumes; kept minimal so a structural change in
// OmniRoute's config modules surfaces as an explicit build/runtime failure.
import { REGISTRY } from "./providers/index.ts";
import { FREE_MODEL_BUDGETS } from "./freeModelCatalog.data.ts";

const MODEL_FIELDS = [
  "id", "name", "toolCalling", "supportsReasoning", "supportsVision",
  "supportsAudio", "supportsVideo", "supportsXHighEffort",
  "supportedThinkingEfforts", "maxOutputTokens", "contextLength",
  "maxInputTokens",
];

const providers: Record<string, unknown> = {};
for (const [id, entry] of Object.entries(REGISTRY)) {
  const e = entry as any;
  providers[id] = {
    id: e.id,
    alias: e.alias ?? null,
    models: (e.models ?? []).map((m: any) => {
      const out: Record<string, unknown> = {};
      for (const field of MODEL_FIELDS) {
        if (m[field] !== undefined) out[field] = m[field];
      }
      return out;
    }),
  };
}

console.log(JSON.stringify({
  providers,
  free_model_budgets: FREE_MODEL_BUDGETS.map((b) => ({
    provider: b.provider,
    modelId: b.modelId,
    monthlyTokens: b.monthlyTokens,
    creditTokens: b.creditTokens,
    freeType: b.freeType,
  })),
}));
"""


def _resolve_node_major(checkout: Path) -> str:
    """Return the pinned Node major version for a checkout.

    Reads OmniRoute's own pin files (``.node-version`` then ``.nvmrc``) and
    returns the major component (e.g. ``"24"``). Falls back to
    :data:`_DEFAULT_NODE_MAJOR` when neither pin file is present, so a bare
    checkout still evaluates against the version the upstream repo declares
    rather than an arbitrary ``PATH`` runtime.
    """
    for name in _NODE_VERSION_FILES:
        pin = checkout / name
        if pin.is_file():
            content = pin.read_text(encoding="utf-8").strip()
            match = re.match(r"\d+", content)
            if match:
                return match.group(0)
    return _DEFAULT_NODE_MAJOR


def _check_node_major(checkout: Path) -> None:
    """Fail loudly if the ``PATH`` node runtime does not match the pinned major.

    The pin lives in the checkout (``.node-version`` / ``.nvmrc``), not in this
    package, so a mismatch -- e.g. Homebrew surfacing Node 26 while OmniRoute
    pins 24 -- is raised instead of silently running the dump on an untested
    runtime.
    """
    pinned = _resolve_node_major(checkout)
    try:
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = proc.stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("OmniRouteAdapter.fetch requires a Node.js runtime matching the checkout pin.") from None

    match = re.match(r"v?(\d+)", output)
    if match is None or match.group(1) != pinned:
        raise RuntimeError(
            f"OmniRoute checkout pins Node major {pinned}, but `node --version` "
            f"reports {output or 'an unparseable value'}. Install Node {pinned} "
            f"(or point PATH at it) before fetching."
        )


def _tsx_binary_dir(checkout: Path) -> Path:
    """Return the directory holding the locked ``tsx`` install for a checkout."""
    return checkout / _TSX_INSTALL_DIR


def _install_tsx(checkout: Path) -> Path:
    """Install the locked ``tsx`` loader, script-free, and return its binary.

    ``tsx`` is resolved to an exact pinned version (:data:`TSX_VERSION`) under
    a dedicated directory inside the checkout. ``npm install`` runs with
    ``--ignore-scripts`` (no lifecycle scripts) plus ``--no-audit``/``--no-fund``
    so nothing beyond the locked loader is pulled. The checkout's own
    ``node_modules`` and ``package.json`` are left untouched.
    """
    install_dir = _tsx_binary_dir(checkout)
    bin_path = install_dir / "node_modules" / ".bin" / "tsx"
    if bin_path.is_file():
        return bin_path

    install_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "npm",
            "install",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--no-save",
            "--prefix",
            str(install_dir),
            f"tsx@{TSX_VERSION}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to install locked tsx@{TSX_VERSION}: {proc.stderr.strip() or proc.stdout.strip()}")
    if not bin_path.is_file():
        raise RuntimeError(f"Locked tsx@{TSX_VERSION} install did not produce {bin_path}.")
    return bin_path


class OmniRouteAdapter:
    """Source adapter for OmniRoute's TypeScript provider configs.

    Satisfies :class:`SourceAdapter`. ``fetch`` evaluates the TS configs via
    a locked ``tsx`` install and returns the JSON payload; ``normalize`` turns
    that payload into :class:`NormalizedEntry` objects. The two steps stay
    separate so callers can cache the raw JSON while still re-normalizing
    against newer schema expectations.
    """

    def __init__(self, checkout_dir: str | None = None) -> None:
        self.checkout_dir = checkout_dir

    def fetch(self) -> object:
        """Evaluate the OmniRoute configs to JSON via a locked ``tsx`` loader.

        Pins the Node runtime to the checkout's ``.node-version`` / ``.nvmrc``
        (failing loudly on a mismatch), resolves ``tsx`` from a locked,
        ``--ignore-scripts`` install, then runs a TypeScript dump module
        against that checkout. No full Next.js build and no ``npx``/registry
        resolution at runtime. The dump prints a single JSON object on stdout.
        """
        checkout = self.checkout_dir
        if not checkout:
            raise RuntimeError(
                f"OmniRouteAdapter.fetch requires checkout_dir pointing at a clone of {OMNIROUTE_REPO_URL}."
            )

        checkout_path = Path(checkout)
        _check_node_major(checkout_path)
        tsx_bin = _install_tsx(checkout_path)

        dump_path = checkout_path / _DUMP_SCRIPT_RELATIVE
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(_DUMP_TS_TEMPLATE, encoding="utf-8")

        proc = subprocess.run(
            [str(tsx_bin), _DUMP_SCRIPT_RELATIVE],
            cwd=str(checkout_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"OmniRoute tsx dump failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return json.loads(proc.stdout)

    def normalize(self, raw: object) -> list[NormalizedEntry]:
        if not isinstance(raw, dict):
            return []
        return _walk_providers(raw)
