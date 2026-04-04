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
_ANTIGRAVITY_SCOPE = " ".join([
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
])
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
    follows DashScope's compatible-mode convention.
    """
    if not resource_url:
        return _QWEN_FALLBACK_BASE_URL
    host = resource_url.rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    return f"{host}/compatible-mode/v1"


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
    except (json.JSONDecodeError, IOError) as e:
        raise RuntimeError(f"Failed to read Qwen credentials from {creds_path}: {e}")

    access_token = creds.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"Qwen credentials at {creds_path} have no access_token. "
            "Please re-authenticate: qwen auth login"
        )

    # Check expiry (expiry_date is in milliseconds)
    expiry_ms = creds.get("expiry_date")
    if expiry_ms and expiry_ms < time.time() * 1000:
        logger.warning(
            "Qwen token appears expired (expiry: %s). "
            "Consider refreshing: qwen auth login",
            expiry_ms,
        )

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

    # Step 1: Request device code
    resp = requests.post(
        _QWEN_DEVICE_ENDPOINT,
        json={
            "client_id": _QWEN_CLIENT_ID,
            "scope": _QWEN_SCOPE,
        },
        timeout=30,
    )
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_uri = device.get("verification_uri", "https://chat.qwen.ai/activate")
    interval = device.get("interval", 5)
    expires_in = device.get("expires_in", 300)

    print(f"\nPlease visit: {verification_uri}")
    print(f"Enter code:   {user_code}\n")
    if webbrowser:
        webbrowser.open(verification_uri)

    # Step 2: Poll for token (RFC 8628)
    max_polls = expires_in // max(interval, 1)
    for _ in range(max_polls):
        time.sleep(interval)
        try:
            resp = requests.post(
                _QWEN_TOKEN_ENDPOINT,
                json={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": _QWEN_CLIENT_ID,
                },
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
    except (json.JSONDecodeError, IOError) as e:
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
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

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


def claude_code_oauth() -> dict[str, Any]:
    """Read Claude Code OAuth token from the local claude CLI config.

    Requires: npm install -g @anthropic-ai/claude-code && claude login
    Token stored at: ~/.config/claude/settings.json
    """
    settings_path = os.path.expanduser("~/.config/claude/settings.json")
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
                    "scope": "claude-code",
                }
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to read claude settings: %s", e)

    print("Claude Code token not found.")
    print("Please install and login:\n  npm install -g @anthropic-ai/claude-code\n  claude login")
    raise RuntimeError("Claude Code token not found.")


def openai_codex_oauth() -> dict[str, Any]:
    """Obtain OpenAI Codex token via ChatGPT OAuth."""
    raise NotImplementedError("OpenAI Codex OAuth not yet implemented")


def google_vertex_adc() -> dict[str, Any]:
    """Use Google Application Default Credentials (gcloud ADC)."""
    import subprocess

    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, check=True,
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
        raise RuntimeError(
            f"Failed to obtain Google ADC token: {e}. "
            "Ensure gcloud is installed and authenticated."
        )


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
            token_data = claude_code_oauth()

        elif args.provider == "openai-codex":
            token_data = openai_codex_oauth()

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
            print("Supported: qwen-portal, claude-code, google-gemini-cli, google-antigravity", file=sys.stderr)
            sys.exit(1)

        _SENSITIVE = {"access_token", "refresh_token", "id_token"}
        safe = {k: ("[REDACTED]" if k in _SENSITIVE else v) for k, v in token_data.items()}
        print(json.dumps(safe, indent=2))
        print("\nToken written to credentials file (use it from there).", file=sys.stderr)

    except Exception as e:
        logger.error("Failed to obtain token: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
