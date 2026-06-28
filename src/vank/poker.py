"""Scrum Poker logic — session management, consensus detection, round results."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Deck
# ---------------------------------------------------------------------------

FIBONACCI_DECK: tuple[str, ...] = (
    "0", "1", "2", "3", "5", "8", "13", "20", "40", "100", "?", "☕"
)

_SPECIAL = frozenset({"?", "☕"})
_DECK_INDEX: dict[str, int] = {c: i for i, c in enumerate(FIBONACCI_DECK)}
# Numeric cards in deck order (excludes "?" and "☕")
_NUMERIC_CARDS: tuple[str, ...] = tuple(c for c in FIBONACCI_DECK if c not in _SPECIAL)


def _is_numeric(card: str) -> bool:
    return card not in _SPECIAL


def _deck_pos(card: str) -> int:
    return _DECK_INDEX[card]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PlayerState:
    name: str
    voted: bool
    card: str | None


@dataclass
class RoundResult:
    cards: dict[str, str]           # player → card
    distribution: dict[str, float]  # card → fraction of total votes
    consensus: str | None           # agreed card string when consensus reached
    range: int                      # numeric value range (max_val − min_val)
    median: float                   # median of numeric card values
    mean: float                     # mean of numeric card values
    spread_steps: int               # max deck-position − min deck-position
    outliers: list[str]             # player names whose card is > tolerance steps from agreed
    agreed_card: str | None         # conservative upper-median card in deck order

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "cards": dict(self.cards),
            "distribution": dict(self.distribution),
            "consensus": self.consensus,
            "range": self.range,
            "median": self.median,
            "mean": self.mean,
            "spread_steps": self.spread_steps,
            "outliers": list(self.outliers),
            "agreed_card": self.agreed_card,
        }


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class PokerSession:
    """A single Scrum Poker session (one story, multiple rounds via revote)."""

    def __init__(self, name: str, tolerance: int = 0) -> None:
        self.name = name
        self.tolerance = tolerance

        self._players: list[str] = []          # insertion-ordered
        self._votes: dict[str, str] = {}       # player → card (current round)
        self._revealed: bool = False
        self._last_result: RoundResult | None = None
        self._velocity: list[float] = []       # finalized values across rounds
        self._version: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bump(self) -> None:
        self._version += 1

    @staticmethod
    def _upper_median_card(numeric_cards: list[str]) -> str | None:
        """Conservative upper-median: for even n pick the upper of the two
        midpoints; for odd n pick the true median."""
        if not numeric_cards:
            return None
        sorted_cards = sorted(numeric_cards, key=_deck_pos)
        n = len(sorted_cards)
        # n=1→0, n=2→1, n=3→1, n=4→2, n=5→2 — always the upper midpoint
        return sorted_cards[n // 2]

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def join(self, player: str) -> None:
        """Add *player* to the session (idempotent)."""
        if player not in self._players:
            self._players.append(player)
            self._bump()

    def vote(self, player: str, card: str) -> None:
        """Cast a vote for *player*.

        Raises :class:`ValueError` if:
        - the player has not joined,
        - the card is not in the deck,
        - the round has already been revealed (call :meth:`revote` first),
        - the player already voted this round.
        """
        if player not in self._players:
            raise ValueError(f"Player {player!r} has not joined the session")
        if card not in _DECK_INDEX:
            raise ValueError(f"Card {card!r} is not in the Fibonacci deck")
        if self._revealed:
            raise ValueError("Round already revealed — call revote() before voting again")
        if player in self._votes:
            raise ValueError(
                f"Player {player!r} already voted this round — call revote() to reset"
            )
        self._votes[player] = card
        self._bump()

    def reveal(self) -> RoundResult:
        """Reveal all votes and compute :class:`RoundResult`.

        Raises :class:`ValueError` if no votes have been cast.
        Calling reveal a second time returns the cached result.
        """
        if not self._votes:
            raise ValueError("No votes to reveal")
        if self._revealed and self._last_result is not None:
            return self._last_result

        self._revealed = True
        self._bump()

        cards: dict[str, str] = dict(self._votes)
        total = len(cards)

        # Distribution — fraction of voters per card
        dist_counts: dict[str, int] = {}
        for c in cards.values():
            dist_counts[c] = dist_counts.get(c, 0) + 1
        distribution = {c: cnt / total for c, cnt in dist_counts.items()}

        # Numeric cards only
        numeric_cards = [c for c in cards.values() if _is_numeric(c)]
        numeric_values = [float(c) for c in numeric_cards]

        if numeric_values:
            mean_val = sum(numeric_values) / len(numeric_values)
            median_val = float(statistics.median(numeric_values))
            positions = [_deck_pos(c) for c in numeric_cards]
            spread_steps = max(positions) - min(positions)
            range_val = int(max(numeric_values) - min(numeric_values))
        else:
            mean_val = 0.0
            median_val = 0.0
            spread_steps = 0
            range_val = 0

        agreed_card = self._upper_median_card(numeric_cards)

        # Consensus: all numeric votes within *tolerance* deck-steps
        if numeric_cards and spread_steps <= self.tolerance:
            consensus = agreed_card
        else:
            consensus = None

        # Outliers: numeric voters whose deck-position differs by > tolerance
        # from the agreed card's deck-position
        outliers: list[str] = []
        if agreed_card is not None:
            agreed_pos = _deck_pos(agreed_card)
            for player, card in cards.items():
                if not _is_numeric(card):
                    continue
                if abs(_deck_pos(card) - agreed_pos) > self.tolerance:
                    outliers.append(player)

        result = RoundResult(
            cards=cards,
            distribution=distribution,
            consensus=consensus,
            range=range_val,
            median=median_val,
            mean=mean_val,
            spread_steps=spread_steps,
            outliers=outliers,
            agreed_card=agreed_card,
        )
        self._last_result = result
        return result

    def revote(self) -> None:
        """Reset votes for a new round (velocity is preserved)."""
        self._votes.clear()
        self._revealed = False
        self._last_result = None
        self._bump()

    def finalize(self) -> float | None:
        """Finalise the current round.

        Appends the agreed card's numeric value to the velocity series and
        returns it, or returns ``None`` if no numeric agreement was reached.

        Raises :class:`ValueError` if the round has not been revealed yet.
        """
        if not self._revealed:
            raise ValueError("Must call reveal() before finalize()")
        if self._last_result is None:
            return None
        agreed = self._last_result.agreed_card
        if agreed is None or not _is_numeric(agreed):
            return None
        val = float(agreed)
        self._velocity.append(val)
        self._bump()
        return val

    # ------------------------------------------------------------------
    # State / serialisation
    # ------------------------------------------------------------------

    def state_for(self, viewer: str) -> dict[str, Any]:
        """Return session state for *viewer*.

        Pre-reveal: only *viewer*'s own card is visible; other players'
        cards are ``null`` (hidden).  After reveal all cards are visible.
        """
        players = []
        for p in self._players:
            voted = p in self._votes
            if self._revealed or p == viewer:
                card: str | None = self._votes.get(p)
            else:
                card = None
            players.append({"name": p, "voted": voted, "card": card})

        result_dict = None
        if self._revealed and self._last_result is not None:
            result_dict = self._last_result.as_dict()

        return {
            "session": self.name,
            "revealed": self._revealed,
            "players": players,
            "result": result_dict,
            "velocity": list(self._velocity),
            "version": self._version,
        }

    def as_dict(self) -> dict[str, Any]:
        """Full internal state (for debugging / persistence)."""
        return {
            "session": self.name,
            "tolerance": self.tolerance,
            "players": list(self._players),
            "votes": dict(self._votes),
            "revealed": self._revealed,
            "result": self._last_result.as_dict() if self._last_result else None,
            "velocity": list(self._velocity),
            "version": self._version,
        }
