"""Token accounting and hard budget enforcement for OMEGA requests."""

from __future__ import annotations

from dataclasses import dataclass

from omega.llm_models.gateway import TokenEstimator


class TokenBudgetExceeded(RuntimeError):
    """Raised when reserving tokens would exceed a hard budget."""


@dataclass(slots=True)
class TokenLedger:
    limit: int
    used: int = 0

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("Token limit must be >= 1")

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def charge(self, text: str) -> int:
        amount = TokenEstimator.estimate(text)
        if amount > self.remaining:
            raise TokenBudgetExceeded(f"Token budget exceeded: requested={amount}, remaining={self.remaining}")
        self.used += amount
        return amount

    def reserve(self, amount: int) -> None:
        if amount < 1:
            raise ValueError("Reservation must be >= 1")
        if amount > self.remaining:
            raise TokenBudgetExceeded(f"Token reservation exceeds budget: requested={amount}, remaining={self.remaining}")
        self.used += amount
