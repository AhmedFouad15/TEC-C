from datetime import datetime, timezone

from tecc_brain.sentinel.cmc_feargreed import CmcFearGreedClient, FearGreedReading


def test_fear_greed_contrarian_vice_versa_scale():
    """Verifies that CMC Fear & Greed uses the contrarian ('vice versa') scale per project spec:
    - Extreme Greed (100) -> motivated to sell -> 0.0 (strong sell)
    - Extreme Fear (0) -> motivated to buy -> 1.0 (strong buy)
    - Neutral (50) -> 0.5 (neutral)
    """
    now = datetime.now(timezone.utc)
    
    # Extreme greed -> sell
    greed_100 = FearGreedReading(value=100, classification="Extreme Greed", as_of=now)
    assert greed_100.buy_sell_score == 0.0

    # High greed (80) -> sell
    greed_80 = FearGreedReading(value=80, classification="Greed", as_of=now)
    assert round(greed_80.buy_sell_score, 2) == 0.20

    # Neutral (50) -> neutral
    neutral_50 = FearGreedReading(value=50, classification="Neutral", as_of=now)
    assert neutral_50.buy_sell_score == 0.50

    # High fear (20) -> buy
    fear_20 = FearGreedReading(value=20, classification="Fear", as_of=now)
    assert round(fear_20.buy_sell_score, 2) == 0.80

    # Extreme fear (0) -> buy
    fear_0 = FearGreedReading(value=0, classification="Extreme Fear", as_of=now)
    assert fear_0.buy_sell_score == 1.0


def test_cmc_client_fallback_to_neutral():
    """When CMC_API_KEY is unset, client must safely degrade to 0.5 neutral reading."""
    client = CmcFearGreedClient(api_key=None)
    reading = client.fetch()
    assert reading.value == 50
    assert reading.classification == "Neutral"
    assert reading.buy_sell_score == 0.50
    assert "fallback" in reading.source
