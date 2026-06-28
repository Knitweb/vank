# Knitweb vBank

Standalone vBank domain package for Knitweb/Pulse.

This repo owns the voting-domain layer:

- personhood-gated ballot emission;
- deterministic one-person-one-vote tallying;
- signed poll definitions and independently auditable results;
- weighted, liquid, and ranked-choice voting;
- signed election manifests that group multiple poll definitions for clients and indexers.
- demographic vote-supply registries, treasury-backed vote issuance, recency weighting,
  one-person-one-backing crowdfunding, and proximity-gated local backing.

Pulse remains the dependency for core primitives: canonical encoding/CIDs, signatures,
fabric Web storage, attestations, and personhood tickets.

## Layout

- `src/knitweb_vbank/` - package code.
- `tests/property/` - deterministic regression/property tests.
- `docs/ARCHITECTURE.md` - package boundary and record overview.
- `docs/VOTE_SUPPLY_CROWDFUND.md` - migrated VoteBank supply, recency, and crowdfunding notes.
- `docs/TIME_VALUE_AND_RELEVANCE.md` - geometric time-value research note.

## Development

Until Pulse is published as a package, keep a Pulse checkout available and install it
editable for local tests:

```bash
git clone https://github.com/Knitweb/pulse ../pulse
python -m pip install -e ../pulse
PYTHONPATH=src:../pulse/src python -m pytest -q
```

If you already have a Pulse checkout, use that path instead of cloning again.

The GitHub Actions workflow checks out `Knitweb/pulse` beside this repo, installs it
editable, and runs the same package compile + pytest flow with `PYTHONPATH=src:pulse/src`.

## New in this repo

The `vbank-election` manifest is the first layer that belongs naturally outside the
Pulse core. It signs a user-facing election event that links to one or more signed
`vbank-poll` definitions by CID, giving frontends and indexers a stable object to
discover before resolving the individual poll records.

The migrated VoteBank supply layer adds the treasury-style issuance and campaign mechanics
from `febuz/pulse` PR #74 as standalone `knitweb_vbank` modules, keeping Pulse as the
primitive dependency for canonical IDs, signatures, ledger settlement, and personhood.
