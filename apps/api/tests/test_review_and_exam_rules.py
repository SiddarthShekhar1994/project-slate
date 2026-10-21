
import pytest

from slate_api.services.exam import allocate, time_limit_seconds
from slate_api.services.review import CardState, item_quality, review, session_quality


def test_item_quality():
    assert item_quality(correct=True, misses=0, hints_used=0) == 5
    assert item_quality(correct=True, misses=0, hints_used=2) == 4
    assert item_quality(correct=True, misses=1, hints_used=0) == 3
    assert item_quality(correct=True, misses=3, hints_used=3) == 2
    assert item_quality(correct=False, misses=0, hints_used=0) == 1


def test_session_quality_rounds_down():
    assert session_quality([5, 4]) == 4
    assert session_quality([5, 3, 3]) == 3
    with pytest.raises(ValueError):
        session_quality([])


def test_sm2_intervals_grow_then_reset():
    card = CardState()
    intervals = []
    for _ in range(4):
        card = review(card, 5)
        intervals.append(card.interval_days)
    # Easiness climbs 0.1 per perfect review: 6 * 2.8 = 16.8, then 17 * 2.9 = 49.3.
    assert intervals == [1, 6, 17, 49]
    assert card.easiness == pytest.approx(2.9)

    lapsed = review(card, 2)
    assert (lapsed.interval_days, lapsed.repetitions, lapsed.lapses) == (1, 0, 1)
    assert lapsed.easiness < card.easiness


def test_easiness_never_below_floor():
    card = CardState()
    for _ in range(20):
        card = review(card, 0)
    assert card.easiness == 1.3


def test_allocate_follows_weights_and_covers_every_topic():
    assert allocate({"a": 50, "b": 30, "c": 20}, 10) == {"a": 5, "b": 3, "c": 2}
    # Largest remainder: 8 * (0.5, 0.3, 0.2) = 4, 2.4, 1.6
    assert allocate({"a": 50, "b": 30, "c": 20}, 8) == {"a": 4, "b": 2, "c": 2}
    # A tiny weight still gets one problem when there are enough to go round.
    out = allocate({"a": 95, "b": 5}, 6)
    assert out["b"] == 1 and sum(out.values()) == 6
    # Fewer problems than topics: the heaviest topics win.
    assert allocate({"a": 10, "b": 60, "c": 30}, 2) == {"a": 0, "b": 1, "c": 1}
    assert allocate({"a": 0, "b": 10}, 3) == {"a": 0, "b": 3}


def test_time_limit_by_pace():
    assert time_limit_seconds([1, 2, 3, 4], "exam") == 17 * 60
    assert time_limit_seconds([1, 2, 3, 4], "study") == 26 * 60  # 25.5 rounded up
