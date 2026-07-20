"""vfloat kernel — determinism, accuracy and boundary properties.

The kernel's contract is bit-identical results everywhere, so the key tests
are golden integers (locked expected values), not float comparisons. Accuracy
against ``math`` is checked loosely (the series are ~1e-15 accurate; the
contract is determinism, not ulp-perfection).
"""

import math

from knitweb_vank.vfloat import (
    CF, HALF_PI, ONE, PI, SCALE, TWO_PI,
    amplitude_micro, c_abs2, c_add, c_exp_i, c_mul, div_round,
    fp_cos, fp_div, fp_exp, fp_from_str, fp_mul, fp_sin, fp_sqrt, fp_to_str,
    path_sum, prob_milli,
)


def test_div_round_half_to_even_incl_negatives():
    assert div_round(5, 2) == 2          # 2.5 -> even 2
    assert div_round(7, 2) == 4          # 3.5 -> even 4
    assert div_round(-5, 2) == -2        # -2.5 -> even -2
    assert div_round(-7, 2) == -4        # -3.5 -> even -4
    assert div_round(6, 3) == 2          # exact stays exact


def test_literals_round_trip():
    assert fp_from_str("-1.5") == -3 * SCALE // 2
    assert fp_to_str(fp_from_str("2.25")) == "2.25"
    assert fp_to_str(0) == "0"


def test_constants_are_locked():
    # Regression-lock the pre-scaled constants (40-digit Decimal derivation).
    assert PI == 3141592653589793238
    assert TWO_PI == 6283185307179586477
    assert HALF_PI == 1570796326794896619


def test_mul_div_sqrt_exactness():
    assert fp_mul(2 * ONE, 3 * ONE) == 6 * ONE
    assert fp_div(ONE, 2 * ONE) == ONE // 2
    assert fp_sqrt(4 * ONE) == 2 * ONE


def test_trig_accuracy_and_angle_reduction():
    for frac in (-3.5, -1.0, -0.25, 0.0, 0.5, 1.0, 2.9, 7.75, 123.0):
        x = fp_from_str(f"{frac:.6f}")
        assert abs(fp_sin(x) / SCALE - math.sin(frac)) < 1e-12
        assert abs(fp_cos(x) / SCALE - math.cos(frac)) < 1e-12


def test_trig_golden_values_bit_exact():
    # These integers must never change on any platform or Python version:
    # they are what peers re-executing a PQ proof will compare.
    assert fp_sin(ONE) == 841470984807896507
    assert fp_cos(ONE) == 540302305868139717
    assert abs(fp_sin(PI)) <= 2  # π itself is 1 ulp off, so sin(π) is a few ulp
    assert fp_cos(TWO_PI) == ONE


def test_exp_accuracy_and_bound():
    assert fp_exp(0) == ONE
    assert abs(fp_exp(ONE) / SCALE - math.e) < 1e-12
    try:
        fp_exp(41 * ONE)
        raise AssertionError("expected ValueError for out-of-range fp_exp")
    except ValueError:
        pass


def test_unit_phasor_norm():
    for frac in (0.0, 0.7, 1.9, 3.1, 5.5):
        amp = c_exp_i(fp_from_str(f"{frac:.6f}"))
        assert abs(c_abs2(amp) - ONE) < 10  # |e^iθ|² = 1 to ~1e-17


def test_complex_mul_matches_phase_addition():
    a, b = fp_from_str("0.6"), fp_from_str("1.1")
    lhs = c_mul(c_exp_i(a), c_exp_i(b))
    rhs = c_exp_i(a + b)
    assert abs(lhs.re - rhs.re) < 10 and abs(lhs.im - rhs.im) < 10


def test_two_slit_interference():
    # Two paths in phase: |1+1|² = 4. In counter-phase (Δ=π): |1-1|² ≈ 0.
    constructive = c_abs2(path_sum([0, 0]))
    destructive = c_abs2(path_sum([0, PI]))
    assert abs(constructive - 4 * ONE) < 10
    assert destructive < 10


def test_path_sum_is_deterministic_and_repeatable():
    actions = [fp_from_str(f"{k * 0.371:.6f}") for k in range(50)]
    first = path_sum(actions)
    second = path_sum(actions)
    assert first == second == CF(first.re, first.im)


def test_integer_boundaries():
    assert amplitude_micro(fp_from_str("0.5")) == 500_000
    weights = [c_abs2(c_exp_i(0)), c_abs2(path_sum([0, PI]))]
    total = sum(weights)
    millis = [prob_milli(w, total) for w in weights]
    assert millis[0] == 1000 and millis[1] == 0
    assert c_add(CF(1, 2), CF(3, 4)) == CF(4, 6)
