"""OAuth CLI helper for managed providers."""

import argparse
import json
import logging
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


def qwen_device_code_flow(client_id: str, scope: str = "openid email") -> dict[str, Any]:
    """Obtain Qwen OAuth token via device code flow."""
    if requests is None:
        raise RuntimeError("requests package required for Qwen OAuth. Install with: pip install faigate[oauth]")

    # Hypothetical endpoints – should be replaced with real Qwen OAuth endpoints
    device_endpoint = "https://qwen.example.com/oauth/device/code"
    token_endpoint = "https://qwen.example.com/oauth/token"

    # Step 1: Request device code
    resp = requests.post(
        device_endpoint,
        data={"client_id": client_id, "scope": scope},
        timeout=30,
    )
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_uri = device.get("verification_uri", "https://qwen.example.com/activate")
    interval = device.get("interval", 5)

    print(f"Please visit {verification_uri} and enter code: {user_code}")
    if webbrowser and webbrowser.open(verification_uri):
        print("Browser opened.")

    # Step 2: Poll for token
    for _ in range(60):  # max 5 minutes
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
            # Still pending
            if resp.status_code == 400 and "authorization_pending" in resp.text:
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Poll error: %s", e)

    raise RuntimeError("Device code flow timed out")


def claude_code_oauth() -> dict[str, Any]:
    """Obtain Claude Code token from local claude CLI configuration.

    Requires: npm install -g @anthropic-ai/claude-code
    Then run: claude login
    Token is stored in ~/.config/claude/settings.json
    """
    import os
    import json
    import subprocess

    # Try to read token from settings.json
    settings_path = os.path.expanduser("~/.config/claude/settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r") as f:
                settings = json.load(f)
            # The token field might be named "token" or "api_key"
            token = settings.get("token") or settings.get("api_key")
            if token and token.startswith("sk-ant-"):
                return {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": 3600 * 24 * 365,  # long-lived token
                    "scope": "claude-code",
                }
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.warning("Failed to read claude settings: %s", e)

    # If token not found, guide user to login
    print("Claude Code token not found.")
    print("Please install and login with Claude CLI:")
    print("  npm install -g @anthropic-ai/claude-code")
    print("  claude login")
    print("Then run this command again.")
    raise RuntimeError("Claude Code token not found. Please run 'claude login' first.")


def openai_codex_oauth() -> dict[str, Any]:
    """Obtain OpenAI Codex token via ChatGPT OAuth."""
    raise NotImplementedError("OpenAI Codex OAuth not yet implemented")


def google_vertex_adc() -> dict[str, Any]:
    """Use Google Application Default Credentials (ADC)."""
    import subprocess
    import json

    try:
        # Use gcloud to get access token for default account
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True,
        )
        access_token = result.stdout.strip()
        if not access_token:
            raise RuntimeError("gcloud returned empty access token")

        # Token expires in 1 hour (default). We don't have refresh token.
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
    """Obtain Google OAuth token via device code flow."""
    if requests is None:
        raise RuntimeError("requests package required for Google OAuth. Install with: pip install faigate[oauth]")

    # Step 1: Request device code
    resp = requests.post(
        device_endpoint,
        data={
            "client_id": client_id,
            "scope": scope,
        },
        timeout=30,
    )
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_uri = device.get("verification_uri", "https://www.google.com/device")
    interval = device.get("interval", 5)

    print(f"Please visit {verification_uri} and enter code: {user_code}")
    if webbrowser and webbrowser.open(verification_uri):
        print("Browser opened.")

    # Step 2: Poll for token
    for _ in range(60):  # max 5 minutes (60 * interval)
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
            # Still pending
            if resp.status_code == 400 and "authorization_pending" in resp.text:
                continue
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Poll error: %s", e)

    raise RuntimeError("Device code flow timed out")


def main() -> None:
    parser = argparse.ArgumentParser(description="OAuth helper for managed providers")
    parser.add_argument("provider", help="Provider canonical name")
    parser.add_argument("--client-id", help="OAuth client ID")
    parser.add_argument("--scope", default="openid email", help="OAuth scope")
    parser.add_argument("--device-endpoint", help="Device authorization endpoint (for device flow)")
    parser.add_argument("--token-endpoint", help="Token endpoint (for device flow)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    # Map provider to function
    handlers = {
        "qwen-portal": lambda: qwen_device_code_flow(args.client_id or "qwen-portal-client", args.scope),
        "claude-code": claude_code_oauth,
        "openai-codex": openai_codex_oauth,
        "google-gemini-cli": google_vertex_adc,
        "google-antigravity": lambda: google_oauth_device_flow(
            client_id=args.client_id or "",
            scope=args.scope,
            device_endpoint=args.device_endpoint or "https://accounts.google.com/o/oauth2/device/code",
            token_endpoint=args.token_endpoint or "https://oauth2.googleapis.com/token",
        ),
    }

    if args.provider not in handlers:
        print(f"Unknown provider: {args.provider}", file=sys.stderr)
        print("Supported providers:", ", ".join(handlers.keys()), file=sys.stderr)
        sys.exit(1)

    try:
        token_data = handlers[args.provider]()
        # Ensure provider_config is included for refresh
        token_data["provider_config"] = {
            "client_id": args.client_id,
            "scope": args.scope,
        }
        print(json.dumps(token_data, indent=2))
    except Exception as e:
        logger.error("Failed to obtain token: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
