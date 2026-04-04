#!/usr/bin/env python3
"""Run Claude Desktop validation with auto-started server."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def start_server() -> subprocess.Popen:
    """Start faigate server in background."""
    env = os.environ.copy()
    # Use default config (already modified)
    cmd = [sys.executable, "-m", "faigate"]
    print(f"Starting server: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )

    # Wait for server to be ready (check health endpoint)
    max_wait = 30
    for i in range(max_wait):
        if proc.poll() is not None:
            # Server died
            output = proc.stdout.read() if proc.stdout else ""
            print(f"Server exited early: {output}")
            raise RuntimeError("Server failed to start")

        # Try to connect
        try:
            import httpx

            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get("http://127.0.0.1:8090/health")
                if resp.status_code == 200:
                    print("Server is ready")
                    return proc
        except Exception:
            pass

        await asyncio.sleep(1)
        if i % 5 == 0:
            print(f"Waiting for server... ({i + 1}s)")

    raise RuntimeError("Server did not become ready in time")


async def stop_server(proc: subprocess.Popen) -> None:
    """Stop faigate server gracefully."""
    if proc.poll() is None:
        print("Stopping server...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Server did not terminate, killing...")
            proc.kill()
            proc.wait()


async def main() -> int:
    """Main validation runner."""
    server = None
    try:
        # Start server
        server = await start_server()

        # Run validation script
        validation_script = project_root / "scripts" / "validate-claude-desktop.py"
        if not validation_script.exists():
            print(f"Validation script not found: {validation_script}")
            return 1

        print("\n" + "=" * 70)
        print("Running Claude Desktop validation...")
        print("=" * 70)

        result = subprocess.run(
            [sys.executable, str(validation_script)],
            capture_output=True,
            text=True,
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        return result.returncode

    except Exception as e:
        print(f"Validation failed: {e}")
        return 1
    finally:
        if server:
            await stop_server(server)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
