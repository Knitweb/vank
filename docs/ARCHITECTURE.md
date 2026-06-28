# vBank Architecture

vBank is a domain package on top of Knitweb/Pulse. It does not define core consensus,
fabric, identity, or personhood primitives. It consumes those primitives to build
auditable voting records.

## Dependency Boundary

Owned here:

- `vbank-ballot`
- `vbank-tally`
- `vbank-poll`
- `vbank-result`
- `vbank-ranked-ballot`
- `vbank-ranked-result`
- `vbank-delegation`
- `vbank-liquid-result`
- `vbank-election`
- `govern-registration`
- `govern-vote-issuance`
- `govern-pledge`
- `govern-campaign`
- `govern-proximity`
- `govern-settlement`

Provided by Pulse:

- canonical encoding and content IDs;
- signatures and attestations;
- fabric `Web` storage;
- personhood tickets and scope nullifiers.

## Agent Identity Issuance Boundary

vBank may grow into an issuer of traceable agent identity attestations, but it should still
avoid owning raw identity primitives on the public fabric.

That means:

- ballots, tallies, and public election records remain PII-free;
- public attestations should carry only pairwise or agent identifiers, issuer/provider
  trust anchors, validity windows, revocation pointers, and evidence digests;
- copies of identity documents, liveness evidence, and service-provider qualification
  evidence must stay in an encrypted off-fabric evidence vault;
- any “traceable to a real person” requirement should resolve through that encrypted
  evidence vault plus provider due process, not through public replicated records.

This keeps the current privacy boundary intact while still allowing stronger accountability
for agents and operators.

## Election Manifests

`vbank-election` is a signed manifest for a user-facing election event. It contains:

- `scope`
- `election_id`
- `title`
- `poll_cids`
- `opens_at`
- `closes_at`
- `mode`
- `authority`

The manifest links to signed `vbank-poll` records by CID. Clients can collect
elections first, show their status, then resolve the exact poll records in manifest
order.

## Determinism

All public records are canonical-encoded before signing or returning. Read models sort
by CID when reading from a `Web`. Tally algorithms are order-independent: repeated votes
dedupe by scope nullifier, with highest sequence winning and CID tie-breaks where needed.

## Vote Supply And Crowdfunding

The VoteBank supply modules migrated from `febuz/pulse` PR #74 live beside the ballot
domain rather than inside Pulse core. `WorldRegistry` keeps the demographic cap, `VoteBank`
issues one vote per registered subject from that cap, `recency_tally` handles integer
geometric vote decay, and `Campaign` applies the same one-person rule to crowdfunding
backing. `settle` remains a bridge onto Pulse ledger Knits; float analytics stay outside
the value path.
