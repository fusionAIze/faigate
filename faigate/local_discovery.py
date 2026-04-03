"""Local worker discovery for fusionAIze Gate.

This module provides auto-discovery of local AI model workers (Ollama, vLLM, LM Studio, etc.)
and integration with fusionAIze Grid when available.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, TypedDict

import httpx

from .registry import LOCAL

logger = logging.getLogger(__name__)


class DiscoveredWorker(TypedDict):
    """A discovered local worker instance."""

    name: str  # Canonical name (e.g., "ollama", "vllm")
    base_url: str  # Full base URL including port and /v1 path
    healthy: bool  # Whether the worker responds to health check
    models: list[str]  # List of available model IDs (if discoverable)
    capabilities: dict[str, Any]  # Capabilities inferred from worker type


# Default ports for known local workers
DEFAULT_PORTS = {
    "ollama": 11434,
    "vllm": 8000,
    "lmstudio": 1234,
    "litellm": 4000,
}

# Health check endpoints and expected response patterns
HEALTH_CHECKS = {
    "ollama": ("/v1/models", {"object": "list"}),
    "vllm": ("/v1/models", {"object": "list"}),
    "lmstudio": ("/v1/models", {"object": "list"}),
    "litellm": ("/v1/models", {"object": "list"}),
}


async def check_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a TCP port is open."""
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (TimeoutError, OSError):
        return False


async def probe_worker(base_url: str, worker_type: str, timeout: float = 5.0) -> tuple[bool, list[str]]:
    """Probe a worker endpoint to check health and discover models."""
    endpoint, expected_key = HEALTH_CHECKS.get(worker_type, ("/v1/models", {"object": "list"}))
    url = f"{base_url.rstrip('/')}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Check if response matches expected pattern
                if expected_key.items() <= data.items():
                    # Extract model IDs if available
                    models = []
                    if "data" in data and isinstance(data["data"], list):
                        models = [model.get("id", "") for model in data["data"] if model.get("id")]
                    return True, models
                return True, []
            return False, []
    except Exception as e:
        logger.debug("Worker probe failed for %s: %s", url, e)
        return False, []


async def discover_local_workers(
    scan_ports: bool = True, check_grid: bool = True, timeout_per_worker: float = 3.0
) -> list[DiscoveredWorker]:
    """Discover local AI workers.

    Args:
        scan_ports: Whether to scan default ports for known worker types
        check_grid: Whether to check for fusionAIze Grid configuration
        timeout_per_worker: Timeout for each worker probe in seconds

    Returns:
        List of discovered workers with health status and available models
    """
    discovered: list[DiscoveredWorker] = []

    # 1. Scan default ports for known worker types
    if scan_ports:
        for worker_name, port in DEFAULT_PORTS.items():
            base_url = f"http://127.0.0.1:{port}/v1"
            logger.debug("Checking %s at %s", worker_name, base_url)

            # First check if port is open
            if not await check_port_open("127.0.0.1", port, timeout=1.0):
                continue

            # Probe the worker
            healthy, models = await probe_worker(base_url, worker_name, timeout_per_worker)

            worker: DiscoveredWorker = {
                "name": worker_name,
                "base_url": base_url,
                "healthy": healthy,
                "models": models,
                "capabilities": {
                    "local": True,
                    "cloud": False,
                    "network_zone": "local",
                    "cost_tier": "local",
                    "latency_tier": "local",
                },
            }
            discovered.append(worker)

            if healthy:
                logger.info("Discovered healthy %s worker at %s", worker_name, base_url)
            else:
                logger.debug("Found %s worker at %s but health check failed", worker_name, base_url)

    # 2. Check for fusionAIze Grid configuration
    if check_grid:
        grid_workers = await discover_grid_workers(timeout_per_worker)
        discovered.extend(grid_workers)

    return discovered


async def discover_grid_workers(timeout: float = 5.0) -> list[DiscoveredWorker]:
    """Discover workers configured via fusionAIze Grid.

    Checks for Grid configuration files and extracts worker endpoints.
    """
    # TODO: Implement Grid configuration reading
    # For now, check common Grid worker patterns
    grid_workers = []

    # Check for Grid state files
    import os

    grid_state_path = os.path.expanduser("~/.faigrid/state/worker.state")
    if os.path.exists(grid_state_path):
        try:
            with open(grid_state_path) as f:
                # Parse Grid state format (key=value pairs)
                state = {}
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        key, value = line.split("=", 1)
                        state[key.strip()] = value.strip()

                # Extract worker endpoints from Grid state
                # This is a placeholder - actual implementation depends on Grid's state format
                if "WORKER_ENDPOINTS" in state:
                    endpoints = state["WORKER_ENDPOINTS"].split(",")
                    for endpoint in endpoints:
                        if endpoint:
                            # Assume endpoint includes worker type and port
                            # Format: worker_type:host:port
                            parts = endpoint.split(":")
                            if len(parts) >= 3:
                                worker_type, host, port = parts[0], parts[1], parts[2]
                                base_url = f"http://{host}:{port}/v1"
                                healthy, models = await probe_worker(base_url, worker_type, timeout)
                                worker: DiscoveredWorker = {
                                    "name": f"grid-{worker_type}",
                                    "base_url": base_url,
                                    "healthy": healthy,
                                    "models": models,
                                    "capabilities": {
                                        "local": True,
                                        "cloud": False,
                                        "network_zone": "local",
                                        "cost_tier": "local",
                                        "latency_tier": "local",
                                    },
                                }
                                grid_workers.append(worker)
        except Exception as e:
            logger.debug("Failed to read Grid state: %s", e)

    return grid_workers


def generate_provider_config(worker: DiscoveredWorker) -> dict[str, Any]:
    """Generate a provider configuration entry for a discovered worker."""
    # Get base definition from registry
    base_def = LOCAL.get(worker["name"])

    config = {
        "contract": "local-worker",
        "backend": "openai-compat",
        "base_url": worker["base_url"],
        "tier": "local",
        "capabilities": worker["capabilities"],
    }

    # Add model if available
    if worker["models"]:
        config["model"] = worker["models"][0]
    elif base_def and "example_model" in base_def:
        config["model"] = base_def["example_model"]

    return config


async def main() -> None:
    """CLI entry point for local worker discovery."""
    import argparse

    parser = argparse.ArgumentParser(description="Discover local AI workers")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-scan", action="store_true", help="Skip port scanning")
    parser.add_argument("--no-grid", action="store_true", help="Skip Grid check")
    parser.add_argument("--timeout", type=float, default=3.0, help="Timeout per worker")

    args = parser.parse_args()

    workers = await discover_local_workers(
        scan_ports=not args.no_scan, check_grid=not args.no_grid, timeout_per_worker=args.timeout
    )

    if args.json:
        print(json.dumps(workers, indent=2))
    else:
        if not workers:
            print("No local workers discovered.")
            return

        print(f"Discovered {len(workers)} local worker(s):")
        for worker in workers:
            status = "✓" if worker["healthy"] else "✗"
            models = f", {len(worker['models'])} models" if worker["models"] else ""
            print(f"  {status} {worker['name']}: {worker['base_url']}{models}")

            if worker["models"]:
                print(f"    Models: {', '.join(worker['models'][:5])}")
                if len(worker["models"]) > 5:
                    print(f"    ... and {len(worker['models']) - 5} more")


if __name__ == "__main__":
    asyncio.run(main())
