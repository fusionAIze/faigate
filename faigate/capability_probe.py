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
