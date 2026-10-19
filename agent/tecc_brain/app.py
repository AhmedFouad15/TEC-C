"""FastAPI entrypoint for the Tec-C Brain."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os

from tecc_brain import __version__
from tecc_brain.api import arbitrage, biometrics, insight, mandate, options, profile, risk, settings, vault
from tecc_brain.api.deps import allowed_origins, require_client
from tecc_brain.monitor.hourly import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    network = os.environ.get("TECC_NETWORK", "anvil").strip().lower()
    auto_fisco = os.environ.get(
        "TECC_AUTO_START_FISCO", "1" if network == "fisco_bcos" else "0"
    ).lower() in ("1", "true", "yes")
    fisco_started = False
    if auto_fisco:
        from tecc_brain.onchain.fisco_node import ensure_fisco_node_running
        fisco_started = ensure_fisco_node_running()

    start_scheduler()  # no-op unless TECC_ENABLE_HOURLY_MONITOR=1
    try:
        yield
    finally:
        stop_scheduler()
        if fisco_started or os.environ.get("TECC_STOP_FISCO_ON_SHUTDOWN", "0").lower() in ("1", "true", "yes"):
            from tecc_brain.onchain.fisco_node import stop_fisco_node
            stop_fisco_node()


app = FastAPI(
    title="Tec-C Brain",
    version=__version__,
    description="Cognitive planner and risk engine for the Tec-C agent wallet (Member 2).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
from tecc_brain.virtual_session.admin_router import router as virtual_session_admin_router

for module in (mandate, risk, profile, insight, options, arbitrage, biometrics, settings, vault):
    app.include_router(module.router, dependencies=[Depends(require_client)])

app.include_router(virtual_session_admin_router, dependencies=[Depends(require_client)])


from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


# The web UI (landing page, Command Center, assets) from the same port. Mounted last, so every API route above wins.
if WEB_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
