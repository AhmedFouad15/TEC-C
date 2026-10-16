"""Five-question onboarding quiz → risk tier and a personal λ prior, so a new user doesn't start on a generic default.

Points 0/1/2 per answer (0 = most cautious). 0–3 Conservative, 4–7 Balanced, 8–10 Aggressive. Inside the tier,
λ = tier start × (1.25 − 0.5·frac), where frac is how far the points sit inside the tier's range, then banded.
Money needed within 3 months is never put in the Aggressive tier.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel

from tecc_brain.learning.update import clamp_lambda, new_profile
from tecc_brain.models import LAMBDA_START, BrainProfile, RiskTier


class QuizOption(BaseModel):
    id: str
    text: str
    points: int


class QuizQuestion(BaseModel):
    id: str
    text: str
    options: list[QuizOption]


def _q(qid: str, text: str, *options: tuple[str, str]) -> QuizQuestion:
    return QuizQuestion(id=qid, text=text, options=[QuizOption(id=o, text=t, points=i) for i, (o, t) in enumerate(options)])


QUIZ: tuple[QuizQuestion, ...] = (
    _q("horizon", "When might you need this money back?",
       ("soon", "Within 3 months"), ("year", "In 3–12 months"), ("long", "Not for over a year")),
    _q("drawdown", "Your portfolio falls 20% in a week. What do you do?",
       ("sell", "Sell to stop the loss"), ("wait", "Wait and see"), ("buy", "Buy more while it's cheap")),
    _q("gamble", "Which one-year outcome would you pick?",
       ("sure", "A sure +3%"), ("mild", "50/50: +10% or −2%"), ("bold", "50/50: +25% or −10%")),
    _q("experience", "How familiar are you with DeFi?",
       ("none", "I've never used it"), ("some", "I've used a few apps"), ("weekly", "I use DeFi every week")),
    _q("depeg", "USDC drops to $0.90 on scary news. What do you do?",
       ("exit", "Sell it all now"), ("hold", "Hold if the reserves are fine"), ("buy", "Buy the discount")),
)

TIER_POINTS: dict[RiskTier, tuple[int, int]] = {
    RiskTier.CONSERVATIVE: (0, 3),
    RiskTier.BALANCED: (4, 7),
    RiskTier.AGGRESSIVE: (8, 10),
}


class OnboardingResult(BaseModel):
    tier: RiskTier
    lam: float
    points: int
    rationale: list[str]


def score_quiz(answers: Mapping[str, str]) -> OnboardingResult:
    questions = {q.id: q for q in QUIZ}
    if set(answers) != set(questions):
        raise ValueError(f"answer exactly these questions: {sorted(questions)}")
    chosen: dict[str, QuizOption] = {}
    for qid, oid in answers.items():
        option = next((o for o in questions[qid].options if o.id == oid), None)
        if option is None:
            raise ValueError(f"unknown option {oid!r} for question {qid!r}")
        chosen[qid] = option

    points = sum(o.points for o in chosen.values())
    tier = next(t for t, (lo, hi) in TIER_POINTS.items() if lo <= points <= hi)
    rationale = [f"{points}/10 points → {tier.name.title()}."]
    if chosen["horizon"].id == "soon" and tier == RiskTier.AGGRESSIVE:
        tier = RiskTier.BALANCED
        rationale.append("You may need the money within 3 months, so the Aggressive tier is off the table.")

    lo, hi = TIER_POINTS[tier]
    frac = (min(max(points, lo), hi) - lo) / (hi - lo)
    lam = clamp_lambda(tier, LAMBDA_START[tier] * (1.25 - 0.5 * frac))
    rationale.append(
        f"Loss aversion λ = {lam:.2f}: each $1 of expected loss counts as ${1 + lam:.2f} when the Brain compares options."
    )
    if chosen["depeg"].id == "exit":
        rationale.append("You'd sell a de-pegged stablecoin at once; the Brain will still explain when a dip is temporary.")
    return OnboardingResult(tier=tier, lam=lam, points=points, rationale=rationale)


def onboard(account: str, answers: Mapping[str, str]) -> BrainProfile:
    result = score_quiz(answers)
    return new_profile(account, result.tier).model_copy(update={"lam": result.lam})
