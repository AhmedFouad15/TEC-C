import pytest

from tecc_brain.learning.onboarding import QUIZ, onboard, score_quiz
from tecc_brain.models import LAMBDA_BANDS, RiskTier


def answers(points: list[int]) -> dict[str, str]:
    return {q.id: next(o.id for o in q.options if o.points == p) for q, p in zip(QUIZ, points)}


def test_quiz_has_five_questions_with_three_scored_options_and_stable_ids():
    assert len(QUIZ) == 5
    assert len({q.id for q in QUIZ}) == 5
    for q in QUIZ:
        assert sorted(o.points for o in q.options) == [0, 1, 2]


@pytest.mark.parametrize("points, tier, lam", [
    ([0, 0, 0, 0, 0], RiskTier.CONSERVATIVE, 3.75),
    ([1, 1, 1, 0, 0], RiskTier.CONSERVATIVE, 2.25),
    ([1, 1, 1, 1, 0], RiskTier.BALANCED, 1.25),
    ([2, 2, 1, 1, 1], RiskTier.BALANCED, 0.75),
    ([2, 2, 2, 2, 0], RiskTier.AGGRESSIVE, 0.375),
    ([2, 2, 2, 2, 2], RiskTier.AGGRESSIVE, 0.225),
])
def test_points_map_to_tier_and_lambda(points, tier, lam):
    result = score_quiz(answers(points))
    assert result.tier == tier and result.points == sum(points)
    assert result.lam == pytest.approx(lam)
    lo, hi = LAMBDA_BANDS[tier]
    assert lo <= result.lam <= hi
    assert result.rationale


def test_money_needed_soon_is_never_aggressive():
    result = score_quiz(answers([0, 2, 2, 2, 2]))
    assert result.points == 8 and result.tier == RiskTier.BALANCED


def test_unknown_or_missing_answers_are_rejected():
    good = answers([1, 1, 1, 1, 1])
    with pytest.raises(ValueError):
        score_quiz({k: v for k, v in list(good.items())[:4]})
    with pytest.raises(ValueError):
        score_quiz({**good, QUIZ[0].id: "nope"})
    with pytest.raises(ValueError):
        score_quiz({**good, "extra": "x"})


def test_onboard_builds_a_fresh_profile():
    profile = onboard("0x" + "cd" * 20, answers([2, 2, 2, 2, 2]))
    assert profile.tier == RiskTier.AGGRESSIVE and profile.lam == pytest.approx(0.225) and profile.tau == 0.6
