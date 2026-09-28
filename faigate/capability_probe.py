"""Probe provider /models endpoints for capability facts.

Each provider exposes model metadata under its own /models endpoint, but
the field names for the same fact differ: byteplus uses
``token_limits.context_window``, deepseek uses ``context_window``,
openrouter uses ``context_length``, mistral uses ``max_context_length``,
and nvidia provides none.  The mapping from provider to field path lives
in the curated catalog so it can be updated without a code change.
"""

from __future__ import annotations

from typing import Any


def extract_context_window(models_data: dict[str, Any], field_path: str) -> int | None:
    """Extract a context window from a /models response using a dotted field path.

    ``field_path`` is a dotted path into the response, e.g.
    ``"token_limits.context_window"`` for BytePlus or ``"context_window"``
    for DeepSeek.  The function walks the path segment by segment and
    returns the integer value found at the leaf.
    """
    if not field_path or not isinstance(models_data, dict):
        return None

    # The standard /models response wraps model entries in a top-level
    # ``data`` array.  Navigate into the first entry; when there is no
    # such array, walk the path from the root of the given dict so that
    # simple test payloads work without the /models envelope.
    data_list = models_data.get("data")
    if isinstance(data_list, list) and data_list:
        current: Any = data_list[0]
    else:
        current = models_data

    segments = field_path.split(".")
    for segment in segments:
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None

    if isinstance(current, int) and not isinstance(current, bool):
        return current
    return None


def extract_model_lifecycles(
    models_data: dict[str, Any],
    status_field: str = "status",
) -> list[dict[str, Any]]:
    """Extract per-model lifecycle status from a /models response.

    Each model entry in the ``data`` array is scanned for its ``id`` and the
    field named by *status_field*.  When a model carries a ``versioned_id``
    that differs from its ``id``, both are recorded so callers can detect
    short-name/versioned-name divergence.

    Returns a list of lifecycle entries, one per model in the response.
    When the same short ``id`` appears multiple times (e.g., active and
    retiring variants of the same base model), each entry is separate so
    callers can detect the ambiguity.
    """
    if not isinstance(models_data, dict):
        return []

    data_list = models_data.get("data")
    if not isinstance(data_list, list):
        return []

    entries: list[dict[str, Any]] = []
    for entry in data_list:
        if not isinstance(entry, dict):
            continue
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            continue

        lifecycle: dict[str, Any] = {
            "model_id": model_id,
            "status": str(entry.get(status_field, "") or ""),
        }

        versioned_id = entry.get("versioned_id")
        if isinstance(versioned_id, str) and versioned_id and versioned_id != model_id:
            lifecycle["versioned_id"] = versioned_id

        entries.append(lifecycle)

    return entries
