"""FastAPI entrypoint for the Tec-C Brain."""

from fastapi import FastAPI

from tecc_brain import __version__

app = FastAPI(
    title="Tec-C Brain",
    version=__version__,
    description="Cognitive planner and risk engine for the Tec-C agent wallet (Member 2).",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
