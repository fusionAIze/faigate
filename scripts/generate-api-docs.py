#!/usr/bin/env python3
"""Generate API.md from OpenAPI specification.

This script extracts the OpenAPI spec from the FastAPI application and
generates a Markdown documentation file.

Usage:
    python scripts/generate-api-docs.py
"""

import json
import sys
from pathlib import Path

# Add the project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import after path setup
try:
    from faigate.main import app
except ImportError as e:
    print(f"Error importing faigate.main: {e}")
    sys.exit(1)


def generate_markdown_from_openapi(openapi_spec: dict) -> str:
    """Convert OpenAPI spec to Markdown documentation."""
    lines = []

    # Title
    lines.append(f"# {openapi_spec.get('info', {}).get('title', 'API Reference')}")
    lines.append("")

    # Description
    description = openapi_spec.get("info", {}).get("description", "")
    if description:
        lines.append(description)
        lines.append("")

    # Servers
    servers = openapi_spec.get("servers", [])
    if servers:
        lines.append("## Servers")
        lines.append("")
        for server in servers:
            lines.append(f"- `{server.get('url', '')}`")
            if server.get("description"):
                lines.append(f"  - {server['description']}")
        lines.append("")

    # Paths
    paths = openapi_spec.get("paths", {})
    if paths:
        lines.append("## Endpoints")
        lines.append("")

        for path, methods in sorted(paths.items()):
            lines.append(f"### `{path}`")
            lines.append("")

            for method, details in methods.items():
                lines.append(f"#### `{method.upper()}`")
                lines.append("")

                # Summary and description
                summary = details.get("summary", "")
                description = details.get("description", "")
                if summary:
                    lines.append(f"**{summary}**")
                    lines.append("")
                if description:
                    lines.append(description)
                    lines.append("")

                # Parameters
                parameters = details.get("parameters", [])
                if parameters:
                    lines.append("**Parameters:**")
                    lines.append("")
                    for param in parameters:
                        param_name = param.get("name", "")
                        param_in = param.get("in", "")
                        param_desc = param.get("description", "")
                        param_required = param.get("required", False)
                        required_str = "required" if param_required else "optional"
                        lines.append(f"- `{param_name}` ({param_in}, {required_str})")
                        if param_desc:
                            lines.append(f"  - {param_desc}")
                    lines.append("")

                # Request body
                request_body = details.get("requestBody", {})
                if request_body:
                    lines.append("**Request Body:**")
                    lines.append("")
                    content = request_body.get("content", {})
                    for content_type, media_type in content.items():
                        lines.append(f"- `{content_type}`")
                        schema = media_type.get("schema", {})
                        if schema:
                            # Simplified schema representation
                            lines.append(f"  - Schema: {json.dumps(schema, indent=2)}")
                    lines.append("")

                # Responses
                responses = details.get("responses", {})
                if responses:
                    lines.append("**Responses:**")
                    lines.append("")
                    for status_code, response in responses.items():
                        lines.append(f"- `{status_code}`")
                        desc = response.get("description", "")
                        if desc:
                            lines.append(f"  - {desc}")
                    lines.append("")

                # Security
                security = details.get("security", [])
                if security:
                    lines.append("**Security:**")
                    lines.append("")
                    for sec in security:
                        for scheme, scopes in sec.items():
                            lines.append(f"- `{scheme}`: {', '.join(scopes)}")
                    lines.append("")

                lines.append("---")
                lines.append("")

    return "\n".join(lines)


def main():
    """Main entry point."""
    # Get OpenAPI spec
    openapi_spec = app.openapi()

    # Generate Markdown
    markdown = generate_markdown_from_openapi(openapi_spec)

    # Write to docs/API.md
    output_path = project_root / "docs" / "API.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"Generated API documentation at {output_path}")
    print(f"Total paths documented: {len(openapi_spec.get('paths', {}))}")


if __name__ == "__main__":
    main()
