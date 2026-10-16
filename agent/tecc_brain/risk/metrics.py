"""Sharpe ratio and 95% CVaR from the same model the score uses — shown on every card, never used to decide.

One-year return R (in units of the deposited asset) is a mixture:
    with probability 1 − PD:  Normal(μ, σ)   μ = APY − entry cost, σ = the venue's normal-times volatility
    with probability PD:      −LGD           permanent impairment (PD already includes live regime failure risk)

    Sharpe = (E[R] − hurdle) / sd(R)            hurdle = 1Y Shibor, as in the score
    CVaR95 = −E[R | R in its worst 5%]          a positive number is an average loss in the worst years

Why the score, not Sharpe, decides: Sharpe counts upside as risk and, with thin tails, hides the impairment jump;
CVaR sees the jump, and the score prices it with the user's own loss aversion λ.
"""

from __future__ import annotations

import math
from statistics import NormalDist

from pydantic import BaseModel

CVAR_LEVEL = 0.95
_MIN_SIGMA = 1e-9
_N = NormalDist()


class RiskMetrics(BaseModel):
    mean: float
    sd: float
    sharpe: float | None
    cvar_95: float


def mixture_moments(mu: float, sigma: float, pd: float, lgd: float) -> tuple[float, float]:
    mean = (1 - pd) * mu + pd * -lgd
    second = (1 - pd) * (sigma**2 + mu**2) + pd * lgd**2
    return mean, math.sqrt(max(0.0, second - mean**2))


def sharpe(mu: float, sigma: float, pd: float, lgd: float, hurdle: float) -> float | None:
    mean, sd = mixture_moments(mu, sigma, pd, lgd)
    return None if sd < _MIN_SIGMA else (mean - hurdle) / sd


def cvar(mu: float, sigma: float, pd: float, lgd: float, level: float = CVAR_LEVEL) -> float:
    """Expected shortfall of the mixture, solved in closed form (no simulation, deterministic)."""
    alpha = 1.0 - level
    sigma = max(sigma, _MIN_SIGMA)
    atom = -lgd
    w = 1.0 - pd

    def normal_mass(v: float) -> float:
        return w * _N.cdf((v - mu) / sigma)

    def normal_partial(v: float) -> float:
        """E[R; R ≤ v] over the normal part."""
        z = (v - mu) / sigma
        return w * (mu * _N.cdf(z) - sigma * _N.pdf(z))

    def normal_quantile(mass: float) -> float:
        return mu + sigma * _N.inv_cdf(min(max(mass / w, 1e-12), 1 - 1e-12))

    below_atom = normal_mass(atom)
    if pd <= 0 or below_atom >= alpha:  # the tail is all normal years, worse than the impairment
        v = normal_quantile(alpha)
        tail_sum = normal_partial(v)
    elif below_atom + pd >= alpha:  # the impairment sits at the 5% line: take part of it
        tail_sum = normal_partial(atom) + (alpha - below_atom) * atom
    else:  # the whole impairment plus the worst normal years
        v = normal_quantile(alpha - pd)
        tail_sum = pd * atom + normal_partial(v)
    return -tail_sum / alpha


def risk_metrics(mu: float, sigma: float, pd: float, lgd: float, hurdle: float) -> RiskMetrics:
    mean, sd = mixture_moments(mu, sigma, pd, lgd)
    return RiskMetrics(mean=mean, sd=sd, sharpe=sharpe(mu, sigma, pd, lgd, hurdle), cvar_95=cvar(mu, sigma, pd, lgd))
