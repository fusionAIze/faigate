"""Local worker discovery for fusionAIze Gate.

This module provides auto-discovery of local AI model workers (Ollama, vLLM, LM Studio, etc.)
and integration with fusionAIze Grid when available.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, TypedDict

import httpx

from .registry import LOCAL

logger = logging.getLogger(__name__)


class GpuInfo(TypedDict, total=False):
    """GPU metrics from a local worker."""

    gpu_name: str
    vram_total_mb: int
    vram_used_mb: int
    vram_free_mb: int
    utilization_pct: float
    queue_depth: int


class DiscoveredWorker(TypedDict):
    """A discovered local worker instance."""

    name: str  # Canonical name (e.g., "ollama", "vllm")
    base_url: str  # Full base URL including port and /v1 path
    healthy: bool  # Whether the worker responds to health check
    models: list[str]  # List of available model IDs (dynamically enumerated)
    dynamic_models: bool  # Whether models were fetched from /v1/models at discovery time
    capabilities: dict[str, Any]  # Capabilities inferred from worker type
    gpu_info: GpuInfo | None  # GPU/VRAM metrics if available


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

# GPU/metrics endpoints per worker type
# These are best-effort — failure is silently ignored
GPU_ENDPOINTS = {
    "ollama": "/api/ps",  # Ollama process info including GPU usage
    "vllm": "/metrics",  # Prometheus text metrics
    "lmstudio": None,
    "litellm": None,
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
    """Probe a worker endpoint to check health and discover models dynamically."""
    endpoint, expected_key = HEALTH_CHECKS.get(worker_type, ("/v1/models", {"object": "list"}))
    url = f"{base_url.rstrip('/')}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                if expected_key.items() <= data.items():
                    models = []
                    if "data" in data and isinstance(data["data"], list):
                        models = [model.get("id", "") for model in data["data"] if model.get("id")]
                    return True, models
                return True, []
            return False, []
    except Exception as e:
        logger.debug("Worker probe failed for %s: %s", url, e)
        return False, []


async def probe_gpu_info(base_url: str, worker_type: str, timeout: float = 3.0) -> GpuInfo | None:
    """Probe GPU/VRAM metrics from a worker. Returns None on any failure."""
    gpu_endpoint = GPU_ENDPOINTS.get(worker_type)
    if not gpu_endpoint:
        return None

    url = f"{base_url.rstrip('/')}{gpu_endpoint}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None

            if worker_type == "ollama":
                # Ollama /api/ps returns running models with size_vram field
                data = response.json()
                models_running = data.get("models", [])
                if not models_running:
                    return None
                total_vram = sum(m.get("size_vram", 0) for m in models_running) // (1024 * 1024)
                queue = len(models_running)
                info: GpuInfo = {"vram_used_mb": total_vram, "queue_depth": queue}
                return info

            if worker_type == "vllm":
                # vLLM /metrics returns Prometheus text format
                text = response.text
                gpu_info: GpuInfo = {}
                for line in text.splitlines():
                    if line.startswith("#"):
                        continue
                    if "vllm:gpu_cache_usage_perc" in line:
                        try:
                            val = float(line.split()[-1])
                            gpu_info["utilization_pct"] = round(val * 100, 1)
                        except (ValueError, IndexError):
                            pass
                    if "vllm:num_requests_running" in line:
                        try:
                            gpu_info["queue_depth"] = int(float(line.split()[-1]))
                        except (ValueError, IndexError):
                            pass
                return gpu_info if gpu_info else None

    except Exception as e:
        logger.debug("GPU probe failed for %s: %s", url, e)

    return None


async def discover_local_workers(
    scan_ports: bool = True, check_grid: bool = True, timeout_per_worker: float = 3.0
) -> list[DiscoveredWorker]:
    """Discover local AI workers.

    Args:
        scan_ports: Whether to scan default ports for known worker types
        check_grid: Whether to check for fusionAIze Grid configuration
        timeout_per_worker: Timeout for each worker probe in seconds

    Returns:
        List of discovered workers with health status, dynamically enumerated models,
        and GPU metrics where available.
    """
    discovered: list[DiscoveredWorker] = []

    # 1. Scan default ports for known worker types
    if scan_ports:
        for worker_name, port in DEFAULT_PORTS.items():
            base_url = f"http://127.0.0.1:{port}/v1"
            logger.debug("Checking %s at %s", worker_name, base_url)

            if not await check_port_open("127.0.0.1", port, timeout=1.0):
                continue

            healthy, models = await probe_worker(base_url, worker_name, timeout_per_worker)
            gpu_info = await probe_gpu_info(base_url, worker_name, timeout=2.0) if healthy else None

            worker: DiscoveredWorker = {
                "name": worker_name,
                "base_url": base_url,
                "healthy": healthy,
                "models": models,
                "dynamic_models": len(models) > 0,
                "capabilities": {
                    "local": True,
                    "cloud": False,
                    "network_zone": "local",
                    "cost_tier": "local",
                    "latency_tier": "local",
                },
                "gpu_info": gpu_info,
            }
            discovered.append(worker)

            if healthy:
                model_count = len(models)
                gpu_note = f", GPU: {gpu_info}" if gpu_info else ""
                logger.info(
                    "Discovered healthy %s worker at %s (%d model(s)%s)",
                    worker_name,
                    base_url,
                    model_count,
                    gpu_note,
                )
            else:
                logger.debug("Found %s worker at %s but health check failed", worker_name, base_url)

    # 2. Check for fusionAIze Grid configuration
    if check_grid:
        grid_workers = await discover_grid_workers(timeout_per_worker)
        discovered.extend(grid_workers)

    return discovered


async def discover_grid_workers(timeout: float = 5.0) -> list[DiscoveredWorker]:
    """Discover workers configured via fusionAIze Grid.

    Reads Grid configuration from:
    - ~/.faigrid/config.json  (primary JSON config)
    - ~/.faigrid/state/worker.state  (key=value state file, legacy)
    """
    grid_workers: list[DiscoveredWorker] = []

    # Primary: ~/.faigrid/config.json
    config_path = os.path.expanduser("~/.faigrid/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)

            for entry in config.get("workers", []):
                worker_type = entry.get("type", "openai-compat")
                host = entry.get("host", "127.0.0.1")
                port = entry.get("port")
                name = entry.get("name", f"grid-{worker_type}")

                if not port:
                    logger.debug("Grid config entry '%s' missing port, skipping", name)
                    continue

                base_url = entry.get("base_url") or f"http://{host}:{port}/v1"
                healthy, models = await probe_worker(base_url, worker_type, timeout)
                gpu_info = await probe_gpu_info(base_url, worker_type, timeout=2.0) if healthy else None

                worker: DiscoveredWorker = {
                    "name": name,
                    "base_url": base_url,
                    "healthy": healthy,
                    "models": models or entry.get("models", []),
                    "dynamic_models": len(models) > 0,
                    "capabilities": {
                        "local": True,
                        "cloud": False,
                        "network_zone": entry.get("network_zone", "local"),
                        "cost_tier": entry.get("cost_tier", "local"),
                        "latency_tier": "local",
                    },
                    "gpu_info": gpu_info,
                }
                grid_workers.append(worker)

            if grid_workers:
                logger.info("Grid config: found %d worker(s) in %s", len(grid_workers), config_path)
        except Exception as e:
            logger.debug("Failed to read Grid config %s: %s", config_path, e)

    # Fallback: ~/.faigrid/state/worker.state (key=value format)
    state_path = os.path.expanduser("~/.faigrid/state/worker.state")
    if os.path.exists(state_path) and not grid_workers:
        try:
            with open(state_path) as f:
                state: dict[str, str] = {}
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        key, value = line.split("=", 1)
                        state[key.strip()] = value.strip()

            if "WORKER_ENDPOINTS" in state:
                for endpoint in state["WORKER_ENDPOINTS"].split(","):
                    endpoint = endpoint.strip()
                    if not endpoint:
                        continue
                    # Format: worker_type:host:port
                    parts = endpoint.split(":")
                    if len(parts) >= 3:
                        worker_type, host, port_str = parts[0], parts[1], parts[2]
                        base_url = f"http://{host}:{port_str}/v1"
                        healthy, models = await probe_worker(base_url, worker_type, timeout)
                        gpu_info = await probe_gpu_info(base_url, worker_type, timeout=2.0) if healthy else None

                        worker = {
                            "name": f"grid-{worker_type}",
                            "base_url": base_url,
                            "healthy": healthy,
                            "models": models,
                            "dynamic_models": len(models) > 0,
                            "capabilities": {
                                "local": True,
                                "cloud": False,
                                "network_zone": "local",
                                "cost_tier": "local",
                                "latency_tier": "local",
                            },
                            "gpu_info": gpu_info,
                        }
                        grid_workers.append(worker)
        except Exception as e:
            logger.debug("Failed to read Grid state %s: %s", state_path, e)

    return grid_workers


def generate_provider_config(worker: DiscoveredWorker) -> dict[str, Any]:
    """Generate a provider configuration entry for a discovered worker."""
    base_def = LOCAL.get(worker["name"])

    config: dict[str, Any] = {
        "contract": "local-worker",
        "backend": "openai-compat",
        "base_url": worker["base_url"],
        "tier": "local",
        "capabilities": worker["capabilities"],
    }

    # Prefer dynamically enumerated model over static default
    if worker["models"]:
        config["model"] = worker["models"][0]
        if len(worker["models"]) > 1:
            config["available_models"] = worker["models"]
    elif base_def and "example_model" in base_def:
        config["model"] = base_def["example_model"]

    if worker.get("gpu_info"):
        config["gpu_info"] = worker["gpu_info"]

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
            model_note = (
                f", {len(worker['models'])} models (dynamic)"
                if worker["dynamic_models"]
                else (f", {len(worker['models'])} models" if worker["models"] else "")
            )
            print(f"  {status} {worker['name']}: {worker['base_url']}{model_note}")

            if worker["models"]:
                print(f"    Models: {', '.join(worker['models'][:5])}")
                if len(worker["models"]) > 5:
                    print(f"    ... and {len(worker['models']) - 5} more")

            if worker.get("gpu_info"):
                gpu = worker["gpu_info"]
                parts = []
                if "vram_used_mb" in gpu:
                    parts.append(f"VRAM used: {gpu['vram_used_mb']}MB")
                if "utilization_pct" in gpu:
                    parts.append(f"GPU: {gpu['utilization_pct']}%")
                if "queue_depth" in gpu:
                    parts.append(f"queue: {gpu['queue_depth']}")
                if parts:
                    print(f"    GPU: {', '.join(parts)}")


if __name__ == "__main__":
    asyncio.run(main())
