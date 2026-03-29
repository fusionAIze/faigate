"""Optional request hook for Claude Code / Anthropic bridge traffic.

This hook is intentionally bounded: it only derives routing hints from bridge
metadata and headers. It does not perform protocol translation or provider
execution, and it stays optional via ``request_hooks.community_hooks_dir``.
"""

from __future__ import annotations

from typing import Any

from faigate.hooks import RequestHookContext, RequestHookResult

_DEFAULT_PROFILE = "coding-default"
_SUPPORTED_PROFILES = {"coding-default", "fast", "premium"}
_CLAUDE_SOURCES = {"claude", "claude-code", "anthropic"}


def register(register_hook, _register_provider=None) -> None:
    """Register the Claude Code routing hint hook."""

    register_hook("claude-code-router", _claude_code_router_hook)


def _claude_code_router_hook(context: RequestHookContext) -> RequestHookResult | None:
    metadata = _metadata(context.body)
    source = _normalized_source(metadata, context.headers)
    surface = _normalized_surface(metadata, context.headers)

    if source not in _CLAUDE_SOURCES and surface != "anthropic-messages":
        return None

    profile = _resolve_profile(metadata, context.headers)
    routing_hints = _profile_hints(profile)
    notes = [
        f"Claude Code router hook applied profile: {profile}",
        f"Bridge source: {source or 'unknown'}",
    ]
    if surface:
        notes.append(f"Bridge surface: {surface}")

    return RequestHookResult(routing_hints=routing_hints, notes=notes)


def _profile_hints(profile: str) -> dict[str, Any]:
    base = {
        "require_capabilities": ["tools"],
        "capability_values": {
            "tools": [True],
            "long_context": [True],
        },
    }

    if profile == "premium":
        return {
            **base,
            "prefer_tiers": ["reasoning", "default"],
            "routing_mode": "premium",
        }
    if profile == "fast":
        return {
            "require_capabilities": ["tools"],
            "capability_values": {"tools": [True]},
            "prefer_tiers": ["default", "cheap"],
            "routing_mode": "auto",
        }
    return {
        **base,
        "prefer_tiers": ["default", "reasoning"],
    }


def _resolve_profile(metadata: dict[str, Any], headers: dict[str, str]) -> str:
    for candidate in (
        metadata.get("claude_code_profile"),
        metadata.get("routing_profile"),
        headers.get("x-faigate-bridge-profile"),
    ):
        normalized = str(candidate or "").strip().lower()
        if normalized in _SUPPORTED_PROFILES:
            return normalized
    return _DEFAULT_PROFILE


def _normalized_source(metadata: dict[str, Any], headers: dict[str, str]) -> str:
    return str(
        metadata.get("source")
        or headers.get("x-faigate-client")
        or headers.get("anthropic-client")
        or ""
    ).strip().lower()


def _normalized_surface(metadata: dict[str, Any], headers: dict[str, str]) -> str:
    return str(
        metadata.get("bridge_surface")
        or metadata.get("surface")
        or headers.get("x-faigate-surface")
        or ""
    ).strip().lower()


def _metadata(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("metadata", {})
    return dict(value) if isinstance(value, dict) else {}

