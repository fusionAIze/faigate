#!/usr/bin/env python3
"""Validate Claude Desktop compatibility with fusionAIze Gate.

This script tests the Anthropic bridge endpoints to ensure they meet
Claude Desktop's requirements for local gateway integration.

Usage:
    python scripts/validate-claude-desktop.py
"""

import asyncio
import json
import sys
from typing import Any

import httpx

# Test server (assumes faigate is running on default port)
BASE_URL = "http://127.0.0.1:8091"
ANTHROPIC_BASE_URL = f"{BASE_URL}/v1"


async def test_health() -> bool:
    """Test basic gateway health."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code == 200:
                print("✓ Gateway health endpoint OK")
                return True
            else:
                print(f"✗ Gateway health endpoint returned {resp.status_code}")
                return False
        except Exception as e:
            print(f"✗ Cannot reach gateway: {e}")
            return False


async def test_messages_non_streaming() -> bool:
    """Test POST /v1/messages non-streaming."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "max-tokens-2024-07-15",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "system": "You are a helpful assistant.",
            "messages": [{"role": "user", "content": "Hello, please respond with 'Gateway test successful'."}],
            "max_tokens": 100,
            "stream": False,
        }

        try:
            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/messages",
                headers=headers,
                json=payload,
            )

            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ Non-streaming messages OK (model: {data.get('model')})")
                # Check response structure
                required_keys = {"id", "model", "content", "stop_reason", "usage"}
                if all(key in data for key in required_keys):
                    print("  Response structure valid")
                    return True
                else:
                    print(f"  Missing keys: {required_keys - set(data.keys())}")
                    return False
            elif resp.status_code == 401:
                # Bridge is active but authentication failed
                print("⚠ Non-streaming messages: Bridge active but authentication failed (401)")
                print("  This is expected with dummy API keys")
                # Check if response indicates bridge is enabled (not "Anthropic bridge is disabled")
                if "Anthropic bridge is disabled" not in resp.text:
                    print("  ✓ Bridge endpoint is enabled")
                    return True
                else:
                    print("  ✗ Bridge endpoint reports disabled")
                    return False
            elif resp.status_code == 404:
                print(f"✗ Non-streaming messages failed: 404 (Bridge likely disabled)")
                print(f"  Response: {resp.text[:200]}")
                return False
            else:
                print(f"✗ Non-streaming messages failed: {resp.status_code}")
                print(f"  Response: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"✗ Non-streaming messages error: {e}")
            return False


async def test_messages_streaming() -> bool:
    """Test POST /v1/messages streaming (SSE)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "anthropic-version": "2023-06-01",
            "accept": "text/event-stream",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Stream a short response."}],
            "max_tokens": 50,
            "stream": True,
        }

        try:
            async with client.stream(
                "POST",
                f"{ANTHROPIC_BASE_URL}/messages",
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code == 200:
                    event_count = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            event_count += 1
                            data = line[5:].strip()
                            if data == "[DONE]":
                                print(f"✓ Streaming messages OK ({event_count} events)")
                                return True
                    if event_count > 0:
                        print(f"✓ Streaming messages OK ({event_count} events)")
                        return True
                    else:
                        print("✗ Streaming messages: no events received")
                        return False
                elif response.status_code == 401:
                    # Bridge is active but authentication failed
                    print("⚠ Streaming messages: Bridge active but authentication failed (401)")
                    print("  This is expected with dummy API keys")
                    return True
                elif response.status_code == 404:
                    print(f"✗ Streaming messages failed: 404 (Bridge likely disabled)")
                    return False
                else:
                    print(f"✗ Streaming messages failed: {response.status_code}")
                    return False
        except Exception as e:
            print(f"✗ Streaming messages error: {e}")
            return False


async def test_count_tokens() -> bool:
    """Test POST /v1/messages/count_tokens."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Count these tokens please."}],
        }

        try:
            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/messages/count_tokens",
                headers=headers,
                json=payload,
            )

            if resp.status_code == 200:
                data = resp.json()
                if "input_tokens" in data:
                    print(f"✓ Count tokens OK ({data['input_tokens']} tokens)")
                    # Check for X-faigate headers
                    if "X-faigate-Token-Count-Exact" in resp.headers:
                        print(f"  Token count method: {resp.headers.get('X-faigate-Token-Count-Method', 'unknown')}")
                    return True
                else:
                    print(f"✗ Count tokens missing 'input_tokens': {data}")
                    return False
            elif resp.status_code == 401:
                # Bridge is active but authentication failed
                print("⚠ Count tokens: Bridge active but authentication failed (401)")
                print("  This is expected with dummy API keys")
                return True
            elif resp.status_code == 404:
                print(f"✗ Count tokens failed: 404 (Bridge likely disabled)")
                print(f"  Response: {resp.text[:200]}")
                return False
            else:
                print(f"✗ Count tokens failed: {resp.status_code}")
                print(f"  Response: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"✗ Count tokens error: {e}")
            return False


async def test_model_aliases() -> bool:
    """Test that Claude Desktop model aliases work correctly."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {"content-type": "application/json"}

        # Common Claude Desktop model IDs
        test_models = [
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
            "claude-3-5-sonnet",  # Short alias
            "claude-3-opus",
            "claude-3-haiku",
        ]

        success = True
        for model in test_models:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "Test"}],
                "max_tokens": 10,
            }

            try:
                resp = await client.post(
                    f"{ANTHROPIC_BASE_URL}/messages",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    print(f"  ✓ Model alias '{model}' accepted")
                elif resp.status_code == 401:
                    print(f"  ⚠ Model alias '{model}' accepted (auth failed)")
                elif resp.status_code == 404:
                    print(f"  ✗ Model alias '{model}' failed: 404 (Bridge likely disabled)")
                    success = False
                else:
                    print(f"  ✗ Model alias '{model}' failed: {resp.status_code}")
                    success = False
            except Exception as e:
                print(f"  ✗ Model alias '{model}' error: {e}")
                success = False

        if success:
            print("✓ Model aliases test passed")
        else:
            print("✗ Model aliases test failed")

        return success


async def test_desktop_headers() -> bool:
    """Test that Claude Desktop specific headers are handled."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Headers that Claude Desktop might send
        headers = {
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "max-tokens-2024-07-15",
            "anthropic-client": "claude-desktop",
            "x-api-key": "test-key-ignored",  # Should be ignored if not needed
            "content-type": "application/json",
        }

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Test headers"}],
            "max_tokens": 10,
        }

        try:
            resp = await client.post(
                f"{ANTHROPIC_BASE_URL}/messages",
                headers=headers,
                json=payload,
            )

            if resp.status_code == 200:
                # Check that gateway adds its own headers
                gate_headers = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-faigate")}
                if gate_headers:
                    print(f"✓ Desktop headers handled (added {len(gate_headers)} gateway headers)")
                    return True
                else:
                    print("✓ Desktop headers handled (no gateway headers added)")
                    return True
            elif resp.status_code == 401:
                # Bridge is active but authentication failed
                print("⚠ Desktop headers: Bridge active but authentication failed (401)")
                print("  This is expected with dummy API keys")
                return True
            elif resp.status_code == 404:
                print(f"✗ Desktop headers test failed: 404 (Bridge likely disabled)")
                return False
            else:
                print(f"✗ Desktop headers test failed: {resp.status_code}")
                return False
        except Exception as e:
            print(f"✗ Desktop headers error: {e}")
            return False


async def main() -> int:
    """Run all validation tests."""
    print("=" * 70)
    print("Claude Desktop Compatibility Validation")
    print("=" * 70)
    print(f"Testing gateway at: {BASE_URL}")
    print(f"Anthropic base URL: {ANTHROPIC_BASE_URL}")
    print()

    # Check if gateway is running
    if not await test_health():
        print("\n❌ Gateway not reachable. Please start faigate first:")
        print("    python -m faigate")
        return 1

    tests = [
        ("Non-streaming messages", test_messages_non_streaming),
        ("Streaming messages", test_messages_streaming),
        ("Count tokens", test_count_tokens),
        ("Model aliases", test_model_aliases),
        ("Desktop headers", test_desktop_headers),
    ]

    passed = 0
    total = len(tests)

    for name, test_func in tests:
        print(f"\n{name}:")
        try:
            if await test_func():
                passed += 1
            else:
                print(f"  ❌ {name} failed")
        except Exception as e:
            print(f"  ❌ {name} exception: {e}")

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All tests passed! Claude Desktop compatibility looks good.")
        print("\nNext steps:")
        print("1. Configure Claude Desktop with ANTHROPIC_BASE_URL=" + ANTHROPIC_BASE_URL)
        print("2. Test real desktop workflows")
        return 0
    else:
        print("❌ Some tests failed. Review logs above.")
        print("\nCommon issues:")
        print("- Ensure anthropic_bridge.enabled: true in config.yaml")
        print("- Check gateway logs for bridge-related errors")
        print("- Verify model aliases are configured in anthropic_bridge.model_aliases")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
