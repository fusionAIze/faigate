"""Model-identity derivation: short names, long forms, and alias resolution.

Every model the gateway can route has one canonical *long form* derived from
its split ``vendor`` / ``model`` identity fields (plus optional ``hop`` and
``variant``). That long form is what faigate returns to clients, writes to the
request log, and bills against. Nothing shorter is ever canonical.

Two convenience addresses are derived on top of the long form, neither of
which needs curation:

*   the **derived short name** — ``vendor/model`` (``hop`` and ``variant``
    dropped) — computed automatically from the identity fields;
*   **kuerzel aliases** — extra abbreviations such as ``ds`` or ``kc`` that
    resolve to the long form but must never surface in an answer, a log entry,
    or a billing record.

A catalog may declare a curated short name on an entry. A declared short name
takes precedence over the derived one. Ambiguity — a token that resolves to
more than one distinct identity — is reported as a candidate list and is never
silently collapsed onto one entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def join_identity_path(
    vendor: str,
    model: str,
    hop: list[str] | tuple[str, ...] | None = None,
    variant: str | None = None,
) -> str:
    """Build a canonical identity path from split fields.

    ``[hop/]...vendor/model[:variant]`` — the same trail
    ``faigate.registry.provider_identity`` produces, kept here so this module
    does not depend on the registry.
    """
    segments = [str(seg) for seg in (hop or []) if str(seg)]
    segments.append(str(vendor))
    segments.append(str(model))
    path = "/".join(segments)
    variant_text = str(variant or "").strip()
    if variant_text:
        path = f"{path}:{variant_text}"
    return path


def derive_short_name(vendor: str, model: str) -> str:
    """Return the default short name for an identity: ``vendor/model``.

    The derived short name needs no curation: it is a pure function of the
    ``vendor`` and ``model`` fields. A catalog-declared short name overrides it
    at resolution time, but is never required for an entry to be addressable.
    """
    return f"{str(vendor)}/{str(model)}"


@dataclass(frozen=True)
class ModelIdentity:
    """One resolvable model identity.

    ``long_form`` is the canonical string returned, logged, and billed.
    ``short_name`` is the effective short name (declared if present, otherwise
    derived). ``aliases`` are kuerzel that resolve to ``long_form`` but are
    never canonical.
    """

    long_form: str
    vendor: str
    model: str
    hop: tuple[str, ...] = field(default_factory=tuple)
    variant: str = ""
    short_name: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_fields(
        cls,
        vendor: str,
        model: str,
        hop: list[str] | tuple[str, ...] | None = None,
        variant: str | None = None,
        short_name: str | None = None,
        aliases: list[str] | tuple[str, ...] | None = None,
    ) -> ModelIdentity:
        hops = tuple(str(seg) for seg in (hop or []) if str(seg))
        variant_text = str(variant or "").strip()
        long_form = join_identity_path(vendor, model, hops, variant_text)
        return cls(
            long_form=long_form,
            vendor=str(vendor),
            model=str(model),
            hop=hops,
            variant=variant_text,
            short_name=str(short_name).strip() if short_name else None,
            aliases=tuple(str(alias).strip() for alias in (aliases or []) if str(alias).strip()),
        )

    @property
    def effective_short_name(self) -> str:
        """The short name that addresses this identity: declared or derived."""
        if self.short_name:
            return self.short_name
        return derive_short_name(self.vendor, self.model)


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving a requested token against a set of identities.

    Exactly one of ``identity`` / ``ambiguous`` / ``unknown`` is meaningful:
    ``identity`` is set on an unambiguous hit, ``ambiguous`` carries the
    candidate long forms when a token matches more than one identity, and both
    are empty when the token is unknown.
    """

    identity: ModelIdentity | None = None
    ambiguous: tuple[str, ...] = field(default_factory=tuple)
    unknown: bool = False

    @classmethod
    def resolved(cls, identity: ModelIdentity) -> Resolution:
        return cls(identity=identity)

    @classmethod
    def conflict(cls, candidates: list[str]) -> Resolution:
        return cls(ambiguous=tuple(sorted(candidates)))

    @classmethod
    def not_found(cls) -> Resolution:
        return cls(unknown=True)


def _normalize(token: Any) -> str:
    return str(token or "").strip().lower()


class ModelIdentityResolver:
    """Resolve requested tokens against a set of model identities.

    Precedence, highest first:

    1. exact long form,
    2. declared short name,
    3. derived short name,
    4. kuerzel aliases.

    A token that lands in more than one distinct identity is ambiguous and is
    reported as a candidate list — never silently resolved. A token that lands
    in nothing is unknown.
    """

    def __init__(self, identities: list[ModelIdentity]) -> None:
        self._identities = list(identities)
        self._by_long: dict[str, ModelIdentity] = {}
        self._by_token: dict[str, list[ModelIdentity]] = {}
        for identity in self._identities:
            self._by_long[_normalize(identity.long_form)] = identity
            self._add_token(_normalize(identity.long_form), identity)
            self._add_token(_normalize(identity.effective_short_name), identity)
            if identity.short_name:
                self._add_token(_normalize(identity.short_name), identity)
            for alias in identity.aliases:
                self._add_token(_normalize(alias), identity)

    def _add_token(self, token: str, identity: ModelIdentity) -> None:
        if not token:
            return
        bucket = self._by_token.setdefault(token, [])
        if identity not in bucket:
            bucket.append(identity)

    def resolve(self, requested: Any) -> Resolution:
        token = _normalize(requested)
        if not token:
            return Resolution.not_found()

        exact = self._by_long.get(token)
        if exact is not None:
            return Resolution.resolved(exact)

        bucket = self._by_token.get(token, [])
        if not bucket:
            return Resolution.not_found()
        if len(bucket) == 1:
            return Resolution.resolved(bucket[0])
        return Resolution.conflict([identity.long_form for identity in bucket])

    def long_forms(self) -> list[str]:
        """Return the canonical long forms, in declaration order."""
        return [identity.long_form for identity in self._identities]


# ── Unknown-kind vocabulary (FAI-251) ────────────────────────────────
#
# When a name cannot be classified as provider-bound or intent it is
# *unknown*.  The kind explains why:
#
#   derivable          Classification is derivable from available data but
#                      not yet implemented.
#   not_applicable     The entry's source markers do not fit the
#                      classification scheme (e.g. a contract entry whose
#                      name is not in the configured provider set).
#   runtime_dependent  Classification depends on runtime state that is not
#                      available at list-building time.
#   unlisted           The entry carries a source marker this function does
#                      not recognise.
#
# ``not_applicable`` is the reachable kind: the ``contract`` branch returns
# it when an entry claims a provider that is not configured, and the
# fallthrough returns it when an entry carries no recognised source marker
# at all.  The other three kinds are vocabulary the guard can grow into
# without changing the return signature.

UNKNOWN_KIND_DERIVABLE = "derivable"
UNKNOWN_KIND_NOT_APPLICABLE = "not_applicable"
UNKNOWN_KIND_RUNTIME_DEPENDENT = "runtime_dependent"
UNKNOWN_KIND_UNLISTED = "unlisted"


def classify_entry_binding(
    offered_name: str,
    entry: dict[str, Any],
    configured_providers: set[str],
) -> tuple[str, str | None]:
    """Classify an offered model entry as ``provider-bound``, ``intent``, or ``unknown``.

    A name is *provider-bound* when it names exactly one configured provider
    backend — the entry then carries that provider name.  A name is *intent*
    when it routes by policy and does not name a specific provider.  A name
    that is neither is *unknown* and must not be advertised.

    Classification is total: every entry either names a provider, is one of
    the recognised policy sources (mode, catalog, static rule, shortcut, or
    the ``auto`` selector), or is unknown.  There is no markerless default
    that silently advertises as intent.

    Parameters
    ----------
    offered_name:
        The name as it appears in the offered model list (the entry key).
    entry:
        The entry dict produced by ``_routable_model_entries``.  Source
        markers (``mode``, ``catalog``, ``static_rule``, ``shortcut``,
        ``contract``) determine the classification strategy.
    configured_providers:
        Set of configured provider backend names.

    Returns
    -------
    ``("provider-bound", provider_name)``, ``("intent", None)``, or
    ``("unknown", kind)`` where *kind* is one of the ``UNKNOWN_KIND_*``
    constants.
    """
    # Modes are always intent — they express routing policy, not a provider.
    if entry.get("mode"):
        return "intent", None

    # Catalog identities describe a model, not a configured backend.
    if entry.get("catalog"):
        return "intent", None

    # Static rules and shortcuts: if the offered name itself IS a configured
    # provider, it is provider-bound to that provider.  Otherwise the name
    # is an intent label (e.g. "chat", "flash") that routes through a rule.
    #
    # In production the provider-bound branch here is unreachable because
    # ``_routable_model_entries`` claims provider names via ``contract``
    # before any static rule or shortcut can claim them.  The branch is
    # correct by construction and is exercised by unit tests; removing it
    # would make the function silently wrong if the claim order ever changes.
    if entry.get("static_rule") or entry.get("shortcut"):
        normalized = offered_name.strip().lower()
        if normalized in configured_providers:
            return "provider-bound", normalized
        return "intent", None

    # Provider backend entries: the offered name IS the provider name.
    if entry.get("contract"):
        normalized = offered_name.strip().lower()
        # openai-codex-spark: a configured provider that the
        # "explicit-codex-mini" static rule claims before the named-provider
        # layer can route it.  The name demonstrably does not route to
        # exactly one provider, so it is intent, not provider-bound.
        # Tracked in FAI-242 (static-rule conflict).
        if normalized == "openai-codex-spark":
            return "intent", None
        if normalized in configured_providers:
            return "provider-bound", normalized
        # A contract entry whose name is not in the configured set is a
        # configuration error — the entry claims a provider that does not
        # exist.  Classify as unknown so the gateway never advertises it.
        return "unknown", UNKNOWN_KIND_NOT_APPLICABLE

    # The virtual ``auto`` selector routes by policy, never to a named
    # provider — it is intent.  It is the one entry with no source marker,
    # so it must be named here rather than left to the fallthrough.
    if offered_name.strip().lower() == "auto":
        return "intent", None

    # Fallthrough: the entry carries no source marker this function
    # recognises, so nothing establishes that it binds to exactly one
    # provider.  Before FAI-251 this returned ``intent``, which advertised
    # an unclassifiable name as if it were a policy label — the silent
    # third kind the invariant forbids.  Classify as unknown so
    # ``_routable_model_entries`` drops it instead of offering it.
    return "unknown", UNKNOWN_KIND_NOT_APPLICABLE


def catalog_model_identities() -> list[ModelIdentity]:
    """Build model identities from the catalog, with ``registry.ALL`` fallback.

    This is the single source of truth for "what the gateway can address": the
    catalog carries the split ``vendor`` / ``model`` (plus optional ``hop`` /
    ``variant``) fields, and ``registry.ALL`` covers the offline case (no catalog
    at all) and any identity the catalog omits. Identity resolution — the
    resolver that answers "does this requested token name a known model" — and
    the routing gate that accepts or rejects a request must both call this same
    function, so the two can never drift onto different sources.

    Order is catalog first, then ``registry.ALL``. A long form is deduplicated
    so a provider present in both sources contributes exactly one identity.
    """
    from . import registry
    from .provider_catalog import catalog_provider_identities

    identities: list[ModelIdentity] = []
    seen: set[str] = set()

    def _add(vendor: str, model: str, hop: list[str] | None, variant: str | None) -> None:
        identity = ModelIdentity.from_fields(
            vendor=vendor,
            model=model,
            hop=hop,
            variant=variant,
        )
        key = identity.long_form.lower()
        if key in seen:
            return
        seen.add(key)
        identities.append(identity)

    for fields in catalog_provider_identities():
        _add(fields["vendor"], fields["model"], fields["hop"], fields["variant"] or None)

    for name in registry.known_names():
        identity = registry.provider_identity(name)
        if identity is None:
            continue
        vendor, model, _long_form = identity
        entry = registry.ALL.get(name) or {}
        _add(vendor, model, entry.get("hop") or [], entry.get("variant"))

    return identities
