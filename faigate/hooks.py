"""Optional request hook interfaces for pre-routing extensions."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import pathlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass
class RequestHookContext:
    """Mutable request context passed through the hook pipeline."""

    body: dict[str, Any]
    headers: dict[str, str]
    model_requested: str


@dataclass
class RequestHookResult:
    """One hook result with optional request and routing adjustments."""

    body_updates: dict[str, Any] = field(default_factory=dict)
    profile_override: str | None = None
    routing_hints: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class AppliedHooks:
    """Aggregated hook state used by the runtime."""

    body: dict[str, Any]
    profile_override: str | None = None
    routing_hints: dict[str, Any] = field(default_factory=dict)
    applied_hooks: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HookExecutionError(RuntimeError):
    """Raised when request hook execution is configured to fail closed."""


RequestHook = Callable[
    [RequestHookContext],
    RequestHookResult | Awaitable[RequestHookResult | None] | None,
]

_REQUEST_HOOKS: dict[str, RequestHook] = {}
_ALLOWED_BODY_UPDATE_KEYS = {
    "messages",
    "model",
    "tools",
    "tool_choice",
    "temperature",
    "max_tokens",
    "stream",
    "response_format",
    "metadata",
    "user",
}
_LIST_HINT_KEYS = {
    "allow_providers",
    "deny_providers",
    "prefer_providers",
    "prefer_tiers",
    "require_capabilities",
}


def register_request_hook(name: str, hook: RequestHook) -> None:
    """Register one named request hook."""
    _REQUEST_HOOKS[name] = hook


def get_registered_request_hooks() -> dict[str, RequestHook]:
    """Return the current hook registry."""
    return dict(_REQUEST_HOOKS)


async def apply_request_hooks(config: dict[str, Any], context: RequestHookContext) -> AppliedHooks:
    """Apply configured request hooks in order."""
    applied = AppliedHooks(body=dict(context.body))
    if not config.get("enabled"):
        return applied
    on_error = config.get("on_error", "continue")

    ctx = RequestHookContext(
        body=applied.body,
        headers=dict(context.headers),
        model_requested=context.model_requested,
    )

    for name in config.get("hooks", []):
        hook = _REQUEST_HOOKS.get(name)
        if hook is None:
            continue

        try:
            result = hook(ctx)
            if inspect.isawaitable(result):
                result = await result
            if not result:
                continue

            body_updates, body_warnings = _sanitize_body_updates(result.body_updates)
            if body_updates:
                ctx.body.update(body_updates)
            applied.notes.extend(body_warnings)

            if result.profile_override:
                profile_override = _sanitize_profile_override(result.profile_override)
                if profile_override:
                    applied.profile_override = profile_override
                else:
                    applied.errors.append(f"Hook '{name}' returned an invalid profile override")

            if result.routing_hints:
                sanitized_hints, hint_errors = _sanitize_routing_hints(result.routing_hints)
                if sanitized_hints:
                    _merge_routing_hints(applied.routing_hints, sanitized_hints)
                applied.errors.extend(f"Hook '{name}': {error}" for error in hint_errors)

            if result.notes:
                applied.notes.extend(result.notes)

            applied.body = dict(ctx.body)
            applied.applied_hooks.append(name)
        except Exception as exc:
            message = f"Hook '{name}' failed: {exc}"
            if on_error == "fail":
                raise HookExecutionError(message) from exc
            applied.errors.append(message)

    return applied


def _sanitize_body_updates(updates: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Keep request-body updates within a small, predictable surface."""
    if not updates:
        return {}, []
    if not isinstance(updates, dict):
        return {}, ["Ignored invalid hook body updates (expected a mapping)"]

    sanitized: dict[str, Any] = {}
    warnings: list[str] = []
    for key, value in updates.items():
        if key not in _ALLOWED_BODY_UPDATE_KEYS:
            warnings.append(f"Ignored unsupported hook body update field '{key}'")
            continue
        if key == "messages" and not isinstance(value, list):
            warnings.append("Ignored hook body update for 'messages' because it was not a list")
            continue
        if key in {"model", "tool_choice", "user"} and not isinstance(value, str):
            warnings.append(f"Ignored hook body update for '{key}' because it was not a string")
            continue
        if key in {"temperature"} and not isinstance(value, (int, float)):
            warnings.append(f"Ignored hook body update for '{key}' because it was not numeric")
            continue
        if key in {"max_tokens"} and (isinstance(value, bool) or not isinstance(value, int) or value <= 0):
            warnings.append("Ignored hook body update for 'max_tokens' because it was not a positive integer")
            continue
        if key == "stream" and not isinstance(value, bool):
            warnings.append("Ignored hook body update for 'stream' because it was not a boolean")
            continue
        if key in {"tools"} and not isinstance(value, list):
            warnings.append(f"Ignored hook body update for '{key}' because it was not a list")
            continue
        if key in {"response_format", "metadata"} and not isinstance(value, dict):
            warnings.append(f"Ignored hook body update for '{key}' because it was not a mapping")
            continue
        sanitized[key] = value
    return sanitized, warnings


def _sanitize_profile_override(profile_override: str) -> str | None:
    """Accept only simple, stable profile override names."""
    cleaned = profile_override.strip().lower()
    if not cleaned:
        return None
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    if any(ch not in allowed for ch in cleaned):
        return None
    return cleaned


def _sanitize_routing_hints(hints: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize hook-provided routing hints to the supported runtime surface."""
    if not isinstance(hints, dict):
        return {}, ["ignored invalid routing_hints (expected a mapping)"]

    sanitized: dict[str, Any] = {}
    errors: list[str] = []
    for key in _LIST_HINT_KEYS:
        if key not in hints:
            continue
        raw_values = hints[key]
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        normalized = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"ignored invalid value in routing_hints.{key}")
                continue
            normalized.append(value.strip())
        if normalized:
            sanitized[key] = normalized

    if "capability_values" in hints:
        raw_cap_values = hints["capability_values"]
        if not isinstance(raw_cap_values, dict):
            errors.append("ignored invalid routing_hints.capability_values (expected a mapping)")
        else:
            cap_values: dict[str, list[Any]] = {}
            for capability, raw_values in raw_cap_values.items():
                if not isinstance(capability, str) or not capability.strip():
                    errors.append("ignored invalid routing_hints capability name")
                    continue
                values = raw_values if isinstance(raw_values, list) else [raw_values]
                normalized_values = [
                    value
                    for value in values
                    if isinstance(value, (str, bool)) and (not isinstance(value, str) or value.strip())
                ]
                if normalized_values:
                    cap_values[capability.strip()] = normalized_values
                else:
                    errors.append(f"ignored invalid routing_hints.capability_values.{capability}")
            if cap_values:
                sanitized["capability_values"] = cap_values

    if "routing_mode" in hints:
        raw_mode = hints["routing_mode"]
        if isinstance(raw_mode, str) and raw_mode.strip():
            sanitized["routing_mode"] = raw_mode.strip().lower()
        else:
            errors.append("ignored invalid routing_hints.routing_mode (expected a non-empty string)")

    unknown = sorted(set(hints) - (_LIST_HINT_KEYS | {"capability_values", "routing_mode"}))
    for key in unknown:
        errors.append(f"ignored unsupported routing_hints field '{key}'")

    return sanitized, errors


def _merge_routing_hints(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    """Merge hook-provided routing hints using config-like semantics."""
    for key in _LIST_HINT_KEYS:
        if key not in incoming:
            continue
        target.setdefault(key, [])
        for value in incoming[key]:
            if value not in target[key]:
                target[key].append(value)

    if "capability_values" in incoming:
        target.setdefault("capability_values", {})
        for capability, values in incoming["capability_values"].items():
            target["capability_values"].setdefault(capability, [])
            for value in values:
                if value not in target["capability_values"][capability]:
                    target["capability_values"][capability].append(value)

    if "routing_mode" in incoming:
        target["routing_mode"] = incoming["routing_mode"]


def _hook_prefer_provider_header(context: RequestHookContext) -> RequestHookResult | None:
    """Respect explicit provider preferences from a request header."""
    raw = context.headers.get("x-faigate-prefer-provider", "").strip()
    if not raw:
        return None

    providers = [part.strip() for part in raw.split(",") if part.strip()]
    if not providers:
        return None

    return RequestHookResult(
        routing_hints={"prefer_providers": providers},
        notes=[f"Preferred provider header requested: {', '.join(providers)}"],
    )


def _hook_locality_header(context: RequestHookContext) -> RequestHookResult | None:
    """Request a local-only or cloud-only route from one header."""
    raw = context.headers.get("x-faigate-locality", "").strip().lower()
    if raw not in {"local", "local-only", "cloud", "cloud-only"}:
        return None

    if raw in {"local", "local-only"}:
        return RequestHookResult(
            routing_hints={
                "prefer_tiers": ["local"],
                "capability_values": {"local": [True], "cloud": [False]},
            },
            notes=["Locality hook requested local providers only"],
        )

    return RequestHookResult(
        routing_hints={
            "capability_values": {"cloud": [True], "local": [False]},
        },
        notes=["Locality hook requested cloud providers only"],
    )


def _hook_profile_override_header(context: RequestHookContext) -> RequestHookResult | None:
    """Override the resolved client profile for one request."""
    raw = context.headers.get("x-faigate-profile", "").strip().lower()
    if not raw:
        return None

    return RequestHookResult(
        profile_override=raw,
        notes=[f"Profile override hook requested profile: {raw}"],
    )


def _hook_mode_override_header(context: RequestHookContext) -> RequestHookResult | None:
    """Override the routing mode (posture) for one request via X-faigate-Mode header.

    Accepted values mirror the virtual routing modes defined in config.yaml:
    auto, eco, premium, free — plus common aliases (quality, save, cheap, balanced).
    Unknown values are silently ignored so misconfigured clients cannot break routing.
    """
    raw = context.headers.get("x-faigate-mode", "").strip().lower()
    if not raw:
        return None

    _KNOWN_MODE_ALIASES = {
        "auto",
        "eco",
        "premium",
        "free",
        # common aliases that _normalize_routing_posture already handles
        "quality",
        "save",
        "cheap",
        "balanced",
        "standard",
    }
    if raw not in _KNOWN_MODE_ALIASES:
        return None

    return RequestHookResult(
        routing_hints={"routing_mode": raw},
        notes=[f"Mode override hook set routing mode: {raw}"],
    )


register_request_hook("prefer-provider-header", _hook_prefer_provider_header)
register_request_hook("locality-header", _hook_locality_header)
register_request_hook("profile-override-header", _hook_profile_override_header)
register_request_hook("mode-override-header", _hook_mode_override_header)


# ── Community / plugin hook loader ──────────────────────────────────────────

_COMMUNITY_HOOKS_LOADED: list[str] = []
_VIRTUAL_PROVIDERS: dict[str, dict[str, Any]] = {}


def register_virtual_provider(name: str, config: dict[str, Any]) -> None:
    """Register a virtual provider from a community hook.

    Virtual providers are programmatically registered OpenAI-compatible
    endpoints that do not require a config.yaml entry.  They are merged
    into the live provider registry during gateway startup.

    Minimum required keys: ``base_url``, ``model``.
    Optional but recommended: ``tier``, ``capabilities``, ``lane``,
    ``pricing``, ``timeout``.
    """
    if not isinstance(config, dict):
        _logger.error("register_virtual_provider(%r): config must be a dict", name)
        return
    if not config.get("base_url") or not config.get("model"):
        _logger.error("register_virtual_provider(%r): requires at least base_url and model", name)
        return
    config.setdefault("backend", "openai-compat")
    config.setdefault("api_key", "virtual-provider-no-key")
    config.setdefault("tier", "mid")
    _VIRTUAL_PROVIDERS[name] = config
    _logger.info("Registered virtual provider: %s → %s", name, config.get("base_url"))


def get_virtual_providers() -> dict[str, dict[str, Any]]:
    """Return all virtual providers registered by community hooks."""
    return dict(_VIRTUAL_PROVIDERS)


def load_community_hooks(plugin_dir: str | None) -> list[str]:
    """Discover and register community hooks from a directory of Python files.

    Each ``.py`` file in *plugin_dir* must expose a top-level ``register``
    callable.  Two signatures are supported::

        # Hook-only (v1.10.0)
        def register(register_fn) -> None: ...

        # Hook + virtual provider (v1.10.1+)
        def register(register_fn, register_provider_fn) -> None: ...

    Files that do not expose ``register`` are silently skipped.

    Returns the list of successfully loaded filenames (e.g. ``["grok-wrapper.py"]``).
    """
    if not plugin_dir:
        return []

    path = pathlib.Path(plugin_dir).expanduser().resolve()
    if not path.is_dir():
        _logger.warning("community_hooks_dir %r is not a directory — skipping", str(plugin_dir))
        return []

    loaded: list[str] = []
    for py_file in sorted(path.glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"faigate_community_hook_{py_file.stem}", py_file)
            if spec is None or spec.loader is None:
                _logger.warning("Cannot load community hook %s — invalid spec", py_file.name)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            if not hasattr(module, "register"):
                _logger.warning("Community hook %s has no register() function — skipped", py_file.name)
                continue
            # Support optional second arg for virtual provider registration
            try:
                sig = inspect.signature(module.register)
                n_params = len(sig.parameters)
            except (ValueError, TypeError):
                n_params = 1
            if n_params >= 2:
                module.register(register_request_hook, register_virtual_provider)
            else:
                module.register(register_request_hook)
            loaded.append(py_file.name)
            _logger.info("Loaded community hook: %s", py_file.name)
        except Exception as exc:  # noqa: BLE001
            _logger.error("Failed to load community hook %s: %s", py_file.name, exc)

    _COMMUNITY_HOOKS_LOADED.extend(loaded)
    return loaded


def get_community_hooks_loaded() -> list[str]:
    """Return the list of successfully loaded community hook filenames."""
    return list(_COMMUNITY_HOOKS_LOADED)
