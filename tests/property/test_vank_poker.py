"""Property tests for PokerSession, FIBONACCI_DECK, and RoundResult."""
import json

import pytest

from vank.poker import FIBONACCI_DECK, PokerSession, RoundResult


# ---------------------------------------------------------------------------
# Deck constants
# ---------------------------------------------------------------------------


def test_fibonacci_deck_length():
    assert len(FIBONACCI_DECK) == 12


def test_fibonacci_deck_has_specials():
    assert "?" in FIBONACCI_DECK
    assert "☕" in FIBONACCI_DECK


def test_fibonacci_deck_numeric_order():
    numerics = [c for c in FIBONACCI_DECK if c not in ("?", "☕")]
    vals = [int(c) for c in numerics]
    assert vals == sorted(vals), "numeric cards must be in ascending order"


def test_fibonacci_deck_is_tuple():
    assert isinstance(FIBONACCI_DECK, tuple)


def test_fibonacci_deck_standard_cards():
    for card in ("0", "1", "2", "3", "5", "8", "13", "20", "40", "100"):
        assert card in FIBONACCI_DECK


# ---------------------------------------------------------------------------
# Round lifecycle: join → vote → reveal → revote → finalize
# ---------------------------------------------------------------------------


def test_basic_lifecycle():
    s = PokerSession("demo")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "8")
    s.vote("bob", "8")
    r = s.reveal()
    assert isinstance(r, RoundResult)
    assert r.cards == {"alice": "8", "bob": "8"}
    assert r.agreed_card == "8"


def test_reveal_with_no_votes_raises():
    s = PokerSession("demo")
    s.join("alice")
    with pytest.raises(ValueError, match="[Nn]o votes"):
        s.reveal()


def test_reveal_returns_cached_on_second_call():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "5")
    r1 = s.reveal()
    r2 = s.reveal()
    assert r1 is r2


def test_revote_resets_state():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "5")
    s.reveal()
    s.revote()
    assert not s._revealed
    assert s._votes == {}
    assert s._last_result is None


def test_revote_allows_new_vote():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "5")
    s.revote()
    s.vote("alice", "13")  # should not raise
    r = s.reveal()
    assert r.cards["alice"] == "13"


# ---------------------------------------------------------------------------
# One-person-one-vote
# ---------------------------------------------------------------------------


def test_cannot_vote_twice_before_revote():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "5")
    with pytest.raises(ValueError, match="[Aa]lready voted"):
        s.vote("alice", "8")


def test_cannot_vote_after_reveal_before_revote():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "5")
    s.reveal()
    with pytest.raises(ValueError, match="[Rr]eveal"):
        s.vote("alice", "8")


def test_must_join_before_voting():
    s = PokerSession("demo")
    with pytest.raises(ValueError, match="[Jj]oin"):
        s.vote("stranger", "8")


def test_invalid_card_raises():
    s = PokerSession("demo")
    s.join("alice")
    with pytest.raises(ValueError, match="[Dd]eck"):
        s.vote("alice", "99")


# ---------------------------------------------------------------------------
# Consensus — exact
# ---------------------------------------------------------------------------


def test_consensus_all_equal():
    s = PokerSession("demo", tolerance=0)
    for p in ["a", "b", "c"]:
        s.join(p)
        s.vote(p, "5")
    r = s.reveal()
    assert r.consensus == "5"
    assert r.agreed_card == "5"
    assert r.outliers == []


def test_no_consensus_when_cards_differ_tolerance_zero():
    s = PokerSession("demo", tolerance=0)
    s.join("a"); s.vote("a", "5")
    s.join("b"); s.vote("b", "8")
    r = s.reveal()
    assert r.consensus is None


# ---------------------------------------------------------------------------
# Consensus — tolerance
# ---------------------------------------------------------------------------


def test_consensus_within_tolerance():
    # "5" is at index 4, "8" is at index 5 — 1 step apart
    s = PokerSession("demo", tolerance=1)
    s.join("a"); s.vote("a", "5")
    s.join("b"); s.vote("b", "8")
    r = s.reveal()
    assert r.consensus is not None
    assert r.agreed_card is not None


def test_no_consensus_beyond_tolerance():
    s = PokerSession("demo", tolerance=1)
    s.join("a"); s.vote("a", "1")
    s.join("b"); s.vote("b", "100")
    r = s.reveal()
    assert r.consensus is None


# ---------------------------------------------------------------------------
# Outliers
# ---------------------------------------------------------------------------


def test_outliers_detected():
    s = PokerSession("demo", tolerance=1)
    s.join("a"); s.vote("a", "8")
    s.join("b"); s.vote("b", "8")
    s.join("c"); s.vote("c", "100")  # far outlier
    r = s.reveal()
    assert "c" in r.outliers
    assert "a" not in r.outliers
    assert "b" not in r.outliers


def test_no_outliers_when_all_agree():
    s = PokerSession("demo", tolerance=0)
    s.join("a"); s.vote("a", "8")
    s.join("b"); s.vote("b", "8")
    r = s.reveal()
    assert r.outliers == []


def test_special_card_not_outlier():
    s = PokerSession("demo", tolerance=0)
    s.join("a"); s.vote("a", "8")
    s.join("b"); s.vote("b", "?")  # special — not a deck-step outlier
    r = s.reveal()
    assert "b" not in r.outliers


# ---------------------------------------------------------------------------
# Agreed card (upper-median)
# ---------------------------------------------------------------------------


def test_agreed_card_single_voter():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "13")
    r = s.reveal()
    assert r.agreed_card == "13"


def test_agreed_card_two_voters_upper():
    # n=2: upper-median takes index 1 (the higher card)
    s = PokerSession("demo", tolerance=10)
    s.join("a"); s.vote("a", "5")
    s.join("b"); s.vote("b", "8")
    r = s.reveal()
    assert r.agreed_card == "8"


def test_agreed_card_four_voters_upper_middle():
    # deck: 0,1,2,3,5,8,13,20,40,100
    # cards 1,3,5,8 → sorted by deck pos → [1,3,5,8] → n=4, idx=2 → "5"
    s = PokerSession("demo", tolerance=10)
    for p, c in zip(["a", "b", "c", "d"], ["1", "3", "5", "8"]):
        s.join(p); s.vote(p, c)
    r = s.reveal()
    assert r.agreed_card == "5"


def test_agreed_card_odd_voters():
    # 3 voters: 3, 5, 8 → sorted → [3,5,8] → n=3, idx=1 → "5"
    s = PokerSession("demo", tolerance=10)
    for p, c in zip(["a", "b", "c"], ["3", "5", "8"]):
        s.join(p); s.vote(p, c)
    r = s.reveal()
    assert r.agreed_card == "5"


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def test_distribution_sums_to_one():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "5")
    s.join("b"); s.vote("b", "5")
    s.join("c"); s.vote("c", "8")
    r = s.reveal()
    assert sum(r.distribution.values()) == pytest.approx(1.0)


def test_distribution_correct_fractions():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "5")
    s.join("b"); s.vote("b", "5")
    s.join("c"); s.vote("c", "8")
    r = s.reveal()
    assert r.distribution["5"] == pytest.approx(2 / 3)
    assert r.distribution["8"] == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# Numeric stats
# ---------------------------------------------------------------------------


def test_mean_and_median():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "3")
    s.join("b"); s.vote("b", "5")
    s.join("c"); s.vote("c", "13")
    r = s.reveal()
    assert r.mean == pytest.approx((3 + 5 + 13) / 3)
    assert r.median == pytest.approx(5.0)


def test_range_value():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "3")
    s.join("b"); s.vote("b", "13")
    r = s.reveal()
    assert r.range == 10  # 13 - 3 = 10


def test_spread_steps_value():
    # "3" is index 3, "13" is index 6 → spread = 3
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "3")
    s.join("b"); s.vote("b", "13")
    r = s.reveal()
    assert r.spread_steps == 3


# ---------------------------------------------------------------------------
# State privacy
# ---------------------------------------------------------------------------


def test_state_hides_others_pre_reveal():
    s = PokerSession("demo")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "8")
    state = s.state_for("bob")
    alice = next(p for p in state["players"] if p["name"] == "alice")
    assert alice["voted"] is True
    assert alice["card"] is None  # hidden pre-reveal


def test_state_shows_own_card_pre_reveal():
    s = PokerSession("demo")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "8")
    state = s.state_for("alice")
    alice = next(p for p in state["players"] if p["name"] == "alice")
    assert alice["card"] == "8"


def test_state_reveals_all_post_reveal():
    s = PokerSession("demo")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "8")
    s.vote("bob", "5")
    s.reveal()
    for viewer in ("alice", "bob", ""):
        state = s.state_for(viewer)
        alice = next(p for p in state["players"] if p["name"] == "alice")
        assert alice["card"] == "8", f"alice's card should be visible to {viewer!r}"


def test_state_unvoted_player_card_is_none():
    s = PokerSession("demo")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "8")
    state = s.state_for("alice")
    bob = next(p for p in state["players"] if p["name"] == "bob")
    assert bob["voted"] is False
    assert bob["card"] is None


# ---------------------------------------------------------------------------
# Finalize → velocity
# ---------------------------------------------------------------------------


def test_finalize_returns_float():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    s.reveal()
    val = s.finalize()
    assert val == pytest.approx(8.0)


def test_finalize_appends_to_velocity():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    s.reveal()
    s.finalize()
    assert 8.0 in s.as_dict()["velocity"]


def test_finalize_before_reveal_raises():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    with pytest.raises(ValueError, match="[Rr]eveal"):
        s.finalize()


def test_velocity_grows_across_rounds():
    s = PokerSession("demo", tolerance=10)
    for card in ("5", "8", "13"):
        s.revote()
        s.join("a")  # idempotent
        s.vote("a", card)
        s.reveal()
        s.finalize()
    assert s.as_dict()["velocity"] == [5.0, 8.0, 13.0]


def test_finalize_special_card_returns_none():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "?")
    s.reveal()
    val = s.finalize()
    assert val is None


# ---------------------------------------------------------------------------
# Version counter
# ---------------------------------------------------------------------------


def test_version_increments_on_join():
    s = PokerSession("demo")
    v0 = s._version
    s.join("alice")
    assert s._version > v0


def test_version_increments_on_vote():
    s = PokerSession("demo")
    s.join("alice")
    v1 = s._version
    s.vote("alice", "8")
    assert s._version > v1


def test_version_increments_on_reveal():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "8")
    v2 = s._version
    s.reveal()
    assert s._version > v2


def test_version_increments_on_revote():
    s = PokerSession("demo")
    s.join("alice")
    s.vote("alice", "8")
    s.reveal()
    v3 = s._version
    s.revote()
    assert s._version > v3


# ---------------------------------------------------------------------------
# JSON serialisability
# ---------------------------------------------------------------------------


def test_round_result_as_dict_json_serializable():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    r = s.reveal()
    d = r.as_dict()
    json.dumps(d)  # must not raise


def test_round_result_as_dict_has_required_keys():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    r = s.reveal()
    d = r.as_dict()
    for key in ("cards", "distribution", "consensus", "range", "median",
                 "mean", "spread_steps", "outliers", "agreed_card"):
        assert key in d, f"missing key: {key}"


def test_state_for_has_version():
    s = PokerSession("demo")
    state = s.state_for("nobody")
    assert "version" in state


# ---------------------------------------------------------------------------
# Reset (via revote) and re-vote recency check
# ---------------------------------------------------------------------------


def test_revote_preserves_velocity():
    s = PokerSession("demo")
    s.join("a"); s.vote("a", "8")
    s.reveal(); s.finalize()
    s.revote()
    assert s.as_dict()["velocity"] == [8.0]  # velocity survives revote
