"""A plan offer is a separate billing surface, so it needs a separate endpoint.

BytePlus bills the same API key differently depending on the path: requests to
``/api/coding/v3`` are covered by the coding plan, requests to ``/api/v3`` are
billed per token. Measured on 2026-09-23 against a live coding-plan key:

* ``/api/coding/v3`` answers 200 for the eight plan models and refuses every
  other model with ``UnsupportedModel`` instead of silently billing it.
* ``https://api.byteplus.com/api/v3`` -- the value both entries shipped --
  answers 302 and redirects to ``/api-explorer/...``, a documentation page,
  not an API.
* ``ark-code-latest`` -- the model the plan entry shipped -- answers 404 on the
  plain path and ``UnsupportedModel`` on the coding path.

If a plan entry and its pay-per-token sibling share one ``base_url``, the plan
is not reachable at all. If they share one ``base_url_env``, an operator who
overrides the endpoint for one of them silently moves the other onto the same
billing surface. Both are the same failure: one signal, two meanings.
"""

import pytest

from faigate.registry import ALL as PROVIDERS

# Volcano Engine carries the same structural defect, but no account was
# available to measure its plan endpoint, and inventing a path would be exactly
# the guess this test exists to prevent. Remove the entry once measured.
UNMEASURED = {"volcengine-plan"}

PLAN_SUFFIX = "-plan"


def _plan_pairs() -> list[tuple[str, str]]:
    pairs = []
    for name in PROVIDERS:
        if not name.endswith(PLAN_SUFFIX):
            continue
        sibling = name[: -len(PLAN_SUFFIX)]
        if sibling in PROVIDERS:
            pairs.append((name, sibling))
    return sorted(pairs)


def test_there_is_at_least_one_measured_plan_pair() -> None:
    # Without this the tests below would pass on an empty or fully skipped list.
    measured = [p for p, _ in _plan_pairs() if p not in UNMEASURED]
    assert measured, "no measured '<name>' / '<name>-plan' pair left to check"


@pytest.mark.parametrize("plan,payg", _plan_pairs())
def test_plan_endpoint_differs_from_pay_per_token_endpoint(plan: str, payg: str) -> None:
    if plan in UNMEASURED:
        pytest.skip(f"{plan}: plan endpoint not measured, see UNMEASURED")
    assert PROVIDERS[plan]["base_url"] != PROVIDERS[payg]["base_url"], (
        f"{plan} and {payg} share one base_url, so the plan endpoint is unreachable"
    )
    assert PROVIDERS[plan]["base_url_env"] != PROVIDERS[payg]["base_url_env"], (
        f"{plan} and {payg} share one base_url override variable, so overriding "
        f"either one moves both onto the same billing surface"
    )


@pytest.mark.parametrize("plan,payg", _plan_pairs())
def test_plan_model_is_not_a_provider_resolved_alias(plan: str, payg: str) -> None:
    if plan in UNMEASURED:
        pytest.skip(f"{plan}: plan models not measured, see UNMEASURED")
    # An alias the provider resolves server-side (BytePlus calls this "Auto")
    # carries no stable facts: its context window, price and capabilities change
    # underneath the catalog without any signal. It also did not resolve at all.
    model = PROVIDERS[plan]["model"]
    assert "latest" not in model, (
        f"{plan} points at '{model}', an alias the provider resolves at its own "
        f"discretion; the catalog cannot hold facts about it"
    )
