"""Replay the News Risk Sentinel on the three historical de-pegs and rank its weightings (review Finding D).

    .venv/bin/python scripts/backtest_sentinel.py            # 5% grid, both formulas
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tecc_brain.reference import load_reference  # noqa: E402
from tecc_brain.strategy.sentinel_backtest import CURRENT, evaluate, grid_search  # noqa: E402


def row(label: str, r) -> str:
    p = r.pnl
    return (f"{label:36s} {p['usdc_svb_2023'] * 100:+6.1f}% {p['steth_celsius_2022'] * 100:+6.1f}% "
            f"{p['ust_2022'] * 100:+6.1f}%   {r.calm_bias:+.3f}   {r.calm_autonomy:5.0%}   {r.ust_warning}")


def main() -> None:
    ref = load_reference()
    print(f"{'weighting (CoinGlass, FinBERT, Grok)':36s} {'USDC':>7s} {'stETH':>7s} {'UST':>7s}   bias    auton.  UST warning")
    print(row("no sentinel (regime model alone)", evaluate(None, ref)))
    print(row("original: linear (.45, .30, .25)", evaluate((0.45, 0.30, 0.25), ref, mode="linear")))
    print(row(f"shipped: anchored {CURRENT}", evaluate(CURRENT, ref, mode="anchored")))
    print("\ntop of the 462-weighting grid (calibration first, then autonomy, then worst-episode P&L):")
    for r in grid_search(0.05, ref=ref)[:5]:
        print(row(f"{r.mode} {r.weights}", r))


if __name__ == "__main__":
    main()
