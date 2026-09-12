"""One entrance, two answers: the router must not enforce an unconfirmed cap.

``faigate/catalog_views.py`` promises that an ``unconfirmed`` fact is
"invisible to the router, the capacity calculator, and error output". The
error-output half of that promise is pinned by ``test_evidence_gating.py``.
These tests pin the routing half.

The routing decision reads a single entrance, ``get_model_max_input_tokens``:
``Router._provider_fits_request_dimensions`` lets it *override* the
provider-wide ``limits.max_input_tokens`` floor, and
``Router._provider_dimension_details`` lets it drive the input-headroom score.
If that entrance answers with a number for a cap whose own evidence says
``unconfirmed``, the router enforces a fact the splitter deliberately hides and
the docstring is false. When it answers ``None`` instead, both call sites fall
back to the operator's provider-level limits — the properties asserted here.

The fixtures are derived from the live catalog rather than a name list: any
entry that is later recorded (or downgraded) as ``unconfirmed`` is picked up
automatically, so a new entry cannot slip past.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faigate import provider_catalog
from faigate.catalog_resolver import suppressed_bundled_snapshot
from faigate.config import load_config
from faigate.router import Router, RoutingDecision

# --------------------------------------------------------------------------- #
# Fixtures built from the live catalog, not from a name list
# --------------------------------------------------------------------------- #


def _reset_catalog_caches() -> None:
    provider_catalog._EXTERNAL_CATALOG_CACHE = None
    provider_catalog._EXTERNAL_CATALOG_MTIME = 0.0


def _catalog_model_caps() -> dict:
    """Return the ``model_caps`` block the runtime actually resolves.

    Resolved through the production chain, so the fixtures below describe the
    catalog the router really reads — not a hand-copied name list that drifts
    the moment an entry is added or re-levelled.
    """
    return provider_catalog._load_external_model_caps()


def _unconfirmed_cap_entries() -> list[tuple[str, int]]:
    """Every ``(model_id, cap)`` the catalog records as ``unconfirmed``."""
    return [
        (model_id, int(fact["max_input_tokens"]))
        for model_id, fact in _catalog_model_caps().items()
        if isinstance(fact, dict)
        and isinstance(fact.get("max_input_tokens"), int)
        and (fact.get("evidence") or {}).get("level") == "unconfirmed"
    ]


def _write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(body)
    return path


def _router_with(provider_model: str) -> Router:
    """A one-provider router whose provider floor conflicts with the model cap.

    The provider carries a deliberately cramped operator floor (``4096``), so a
    request of a whole unconfirmed-cap worth of tokens only fits the provider
    when the router substitutes that cap for the floor. If the cap is
    evidence-gated away, the operator floor governs and the provider no longer
    fits — which is exactly the observable difference this file measures.
    """
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    cfg = load_config(
        _write_config(
            tmp,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cramped:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "{provider_model}"
    tier: default
    context_window: 10000000
    limits:
      max_input_tokens: 4096
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    return Router(cfg)


# --------------------------------------------------------------------------- #
# The docstring promise, asserted at the entrance
# --------------------------------------------------------------------------- #


def test_every_unconfirmed_cap_is_invisible_to_the_cap_lookup() -> None:
    """Every ``unconfirmed`` catalog cap resolves to ``None``, not its number.

    Fails on the base commit, where the lookup read the ``model_caps`` block
    without consulting evidence and returned a number for all of them.
    """
    entries = _unconfirmed_cap_entries()

    # If the catalog ever stops recording unconfirmed caps this assertion is the
    # honest signal that the test has lost its subject — not a silent pass.
    assert entries, "catalog records no unconfirmed model_caps entry to gate"

    offenders = []
    for model_id, cap in entries:
        resolved = provider_catalog.get_model_max_input_tokens(model_id)
        fact = provider_catalog.get_model_input_cap_fact(model_id)
        if resolved is not None:
            offenders.append(
                f"{model_id}: get_model_max_input_tokens returned {resolved} "
                f"for an unconfirmed cap of {cap} (fact={fact!r})"
            )

    assert not offenders, (
        "the router-facing cap lookup enforced caps the catalog marks "
        "unconfirmed, contradicting catalog_views.split_catalog_facts:\n  "
        + "\n  ".join(offenders)
    )


def test_prefixed_and_bare_spellings_of_every_unconfirmed_cap_agree() -> None:
    """The ``provider/<model>`` spelling is gated exactly like the bare id."""
    offenders = []
    for model_id, cap in _unconfirmed_cap_entries():
        for spelling in (model_id, f"provider/{model_id}"):
            resolved = provider_catalog.get_model_max_input_tokens(spelling)
            if resolved is not None:
                offenders.append(f"{spelling}: returned {resolved} (cap {cap})")

    assert not offenders, "unconfirmed caps leaked through a lookup spelling:\n  " + "\n  ".join(offenders)


def test_confirmed_caps_are_still_enforceable() -> None:
    """The gate must not blind the router to *confirmed* caps.

    This is the control for the tests above: the fix has to be evidence-gating,
    not a blanket ``return None``.
    """
    confirmed = [
        (model_id, int(fact["max_input_tokens"]))
        for model_id, fact in _catalog_model_caps().items()
        if isinstance(fact, dict)
        and isinstance(fact.get("max_input_tokens"), int)
        and (fact.get("evidence") or {}).get("level") == "confirmed"
    ]

    assert confirmed, "catalog records no confirmed model_caps entry"

    for model_id, cap in confirmed:
        assert provider_catalog.get_model_max_input_tokens(model_id) == cap, (
            f"confirmed cap for {model_id} must stay enforceable"
        )


# --------------------------------------------------------------------------- #
# The routing consequence: the operator floor governs again
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_unconfirmed_cap_no_longer_overrides_the_provider_floor(tmp_path) -> None:
    """Routing falls back to the provider limit, not to an unconfirmed cap.

    On the base commit the cramped provider was judged to fit because its 4096
    floor was replaced by the large unconfirmed model cap; the router then sent
    a request far above what the operator configured. After the fix the floor
    governs again and the provider is correctly judged unfit.
    """
    entries = _unconfirmed_cap_entries()
    assert entries, "catalog records no unconfirmed model_caps entry to gate"

    for model_id, cap in entries:
        assert cap > 4096, f"fixture assumes an unconfirmed cap above the 4096 floor ({model_id})"

        router = _router_with(model_id)
        runner = getattr(router, "_provider_fits_request_dimensions")
        ctx = _minimal_ctx(router, model_id, total_tokens=cap)

        assert runner("cramped", router.config.provider("cramped") or {}, ctx) is False, (
            f"provider floor 4096 was overridden by the unconfirmed cap {cap} of {model_id}"
        )


def _minimal_ctx(router: Router, model_requested: str, *, total_tokens: int):
    """Build a routing context carrying only the token shape under test."""
    from faigate.router import _RoutingContext

    return _RoutingContext(
        system_prompt="",
        last_user_message="",
        full_text="",
        total_tokens=total_tokens,
        stable_prefix_tokens=0,
        requested_output_tokens=0,
        total_requested_tokens=total_tokens,
        requested_image_outputs=0,
        requested_image_side_px=0,
        requested_image_size="",
        requested_image_policy="",
        required_capability="",
        cache_preference="",
        model_requested=model_requested,
        has_tools=False,
        client_profile="",
        profile_hints={},
        hook_hints={},
        applied_hooks=[],
        headers={},
        provider_health={},
        provider_runtime_state={},
        providers=dict(router.config.providers),
        request_insights={},
    )


@pytest.mark.asyncio
async def test_no_model_cap_falls_back_to_provider_limits(tmp_path) -> None:
    """When no enforceable cap exists the provider's own limits decide.

    Runs the same shaped request twice: once against a cramped provider and
    once against a roomy one, with a model id the catalog does not describe.
    The outcome must be decided by the provider configuration alone — the
    cramped provider rejects, the roomy provider accepts. Nothing silently
    changes because a cap lookup came back empty.
    """
    absent_model = "__no_catalog_entry__"
    assert provider_catalog.get_model_max_input_tokens(absent_model) is None

    cfg = load_config(
        _write_config(
            tmp_path,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cramped:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "{absent_model}"
    tier: default
    context_window: 10000000
    limits:
      max_input_tokens: 4096
  roomy:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "{absent_model}"
    tier: default
    context_window: 10000000
    limits:
      max_input_tokens: 1048576
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain: []
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    ctx = _minimal_ctx(router, absent_model, total_tokens=262144)

    assert router._provider_fits_request_dimensions("cramped", cfg.provider("cramped") or {}, ctx) is False
    assert router._provider_fits_request_dimensions("roomy", cfg.provider("roomy") or {}, ctx) is True


@pytest.mark.asyncio
async def test_gated_cap_leaves_the_fallback_walk_intact(tmp_path) -> None:
    """A gated-away cap makes the unfit primary fall through, not stall.

    This is the end-to-end consequence of returning ``None``: the primary is
    now judged unfit (its 4096 floor governs), the chain is walked, and a
    healthy fallback that still fits is selected. The empty cap must not leave
    the request pinned to a provider that cannot serve it — that would be the
    new silent behaviour the change has to avoid.
    """
    entries = _unconfirmed_cap_entries()
    assert entries, "catalog records no unconfirmed model_caps entry to gate"
    model_id, cap = entries[0]

    cfg = load_config(
        _write_config(
            tmp_path,
            f"""
server:
  host: "127.0.0.1"
  port: 8090
providers:
  cramped:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "{model_id}"
    tier: default
    context_window: 10000000
    limits:
      max_input_tokens: 4096
  roomy:
    backend: openai-compat
    base_url: "https://api.example.com/v1"
    api_key: "secret"
    model: "{model_id}"
    tier: default
    context_window: 10000000
    limits:
      max_input_tokens: 1048576
static_rules:
  enabled: false
  rules: []
heuristic_rules:
  enabled: false
  rules: []
fallback_chain:
  - roomy
metrics:
  enabled: false
""",
        )
    )
    router = Router(cfg)
    ctx = _minimal_ctx(router, model_id, total_tokens=cap)

    decision = RoutingDecision(
        provider_name="cramped",
        layer="heuristic",
        rule_name="pinned-primary",
        confidence=1.0,
        reason="primary chosen",
    )
    resolved = router._validate_health(decision, ctx)

    assert resolved.provider_name == "roomy", (
        f"an unfit primary with a gated cap {cap} for {model_id} was not "
        f"replaced by the fitting fallback (got {resolved.provider_name!r})"
    )
    assert "fallback" in resolved.rule_name


def test_docstring_promise_holds_at_the_entrance() -> None:
    """A name-free sweep: no view-hidden cap is answered by the router entrance."""
    with suppressed_bundled_snapshot():
        _reset_catalog_caches()
        caps = provider_catalog._load_external_model_caps()
        hidden = [
            model_id
            for model_id, fact in caps.items()
            if isinstance(fact, dict)
            and (fact.get("evidence") or {}).get("level") not in ("confirmed", None)
            and provider_catalog.get_model_max_input_tokens(model_id) is not None
        ]
    _reset_catalog_caches()

    assert not hidden, f"caps outside the enforceable view were answered: {hidden}"
