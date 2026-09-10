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
