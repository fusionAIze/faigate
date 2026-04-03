"""OAuth token storage and refresh logic.

This module manages OAuth2 tokens for managed providers (Gemini, Antigravity, Qwen,
OpenAI Codex, Claude Code). Tokens are stored in a JSON file under the user's
config directory with restricted permissions.

Tokens are stored as:

    {
      "provider_name": {
        "access_token": "ey...",
        "refresh_token": "ey...",
        "expires_at": 1735689600.0,
        "token_type": "Bearer",
        "scope": "openid email",
        "provider_config": {
          "client_id": "...",
          "token_endpoint": "...",
          "refresh_endpoint": "..."
        }
      }
    }

If a refresh token is present and the access token is expired, the store can
attempt to refresh it automatically (requires a refresh callback).

The store does not handle interactive login flows; those are delegated to an
external helper (e.g., `faigate-auth`). This module only stores, loads, and
refreshes tokens once they are obtained.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("faigate.oauth")


class TokenStore:
    """Manages OAuth2 tokens for managed providers."""

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize token store.

        Args:
            config_dir: Directory to store tokens.json. Defaults to
                ~/.config/faigate.
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "faigate"
        self.config_dir = Path(config_dir).expanduser().resolve()
        self.token_path = self.config_dir / "tokens.json"
        self._tokens: dict[str, dict[str, Any]] = {}
        self._load()

    def _ensure_config_dir(self) -> None:
        """Create config directory if it doesn't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load tokens from disk."""
        if not self.token_path.exists():
            self._tokens = {}
            return
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                self._tokens = json.load(f)
            logger.debug("Loaded tokens for %d providers", len(self._tokens))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load tokens from %s: %s", self.token_path, e)
            self._tokens = {}

    def _save(self) -> None:
        """Save tokens to disk."""
        self._ensure_config_dir()
        try:
            with open(self.token_path, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, indent=2)
            # Restrict permissions to owner only (0o600)
            self.token_path.chmod(0o600)
            logger.debug("Saved tokens for %d providers", len(self._tokens))
        except OSError as e:
            logger.error("Failed to save tokens to %s: %s", self.token_path, e)
            raise

    def get(self, provider: str) -> Optional[dict[str, Any]]:
        """Get token data for a provider.

        Returns None if the provider has no stored token.
        """
        return self._tokens.get(provider)

    def set(self, provider: str, token_data: dict[str, Any]) -> None:
        """Store or update token data for a provider.

        Args:
            provider: Provider canonical name (e.g., "qwen-portal").
            token_data: Dictionary containing at least "access_token".
                Should include "refresh_token", "expires_at", "token_type",
                "scope", and "provider_config" if available.
        """
        self._tokens[provider] = token_data
        self._save()

    def delete(self, provider: str) -> None:
        """Remove token data for a provider."""
        if provider in self._tokens:
            del self._tokens[provider]
            self._save()

    def list_providers(self) -> list[str]:
        """Return list of providers with stored tokens."""
        return list(self._tokens.keys())

    def is_expired(self, provider: str, margin_seconds: int = 60) -> bool:
        """Check if the access token for a provider is expired.

        Args:
            provider: Provider canonical name.
            margin_seconds: Consider token expired this many seconds before
                actual expiry to avoid race conditions.

        Returns:
            True if token is missing or expired, False otherwise.
        """
        token = self.get(provider)
        if not token:
            return True
        expires_at = token.get("expires_at")
        if expires_at is None:
            return False  # No expiry information, assume still valid
        return time.time() >= (expires_at - margin_seconds)

    def refresh_if_needed(
        self,
        provider: str,
        refresh_callback: callable,
        *args,
        **kwargs,
    ) -> bool:
        """Refresh access token if expired.

        Args:
            provider: Provider canonical name.
            refresh_callback: Callable that takes the current token data and
                returns refreshed token data (dict). Should raise an exception
                if refresh fails.
            *args, **kwargs: Passed to refresh_callback.

        Returns:
            True if token was refreshed, False if no refresh needed or no
            refresh token available.
        """
        token = self.get(provider)
        if not token:
            logger.debug("No token for %s, cannot refresh", provider)
            return False
        if not self.is_expired(provider):
            logger.debug("Token for %s still valid, skipping refresh", provider)
            return False
        if "refresh_token" not in token:
            logger.warning("Token for %s expired but no refresh token", provider)
            return False
        try:
            new_token = refresh_callback(token, *args, **kwargs)
            self.set(provider, new_token)
            logger.info("Refreshed token for %s", provider)
            return True
        except Exception as e:
            logger.error("Failed to refresh token for %s: %s", provider, e)
            return False
