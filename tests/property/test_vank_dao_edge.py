"""Edge-case tests for VoteBankDAO (src/vank/dao.py)."""
import math

import pytest

from vank.dao import Ballot, VoteBankDAO


def test_join_updates_nothing_on_duplicate():
    """Joining the same member twice with different weights keeps the first weight."""
    dao = VoteBankDAO()
    dao.join("alice", 2.0)
    dao.join("alice", 9.9)
    assert dao.members["alice"] == 2.0
    assert len(dao.members) == 1


def test_member_list_insertion_order():
    """member_list() returns names in join order: A, B, C."""
    dao = VoteBankDAO()
    dao.join("A")
    dao.join("B")
    dao.join("C")
    assert dao.member_list() == ["A", "B", "C"]


def test_decide_empty_ballots():
    """Empty ballot list returns all-zero scores for every listed option."""
    dao = VoteBankDAO()
    result = dao.decide(["alpha", "beta"], [], decay=0.5)
    assert result == {"alpha": 0.0, "beta": 0.0}


def test_decide_single_option():
    """One voter, one option: score equals weight (most-recent ballot gets no decay)."""
    dao = VoteBankDAO()
    dao.join("alice", 3.0)
    ballot = dao.cast("alice", "yes", 5.0)
    result = dao.decide(["yes"], [ballot], decay=0.9)
    # alice is the only ballot, so max_ts == ballot.timestamp → exp(0) = 1.0
    assert result["yes"] == pytest.approx(3.0)


def test_momentum_empty():
    """momentum([]) returns 0.0."""
    dao = VoteBankDAO()
    assert dao.momentum([]) == 0.0


def test_momentum_single():
    """momentum([x]) returns x — EMA of a single-element series equals that element."""
    dao = VoteBankDAO()
    assert dao.momentum([7.5]) == pytest.approx(7.5)
    assert dao.momentum([0.0]) == pytest.approx(0.0)
    assert dao.momentum([-3.14]) == pytest.approx(-3.14)


def test_cast_unknown_voter_defaults_weight_1():
    """Casting a ballot for a voter not in the member registry defaults weight to 1.0."""
    dao = VoteBankDAO()
    # Intentionally do NOT join "stranger"
    ballot = dao.cast("stranger", "option_x", 42.0)
    assert ballot.weight == 1.0
    assert ballot.voter == "stranger"
    assert ballot.option == "option_x"


def test_decay_all_same_timestamp():
    """All ballots at the same timestamp experience zero decay; weights sum correctly."""
    dao = VoteBankDAO()
    dao.join("alice", 2.0)
    dao.join("bob", 3.0)
    ts = 100.0
    ballots = [
        dao.cast("alice", "yes", ts),
        dao.cast("bob", "yes", ts),
    ]
    result = dao.decide(["yes", "no"], ballots, decay=0.5)
    # max_ts == ts for all → recency = exp(0) = 1.0 → score = 2.0 + 3.0
    assert result["yes"] == pytest.approx(5.0)
    assert result["no"] == pytest.approx(0.0)
