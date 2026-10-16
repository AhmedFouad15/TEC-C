import json

import pytest

from tecc_brain.strategy.backtest import available_backtests, run_backtest


@pytest.fixture(scope="module")
def results():
    return {episode: run_backtest(episode) for episode in available_backtests()}


def test_all_three_episodes_are_available():
    assert set(available_backtests()) == {"usdc_svb_2023", "steth_celsius_2022", "ust_2022"}


def test_usdc_brain_holds_through_svb_and_beats_the_sentiment_rule(results):
    r = results["usdc_svb_2023"].strategies
    assert r["tec_c"].exited_at is None
    assert r["tec_c"].pnl_pct > r["sentiment_veto"].pnl_pct
    assert r["sentiment_veto"].pnl_pct == pytest.approx(-0.12)


def test_usdc_brain_buys_the_svb_discount(results):
    assert results["usdc_svb_2023"].strategies["tec_c"].bought_at == "2023-03-11"


def test_steth_brain_holds_and_waits_for_a_real_margin_of_safety(results):
    r = results["steth_celsius_2022"].strategies
    assert r["tec_c"].exited_at is None
    assert r["tec_c"].bought_at == "2022-06-13"
    assert r["tec_c"].pnl_pct > r["mean_reversion"].pnl_pct > r["sentiment_veto"].pnl_pct


def test_ust_brain_exits_before_the_collapse(results):
    result = results["ust_2022"]
    exit_step = next(s for s in result.steps if s.date == result.strategies["tec_c"].exited_at)
    assert exit_step.price >= 0.95


def test_ust_brain_beats_both_naive_rules(results):
    r = results["ust_2022"].strategies
    assert r["tec_c"].pnl_pct > r["sentiment_veto"].pnl_pct
    assert r["tec_c"].pnl_pct > r["mean_reversion"].pnl_pct
    assert r["mean_reversion"].pnl_pct < -0.8


def test_ust_brain_never_buys_the_dip(results):
    assert results["ust_2022"].strategies["tec_c"].bought_at is None


def test_results_serialise_for_the_api(results):
    for result in results.values():
        json.loads(result.model_dump_json())


def test_unknown_episode_is_rejected():
    with pytest.raises(KeyError):
        run_backtest("ftx_2022")
