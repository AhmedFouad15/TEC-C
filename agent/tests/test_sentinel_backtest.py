"""Finding D: the News Risk Sentinel's weights, replayed on USDC-SVB, stETH-Celsius and UST."""

import pytest

from tecc_brain.reference import load_reference, read_data_json
from tecc_brain.sentinel import blended
from tecc_brain.strategy.sentinel_backtest import (
    CURRENT,
    MAX_CALM_BIAS,
    evaluate,
    grid_search,
    sentinel_hook,
    simplex,
)

REF = load_reference()
BASELINE = evaluate(None, REF)
OLD_WEIGHTS = (0.45, 0.30, 0.25)


def test_every_episode_day_has_sentinel_inputs():
    for e in read_data_json("backtests.json")["episodes"]:
        for p in e["points"]:
            assert 0 <= p["fear_greed"] <= 100 and p["headline"]


def test_shipped_defaults_are_calibrated_and_never_hurt_the_brain():
    assert blended.TOKEN_P_NEGATIVE_MODE == "anchored" and CURRENT == (0.30, 0.50, 0.20)
    r = evaluate(CURRENT, REF)
    assert abs(r.calm_bias) <= MAX_CALM_BIAS
    assert r.calm_autonomy == BASELINE.calm_autonomy
    for ep, pnl in r.pnl.items():
        assert pnl >= BASELINE.pnl[ep] - 1e-9, ep


def test_the_original_linear_formula_reads_silence_as_bad_news():
    r = evaluate(OLD_WEIGHTS, REF, mode="linear")
    assert r.calm_bias > 0.15
    assert r.calm_autonomy < BASELINE.calm_autonomy  # the Brain loses its autonomy on calm days


def test_hard_veto_on_the_svb_day_does_not_force_a_panic_sale():
    hook = sentinel_hook("usdc_svb_2023", CURRENT, REF)
    svb_day = next(p for e in read_data_json("backtests.json")["episodes"] if e["id"] == "usdc_svb_2023"
                   for p in e["points"] if p["date"] == "2023-03-11")
    assert hook(svb_day, "USDC") == 1.0  # the gate fires on "de-pegs … stuck at failed SVB"
    assert evaluate(CURRENT, REF).pnl["usdc_svb_2023"] == pytest.approx(BASELINE.pnl["usdc_svb_2023"])


def test_the_best_ranked_weighting_is_calibrated():
    best = grid_search(0.1, ref=REF)[0]
    assert abs(best.calm_bias) <= MAX_CALM_BIAS and best.calm_autonomy == BASELINE.calm_autonomy


def test_simplex_covers_all_weightings():
    grid = simplex(0.05)
    assert len(grid) == 231 and all(abs(sum(w) - 1) < 1e-9 for w in grid)
