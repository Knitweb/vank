"""Proofs for conserving apportionment — the multi-party float→integer seam.

Principles under test (mirrors molgang-web/shared/economy/ledger.ts, the TS twin):
  * Conservation: integer parts sum EXACTLY to the total — rounding never mints or burns.
  * Proportionality: every part within one unit of its exact share.
  * Zero weight ⇒ zero units; all-zero weights split equally (a charge cannot vanish).
  * Charges cap at balances; collected + uncollected == charge, shortfall explicit.
  * The boundary rejects NaN/inf/negative weights and non-integer totals.
"""

import math
import random

import pytest

from knitweb_vank.apportion import ChargeCollection, collect_charge, quantize_conserving


@pytest.mark.property
def test_equal_thirds_conserve_and_stay_close():
    parts = quantize_conserving([1, 1, 1], 100)
    assert sum(parts) == 100
    assert max(parts) - min(parts) <= 1
    assert all(isinstance(p, int) for p in parts)


@pytest.mark.property
def test_fuzz_conservation_and_proportionality():
    rng = random.Random(20260721)
    for _ in range(500):
        n = rng.randrange(1, 18)
        weights = [0.0 if rng.random() < 0.2 else rng.random() * 100 for _ in range(n)]
        total = rng.randrange(-5000, 5000)
        parts = quantize_conserving(weights, total)
        assert sum(parts) == total
        wsum = sum(weights)
        if wsum > 0:
            for w, p in zip(weights, parts):
                exact = (w / wsum) * total
                assert abs(p - exact) <= 1 + 1e-9


@pytest.mark.property
def test_edges():
    assert quantize_conserving([3, 7], 0) == [0, 0]
    assert sum(quantize_conserving([0, 0, 0], 7)) == 7  # equal split, nothing vanishes
    negative = quantize_conserving([2, 1], -9)
    assert sum(negative) == -9 and all(p <= 0 for p in negative)
    assert quantize_conserving([0, 5], 10)[0] == 0
    assert quantize_conserving([], 0) == []
    with pytest.raises(ValueError):
        quantize_conserving([], 5)
    with pytest.raises(ValueError):
        quantize_conserving([-1, 2], 10)
    with pytest.raises(ValueError):
        quantize_conserving([math.nan], 10)
    with pytest.raises(TypeError):
        quantize_conserving([1], 1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        quantize_conserving([1], True)  # bools are not amounts


@pytest.mark.property
def test_collect_charge_caps_and_accounts():
    r = collect_charge([1, 1], 10, [100, 2])
    assert isinstance(r, ChargeCollection)
    assert r.paid[1] == 2
    assert r.collected + r.uncollected == 10

    rich = collect_charge([1, 3], 8, [100, 100])
    assert rich.collected == 8 and rich.uncollected == 0

    broke = collect_charge([1], 5, [0])
    assert broke.collected == 0 and broke.uncollected == 5

    assert collect_charge([1], 5, [3.9]).paid[0] == 3  # fractional balances floor

    with pytest.raises(ValueError):
        collect_charge([1], -1, [10])
    with pytest.raises(ValueError):
        collect_charge([1, 2], 3, [10])


@pytest.mark.property
def test_ts_twin_parity_examples():
    """Fixed vectors shared with the TypeScript twin (ledger.test.ts §7)."""
    assert quantize_conserving([1, 1, 1], 100) == [34, 33, 33]
    r = collect_charge([3 * 1.5, 1 * 2.25, 6 * 0.4], 915, [10**9] * 3)
    assert sum(r.parts) == 915 and r.uncollected == 0
