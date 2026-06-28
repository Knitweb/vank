"""VoteBankDAO — float-friendly financial time-series vote bank.

Unlike the parent pulse codebase, floats are *allowed* here; this module
is intentionally designed for financial / time-series tallying.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

__all__ = ["Ballot", "VoteBankDAO"]


@dataclass
class Ballot:
    """A single weighted vote."""

    voter: str
    option: str
    timestamp: float
    weight: float = 1.0


class VoteBankDAO:
    """Ordered-insertion member registry with recency-weighted vote tallying."""

    def __init__(self) -> None:
        self._members: dict[str, float] = {}  # member → weight, insertion-ordered

    # ------------------------------------------------------------------
    # Member management
    # ------------------------------------------------------------------

    @property
    def members(self) -> dict[str, float]:
        """Return a snapshot of the member→weight mapping (insertion order)."""
        return dict(self._members)

    def join(self, member: str, weight: float = 1.0) -> None:
        """Add *member* with *weight*.  Idempotent: weight is NOT updated if
        the member already exists."""
        if member not in self._members:
            self._members[member] = weight

    def member_list(self) -> list[str]:
        """Return member names in insertion order."""
        return list(self._members.keys())

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def cast(self, voter: str, option: str, timestamp: float) -> Ballot:
        """Create a :class:`Ballot` for *voter*.

        The ballot weight is taken from the member registry; unknown voters
        default to weight ``1.0``.
        """
        weight = self._members.get(voter, 1.0)
        return Ballot(voter=voter, option=option, timestamp=timestamp, weight=weight)

    def decide(
        self,
        options: list[str],
        ballots: list[Ballot],
        decay: float = 0.1,
    ) -> dict[str, float]:
        """Recency-weighted tally.

        Each ballot's effective weight is multiplied by
        ``exp(-decay * (max_ts - ballot.timestamp))`` so that more-recent
        votes carry more weight.

        Returns ``{option: score}`` for every option in *options*.
        """
        if not ballots:
            return {opt: 0.0 for opt in options}

        max_ts = max(b.timestamp for b in ballots)
        scores: dict[str, float] = {opt: 0.0 for opt in options}

        for ballot in ballots:
            if ballot.option in scores:
                recency = math.exp(-decay * (max_ts - ballot.timestamp))
                scores[ballot.option] += ballot.weight * recency

        return scores

    # ------------------------------------------------------------------
    # Momentum
    # ------------------------------------------------------------------

    def momentum(self, velocity_series: list[float], alpha: float = 0.3) -> float:
        """Exponential moving average of *velocity_series*.

        ``ema_t = alpha * v_t + (1 - alpha) * ema_{t-1}``

        Returns ``0.0`` for an empty series.
        """
        if not velocity_series:
            return 0.0
        ema = velocity_series[0]
        for v in velocity_series[1:]:
            ema = alpha * v + (1.0 - alpha) * ema
        return ema
