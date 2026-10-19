"""/api/settings: what the web app's Settings screen shows and toggles.

GET  /api/settings            AI providers and models in use, and the live X Search toggle (never any API key)
PUT  /api/settings/x-search   {"enabled": true|false|null}: flip live X Search at runtime; null = back to the env value

The runtime toggle lasts until the API restarts (TECC_ENABLE_X_SEARCH is the default at startup). Like every /api
route it is behind `require_client`: loopback only, or `Authorization: Bearer $TECC_API_TOKEN`.
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from tecc_brain.graph.brain_llm import brain_model, provider_for
from tecc_brain.sentinel import grok

router = APIRouter(prefix="/api/settings", tags=["settings"])

X_SEARCH_PRICE_NOTE = "Billed by xAI per post returned ($5 per 1,000 posts) on top of tokens."


class XSearchSetting(BaseModel):
    enabled: bool = Field(description="Whether the Sentinel's X-pulse calls attach xAI's live x_search tool")
    source: Literal["env", "runtime"] = Field(description="'env' = TECC_ENABLE_X_SEARCH; 'runtime' = set via this API")
    env_default: bool = Field(description="TECC_ENABLE_X_SEARCH, the value after a restart")
    available: bool = Field(description="False while GROK_API_KEY is unset: the Sentinel then runs offline anyway")
    price_note: str = X_SEARCH_PRICE_NOTE


class ModelSetting(BaseModel):
    configured: bool = Field(description="An API key is set; otherwise this component runs its offline fallback")
    provider: Literal["xai", "gemini"]
    model: str


class SettingsView(BaseModel):
    x_search: XSearchSetting
    sentinel: ModelSetting
    brain: ModelSetting
    pegguard: Literal["deterministic"] = Field("deterministic", description="PegGuard never calls an LLM (Math > AI)")


class XSearchUpdate(BaseModel):
    enabled: bool | None = Field(description="true/false to override; null to return to TECC_ENABLE_X_SEARCH")


def _x_search() -> XSearchSetting:
    return XSearchSetting(enabled=grok.x_search_enabled(), source=grok.x_search_source(),
                          env_default=grok.x_search_env_default(), available=bool(os.environ.get("GROK_API_KEY")))


@router.get("", response_model=SettingsView)
def get_settings() -> SettingsView:
    model = brain_model()
    return SettingsView(
        x_search=_x_search(),
        sentinel=ModelSetting(configured=bool(os.environ.get("GROK_API_KEY")), provider="xai", model=grok.GROK_MODEL),
        brain=ModelSetting(configured=bool(os.environ.get("TECC_BRAIN_LLM_KEY")),
                           provider=provider_for(model, os.environ.get("TECC_BRAIN_LLM_URL")), model=model),
    )


@router.put("/x-search", response_model=XSearchSetting)
def set_x_search(req: XSearchUpdate) -> XSearchSetting:
    grok.set_x_search(req.enabled)
    return _x_search()


class PinStatus(BaseModel):
    configured: bool
    configured_at: float | None = None
    last_used_at: float | None = None


class PinUpdate(BaseModel):
    pin: str = Field(min_length=4, max_length=32, description="4 to 32 digit/character security PIN")


@router.get("/pin", response_model=PinStatus)
def get_pin_status() -> PinStatus:
    from tecc_brain.security_pin import get_pin_info
    return PinStatus(**get_pin_info())


@router.post("/pin", response_model=PinStatus)
def update_pin(req: PinUpdate) -> PinStatus:
    from tecc_brain.security_pin import get_pin_info, set_pin
    set_pin(req.pin)
    return PinStatus(**get_pin_info())


@router.delete("/pin")
def delete_pin() -> dict[str, str]:
    from tecc_brain.security_pin import remove_pin
    remove_pin()
    return {"status": "ok"}

