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


@pytest.mark.skip("ProviderCatalog/Router removed in v2.x refactor")
def test_router_initialization(benchmark):
    pass


@pytest.mark.skip("ProviderCatalog/Router removed in v2.x refactor")
def test_provider_selection(benchmark):
    pass


def test_config_loading(benchmark):
    """Benchmark configuration loading from YAML."""
    config_content = """
providers:
  test-provider:
    backend: openai-compat
    base_url: https://api.test.com/v1
    api_key: test-key
    model: test-model
    tier: default
"""
    config_path = Path("/tmp/test_config.yaml")
    config_path.write_text(config_content)

    def load_config():
        return config.load_config(str(config_path))

    result = benchmark(load_config)
    assert result is not None
    config_path.unlink(missing_ok=True)


@pytest.mark.skip("Router.estimate_cost removed in v2.x refactor")
def test_cost_calculation(benchmark):
    pass


@pytest.mark.skip("Requires actual HTTP endpoints")
def test_request_routing_end_to_end(benchmark):
    """End-to-end request routing benchmark (requires mocked HTTP)."""
    # This would be more complex and require async mocking
    pass


if __name__ == "__main__":
    # Allow running directly for profiling
    pytest.main([__file__, "--benchmark-only"])
