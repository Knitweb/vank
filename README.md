# knitweb/vank

VoteBank DAO, graphical Scrum Poker, and pulse-integrated voting governance for Knitweb.

Two packages co-reside in `src/`:

| Package | Description |
|---------|-------------|
| `knitweb_vbank` | Pulse-integrated voting governance: personhood-gated ballots, deterministic tallying, signed polls, ranked/liquid/crowdfund voting |
| `vank` | Standalone float-friendly DAO + graphical Scrum Poker (zero deps beyond stdlib) |

## knitweb_vbank

Pulse-dependent voting domain layer:

- Personhood-gated ballot emission and one-person-one-vote tallying
- Signed poll definitions with independently auditable results
- Weighted, liquid, and ranked-choice voting
- Signed election manifests grouping multiple poll definitions
- Demographic vote-supply registries, treasury-backed vote issuance, recency weighting
- One-person-one-backing crowdfunding, proximity-gated local backing

Requires `knitweb` (Pulse) for canonical CIDs, signatures, fabric Web, and personhood tickets.

## vank — VoteBank DAO + Scrum Poker

Standalone, zero-dependency (stdlib only) DAO layer with graphical Scrum Poker:

- `VoteBankDAO` — float-friendly, insertion-ordered, recency-weighted tally, EMA momentum
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
  knitweb_vbank/   pulse-integrated governance modules
  vank/            standalone DAO + Scrum Poker
    static/        poker.html self-contained UI
tests/
  property/
    test_vbank_*   knitweb_vbank property tests (require knitweb)
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
