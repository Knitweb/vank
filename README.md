# knitweb/vank

Vault DAO, Vank Mint Node, graphical Scrum Poker, and pulse-integrated voting governance for Knitweb.

Two packages co-reside in `src/`:

| Package | Description |
|---------|-------------|
| `knitweb_vank` | Pulse-integrated voting governance: personhood-gated ballots, deterministic tallying, signed polls, ranked/liquid/crowdfund voting — plus `vfloat`, the deterministic numeric kernel for PQ and voting weights |
| `vank` | Standalone DAO, commodity mint node, FieldLedger, and graphical Scrum Poker |

## knitweb_vank

Pulse-dependent voting domain layer:

- Personhood-gated ballot emission and one-person-one-vote tallying
- Signed poll definitions with independently auditable results
- Weighted, liquid, and ranked-choice voting
- Signed election manifests grouping multiple poll definitions
- Demographic vote-supply registries, treasury-backed vote issuance, recency weighting
- One-person-one-backing crowdfunding, proximity-gated local backing
- **`vfloat` — the vank deterministic numeric kernel ("vank floats")**: fixed point on
  plain Python integers (wei-style `10^18` scale, banker's rounding), integer-Taylor
  trig, complex `e^(i·θ)` phasors and deterministic Feynman path sums. Shared by vBank
  voting weights and **PQ (Pulse Quantum)**; values exit to fabric records only through
  the integer boundaries `amplitude_micro` / `prob_milli`. See
  `docs/DUAL_COIN_IPO_PLAN.md` §5 in [Knitweb/pulse](https://github.com/Knitweb/pulse).

Requires `knitweb` (Pulse) for canonical CIDs, signatures, fabric Web, and personhood tickets.

## Vank Mint Node

A running mint node for commodity tokenization on the Knitweb/ChemField fabric.
The node lets a producer report XRF measurements as signed, content-addressed
ledger events and mint VANK within a network-issued mint grant.

Core rule: where measurement happens, reporting happens. A measurement only
counts after it is in the ledger as a signed event. The mint follows from that
event.

### Quickstart

```bash
pip install cryptography
python -m vank serve
# open http://127.0.0.1:8799/
```

Headless:

```bash
python -m vank register --kvk 93406797 --lab RvA-L123 --custody SLAG-COC-2026-0007 \
  --material v2o5 --material vanadium
python -m vank measure v2o5 SLAG-IJM-2026-021 1000 10000 XRF-2026-0421
python -m vank balance
python -m vank audit
python -m vank export report.json
```

Trust chain:

```text
network authority -> mint grant -> producer key -> signed measurement -> mint
```

Value math is integer-only:

```text
contained_ug = mass_g * grade_ppm
tokens       = contained_ug // ug_per_token
```

Defaults: `ug_per_token = 1_000_000`, so one token equals one gram of measured
contained material. Re-assays can only reduce value; the node burns the delta.

Production notes:

- Use `--no-demo-authority` and install an out-of-band grant for real networks.
- Keep the state file secret; it contains private keys.
- Cross-producer duplicate detection belongs in the shared registry/fabric layer.
- Commodity-token legal scope needs explicit review before scale-up.

## vank — Vault DAO + Scrum Poker

Standalone DAO layer with graphical Scrum Poker:

- `VankDAO` — float-friendly, insertion-ordered, recency-weighted tally, EMA momentum
- `PokerSession` — Fibonacci deck, tolerance-based consensus, outlier detection, upper-median agreed card
- HTTP server + self-contained vanilla JS UI (card grid, reveal, distribution chart, velocity sparkline)

### Run Scrum Poker

```bash
pip install knitweb-vank
vank-poker --port 8000 --tolerance 1
# open http://localhost:8000
```

Or without installing:

```bash
PYTHONPATH=src python3 -m vank.poker_server --port 8000
```

## Layout

```
src/
  knitweb_vank/   pulse-integrated governance modules
  vank/            standalone DAO + Scrum Poker
    crypto.py      Ed25519 keys, signing, content-address helpers
    core.py        authority, grant, signed events, mint node, integer token math
    server.py      stdlib HTTP server for mint-node GUI/API
    cli.py         serve/register/measure/revalue/balance/audit/export
    static/        mint-node browser UI assets
tests/
  property/
    test_vbank_*   knitweb_vank property tests (require knitweb)
    test_vank_*    standalone vank tests (no deps)
docs/              architecture, vote-supply, time-value notes
```

## Development

```bash
git clone https://github.com/Knitweb/pulse ../pulse
pip install -e "../pulse[dev]"
pip install -e ".[dev]"
python3 -m pytest tests/ -q
```

The GitHub Actions workflow checks out `Knitweb/pulse` beside this repo, installs it, and runs compile + pytest.
