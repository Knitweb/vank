"""Conserving apportionment — the multi-party half of the float→integer seam.

:mod:`knitweb_vank.settle` quantises a *single* decided amount and hands it across the seam as
integers. This module covers the other recurring shape: one integer total that must be **split
across many parties** proportionally to float weights — a levy over polluters, a payout over
backers, a coupon over holders. The split uses the largest-remainder method, so:

  * every part is an integer;
  * the parts sum **exactly** to the total — rounding can never mint or burn base units;
  * a zero weight receives zero;
  * every part stays within one unit of exact proportionality.

The doctrine matches ``settle.py``: floats live on the analytics side (vfloat / the game's
"vank lane"), the crossing to integers happens exactly once, and integer-ness is re-asserted at
the boundary. First consumer besides Knitweb itself: MOLGANG's pollution levy
(``molgang-web/shared/economy/ledger.ts`` is the TypeScript twin of this module — keep the
invariants in sync).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

__all__ = ["quantize_conserving", "collect_charge", "ChargeCollection"]


def _check_finite(value: float, what: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{what} must be a real number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{what} must be finite, got {value!r}")


def quantize_conserving(weights: Sequence[float], total_units: int) -> list[int]:
    """Split ``total_units`` (an integer) across non-negative float ``weights``.

    Largest-remainder apportionment. Invariants: integer parts; ``sum(parts) == total_units``
    exactly; zero weight ⇒ zero units; all-zero weights split equally (remainder to the earliest
    indices) so a charge can never silently vanish; negative totals are apportioned on magnitude
    and sign-flipped, so refunds conserve too.
    """
    if isinstance(total_units, bool) or not isinstance(total_units, int):
        raise TypeError(f"total_units must be an int, got {total_units!r}")
    n = len(weights)
    if n == 0:
        if total_units != 0:
            raise ValueError("cannot apportion non-zero total_units over zero participants")
        return []
    if total_units == 0:
        return [0] * n

    total_weight = 0.0
    for i, w in enumerate(weights):
        _check_finite(w, f"weights[{i}]")
        if w < 0:
            raise ValueError(f"weights[{i}] must be non-negative, got {w!r}")
        total_weight += w

    sign = -1 if total_units < 0 else 1
    magnitude = abs(total_units)
    parts = [0] * n
    remainders = [0.0] * n
    allocated = 0
    if total_weight > 0:
        for i, w in enumerate(weights):
            exact = (w / total_weight) * magnitude
            base = math.floor(exact)
            parts[i] = base
            remainders[i] = exact - base
            allocated += base
    else:
        base = magnitude // n
        parts = [base] * n
        allocated = base * n

    # hand the leftover units to the largest remainders (stable on ties)
    leftover = magnitude - allocated
    order = sorted(range(n), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        parts[i] += 1

    if sign < 0:
        parts = [-p for p in parts]
    return parts


@dataclass(frozen=True)
class ChargeCollection:
    """Outcome of collecting a charge against integer balances.

    ``collected + uncollected == total charge`` always holds — a shortfall is reported,
    never silently re-minted.
    """

    parts: list[int]
    paid: list[int]
    collected: int
    uncollected: int


def collect_charge(
    weights: Sequence[float],
    total_units: int,
    balances: Sequence[float],
) -> ChargeCollection:
    """Apportion a non-negative integer charge, capping what each party pays at its balance."""
    if len(balances) != len(weights):
        raise ValueError(f"weights ({len(weights)}) and balances ({len(balances)}) length mismatch")
    if total_units < 0:
        raise ValueError(f"a charge must be non-negative, got {total_units}")
    parts = quantize_conserving(weights, total_units)
    paid: list[int] = []
    collected = 0
    for i, part in enumerate(parts):
        balance = balances[i]
        _check_finite(balance, f"balances[{i}]")
        take = max(0, min(part, math.floor(balance)))
        paid.append(take)
        collected += take
    return ChargeCollection(parts=parts, paid=paid, collected=collected, uncollected=total_units - collected)
