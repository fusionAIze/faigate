"""Performance benchmarks for fusionAIze Gate critical paths.

These benchmarks measure the performance of key operations to detect regressions.
Run with: pytest tests/benchmarks/test_performance.py --benchmark-only
"""

import time
import pytest
from pathlib import Path
import sys
import types

# Set up mock environment before imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Mock httpx before importing our modules
_httpx = types.ModuleType("httpx")
_httpx.Timeout = type("Timeout", (), {"__init__": lambda *a, **kw: None})
_httpx.Limits = type("Limits", (), {"__init__": lambda *a, **kw: None})
_httpx.AsyncClient = type(
    "AsyncClient",
    (),
    {
        "__init__": lambda *a, **kw: None,
        "aclose": lambda self: None,
    },
)
sys.modules["httpx"] = _httpx

# Import faigate modules after mocking
from faigate import config
from faigate.providers import ProviderCatalog
from faigate.routing import Router


@pytest.fixture
def sample_catalog():
    """Create a sample provider catalog for benchmarking."""
    catalog = ProviderCatalog()
    # Add mock providers
    catalog._providers = {
        "openai": {
            "id": "openai",
            "name": "OpenAI",
            "enabled": True,
            "capabilities": ["chat", "completions"],
            "cost_per_token": 0.000001,
        },
        "anthropic": {
            "id": "anthropic",
            "name": "Anthropic",
            "enabled": True,
            "capabilities": ["chat", "claude"],
            "cost_per_token": 0.0000015,
        },
        "local": {
            "id": "local",
            "name": "Local",
            "enabled": True,
            "capabilities": ["chat"],
            "cost_per_token": 0.0,
        },
    }
    return catalog


@pytest.fixture
def sample_router(sample_catalog):
    """Create a router with sample catalog."""
    return Router(catalog=sample_catalog)


def test_router_initialization(benchmark):
    """Benchmark router initialization time."""

    def init_router():
        catalog = ProviderCatalog()
        catalog._providers = {"test": {"id": "test", "enabled": True}}
        return Router(catalog=catalog)

    result = benchmark(init_router)
    assert result is not None


def test_provider_selection(benchmark, sample_router):
    """Benchmark provider selection algorithm."""

    def select_provider():
        return sample_router.select_provider(model="gpt-4", capabilities=["chat"], max_cost=0.01)

    result = benchmark(select_provider)
    assert result in ("openai", "anthropic", "local", None)


def test_config_loading(benchmark):
    """Benchmark configuration loading from YAML."""
    # Create a minimal config YAML content
    config_content = """
providers:
  - id: test
    name: Test Provider
    enabled: true
    api_key: "test-key"
    base_url: "https://api.test.com"
"""
    config_path = Path("/tmp/test_config.yaml")
    config_path.write_text(config_content)

    def load_config():
        return config.load_config(str(config_path))

    result = benchmark(load_config)
    assert result is not None
    config_path.unlink(missing_ok=True)


def test_cost_calculation(benchmark, sample_router):
    """Benchmark cost calculation for requests."""

    def calculate_cost():
        return sample_router.estimate_cost(provider_id="openai", input_tokens=100, output_tokens=50)

    result = benchmark(calculate_cost)
    assert isinstance(result, (int, float))


@pytest.mark.skip("Requires actual HTTP endpoints")
def test_request_routing_end_to_end(benchmark):
    """End-to-end request routing benchmark (requires mocked HTTP)."""
    # This would be more complex and require async mocking
    pass


if __name__ == "__main__":
    # Allow running directly for profiling
    pytest.main([__file__, "--benchmark-only"])
