# vank ↔ knitweb_vbank Interop

## Type boundary

**knitweb_vbank** records use integer-only amounts: PLS-wei balances and beat
counters are `int` throughout. This is a deliberate design choice — integers
are canonical-safe (hash-stable across nodes) and gossip-replicable without
floating-point rounding divergence.

**vank** (`VoteBankDAO`, `PokerSession`) uses `float` timestamps and weights.
These values are advisory and diagnostic: they drive local momentum signals
and session scoring but are never placed on the hash path.

## Why they cannot be mixed directly

A `float` produced by `vank` (e.g. a `momentum()` result like `7.342`) cannot
enter a `knitweb_vbank` record directly. Implicit truncation to `int` (7)
loses precision silently and would produce divergent state across peers if done
inconsistently.

## Bridge pattern

Convert the `vank` float to an integer *proxy* at the boundary using a fixed
scaling factor before handing it to `knitweb_vbank`:

```python
from vank.dao import VoteBankDAO, Ballot

dao = VoteBankDAO()
dao.join("alice", weight=2.0)
dao.join("bob",   weight=1.5)

ballots: list[Ballot] = [
    dao.cast("alice", "feature-x", timestamp=1_000.0),
    dao.cast("bob",   "feature-x", timestamp=1_010.0),
]

scores   = dao.decide(["feature-x"], ballots, decay=0.05)
velocity = [scores["feature-x"]]           # build a series over time
momentum = dao.momentum(velocity)           # float, e.g. 3.461

# Convert to milli-units before passing to knitweb_vbank
attention_weight: int = int(momentum * 1_000)   # e.g. 3461

# Use attention_weight as an integer input to knitweb_vbank (e.g. as a
# wei-denominated attention signal or beat-count proxy).
```

The factor `1_000` (milli-units) preserves three decimal places of precision
while keeping the value well within safe integer range.
