"""OAuth‑wrapped provider backend.

This module provides `OAuthBackend`, a wrapper around an existing provider backend
that injects OAuth2 tokens obtained from the token store. It handles token
refresh and interactive login delegation.
"""

import asyncio
import json
import logging
import os
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from httpx import AsyncClient, Request, Response

from ..providers import ProviderBackend
from .token_store import TokenStore

logger = logging.getLogger("faigate.oauth.backend")


class OAuthBackend(ProviderBackend):
    """Provider backend that adds OAuth2 token management.

    This backend wraps an underlying backend (e.g., openai‑compat, anthropic‑compat)
    and injects an OAuth2 bearer token into each request. Tokens are obtained from
    the token store; if missing or expired, the backend can delegate to an external
    helper for interactive login or token refresh.

    Configuration example in config.yaml:

        providers:
          qwen‑portal:
            backend: oauth
            oauth:
              helper: "faigate‑auth qwen‑portal"
              client_id: "..."
              token_endpoint: "https://qwen.example.com/oauth/token"
              refresh_endpoint: "https://qwen.example.com/oauth/refresh"
              scope: "openid email"
            underlying_backend: openai‑compat
            base_url: "https://qwen‑portal.example.com/v1"

    The `underlying_backend` field specifies which real backend to use after
    token injection.
    """

    def __init__(self, name: str, cfg: dict[str, Any]):
        """Initialize OAuth backend.

        Args:
            name: Provider canonical name.
            cfg: Provider configuration dict. Must contain an "oauth" sub‑dict
                with at least "helper" (command to obtain tokens) and
                "underlying_backend" (backend type to wrap).
        """
        super().__init__(name, cfg)
        self.oauth_cfg = cfg.get("oauth", {})
        self.helper_cmd = self.oauth_cfg.get("helper", "")
        # underlying_backend may be at top-level cfg or nested in the oauth sub-dict
        self.underlying_backend_type = cfg.get("underlying_backend") or self.oauth_cfg.get(
            "underlying_backend", "openai-compat"
        )
        # Optional: inject a system message if none is present in the request
        self.require_system_message: str | None = cfg.get("require_system_message")
        self.token_store = TokenStore()
        self._wrapped_backend = self._create_wrapped_backend()

    def _create_wrapped_backend(self) -> ProviderBackend:
        """Instantiate the underlying backend."""
        # Create a config dict for the wrapped backend by stripping oauth fields
        wrapped_cfg = self.cfg.copy()
        wrapped_cfg.pop("oauth", None)
        wrapped_cfg["backend"] = self.underlying_backend_type
        # Ensure auth_optional is True because we will add the token ourselves
        wrapped_cfg["auth_optional"] = True
        return ProviderBackend(self.name, wrapped_cfg)

    def _resolve_helper_argv(self) -> list[str] | None:
        """Return an executable argv for helper commands when possible.

        Brew installs the real helper in ``libexec/bin``. Service and temporary
        runtime PATHs do not always include that directory, so a bare
        ``faigate-auth ...`` command can fail even when the helper is installed.
        """

        try:
            argv = shlex.split(self.helper_cmd)
        except ValueError:
            return None
        if not argv:
            return None

        helper = argv[0]
        if os.path.isabs(helper) or "/" in helper:
            return argv

        resolved = shutil.which(helper)
        if not resolved:
            python_bin = Path(sys.executable).parent
            prefix_bin = Path(sys.prefix) / "bin"
            candidates = (
                python_bin / helper,
                prefix_bin / helper,
                python_bin.parent / "bin" / helper,
            )
            for candidate in candidates:
                if candidate.exists() and os.access(candidate, os.X_OK):
                    resolved = str(candidate)
                    break
        if not resolved:
            return None
        argv[0] = resolved
        return argv

    async def _ensure_token(self) -> str:
        """Ensure a valid access token exists, refreshing or logging in if needed.

        Returns:
            Access token string.

        Raises:
            RuntimeError: If token cannot be obtained.
        """
        token_data = self.token_store.get(self.name)
        if not token_data:
            logger.info("No token for %s, invoking helper", self.name)
            token_data = await self._run_helper()
            if not token_data:
                raise RuntimeError(
                    f"Could not obtain OAuth token for {self.name}. Run helper manually: {self.helper_cmd}"
                )
            self.token_store.set(self.name, token_data)

        # Check expiration
        if self.token_store.is_expired(self.name):
            logger.info("Token for %s expired, attempting refresh", self.name)
            refreshed = self.token_store.refresh_if_needed(self.name, self._refresh_token)
            if not refreshed:
                # Refresh failed or not possible; try full re‑login
                logger.warning("Refresh failed, invoking helper")
                token_data = await self._run_helper()
                if not token_data:
                    raise RuntimeError(
                        f"Could not refresh OAuth token for {self.name}. Run helper manually: {self.helper_cmd}"
                    )
                self.token_store.set(self.name, token_data)

        # Return access token
        token_data = self.token_store.get(self.name)
        return token_data.get("access_token", "")

    async def _run_helper(self) -> dict[str, Any]:
        """Run external helper to obtain tokens.

        Returns:
            Token data dict (access_token, refresh_token, expires_at, etc.)

        Raises:
            RuntimeError: If helper fails.
        """
        if not self.helper_cmd:
            raise RuntimeError(f"No OAuth helper command configured for {self.name}")

        logger.info("Running OAuth helper: %s", self.helper_cmd)
        try:
            argv = self._resolve_helper_argv()
            if argv is not None:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                # Fall back to shell execution for intentionally shell-based helpers.
                proc = await asyncio.create_subprocess_shell(
                    self.helper_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Helper failed with exit code {proc.returncode}: {stderr_text}")

            # Parse JSON output
            output = stdout.decode("utf-8", errors="replace").strip()
            try:
                token_data = json.loads(output)
            except json.JSONDecodeError as e:
                logger.error("Helper output not valid JSON: %s", output[:200])
                raise RuntimeError(f"Helper output not valid JSON: {e}")

            # Validate required fields
            if "access_token" not in token_data:
                raise RuntimeError("Helper output missing 'access_token' field")

            # Add provider config for future refreshes
            token_data.setdefault("provider_config", self.oauth_cfg.copy())
            logger.info("Obtained OAuth token for %s", self.name)
            return token_data

        except (OSError, Exception) as e:
            logger.error("Failed to run OAuth helper %s: %s", self.helper_cmd, e)
            raise RuntimeError(f"OAuth helper execution failed: {e}")

    def _refresh_token(self, token_data: dict[str, Any]) -> dict[str, Any]:
        """Refresh an access token using the refresh token.

        Args:
            token_data: Current token data (must contain refresh_token).

        Returns:
            New token data.

        Raises:
            RuntimeError: If refresh fails.
        """
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("No refresh token available")

        provider_config = token_data.get("provider_config", self.oauth_cfg)
        token_endpoint = provider_config.get("refresh_endpoint") or provider_config.get("token_endpoint")
        if not token_endpoint:
            raise RuntimeError("No token endpoint configured for refresh")

        client_id = provider_config.get("client_id", "")
        client_secret = provider_config.get("client_secret")

        # Prepare OAuth2 refresh request
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            data["client_secret"] = client_secret

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        logger.info("Refreshing OAuth token for %s", self.name)
        try:
            resp = httpx.post(token_endpoint, data=data, headers=headers, timeout=30.0)
            resp.raise_for_status()
            new_token = resp.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.error("Token refresh failed: %s", e)
            raise RuntimeError(f"Token refresh failed: {e}")

        # Merge new token data with existing (preserve provider_config)
        merged = token_data.copy()
        merged.update(new_token)
        merged.setdefault("provider_config", provider_config)

        # Ensure expires_at is set if expires_in provided
        if "expires_in" in merged and "expires_at" not in merged:
            merged["expires_at"] = time.time() + merged["expires_in"]

        logger.info("Token refreshed for %s", self.name)
        return merged

    async def _inject_token(self) -> None:
        """Obtain a fresh token and inject it into the wrapped backend's api_key."""
        token = await self._ensure_token()
        self._wrapped_backend.api_key = token

    def _ensure_system_message(self, messages: list) -> list:
        """Inject a system message at the start if none exists and require_system_message is set."""
        if not self.require_system_message:
            return messages
        has_system = any(m.get("role") == "system" for m in messages if isinstance(m, dict))
        if has_system:
            return messages
        return [{"role": "system", "content": self.require_system_message}] + list(messages)

    async def complete(self, messages: list, **kwargs):  # type: ignore[override]
        """Inject OAuth token, then delegate to wrapped backend."""
        await self._inject_token()
        messages = self._ensure_system_message(messages)
        return await self._wrapped_backend.complete(messages, **kwargs)

    async def _request(self, client: AsyncClient, req: Request) -> Response:
        """Override _request to inject OAuth bearer token (legacy path)."""
        token = await self._ensure_token()
        req.headers["Authorization"] = f"Bearer {token}"
        return await self._wrapped_backend._request(client, req)

    # Forward all other methods to wrapped backend
    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to wrapped backend."""
        return getattr(self._wrapped_backend, name)
