"""Property tests for VoteBankDAO."""
import math

import pytest

from vank.dao import Ballot, VoteBankDAO


# ---------------------------------------------------------------------------
# join — idempotence & ordering
# ---------------------------------------------------------------------------


def test_join_idempotent_weight_unchanged():
    dao = VoteBankDAO()
    dao.join("alice", 2.0)
    dao.join("alice", 9.9)  # second join must NOT update weight
    assert dao.members["alice"] == 2.0
    assert list(dao.members.keys()) == ["alice"]


def test_join_multiple_idempotent():
    dao = VoteBankDAO()
    for _ in range(5):
        dao.join("bob", 1.5)
    assert len(dao.members) == 1
    assert dao.members["bob"] == 1.5


def test_join_insertion_order():
    dao = VoteBankDAO()
    names = ["charlie", "alice", "bob", "zara"]
    for n in names:
        dao.join(n)
    assert list(dao.members.keys()) == names


def test_join_default_weight():
    dao = VoteBankDAO()
    dao.join("alice")
    assert dao.members["alice"] == 1.0


def test_member_list_order():
    dao = VoteBankDAO()
    for n in ["x", "y", "z"]:
        dao.join(n)
    assert dao.member_list() == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# cast
# ---------------------------------------------------------------------------


def test_cast_returns_ballot():
    dao = VoteBankDAO()
    dao.join("alice", 3.0)
    b = dao.cast("alice", "option_a", 42.5)
    assert isinstance(b, Ballot)
    assert b.voter == "alice"
    assert b.option == "option_a"
    assert b.timestamp == 42.5
    assert b.weight == 3.0


def test_cast_uses_member_weight():
    dao = VoteBankDAO()
    dao.join("alice", 7.0)
    b = dao.cast("alice", "x", 1.0)
    assert b.weight == 7.0


def test_cast_non_member_defaults_to_one():
    dao = VoteBankDAO()
    b = dao.cast("stranger", "x", 1.0)
    assert b.weight == 1.0


# ---------------------------------------------------------------------------
# decide — recency weighting
# ---------------------------------------------------------------------------


def test_decide_no_decay_equal_weights():
    dao = VoteBankDAO()
    dao.join("alice")
    dao.join("bob")
    ballots = [dao.cast("alice", "yes", 1.0), dao.cast("bob", "no", 1.0)]
    res = dao.decide(["yes", "no"], ballots, decay=0.0)
    assert res["yes"] == pytest.approx(1.0)
    assert res["no"] == pytest.approx(1.0)


def test_decide_recency_older_vote_discounted():
    dao = VoteBankDAO()
    dao.join("alice")
    dao.join("bob")
    # alice votes at t=0, bob votes at t=10 (more recent)
    ballots = [dao.cast("alice", "yes", 0.0), dao.cast("bob", "no", 10.0)]
    res = dao.decide(["yes", "no"], ballots, decay=0.1)
    # alice: weight *= exp(-0.1 * 10) = exp(-1) ≈ 0.368
    # bob:   weight *= exp(-0.1 * 0)  = 1.0
    assert res["yes"] == pytest.approx(math.exp(-1.0))
    assert res["no"] == pytest.approx(1.0)
    assert res["no"] > res["yes"]


def test_decide_recency_most_recent_is_undiscounted():
    dao = VoteBankDAO()
    dao.join("alice")
    ballots = [dao.cast("alice", "yes", 99.9)]
    res = dao.decide(["yes"], ballots, decay=1.0)
    # max_ts == ballot.ts → exp(0) = 1.0
    assert res["yes"] == pytest.approx(1.0)


def test_decide_empty_ballots():
    dao = VoteBankDAO()
    res = dao.decide(["a", "b"], [], decay=0.5)
    assert res == {"a": 0.0, "b": 0.0}


def test_decide_ignores_unknown_option():
    dao = VoteBankDAO()
    dao.join("alice")
    b = dao.cast("alice", "unknown_opt", 1.0)
    res = dao.decide(["yes", "no"], [b], decay=0.0)
    assert res == {"yes": 0.0, "no": 0.0}


def test_decide_weighted_members():
    dao = VoteBankDAO()
    dao.join("heavy", 10.0)
    dao.join("light", 1.0)
    ballots = [dao.cast("heavy", "yes", 1.0), dao.cast("light", "no", 1.0)]
    res = dao.decide(["yes", "no"], ballots, decay=0.0)
    assert res["yes"] == pytest.approx(10.0)
    assert res["no"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# momentum — EMA
# ---------------------------------------------------------------------------


def test_momentum_single_element():
    dao = VoteBankDAO()
    assert dao.momentum([7.0]) == pytest.approx(7.0)


def test_momentum_two_elements():
    dao = VoteBankDAO()
    # ema = 0.3*20 + 0.7*10 = 6 + 7 = 13
    assert dao.momentum([10.0, 20.0], alpha=0.3) == pytest.approx(13.0)


def test_momentum_convergence():
    dao = VoteBankDAO()
    series = [5.0] * 200
    result = dao.momentum(series, alpha=0.3)
    assert result == pytest.approx(5.0, abs=1e-6)


def test_momentum_rising():
    dao = VoteBankDAO()
    series = list(range(1, 11))  # 1..10
    result = dao.momentum(series, alpha=0.5)
    # Should be between mid and latest
    assert 5.0 < result < 10.0


def test_momentum_empty():
    dao = VoteBankDAO()
    assert dao.momentum([]) == 0.0


def test_momentum_alpha_zero_returns_first():
    """alpha=0 → EMA never updates, stays at first value."""
    dao = VoteBankDAO()
    assert dao.momentum([3.0, 100.0, 999.0], alpha=0.0) == pytest.approx(3.0)


def test_momentum_alpha_one_returns_last():
    """alpha=1 → EMA always equals last value."""
    dao = VoteBankDAO()
    assert dao.momentum([1.0, 2.0, 42.0], alpha=1.0) == pytest.approx(42.0)
