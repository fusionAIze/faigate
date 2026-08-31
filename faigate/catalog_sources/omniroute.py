"""OmniRoute catalog source adapter.

OmniRoute publishes its provider and model configuration as TypeScript under
``open-sse/config/**``, not as a machine-readable JSON artifact. There is no
``npm run build``-free JSON to download, so this adapter evaluates those
configs to JSON on demand via ``tsx`` (transpile-and-run, no full Next.js
build) and normalizes the result into
:class:`~faigate.catalog_sources.base.NormalizedEntry` objects.

The canonical source is **exclusively** ``diegosouzapw/OmniRoute``. Several
near-identical forks exist with one or two stars; wiring one by accident
would silently pull a divergent provider catalog. To make that mistake loud,
the repository URL is hard-wired as :data:`OMNIROUTE_REPO_URL` and the test
suite asserts it stays that value.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from faigate.catalog_sources.base import FreeTier, NormalizedEntry

#: Hard-wired canonical upstream. Do not change without a deliberate,
#: reviewed decision: several lookalike forks exist and a fork mix-up must
#: be caught by ``tests/test_catalog_sources.py``, not silently accepted.
OMNIROUTE_REPO_URL = "https://github.com/diegosouzapw/OmniRoute.git"

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


def _index_free_tiers(payload: dict[str, Any]) -> dict[tuple[str, str | None], FreeTier]:
    """Index free-tier facts from the free-model budgets.

    Each OmniRoute free-model budget is keyed by ``provider`` and ``modelId``.
    The model id is normalized to the same stripped form the registry uses so a
    budget attaches to the matching catalog entry; a budget without a usable id
    still attaches at provider scope.
    """
    free_tiers: dict[tuple[str, str | None], FreeTier] = {}
    for budget in payload.get("free_model_budgets") or []:
        if not isinstance(budget, dict):
            continue
        provider = str(budget.get("provider") or "").strip()
        if not provider:
            continue
        model_id = budget.get("modelId")
        model_id = str(model_id).strip() if model_id else None
        free_tiers.setdefault((provider, model_id), _free_tier_from_budget(budget))
        if model_id:
            free_tiers.setdefault((provider, None), _free_tier_from_budget(budget))
    return free_tiers


def _resolve_free_tier(
    free_tiers: dict[tuple[str, str | None], FreeTier],
    provider_id: str,
    model_id: str,
) -> FreeTier | None:
    for key in ((provider_id, model_id), (provider_id, None)):
        if key in free_tiers:
            return free_tiers[key]
    return None


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


class OmniRouteAdapter:
    """Source adapter for OmniRoute's TypeScript provider configs.

    Satisfies :class:`SourceAdapter`. ``fetch`` evaluates the TS configs via
    ``tsx`` and returns the JSON payload; ``normalize`` turns that payload into
    :class:`NormalizedEntry` objects. The two steps stay separate so callers
    can cache the raw JSON while still re-normalizing against newer schema
    expectations.
    """

    def __init__(self, checkout_dir: str | None = None) -> None:
        self.checkout_dir = checkout_dir

    def fetch(self) -> object:
        """Evaluate the OmniRoute configs to JSON via ``tsx``.

        Runs a TypeScript dump module inside the OmniRoute checkout using the
        transpile-on-demand loader ``tsx`` (no full Next.js build, no
        ``npm install``). The dump prints a single JSON object on stdout.
        """
        checkout = self.checkout_dir
        if not checkout:
            raise RuntimeError(
                f"OmniRouteAdapter.fetch requires checkout_dir pointing at a clone of {OMNIROUTE_REPO_URL}."
            )

        dump_path = Path(checkout) / _DUMP_SCRIPT_RELATIVE
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(_DUMP_TS_TEMPLATE, encoding="utf-8")

        proc = subprocess.run(
            ["npx", "--yes", "tsx", _DUMP_SCRIPT_RELATIVE],
            cwd=str(checkout),
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
