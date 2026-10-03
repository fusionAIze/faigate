"""Runtime-resolved alias tests.

A model name that the provider resolves at runtime (e.g. ``*-latest``)
cannot carry stable catalog facts because the underlying model can change
without notice.  The catalog is not responsible for such identifiers — it
cannot be ignorant of them either, because ignorance assumes knowability.
"""

from faigate.provider_catalog import get_provider_catalog
from faigate.reachability import model_is_concrete
from faigate.registry import ALL as PROVIDERS
from faigate.registry import is_runtime_dependent_model

# The four defined unknown_kind values (must match provider_catalog.py).
_VALID_UNKNOWN_KINDS = frozenset({"derivable", "not_applicable", "runtime_dependent", "unlisted"})


# ---------------------------------------------------------------------------
# Criterion 1: runtime_dependent is one of the four defined unknown_kinds
# ---------------------------------------------------------------------------


def test_runtime_dependent_is_valid_unknown_kind() -> None:
    """Criterion 1: runtime_dependent is one of the four defined unknown_kinds."""
    assert "runtime_dependent" in _VALID_UNKNOWN_KINDS, (
        "runtime_dependent is not in _VALID_UNKNOWN_KINDS — criterion 1 requires it as one of the four unknown kinds"
    )


def test_is_runtime_dependent_model_detects_latest() -> None:
    """``is_runtime_dependent_model`` detects ``latest`` suffix patterns."""
    assert is_runtime_dependent_model("ark-code-latest"), "ark-code-latest should be runtime-dependent"
    assert is_runtime_dependent_model("mistral-large-latest"), "mistral-large-latest should be runtime-dependent"
    # Concrete model names must not be flagged.
    assert not is_runtime_dependent_model("deepseek-v4-flash"), "deepseek-v4-flash is concrete, not runtime-dependent"
    assert not is_runtime_dependent_model("gpt-4o"), "gpt-4o is concrete, not runtime-dependent"
    assert not is_runtime_dependent_model("claude-opus-4-6"), "claude-opus-4-6 is concrete, not runtime-dependent"


# ---------------------------------------------------------------------------
# Criterion 2: No catalog facts for runtime-dependent identifiers
# ---------------------------------------------------------------------------


def test_at_least_one_runtime_dependent_entry() -> None:
    """Guard: no runtime-dependent entries means the check has nothing to verify.

    Without this guard, an empty candidate set would make every assertion
    below pass trivially.
    """
    catalog = get_provider_catalog()
    runtime_dep_entries = [
        (pid, entry) for pid, entry in catalog.items() if not model_is_concrete(str(entry.get("model") or ""))
    ]
    assert runtime_dep_entries, (
        "no catalog entries have runtime-dependent model names — the check has nothing to verify"
    )


def test_runtime_dependent_entry_has_unknown_kind_runtime_dependent() -> None:
    """Criterion 2: runtime-dependent entries carry unknown_kind runtime_dependent.

    A runtime-dependent model name means the catalog is not responsible
    for window, pricing, or capability facts about the identifier.  The
    ``context_evidence.unknown_kind`` must be ``"runtime_dependent"``.
    """
    catalog = get_provider_catalog()
    failures: list[tuple[str, str, str]] = []
    for provider_id, entry in sorted(catalog.items()):
        model = str(entry.get("model") or "")
        if not model or model_is_concrete(model):
            continue
        ctx_evidence = entry.get("context_evidence") or {}
        unknown_kind = str(ctx_evidence.get("unknown_kind") or "")
        if unknown_kind != "runtime_dependent":
            failures.append((provider_id, model, unknown_kind))

    assert not failures, (
        "runtime-dependent model entries must have "
        "context_evidence.unknown_kind='runtime_dependent':\n"
        + "\n".join(f"  {pid}: model={m!r}, unknown_kind={k!r}" for pid, m, k in failures)
    )


# ---------------------------------------------------------------------------
# Criterion 3: Runtime-dependent identifiers can be wiring targets
# ---------------------------------------------------------------------------


def test_runtime_dependent_as_example_model_is_valid() -> None:
    """Criterion 3: Runtime-dependent models can be wiring targets.

    ``example_model`` (or ``recommended_model``) is a wiring decision, not
    a property claim.  Having a runtime-dependent identifier as the example
    model is valid and does not break the registry.
    """
    for name, entry in PROVIDERS.items():
        model = entry.get("model", "")
        if is_runtime_dependent_model(model):
            # The registry entry points to a runtime-dependent model as its
            # wiring target.  This is valid — it documents the recommended
            # model without claiming catalog facts about it.
            assert isinstance(entry.get("vendor"), str), f"{name}: runtime-dependent model {model!r} must have a vendor"


# ---------------------------------------------------------------------------
# Criterion 4: Runtime-dependent entries carrying facts must have unknown_reason
# ---------------------------------------------------------------------------


def test_runtime_dependent_with_facts_has_unknown_reason() -> None:
    """Criterion 4: runtime-dependent entries carrying catalog facts need unknown_reason.

    If a runtime-dependent identifier carries window, pricing, or other
    catalog facts, there must be a named ``unknown_reason`` explaining why.
    """
    catalog = get_provider_catalog()
    failures: list[str] = []
    for provider_id, entry in sorted(catalog.items()):
        model = str(entry.get("model") or "")
        if not model or model_is_concrete(model):
            continue
        ctx_evidence = entry.get("context_evidence") or {}
        unknown_kind = str(ctx_evidence.get("unknown_kind") or "")
        if unknown_kind != "runtime_dependent":
            continue
        # Does this entry carry any catalog fact?
        has_facts = entry.get("context_window") is not None or entry.get("pricing") is not None
        if has_facts:
            unknown_reason = str(ctx_evidence.get("unknown_reason") or "")
            if not unknown_reason:
                failures.append(provider_id)

    assert not failures, (
        "runtime-dependent entries carrying catalog facts must have "
        "context_evidence.unknown_reason:\n" + "\n".join(f"  {f}" for f in failures)
    )


# ---------------------------------------------------------------------------
# Criterion 5: The check is explicitly documented as a string-pattern heuristic
# ---------------------------------------------------------------------------


def test_is_runtime_dependent_model_documented_as_heuristic() -> None:
    """Criterion 5: ``is_runtime_dependent_model`` is documented as a heuristic.

    The docstring must explicitly state that this is a heuristic on string
    patterns — it forces a judgment, not replaces one.
    """
    doc = is_runtime_dependent_model.__doc__ or ""
    assert "heuristic" in doc.lower(), "is_runtime_dependent_model docstring must mention 'heuristic'"
    assert "string" in doc.lower() or "pattern" in doc.lower(), (
        "is_runtime_dependent_model docstring must mention string or pattern matching"
    )
