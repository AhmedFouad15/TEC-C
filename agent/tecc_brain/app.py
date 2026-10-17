"""FastAPI entrypoint for the Tec-C Brain."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tecc_brain import __version__
from tecc_brain.api import insight, mandate, options, profile, risk
from tecc_brain.api.deps import allowed_origins, require_client
from tecc_brain.monitor.hourly import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()  # no-op unless TECC_ENABLE_HOURLY_MONITOR=1
    yield
    stop_scheduler()


app = FastAPI(
    title="Tec-C Brain",
    version=__version__,
    description="Cognitive planner and risk engine for the Tec-C agent wallet (Member 2).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
for module in (mandate, risk, profile, insight, options):
    app.include_router(module.router, dependencies=[Depends(require_client)])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
