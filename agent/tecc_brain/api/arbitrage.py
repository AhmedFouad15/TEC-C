"""/api/arbitrage/*: User-toggleable autonomous PegGuard de-peg arbitrage control & stateful watermark scanner.

PegGuard Arbitrage is NOT a manual free-text user command:
- The user simply toggles `enabled: true | false` at any time via `POST /api/arbitrage/toggle`.
- When enabled, the bot continuously monitors the 24-asset 4-category PegGuard universe across Ethereum L1,
  Arbitrum L2, and FISCO BCOS to detect de-pegs.
- When a de-peg is found and evaluated through the 5-layer PegGuard engine:
  * If unprofitable, the bot records an `UnprofitableWatermark` at the current price so it does not re-evaluate
    the same unprofitable trade every second — it only re-checks when the price drops strictly lower.
  * If profitable, it clears the watermark and routes the two-leg arbitrage trade through `PegGuardArbitrageExecutor`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account, get_store
from tecc_brain.learning.store import ProfileStore
from tecc_brain.pegguard import (
    PEGGUARD_ASSET_CATALOG,
    PegGuardAssetSpec,
    PegGuardAutonomousScanner,
    ScanTickReport,
    UnprofitableWatermark,
)

router = APIRouter(prefix="/api/arbitrage", tags=["arbitrage"])

_SCANNER = PegGuardAutonomousScanner()


def get_arbitrage_scanner(store: ProfileStore = Depends(get_store)) -> PegGuardAutonomousScanner:
    _SCANNER.store = store
    return _SCANNER


class ToggleArbitrageRequest(BaseModel):
    account: Account = "demo"
    enabled: bool = Field(description="True to enable continuous PegGuard de-peg arbitrage; False to disable at any time")


class ArbitrageStatusResponse(BaseModel):
    account: str
    enabled: bool
    monitored_assets_count: int
    active_watermarks: dict[str, UnprofitableWatermark]


class ScanArbitrageRequest(BaseModel):
    account: Account = "demo"
    order_size_usd: float = Field(250.0, gt=0, le=1_000_000.0)
    price_overrides: dict[str, float] | None = Field(
        None, description="Optional map of symbol -> current ratio R_direct(t) to inspect"
    )
    symbols: list[str] | None = Field(
        None, description="Optional subset of symbols to scan (defaults to all 24 assets in PEGGUARD_ASSET_CATALOG)"
    )


@router.post("/toggle", response_model=ArbitrageStatusResponse)
def toggle_arbitrage(
    req: ToggleArbitrageRequest,
    scanner: PegGuardAutonomousScanner = Depends(get_arbitrage_scanner),
) -> ArbitrageStatusResponse:
    """Enables or disables the autonomous PegGuard arbitrage bot for `req.account` at any time."""
    enabled = scanner.set_enabled(req.account, req.enabled)
    return ArbitrageStatusResponse(
        account=req.account,
        enabled=enabled,
        monitored_assets_count=len(PEGGUARD_ASSET_CATALOG),
        active_watermarks=scanner.get_watermarks(req.account),
    )


@router.get("/status", response_model=ArbitrageStatusResponse)
def arbitrage_status(
    account: Account = "demo",
    scanner: PegGuardAutonomousScanner = Depends(get_arbitrage_scanner),
) -> ArbitrageStatusResponse:
    """Returns whether autonomous PegGuard arbitrage is enabled for `account` and any active unprofitable watermarks."""
    return ArbitrageStatusResponse(
        account=account,
        enabled=scanner.is_enabled(account),
        monitored_assets_count=len(PEGGUARD_ASSET_CATALOG),
        active_watermarks=scanner.get_watermarks(account),
    )


@router.get("/assets", response_model=dict[str, PegGuardAssetSpec])
def arbitrage_assets() -> dict[str, PegGuardAssetSpec]:
    """Returns the complete 24-asset 4-category PegGuard catalog across Ethereum L1, Arbitrum L2, and FISCO BCOS."""
    return PEGGUARD_ASSET_CATALOG


@router.post("/scan", response_model=ScanTickReport)
def scan_arbitrage(
    req: ScanArbitrageRequest,
    scanner: PegGuardAutonomousScanner = Depends(get_arbitrage_scanner),
) -> ScanTickReport:
    """Executes one autonomous PegGuard de-peg scan pass (only runs if `enabled == True` for `req.account`)."""
    return scanner.scan_tick(
        req.account,
        price_overrides=req.price_overrides,
        symbols=req.symbols,
        order_size_usd=req.order_size_usd,
    )
