"""Dashboard settings — persisted under ``dashboard.quotas`` in config.yaml.

The operator's config is a human-authored file (48kb+ with ~220 comment
lines in the reference install). Writing through ``yaml.safe_dump`` would
flatten all of that, so we round-trip through ``ruamel.yaml`` which
preserves comments, key order, and block/flow style.

Scope is intentionally narrow: one nested block (``dashboard.quotas``)
with two keys:

- ``default_view``: ``"overview"`` (the grid) | ``"brand:<slug>"`` (a
  specific detail page) | ``"cockpit"`` (deep-link out).
- ``pinned_brand_slug``: redundant echo of the ``brand:<slug>`` target
  so UI can tell "which card is currently pinned" without re-parsing
  the default_view string.

Reads are cheap (safe_load-style) and happen on every request. Writes
go through a POSIX atomic rename so a crash mid-write can't leave the
operator with a half-written config.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Allowed shapes for ``default_view``. ``brand:<slug>`` is validated
# separately (any non-empty slug matching ``[a-z0-9-]+`` is accepted).
_ALLOWED_FIXED_VIEWS = {"overview", "cockpit"}


def _config_path() -> Path:
    """Resolve the same config.yaml path used by the rest of faigate."""
    env_path = os.environ.get("FAIGATE_CONFIG_FILE") or os.environ.get("FAIGATE_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    candidates = [
        Path(__file__).resolve().parent.parent / "config.yaml",
        Path.cwd() / "config.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("config.yaml not found")


def _slug_is_valid(value: str) -> bool:
    if not value:
        return False
    for ch in value:
        if not (ch.isdigit() or ("a" <= ch <= "z") or ch == "-"):
            return False
    return True


def validate_default_view(value: str) -> str:
    """Return the canonical form or raise ``ValueError``."""
    candidate = (value or "").strip().lower()
    if candidate in _ALLOWED_FIXED_VIEWS:
        return candidate
    if candidate.startswith("brand:"):
        slug = candidate[len("brand:") :]
        if _slug_is_valid(slug):
            return f"brand:{slug}"
    raise ValueError(f"default_view must be 'overview', 'cockpit', or 'brand:<slug>' — got {value!r}")


def get_settings(path: str | Path | None = None) -> dict[str, Any]:
    """Return the ``dashboard.quotas`` block (or the empty defaults)."""
    resolved = Path(path) if path else _config_path()
    if not resolved.exists():
        return _default_settings()
    # Use ruamel.yaml for reads too so we stay consistent with the writer
    # (the main app still reads via pyyaml in config.py — that's fine,
    # these two paths never produce config objects that feed each other).
    from ruamel.yaml import YAML

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    try:
        with resolved.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle) or {}
    except Exception as exc:  # noqa: BLE001 — any parse failure → defaults
        logger.warning("dashboard_settings: failed to parse %s: %s", resolved, exc)
        return _default_settings()
    dashboard = data.get("dashboard") if isinstance(data, dict) else None
    quotas = dashboard.get("quotas") if isinstance(dashboard, dict) else None
    if not isinstance(quotas, dict):
        return _default_settings()
    default_view = str(quotas.get("default_view") or "overview")
    try:
        default_view = validate_default_view(default_view)
    except ValueError:
        default_view = "overview"
    pinned = quotas.get("pinned_brand_slug")
    pinned_slug = str(pinned).strip().lower() if pinned else ""
    if not _slug_is_valid(pinned_slug):
        pinned_slug = ""
    return {"default_view": default_view, "pinned_brand_slug": pinned_slug}


def set_default_view(
    value: str,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Update ``dashboard.quotas.default_view`` with comment-preserving write.

    Returns the new settings dict. Raises ``ValueError`` on a bad value;
    never swallows filesystem errors (caller surfaces them to the HTTP
    layer as a 5xx).
    """
    canonical = validate_default_view(value)
    resolved = Path(path) if path else _config_path()

    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    # Match the existing 2-space indent faigate's wizard writes.
    yaml.indent(mapping=2, sequence=4, offset=2)

    if resolved.exists():
        with resolved.open("r", encoding="utf-8") as handle:
            data = yaml.load(handle)
        if data is None:
            data = CommentedMap()
    else:
        # Brand-new config; extremely rare in this path but we honor it.
        data = CommentedMap()

    dashboard = data.get("dashboard")
    if not isinstance(dashboard, CommentedMap):
        dashboard = CommentedMap()
        data["dashboard"] = dashboard

    quotas = dashboard.get("quotas")
    if not isinstance(quotas, CommentedMap):
        quotas = CommentedMap()
        dashboard["quotas"] = quotas

    quotas["default_view"] = canonical
    # Mirror the brand slug (if any) into a dedicated key so UI can render
    # "Home ⤴ pinned on this card" without parsing ``brand:<slug>``.
    if canonical.startswith("brand:"):
        quotas["pinned_brand_slug"] = canonical[len("brand:") :]
    else:
        # Drop the pinned_brand_slug key when we're not pinning a brand.
        # Comments on neighboring keys survive because ruamel keeps its
        # CommentedMap node graph intact around the drop.
        if "pinned_brand_slug" in quotas:
            del quotas["pinned_brand_slug"]

    # Write atomically: render to string, write to a temp file in the
    # same directory, then rename. Prevents half-written config.yaml on
    # power loss / SIGKILL.
    buffer = io.StringIO()
    yaml.dump(data, buffer)
    rendered = buffer.getvalue()

    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".dashboard_settings.",
        suffix=".yaml.tmp",
        dir=str(resolved.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
        os.replace(tmp_path, resolved)
    except Exception:
        # Best-effort cleanup; swallow the unlink error so the caller
        # sees the original write failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {
        "default_view": canonical,
        "pinned_brand_slug": canonical[len("brand:") :] if canonical.startswith("brand:") else "",
    }


def _default_settings() -> dict[str, Any]:
    return {"default_view": "overview", "pinned_brand_slug": ""}


__all__ = [
    "get_settings",
    "set_default_view",
    "validate_default_view",
]
