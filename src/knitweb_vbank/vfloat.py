"""vfloat — the vank deterministic numeric kernel ("vank floats").

Hardware floats are banned from the fabric because IEEE-754 results can differ
across platforms, compilers and reduction orders — poison for a ledger where
every peer must agree byte-for-byte. Yet two Knitweb domains genuinely need
non-integer arithmetic:

  * **vBank** — fractional voting weights (liquid delegation splits, quorum
    ratios);
  * **PQ (Pulse Quantum)** — Feynman path sums, where each path contributes a
    complex amplitude ``e^(i·S)`` and physics lives in how those phases
    interfere (``docs/DUAL_COIN_IPO_PLAN.md`` §5 in Knitweb/pulse).

This module is the shared answer: fixed-point numbers stored as plain Python
integers scaled by ``10**18`` (wei-style, matching the ledger's base-unit
convention), with every operation defined purely on integers. The same inputs
produce the same bits on every machine — determinism is the contract; the
~18 significant digits of precision are more than either domain needs.

Values cross into fabric records only through the declared integer boundaries
at the bottom (:func:`amplitude_micro`, :func:`prob_milli`) — the
``confidence_milli`` pattern from Pulse field observations.

No imports beyond the stdlib ``math.isqrt`` (integer-exact) and ``dataclasses``.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isqrt

__all__ = [
    "SCALE", "ONE", "PI", "TWO_PI", "HALF_PI",
    "div_round", "fp_from_int", "fp_from_str", "fp_to_str",
    "fp_mul", "fp_div", "fp_sqrt", "fp_sin", "fp_cos", "fp_exp",
    "CF", "c_add", "c_mul", "c_exp_i", "c_abs2",
    "path_sum", "amplitude_micro", "prob_milli",
]

# One fixed-point unit: integers scaled by 10^18 (wei-style).
SCALE = 10 ** 18
ONE = SCALE

# π constants pre-scaled by 10^18, rounded half-to-even at the 18th decimal
# (computed from a 40-digit Decimal expansion; regression-locked in the tests).
PI = 3141592653589793238
TWO_PI = 6283185307179586477
HALF_PI = 1570796326794896619


# --------------------------------------------------------------------------- #
# Scalar fixed-point arithmetic
# --------------------------------------------------------------------------- #
def div_round(n: int, d: int) -> int:
    """Divide ``n`` by ``d`` rounding half-to-even (banker's rounding).

    Python's ``//`` floors toward −∞, which would bias long computations
    negative. Half-to-even is symmetric and matches the rounding used for the
    pre-scaled constants above. ``d`` must be positive.
    """
    if d <= 0:
        raise ValueError("divisor must be positive")
    q, r = divmod(n, d)          # r is always in [0, d)
    twice = 2 * r
    if twice > d or (twice == d and q % 2 != 0):
        q += 1
    return q


def fp_from_int(n: int) -> int:
    return n * SCALE


def fp_from_str(text: str) -> int:
    """Parse a decimal literal like ``"-1.5"`` exactly (≤18 fractional digits)."""
    text = text.strip()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    whole, _, frac = text.partition(".")
    if len(frac) > 18:
        raise ValueError("more than 18 fractional digits is not representable")
    whole_i = int(whole) if whole else 0
    frac_i = int(frac.ljust(18, "0")) if frac else 0
    return sign * (whole_i * SCALE + frac_i)


def fp_to_str(a: int) -> str:
    sign = "-" if a < 0 else ""
    q, r = divmod(abs(a), SCALE)
    return f"{sign}{q}.{r:018d}".rstrip("0").rstrip(".") or "0"


def fp_mul(a: int, b: int) -> int:
    return div_round(a * b, SCALE)


def fp_div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("fp_div by zero")
    if b < 0:
        a, b = -a, -b
    return div_round(a * SCALE, b)


def fp_sqrt(a: int) -> int:
    """Integer-exact floor square root in fixed point (``a ≥ 0``)."""
    if a < 0:
        raise ValueError("fp_sqrt of a negative value")
    return isqrt(a * SCALE)


def _reduce_angle(x: int) -> int:
    """Map any angle into (−π, π] by exact integer modulo of 2π."""
    r = x % TWO_PI               # in [0, 2π)
    if r > PI:
        r -= TWO_PI
    return r


def fp_sin(x: int) -> int:
    """Sine by Taylor series on the reduced angle.

    Terms are generated with integer ops only and the loop stops when a term
    underflows to zero — a deterministic stopping rule (integer magnitudes
    decrease strictly once k exceeds |x|).
    """
    x = _reduce_angle(x)
    x2 = fp_mul(x, x)
    term = x
    total = x
    k = 1
    while term != 0:
        term = -div_round(fp_mul(term, x2), (2 * k) * (2 * k + 1))
        total += term
        k += 1
    return total


def fp_cos(x: int) -> int:
    x = _reduce_angle(x)
    x2 = fp_mul(x, x)
    term = ONE
    total = ONE
    k = 1
    while term != 0:
        term = -div_round(fp_mul(term, x2), (2 * k - 1) * (2 * k))
        total += term
        k += 1
    return total


def fp_exp(x: int) -> int:
    """Real exponential for bounded arguments (|x| ≤ 40); Taylor, integer-only.

    PQ mostly needs the *imaginary* exponential (:func:`c_exp_i`); the real one
    exists for weight decay and normalisation factors. The bound keeps the
    intermediate integers small and the series fast; 40 is far beyond any
    weight-decay use.
    """
    if abs(x) > 40 * SCALE:
        raise ValueError("fp_exp argument out of the supported range (|x| <= 40)")
    term = ONE
    total = ONE
    k = 1
    while term != 0:
        term = div_round(fp_mul(term, x), k)
        total += term
        k += 1
    return total


# --------------------------------------------------------------------------- #
# Complex fixed point — amplitudes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CF:
    """A complex amplitude with fixed-point real and imaginary parts."""

    re: int
    im: int


def c_add(a: CF, b: CF) -> CF:
    return CF(a.re + b.re, a.im + b.im)     # integer addition is exact


def c_mul(a: CF, b: CF) -> CF:
    return CF(
        fp_mul(a.re, b.re) - fp_mul(a.im, b.im),
        fp_mul(a.re, b.im) + fp_mul(a.im, b.re),
    )


def c_exp_i(theta: int) -> CF:
    """``e^(i·θ)`` — the unit phasor every Feynman path contributes."""
    return CF(fp_cos(theta), fp_sin(theta))


def c_abs2(a: CF) -> int:
    """Squared magnitude ``|a|²`` (a probability weight before normalisation)."""
    return fp_mul(a.re, a.re) + fp_mul(a.im, a.im)


def path_sum(actions: list[int]) -> CF:
    """Sum the phasors ``e^(i·S_k)`` over paths, in the given order.

    The order is part of the job definition: peers re-executing a PQ proof must
    receive the action list in canonical order so the (exact, integer) sums
    match bit-for-bit.
    """
    total = CF(0, 0)
    for action in actions:
        total = c_add(total, c_exp_i(action))
    return total


# --------------------------------------------------------------------------- #
# Integer boundaries — the only exits toward fabric records
# --------------------------------------------------------------------------- #
def amplitude_micro(a: int) -> int:
    """A fixed-point scalar as an integer in micro-units (10⁻⁶), for records."""
    return div_round(a * 10 ** 6, SCALE)


def prob_milli(weight: int, total: int) -> int:
    """A normalised probability in milli-units (0..1000), ``confidence_milli`` style."""
    if total <= 0:
        raise ValueError("total weight must be positive")
    if weight < 0:
        raise ValueError("weight must be non-negative")
    return div_round(weight * 1000, total)
