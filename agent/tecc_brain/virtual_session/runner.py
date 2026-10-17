"""Virtual Session Concurrent Runner (Section 8).

Runs two separate uvicorn instances:
  - Admin App: 127.0.0.1:8000 (NEVER tunneled)
  - Mobile Gateway: 127.0.0.1:8001 (tunneled to Cloudflare)
"""

from __future__ import annotations

import asyncio
import sys
import uvicorn


async def run_dual_servers(
    admin_host: str = "127.0.0.1",
    admin_port: int = 8000,
    gateway_host: str = "127.0.0.1",
    gateway_port: int = 8001,
) -> None:
    from tecc_brain.app import app as admin_app
    from tecc_brain.virtual_session.gateway import gateway_app

    config_admin = uvicorn.Config(admin_app, host=admin_host, port=admin_port, log_level="info")
    config_gateway = uvicorn.Config(gateway_app, host=gateway_host, port=gateway_port, log_level="info")

    server_admin = uvicorn.Server(config_admin)
    server_gateway = uvicorn.Server(config_gateway)

    await asyncio.gather(
        server_admin.serve(),
        server_gateway.serve(),
    )


def main() -> None:
    try:
        asyncio.run(run_dual_servers())
    except KeyboardInterrupt:
        print("\n[VirtualSession] Servers stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
