"""Local, gitignored operator overlay on top of the curated catalog.

Some catalog facts belong to the operator and never to a repository: the
token/request quota a plan grants, the account tier a key is bound to, or
limits that apply only to the operator's own key. Writing those into the
project would leak private billing state into a public artifact. They live
in a local overlay instead, outside any checkout, and are merged into the
catalog at load time in memory.

The overlay uses the same shape as the catalog::

    {
        "schema_version": "fusionaize-provider-catalog/v1.2",
        "providers": {
            "deepseek": {
                "quota": {"tokens_per_day": 500000},
                "account_tier": "pro",
                "key_limits": {"requests_per_minute": 60}
            }
        }
    }

Only fields on :data:`OPERATOR_FIELDS` may appear in an overlay. Every other
field names a *physical* fact -- the context window, the modalities, the
public price -- that is a property of the model and the vendor, not of the
operator's account. An overlay that tries to carry one is **rejected**, not
silently dropped: a rejected overlay cannot quietly shadow the catalog and
turn into a second source of truth. The rejection names the offending field
and provider so the operator can fix the file.

The merge is deterministic: providers and operator fields are settled in a
fixed, sorted order and the result never depends on dict insertion order. It
is a pure function -- callers pass the catalog and the overlay in and get a
new catalog out, with no shared mutable state and no I/O.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("faigate.catalog_local_overlay")

#: Catalog shape the overlay mirrors. Kept as a constant so the overlay and
#: the catalog cannot drift apart silently.
SCHEMA_VERSION = "fusionaize-provider-catalog/v1.2"

#: Env var that points at the local overlay file. The default path lives
#: under the user's cache directory, never inside a repository checkout.
ENV_OVERLAY_PATH = "FAIGATE_CATALOG_LOCAL_OVERLAY"

#: Default location. ``~/.cache/faigate`` is runtime state outside any repo,
#: so the overlay is gitignored by construction rather than by a rule that
#: somebody has to remember to keep.
DEFAULT_OVERLAY_PATH = Path.home() / ".cache" / "faigate" / "catalog-local-overlay.v1.json"

#: The allowlist: the only fact keys an overlay may carry. Each one is an
#: operator-bound fact -- tied to a key, an account, or a billing plan --
#: rather than a property of the model. Anything outside this set is a
#: physical fact and is rejected.
OPERATOR_FIELDS = ("account_tier", "key_limits", "quota")

#: Physical facts that an overlay is most likely to reach for by mistake.
#: They are named here so the rejection message can explain *why* the field
#: is off limits instead of only reporting that it is unknown.
PHYSICAL_FIELDS = (
    "aliases",
    "capabilities",
    "context_window",
    "input_modalities",
    "max_input_tokens",
    "max_output_tokens",
    "modalities",
    "offer_track",
    "output_modalities",
    "pricing",
    "provider_type",
    "recommended_model",
    "signup_url",
    "track",
)


class OverlayError(ValueError):
    """Base error for a local overlay that cannot be accepted."""


class OverlayRejectedError(OverlayError):
    """An overlay entry tried to carry a fact it is not allowed to carry.

    ``provider_id`` and ``field_name`` locate the offending entry so the
    operator can fix the file; ``reason`` says whether the field is a known
    physical fact or simply unknown to the overlay schema.
    """

    def __init__(self, *, provider_id: str, field_name: str, reason: str) -> None:
        self.provider_id = provider_id
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"local overlay for provider {provider_id!r} rejected: field {field_name!r} {reason}")


@dataclass
class LocalOverlay:
    """A validated local overlay, ready to merge into a catalog.

    ``providers`` maps a provider id to the allowlisted operator fields for
    that provider. ``source`` records where the overlay was read from (or
    ``"<memory>"`` for one built in tests) for logging and status output.
    """

    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    source: str = "<memory>"
    schema_version: str = SCHEMA_VERSION

    def is_empty(self) -> bool:
        return not self.providers


def _reject(provider_id: str, field_name: str) -> OverlayRejectedError:
    if field_name in PHYSICAL_FIELDS:
        reason = "is a physical fact and may never be overridden by the local overlay"
    else:
        reason = "is not on the operator-field allowlist"
    return OverlayRejectedError(provider_id=provider_id, field_name=field_name, reason=reason)


def validate_overlay(payload: Mapping[str, Any]) -> LocalOverlay:
    """Validate a raw overlay mapping against the operator-field allowlist.

    Every provider entry may carry only keys from :data:`OPERATOR_FIELDS`.
    The first field outside the allowlist, in sorted order so the error is
    deterministic, raises :class:`OverlayRejectedError`. A payload with no
    ``providers`` mapping validates to an empty overlay.
    """
    providers_raw = payload.get("providers")
    if not isinstance(providers_raw, Mapping):
        return LocalOverlay(
            providers={},
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        )

    validated: dict[str, dict[str, Any]] = {}
    for provider_id in sorted(providers_raw):
        entry = providers_raw[provider_id]
        if not isinstance(entry, Mapping):
            raise OverlayRejectedError(
                provider_id=str(provider_id),
                field_name="<entry>",
                reason="must be a mapping of operator fields",
            )
        for field_name in sorted(entry):
            if field_name not in OPERATOR_FIELDS:
                raise _reject(str(provider_id), str(field_name))
        validated[str(provider_id)] = dict(entry)

    return LocalOverlay(
        providers=validated,
        schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
    )


def overlay_path() -> Path:
    """Return the path of the local overlay file.

    ``FAIGATE_CATALOG_LOCAL_OVERLAY`` overrides the default so a test or an
    operator can point at a different file without touching the checkout.
    """
    override = os.environ.get(ENV_OVERLAY_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return DEFAULT_OVERLAY_PATH


def load_overlay(path: Path | str | None = None) -> LocalOverlay:
    """Load and validate the local overlay, if the file exists.

    A missing file is not an error: it means the operator has no local
    overlay, so an empty one is returned. A present but malformed file --
    invalid JSON, a bad shape, or a forbidden field -- raises so the problem
    is visible instead of quietly ignored.
    """
    target = Path(path) if path is not None else overlay_path()
    if not target.exists():
        return LocalOverlay(providers={}, source=str(target))

    try:
        with open(target, encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise OverlayError(f"local overlay {target} is not valid JSON: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise OverlayError(f"local overlay {target} must be a JSON object")

    overlay = validate_overlay(payload)
    overlay.source = str(target)
    return overlay


def merge_local_overlay(
    catalog: Mapping[str, Any],
    overlay: LocalOverlay | Mapping[str, Any],
) -> dict[str, Any]:
    """Merge an overlay's operator facts into a catalog, deterministically.

    The catalog is copied, never mutated. For every provider the overlay
    names, its allowlisted operator fields are written into that provider's
    entry. The result is rebuilt with sorted provider ids and sorted keys so
    two runs over the same inputs produce byte-identical output, independent
    of the input's dict ordering.

    An overlay built from raw mappings is validated first, so a forbidden
    field raises :class:`OverlayRejectedError` here too rather than slipping
    through.
    """
    if not isinstance(overlay, LocalOverlay):
        overlay = validate_overlay(overlay)

    catalog_providers = catalog.get("providers")
    merged_providers: dict[str, Any] = {}
    if isinstance(catalog_providers, Mapping):
        for provider_id in sorted(catalog_providers):
            entry = catalog_providers[provider_id]
            merged_providers[provider_id] = dict(entry) if isinstance(entry, Mapping) else entry

    for provider_id in sorted(overlay.providers):
        operator_fields = overlay.providers[provider_id]
        existing = merged_providers.get(provider_id)
        if not isinstance(existing, Mapping):
            existing = {}
        # Guard again at merge time: even a hand-built LocalOverlay must not
        # smuggle a physical fact past validation.
        for field_name in operator_fields:
            if field_name not in OPERATOR_FIELDS:
                raise _reject(provider_id, field_name)
        merged = dict(existing)
        merged.update(operator_fields)
        merged_providers[provider_id] = merged

    result = dict(catalog)
    result["providers"] = merged_providers
    return result
