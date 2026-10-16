"""FastAPI entrypoint for the Tec-C Brain."""

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tecc_brain import __version__
from tecc_brain.api import insight, mandate, profile, risk
from tecc_brain.api.deps import require_client

app = FastAPI(
    title="Tec-C Brain",
    version=__version__,
    description="Cognitive planner and risk engine for the Tec-C agent wallet (Member 2).",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("TECC_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)
for module in (mandate, risk, profile, insight):
    app.include_router(module.router, dependencies=[Depends(require_client)])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
