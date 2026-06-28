"""Edge-case tests for PokerSession (src/vank/poker.py)."""
import pytest

from vank.poker import FIBONACCI_DECK, PokerSession


def test_vote_after_reveal_raises():
    """Voting after reveal (without revote) raises ValueError."""
    s = PokerSession("story-1")
    s.join("alice")
    s.vote("alice", "5")
    s.reveal()
    with pytest.raises(ValueError):
        s.vote("alice", "8")


def test_revote_clears_previous_cards():
    """After vote → reveal → revote, no player is considered to have voted."""
    s = PokerSession("story-1")
    s.join("alice")
    s.join("bob")
    s.vote("alice", "5")
    s.vote("bob", "8")
    s.reveal()
    s.revote()
    state = s.state_for("alice")
    for player in state["players"]:
        assert player["voted"] is False
        assert player["card"] is None


def test_finalize_without_reveal_raises():
    """Calling finalize() before reveal() raises ValueError."""
    s = PokerSession("story-1")
    s.join("alice")
    s.vote("alice", "8")
    with pytest.raises(ValueError):
        s.finalize()


def test_state_for_hides_others_pre_reveal():
    """Pre-reveal: playerB's state_for view hides playerA's card."""
    s = PokerSession("story-1")
    s.join("playerA")
    s.join("playerB")
    s.vote("playerA", "8")
    state = s.state_for("playerB")
    player_a = next(p for p in state["players"] if p["name"] == "playerA")
    assert player_a["voted"] is True
    assert player_a["card"] is None  # hidden from playerB


def test_state_for_shows_own_card_pre_reveal():
    """Pre-reveal: state_for the voter shows their own card."""
    s = PokerSession("story-1")
    s.join("playerA")
    s.vote("playerA", "8")
    state = s.state_for("playerA")
    player_a = next(p for p in state["players"] if p["name"] == "playerA")
    assert player_a["card"] == "8"


def test_tolerance_one_adjacent_cards_consensus():
    """Two players vote '5' and '8' (one deck-step apart); tolerance=1 yields consensus."""
    # FIBONACCI_DECK: "5" is at index 4, "8" is at index 5 → spread_steps = 1
    s = PokerSession("story-1", tolerance=1)
    s.join("alice")
    s.join("bob")
    s.vote("alice", "5")
    s.vote("bob", "8")
    result = s.reveal()
    assert result.spread_steps == 1
    assert result.consensus is not None


def test_tolerance_zero_different_cards_no_consensus():
    """Two players vote '5' and '8'; tolerance=0 means no consensus."""
    s = PokerSession("story-1", tolerance=0)
    s.join("alice")
    s.join("bob")
    s.vote("alice", "5")
    s.vote("bob", "8")
    result = s.reveal()
    assert result.consensus is None


def test_reset_clears_all_state():
    """A fresh PokerSession (simulating a reset) has no players, no votes, no result."""
    s = PokerSession("story-1")
    s.join("alice")
    s.vote("alice", "5")
    s.reveal()
    s.finalize()
    # Reset = create a brand-new session
    fresh = PokerSession("story-1")
    assert fresh._players == []
    assert fresh._votes == {}
    assert fresh._last_result is None
    assert fresh._version == 0


def test_version_bumps_on_mutation():
    """join, vote, reveal, and revote each independently bump the version counter."""
    s = PokerSession("story-1")

    v0 = s._version
    s.join("alice")
    v_after_join = s._version
    assert v_after_join > v0, "join must bump version"

    s.vote("alice", "5")
    v_after_vote = s._version
    assert v_after_vote > v_after_join, "vote must bump version"

    s.reveal()
    v_after_reveal = s._version
    assert v_after_reveal > v_after_vote, "reveal must bump version"

    s.revote()
    v_after_revote = s._version
    assert v_after_revote > v_after_reveal, "revote must bump version"
