"""OAuth CLI helper for managed providers."""

import argparse
import json
import logging
import os
import sys
import time
from typing import Any

# Optional imports for OAuth flows
try:
    import requests
except ImportError:
    requests = None

try:
    import webbrowser
except ImportError:
    webbrowser = None


logger = logging.getLogger("faigate.oauth.cli")

# ── Antigravity constants (from LLM AI Router OAuth URL) ─────────────────────
_ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
_ANTIGRAVITY_SCOPE = " ".join(
    [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ]
)
_ANTIGRAVITY_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_ANTIGRAVITY_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_ANTIGRAVITY_CREDS_PATH = "~/.gemini/oauth_creds.json"
_ANTIGRAVITY_CALLBACK_PORT = 8080
# Base URL: Antigravity's client-facing interface is a local ephemeral gRPC language server
# (127.0.0.1:<port>/exa.language_server_pb.LanguageServerService/…) that proxies to Google
# internally. faigate uses the OAuth token to call the Google Generative Language API directly.
# Default: https://generativelanguage.googleapis.com/v1beta/openai (matches registry.py)
# Override with ANTIGRAVITY_BASE_URL if a different Google endpoint is needed.
_ANTIGRAVITY_BASE_URL_DEFAULT = "https://generativelanguage.googleapis.com/v1beta/openai"
_ANTIGRAVITY_BASE_URL_ENV = "ANTIGRAVITY_BASE_URL"

# ── Claude Code constants (reverse-engineered from claude-code binary) ────────
_CLAUDE_CODE_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_CLAUDE_CODE_TOKEN_ENDPOINT = "https://platform.claude.com/v1/oauth/token"
_CLAUDE_CODE_KEYCHAIN_SERVICE = "Claude Code-credentials"
_CLAUDE_CODE_SETTINGS_PATH = "~/.config/claude/settings.json"
# Required beta header for OAuth Bearer auth on api.anthropic.com/v1/messages
_CLAUDE_CODE_OAUTH_BETA = "oauth-2025-04-20"

# ── OpenAI Codex constants (from Codex CLI source / community research) ──────
_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CODEX_AUTH_ENDPOINT = "https://auth.openai.com/oauth/authorize"
_CODEX_TOKEN_ENDPOINT = "https://auth.openai.com/oauth/token"
_CODEX_SCOPE = "openid profile email offline_access"
_CODEX_CREDS_PATH = "~/.codex/auth.json"
_CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex/responses"
_CODEX_CALLBACK_PORT = 1455

# ── Qwen constants (from qwen-code source) ───────────────────────────────────
_QWEN_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"
_QWEN_SCOPE = "openid profile email model.completion"
_QWEN_DEVICE_ENDPOINT = "https://chat.qwen.ai/api/v1/oauth2/device/code"
_QWEN_TOKEN_ENDPOINT = "https://chat.qwen.ai/api/v1/oauth2/token"
_QWEN_CREDS_PATH = "~/.qwen/oauth_creds.json"
_QWEN_FALLBACK_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_QWEN_OAUTH_MODEL = "coder-model"


def _qwen_base_url_from_resource(resource_url: str | None) -> str:
    """Build the inference base URL from the resource_url field in Qwen credentials.

    resource_url is a hostname (e.g. 'portal.qwen.ai'). The full API path
    matches qwen-code's getCurrentEndpoint() which appends '/v1' directly
    (not '/compatible-mode/v1').
    """
    if not resource_url:
        return _QWEN_FALLBACK_BASE_URL
    host = resource_url.rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    return f"{host}/v1"


def qwen_oauth() -> dict[str, Any]:
    """Read Qwen OAuth credentials from the local qwen-code CLI token store.

    The qwen-code CLI (https://github.com/QwenLM/qwen-code) stores OAuth
    credentials at ~/.qwen/oauth_creds.json after running `qwen auth login`.
    Token format:
      {
        "access_token": "...",
        "refresh_token": "...",
        "token_type": "Bearer",
        "resource_url": "portal.qwen.ai",   # inference endpoint hostname
        "expiry_date": 1234567890000,        # ms timestamp
      }

    Returns a dict with access_token, base_url, and model suitable for
    injecting into faigate's provider config.
    """
    creds_path = os.path.expanduser(_QWEN_CREDS_PATH)
    if not os.path.exists(creds_path):
        raise RuntimeError(
            f"Qwen credentials not found at {creds_path}.\n"
            "Please authenticate with qwen-code first:\n"
            "  npm install -g @qwen-code/cli  # or: npx @qwen-code/cli\n"
            "  qwen auth login"
        )

    try:
        with open(creds_path) as f:
            creds = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read Qwen credentials from {creds_path}: {e}")

    access_token = creds.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"Qwen credentials at {creds_path} have no access_token. Please re-authenticate: qwen auth login"
        )

    # Check expiry (expiry_date is in milliseconds)
    expiry_ms = creds.get("expiry_date")
    if expiry_ms and expiry_ms < time.time() * 1000:
        raise RuntimeError(f"Qwen token expired (expiry: {expiry_ms}). Run: faigate-auth qwen-portal")

    resource_url = creds.get("resource_url")
    base_url = _qwen_base_url_from_resource(resource_url)

    return {
        "access_token": access_token,
        "refresh_token": creds.get("refresh_token"),
        "token_type": creds.get("token_type", "Bearer"),
        "base_url": base_url,
        "model": _QWEN_OAUTH_MODEL,
        "resource_url": resource_url,
        "expiry_date": expiry_ms,
    }


def qwen_refresh(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired Qwen OAuth token using the refresh_token.

    Writes the updated credentials back to ~/.qwen/oauth_creds.json.
    """
    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    resp = requests.post(
        _QWEN_TOKEN_ENDPOINT,
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _QWEN_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()

    new_creds = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token", refresh_token),
        "token_type": token.get("token_type", "Bearer"),
        "resource_url": token.get("resource_url"),
        "expiry_date": int((time.time() + token.get("expires_in", 3600)) * 1000),
    }

    creds_path = os.path.expanduser(_QWEN_CREDS_PATH)
    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    tmp = creds_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new_creds, f, indent=2)
    os.replace(tmp, creds_path)
    os.chmod(creds_path, 0o600)

    logger.info("Qwen token refreshed and written to %s", creds_path)
    return new_creds


def qwen_device_code_flow() -> dict[str, Any]:
    """Obtain a new Qwen OAuth token via the device code flow.

    Uses the same client_id and endpoints as qwen-code CLI so the resulting
    token is stored in the shared ~/.qwen/oauth_creds.json and usable by
    both faigate and qwen-code.
    """
    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    import base64
    import hashlib
    import secrets

    # Generate PKCE pair (required by qwen-code OAuth server)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    _QWEN_HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    # Step 1: Request device code
    resp = requests.post(
        _QWEN_DEVICE_ENDPOINT,
        data={
            "client_id": _QWEN_CLIENT_ID,
            "scope": _QWEN_SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
        headers=_QWEN_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_uri = device.get("verification_uri_complete") or device.get("verification_uri", "https://chat.qwen.ai/authorize")
    interval = device.get("interval", 5)
    expires_in = device.get("expires_in", 900)

    print(f"\nPlease visit: {verification_uri}", file=sys.stderr)
    print(f"User code:    {user_code}  (pre-filled in URL above)\n", file=sys.stderr)
    if webbrowser:
        webbrowser.open(verification_uri)

    # Step 2: Poll for token (RFC 8628)
    max_polls = expires_in // max(interval, 1)
    for _ in range(max_polls):
        time.sleep(interval)
        try:
            resp = requests.post(
                _QWEN_TOKEN_ENDPOINT,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": _QWEN_CLIENT_ID,
                    "code_verifier": code_verifier,
                },
                headers=_QWEN_HEADERS,
                timeout=30,
            )
            if resp.status_code == 200:
                token = resp.json()
                resource_url = token.get("resource_url")
                new_creds = {
                    "access_token": token["access_token"],
                    "refresh_token": token.get("refresh_token"),
                    "token_type": token.get("token_type", "Bearer"),
                    "resource_url": resource_url,
                    "expiry_date": int((time.time() + token.get("expires_in", 3600)) * 1000),
                }
                # Write to shared ~/.qwen/oauth_creds.json
                creds_path = os.path.expanduser(_QWEN_CREDS_PATH)
                os.makedirs(os.path.dirname(creds_path), exist_ok=True)
                tmp = creds_path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(new_creds, f, indent=2)
                os.replace(tmp, creds_path)
                os.chmod(creds_path, 0o600)
                print(f"Authenticated. Token written to {creds_path}")

                return {
                    **new_creds,
                    "base_url": _qwen_base_url_from_resource(resource_url),
                    "model": _QWEN_OAUTH_MODEL,
                }
            data = resp.json() if resp.content else {}
            error = data.get("error", "")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Poll error: %s", e)

    raise RuntimeError("Qwen device code flow timed out. Please try again.")


def antigravity_oauth() -> dict[str, Any]:
    """Read Antigravity OAuth credentials from the local token store.

    Antigravity (Google's AI coding IDE) stores Google OAuth credentials at
    ~/.gemini/oauth_creds.json after signing in via the app or via
    `antigravity auth login` (agy auth login).

    Token format:
      {
        "access_token": "ya29.a0...",
        "refresh_token": "1//03...",
        "token_type": "Bearer",
        "id_token": "eyJ...",
        "expiry_date": 1234567890000,  # ms timestamp
        "scope": "https://www.googleapis.com/auth/cloud-platform ...",
      }

    Returns token data including the base_url from ANTIGRAVITY_BASE_URL env var
    if set, otherwise flags that discovery is required.
    """
    creds_path = os.path.expanduser(_ANTIGRAVITY_CREDS_PATH)
    if not os.path.exists(creds_path):
        raise RuntimeError(
            f"Antigravity credentials not found at {creds_path}.\n"
            "Please sign in to Antigravity (the IDE) or run:\n"
            "  agy auth login"
        )

    try:
        with open(creds_path) as f:
            creds = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read Antigravity credentials from {creds_path}: {e}")

    access_token = creds.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"Antigravity credentials at {creds_path} have no access_token. "
            "Please sign in to Antigravity or run: agy auth login"
        )

    expiry_ms = creds.get("expiry_date")
    if expiry_ms and expiry_ms < time.time() * 1000:
        logger.warning(
            "Antigravity token appears expired. "
            "Run: faigate-auth google-antigravity --refresh  or sign in to Antigravity."
        )

    base_url = os.environ.get(_ANTIGRAVITY_BASE_URL_ENV, _ANTIGRAVITY_BASE_URL_DEFAULT)

    return {
        "access_token": access_token,
        "refresh_token": creds.get("refresh_token"),
        "token_type": creds.get("token_type", "Bearer"),
        "id_token": creds.get("id_token"),
        "expiry_date": expiry_ms,
        "scope": creds.get("scope", _ANTIGRAVITY_SCOPE),
        "base_url": base_url,
        "base_url_discovered": True,
    }


def antigravity_refresh(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired Antigravity Google OAuth token.

    Writes the updated credentials back to ~/.gemini/oauth_creds.json.
    """
    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    resp = requests.post(
        _ANTIGRAVITY_TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _ANTIGRAVITY_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()

    # Read existing creds to preserve fields (refresh_token may not be re-issued)
    creds_path = os.path.expanduser(_ANTIGRAVITY_CREDS_PATH)
    existing: dict[str, Any] = {}
    try:
        with open(creds_path) as f:
            existing = json.load(f)
    except Exception:
        pass

    new_creds = {
        **existing,
        "access_token": token["access_token"],
        "token_type": token.get("token_type", "Bearer"),
        "scope": token.get("scope", existing.get("scope", _ANTIGRAVITY_SCOPE)),
        "expiry_date": int((time.time() + token.get("expires_in", 3600)) * 1000),
    }
    if "id_token" in token:
        new_creds["id_token"] = token["id_token"]
    if "refresh_token" in token:
        new_creds["refresh_token"] = token["refresh_token"]

    os.makedirs(os.path.dirname(os.path.expanduser(creds_path)), exist_ok=True)
    tmp = creds_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new_creds, f, indent=2)
    os.replace(tmp, creds_path)
    os.chmod(creds_path, 0o600)
    logger.info("Antigravity token refreshed and written to %s", creds_path)

    return {
        **new_creds,
        "base_url": os.environ.get(_ANTIGRAVITY_BASE_URL_ENV, _ANTIGRAVITY_BASE_URL_DEFAULT),
    }


def antigravity_login() -> dict[str, Any]:
    """Full Antigravity Google OAuth login via Authorization Code + PKCE.

    Opens a browser to Google's OAuth consent screen, starts a local HTTP
    server on port 8080 to receive the callback, exchanges the code for
    tokens, and writes credentials to ~/.gemini/oauth_creds.json.

    This uses the same client_id and scopes as the Antigravity IDE so the
    resulting token is valid for Antigravity's inference API.
    """
    import base64
    import hashlib
    import secrets
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    # Generate PKCE code_verifier + code_challenge (S256)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()

    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://localhost:{_ANTIGRAVITY_CALLBACK_PORT}/callback"

    params = {
        "client_id": _ANTIGRAVITY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _ANTIGRAVITY_SCOPE,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{_ANTIGRAVITY_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"

    # Capture auth code via local callback server
    received: dict[str, str] = {}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            received["code"] = qs.get("code", [""])[0]
            received["state"] = qs.get("state", [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Antigravity login complete. You can close this tab.</h2>")

        def log_message(self, *args: Any) -> None:
            pass  # suppress server logs

    server = HTTPServer(("localhost", _ANTIGRAVITY_CALLBACK_PORT), _CallbackHandler)
    server.timeout = 120

    print(f"\nOpening browser for Antigravity login...\n{auth_url}\n")
    if webbrowser:
        webbrowser.open(auth_url)
    else:
        print(f"Open this URL manually:\n{auth_url}")

    print(f"Waiting for callback on http://localhost:{_ANTIGRAVITY_CALLBACK_PORT}/callback ...")
    server.handle_request()
    server.server_close()

    code = received.get("code")
    if not code:
        raise RuntimeError("No authorization code received from callback.")
    if received.get("state") != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF. Aborting.")

    # Exchange code for tokens
    resp = requests.post(
        _ANTIGRAVITY_TOKEN_ENDPOINT,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": _ANTIGRAVITY_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()

    new_creds = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "token_type": token.get("token_type", "Bearer"),
        "id_token": token.get("id_token"),
        "scope": token.get("scope", _ANTIGRAVITY_SCOPE),
        "expiry_date": int((time.time() + token.get("expires_in", 3600)) * 1000),
    }

    creds_path = os.path.expanduser(_ANTIGRAVITY_CREDS_PATH)
    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    tmp = creds_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new_creds, f, indent=2)
    os.replace(tmp, creds_path)
    os.chmod(creds_path, 0o600)
    print(f"Antigravity credentials written to {creds_path}")

    return {
        **new_creds,
        "base_url": os.environ.get(_ANTIGRAVITY_BASE_URL_ENV, _ANTIGRAVITY_BASE_URL_DEFAULT),
        "base_url_discovered": True,
    }


def _claude_code_read_keychain() -> dict[str, Any] | None:
    """Read Claude Code OAuth credentials from macOS Keychain.

    Claude Code stores tokens in the macOS Keychain under the service
    'Claude Code-credentials' as a JSON blob with shape:
      { "claudeAiOauth": { "accessToken": "sk-ant-oat01-...",
                           "refreshToken": "sk-ant-ort01-...",
                           "expiresAt": <ms-epoch>,
                           "scopes": [...], ... } }
    """
    import subprocess

    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", _CLAUDE_CODE_KEYCHAIN_SERVICE, "-w"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        data = json.loads(raw)
        return data.get("claudeAiOauth") or {}
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        return None


def _claude_code_write_keychain(creds: dict[str, Any]) -> None:
    """Write refreshed Claude Code OAuth credentials back to macOS Keychain."""
    import getpass
    import subprocess

    payload = json.dumps({"claudeAiOauth": creds})
    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-U",
            "-s",
            _CLAUDE_CODE_KEYCHAIN_SERVICE,
            "-a",
            getpass.getuser(),
            "-w",
            payload,
        ],
        check=True,
        stderr=subprocess.DEVNULL,
    )


def claude_code_refresh(refresh_token: str) -> dict[str, Any]:
    """Refresh a Claude Code OAuth token via platform.claude.com.

    Single-use refresh tokens: the response includes a new refresh_token
    which must replace the old one in the keychain.
    """
    if requests is None:
        raise RuntimeError("requests package required: pip install faigate[oauth]")

    resp = requests.post(
        _CLAUDE_CODE_TOKEN_ENDPOINT,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _CLAUDE_CODE_CLIENT_ID,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "claude-cli/2.1 faigate-auth",
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Claude Code token refresh failed ({resp.status_code}): {resp.text[:300]}")
    data = resp.json()
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_in": data.get("expires_in", 28800),
        "token_type": "Bearer",
        "scope": data.get("scope", "user:inference"),
    }


def claude_code_oauth() -> dict[str, Any]:
    """Read Claude Code OAuth token from macOS Keychain (or settings.json fallback).

    Prerequisites: claude login  (from @anthropic-ai/claude-code or Claude desktop app)

    The Claude Code desktop app and CLI store OAuth credentials in the macOS Keychain
    under 'Claude Code-credentials'. If the access token is expired, the refresh token
    is used automatically and the new credentials are written back.

    On non-macOS systems, falls back to ~/.config/claude/settings.json.
    """
    # 1. Try macOS Keychain
    kc = _claude_code_read_keychain()
    if kc and kc.get("accessToken"):
        at = kc["accessToken"]
        rt = kc.get("refreshToken")
        expires_at_ms = kc.get("expiresAt", 0)
        now_ms = time.time() * 1000
        # Refresh if expired or expiring within 5 minutes
        if expires_at_ms and now_ms >= expires_at_ms - 300_000 and rt:
            print("Claude Code token expired, refreshing...", file=sys.stderr)
            try:
                refreshed = claude_code_refresh(rt)
                new_creds = {
                    **kc,
                    "accessToken": refreshed["access_token"],
                    "refreshToken": refreshed.get("refresh_token", rt),
                    "expiresAt": int((time.time() + refreshed.get("expires_in", 28800)) * 1000),
                }
                _claude_code_write_keychain(new_creds)
                print("Token refreshed and stored in keychain.", file=sys.stderr)
                at = refreshed["access_token"]
                expires_at_ms = new_creds["expiresAt"]
            except Exception as e:
                logger.warning("Token refresh failed, using potentially expired token: %s", e)

        expires_in = max(0, int((expires_at_ms / 1000) - time.time())) if expires_at_ms else 28800
        return {
            "access_token": at,
            "refresh_token": rt,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "scope": " ".join(kc.get("scopes", ["user:inference"])),
        }

    # 2. Fall back to ~/.config/claude/settings.json (Linux / older installs)
    settings_path = os.path.expanduser(_CLAUDE_CODE_SETTINGS_PATH)
    if os.path.exists(settings_path):
        try:
            with open(settings_path) as f:
                settings = json.load(f)
            token = settings.get("token") or settings.get("api_key")
            if token and token.startswith("sk-ant-"):
                return {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 3600 * 24 * 365,
                    "scope": "user:inference",
                }
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read claude settings: %s", e)

    print("Claude Code token not found.", file=sys.stderr)
    print("Please log in with: claude login", file=sys.stderr)
    raise RuntimeError("Claude Code token not found.")


def _codex_jwt_expiry(token: str) -> float | None:
    """Decode JWT exp claim without verifying signature. Returns UTC epoch seconds or None."""
    try:
        import base64 as _b64

        parts = token.split(".")
        if len(parts) != 3:
            return None
        padding = 4 - len(parts[1]) % 4
        payload = json.loads(_b64.urlsafe_b64decode(parts[1] + "=" * padding))
        return float(payload["exp"])
    except Exception:
        return None


def openai_codex_oauth() -> dict[str, Any]:
    """Read OpenAI Codex credentials from the local Codex CLI token store.

    The OpenAI Codex CLI stores ChatGPT OAuth credentials at ~/.codex/auth.json
    after completing the interactive login on first run.

    Token format:
      {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": null,
        "tokens": {
          "access_token":  "eyJ...",   # JWT – sent as Bearer to inference endpoint
          "refresh_token": "rt_...",   # opaque, single-use
          "id_token":      "eyJ...",   # JWT – identity only
          "account_id":    "...",      # UUID
        },
        "last_refresh": "2026-04-05T..."  # ISO-8601 UTC
      }

    Expiry is derived from the JWT exp claim (no expiry_date field in the file).
    Inference endpoint: https://chatgpt.com/backend-api/codex/responses
    """
    creds_path = os.path.expanduser(_CODEX_CREDS_PATH)
    if not os.path.exists(creds_path):
        raise RuntimeError(
            f"OpenAI Codex credentials not found at {creds_path}.\n"
            "Please install and log in to the OpenAI Codex CLI:\n"
            "  npm install -g @openai/codex\n"
            "  codex  # completes OAuth login on first run\n"
            "Or run: faigate-auth openai-codex --login"
        )

    try:
        with open(creds_path) as f:
            creds = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to read Codex credentials from {creds_path}: {e}")

    if creds.get("auth_mode") != "chatgpt":
        raise RuntimeError(
            f"Codex credentials at {creds_path} use auth_mode={creds.get('auth_mode')!r}, "
            "expected 'chatgpt'. Please log in with: codex  or  faigate-auth openai-codex --login"
        )

    tokens = creds.get("tokens", {})
    access_token = tokens.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"No access_token in Codex credentials at {creds_path}. "
            "Please re-authenticate: codex  or  faigate-auth openai-codex --login"
        )

    exp = _codex_jwt_expiry(access_token)
    if exp is not None and exp < time.time():
        logger.warning("OpenAI Codex token expired (exp=%s). Run: faigate-auth openai-codex --refresh", exp)

    return {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "id_token": tokens.get("id_token"),
        "account_id": tokens.get("account_id"),
        "token_type": "Bearer",
        "expires_at": exp,
        "base_url": _CODEX_BASE_URL,
    }


def openai_codex_refresh(refresh_token: str) -> dict[str, Any]:
    """Refresh an expired OpenAI Codex token.

    Codex refresh tokens are single-use — the new refresh_token from the
    response is always written back to ~/.codex/auth.json immediately.
    """
    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    resp = requests.post(
        _CODEX_TOKEN_ENDPOINT,
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": _CODEX_CLIENT_ID,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()

    new_access_token = token["access_token"]
    new_refresh_token = token.get("refresh_token", refresh_token)
    exp = _codex_jwt_expiry(new_access_token)

    # Preserve existing structure; only overwrite token fields
    creds_path = os.path.expanduser(_CODEX_CREDS_PATH)
    existing: dict[str, Any] = {}
    try:
        with open(creds_path) as f:
            existing = json.load(f)
    except Exception:
        pass

    existing.setdefault("tokens", {})
    existing["tokens"]["access_token"] = new_access_token
    existing["tokens"]["refresh_token"] = new_refresh_token
    if "id_token" in token:
        existing["tokens"]["id_token"] = token["id_token"]
    existing["last_refresh"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    tmp = creds_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(existing, f, indent=2)
    os.replace(tmp, creds_path)
    os.chmod(creds_path, 0o600)
    logger.info("OpenAI Codex token refreshed and written to %s", creds_path)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "id_token": token.get("id_token"),
        "token_type": "Bearer",
        "expires_at": exp,
        "base_url": _CODEX_BASE_URL,
    }


def openai_codex_login() -> dict[str, Any]:
    """Full OpenAI Codex login via Authorization Code + PKCE.

    Opens a browser to auth.openai.com, listens on
    http://localhost:1455/auth/callback for the redirect, exchanges the
    code for tokens, and writes credentials to ~/.codex/auth.json.
    """
    import base64
    import hashlib
    import secrets
    import urllib.parse
    from http.server import BaseHTTPRequestHandler, HTTPServer

    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    redirect_uri = f"http://localhost:{_CODEX_CALLBACK_PORT}/auth/callback"

    params = {
        "client_id": _CODEX_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _CODEX_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{_CODEX_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    received: dict[str, str] = {}

    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            received["code"] = qs.get("code", [""])[0]
            received["state"] = qs.get("state", [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>OpenAI Codex login complete. You can close this tab.</h2>")

        def log_message(self, *args: Any) -> None:
            pass

    server = HTTPServer(("localhost", _CODEX_CALLBACK_PORT), _CallbackHandler)
    server.timeout = 120

    print(f"\nOpening browser for OpenAI Codex login...\n{auth_url}\n")
    if webbrowser:
        webbrowser.open(auth_url)
    else:
        print(f"Open this URL manually:\n{auth_url}")

    print(f"Waiting for callback on {redirect_uri} ...")
    server.handle_request()
    server.server_close()

    code = received.get("code")
    if not code:
        raise RuntimeError("No authorization code received from callback.")
    if received.get("state") != state:
        raise RuntimeError("OAuth state mismatch — possible CSRF. Aborting.")

    resp = requests.post(
        _CODEX_TOKEN_ENDPOINT,
        json={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": _CODEX_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json()

    new_access_token = token["access_token"]
    exp = _codex_jwt_expiry(new_access_token)

    new_creds = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": new_access_token,
            "refresh_token": token.get("refresh_token"),
            "id_token": token.get("id_token"),
            "account_id": None,
        },
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    creds_path = os.path.expanduser(_CODEX_CREDS_PATH)
    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    tmp = creds_path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(new_creds, f, indent=2)
    os.replace(tmp, creds_path)
    os.chmod(creds_path, 0o600)
    print(f"OpenAI Codex credentials written to {creds_path}")

    return {
        "access_token": new_access_token,
        "refresh_token": token.get("refresh_token"),
        "id_token": token.get("id_token"),
        "token_type": "Bearer",
        "expires_at": exp,
        "base_url": _CODEX_BASE_URL,
    }


def google_vertex_adc() -> dict[str, Any]:
    """Use Google Application Default Credentials (gcloud ADC)."""
    import subprocess

    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        access_token = result.stdout.strip()
        if not access_token:
            raise RuntimeError("gcloud returned empty access token")
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/cloud-platform",
        }
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError(f"Failed to obtain Google ADC token: {e}. Ensure gcloud is installed and authenticated.")


def google_oauth_device_flow(
    client_id: str,
    scope: str = "openid email",
    device_endpoint: str = "https://accounts.google.com/o/oauth2/device/code",
    token_endpoint: str = "https://oauth2.googleapis.com/token",
) -> dict[str, Any]:
    """Obtain Google OAuth token via device code flow (for Antigravity etc.)."""
    if requests is None:
        raise RuntimeError("requests package required. Install with: pip install faigate[oauth]")

    resp = requests.post(device_endpoint, data={"client_id": client_id, "scope": scope}, timeout=30)
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_uri = device.get("verification_uri", "https://www.google.com/device")
    interval = device.get("interval", 5)

    print(f"Please visit {verification_uri} and enter code: {user_code}")
    if webbrowser:
        webbrowser.open(verification_uri)

    for _ in range(60):
        time.sleep(interval)
        try:
            resp = requests.post(
                token_endpoint,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": client_id,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                token = resp.json()
                return {
                    "access_token": token["access_token"],
                    "refresh_token": token.get("refresh_token"),
                    "expires_in": token.get("expires_in", 3600),
                    "token_type": token.get("token_type", "Bearer"),
                    "scope": token.get("scope", scope),
                }
            if resp.status_code == 400 and "authorization_pending" in resp.text:
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Poll error: %s", e)

    raise RuntimeError("Device code flow timed out")


def main() -> None:
    parser = argparse.ArgumentParser(description="OAuth helper for managed providers")
    parser.add_argument("provider", help="Provider canonical name")
    parser.add_argument("--client-id", help="OAuth client ID (for Google flows)")
    parser.add_argument("--scope", help="OAuth scope override")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing token instead of new login")
    parser.add_argument(
        "--login", action="store_true", help="Force interactive browser login (openai-codex, google-antigravity)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    try:
        if args.provider == "qwen-portal":
            if args.refresh:
                # Read existing refresh_token and refresh
                creds_path = os.path.expanduser(_QWEN_CREDS_PATH)
                with open(creds_path) as f:
                    creds = json.load(f)
                rt = creds.get("refresh_token")
                if not rt:
                    raise RuntimeError("No refresh_token in existing credentials.")
                token_data = qwen_refresh(rt)
                token_data["base_url"] = _qwen_base_url_from_resource(token_data.get("resource_url"))
                token_data["model"] = _QWEN_OAUTH_MODEL
            else:
                # Try reading existing credentials first; fall back to device flow
                try:
                    token_data = qwen_oauth()
                    print("Using existing Qwen credentials.", file=sys.stderr)
                except RuntimeError:
                    print("No existing credentials found, starting device code flow...", file=sys.stderr)
                    token_data = qwen_device_code_flow()

        elif args.provider == "claude-code":
            if args.refresh:
                kc = _claude_code_read_keychain()
                if not kc or not kc.get("refreshToken"):
                    raise RuntimeError("No refresh_token in Claude Code keychain credentials.")
                token_data = claude_code_refresh(kc["refreshToken"])
                new_creds = {**(kc or {}), "accessToken": token_data["access_token"],
                             "refreshToken": token_data.get("refresh_token", kc.get("refreshToken", "")),
                             "expiresAt": int((time.time() + token_data.get("expires_in", 28800)) * 1000)}
                _claude_code_write_keychain(new_creds)
                print("Token refreshed and stored in keychain.", file=sys.stderr)
            else:
                try:
                    token_data = claude_code_oauth()
                    print("Using existing Claude Code credentials.", file=sys.stderr)
                except RuntimeError:
                    raise RuntimeError(
                        "No Claude Code credentials found. Please run: claude login"
                    )

        elif args.provider == "openai-codex":
            if args.refresh:
                creds_path = os.path.expanduser(_CODEX_CREDS_PATH)
                with open(creds_path) as f:
                    creds = json.load(f)
                rt = creds.get("tokens", {}).get("refresh_token")
                if not rt:
                    raise RuntimeError("No refresh_token in existing Codex credentials.")
                token_data = openai_codex_refresh(rt)
            elif args.login:
                token_data = openai_codex_login()
            else:
                try:
                    token_data = openai_codex_oauth()
                    print("Using existing OpenAI Codex credentials.", file=sys.stderr)
                except RuntimeError:
                    print("No valid credentials found, starting browser login...", file=sys.stderr)
                    token_data = openai_codex_login()

        elif args.provider == "google-gemini-cli":
            token_data = google_vertex_adc()

        elif args.provider == "google-antigravity":
            if args.refresh:
                creds_path = os.path.expanduser(_ANTIGRAVITY_CREDS_PATH)
                with open(creds_path) as f:
                    creds = json.load(f)
                rt = creds.get("refresh_token")
                if not rt:
                    raise RuntimeError("No refresh_token in existing Antigravity credentials.")
                token_data = antigravity_refresh(rt)
            else:
                try:
                    token_data = antigravity_oauth()
                    print("Using existing Antigravity credentials.", file=sys.stderr)
                except RuntimeError:
                    print("No existing credentials, starting browser login...", file=sys.stderr)
                    token_data = antigravity_login()

        else:
            print(f"Unknown provider: {args.provider}", file=sys.stderr)
            print(
                "Supported: qwen-portal, claude-code, openai-codex, google-gemini-cli, google-antigravity",
                file=sys.stderr,
            )
            sys.exit(1)

        # Output token data as JSON to stdout so OAuthBackend._run_helper() can parse it.
        # All human-readable status messages go to stderr (see above).
        print(json.dumps(token_data))

    except Exception as e:
        logger.error("Failed to obtain token: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
