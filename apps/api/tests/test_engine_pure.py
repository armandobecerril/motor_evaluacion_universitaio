"""Selección y calificación (sin BD). Casos de docs/07_TEST_PLAN.md."""

from __future__ import annotations

import random
from collections import Counter
from decimal import Decimal

import pytest

from exam_engine.services.scoring import compute
from exam_engine.services.selection import PoolItem, SelectionError, feasibility, select

SCORING = {"correct": 1, "wrong": -1, "omitted": 0, "expired": 0}


def _pool(groups_per_module=25, variants=4, modules=4):
    return [
        PoolItem(f"m{m}g{g}v{v}", m, f"M{m:02d}-C{g:02d}")
        for m in range(1, modules + 1)
        for g in range(1, groups_per_module + 1)
        for v in range(1, variants + 1)
    ]


@pytest.mark.parametrize(
    ("c", "w", "o", "grade"),
    [(200, 0, 0, "100.00"), (100, 100, 0, "0.00"), (150, 25, 25, "62.50"), (0, 200, 0, "0.00"), (0, 0, 200, "0.00")],
)
def test_scoring_cases(c, w, o, grade):
    s = compute(["correct"] * c + ["wrong"] * w + ["omitted"] * o, 200, SCORING)
    assert s.grade_display == grade
    assert s.correct + s.wrong + s.omitted + s.expired == 200


def test_unanswered_count_as_expired_zero_points():
    s = compute(["correct"] * 10, 200, SCORING)
    assert (s.correct, s.expired, s.raw) == (10, 190, 10)
    assert s.grade == Decimal("5.0000")


def test_selection_200_balanced_two_variants_per_group():
    sel = select(_pool(), [1, 2, 3, 4], quota=50, max_per_group=2, rng=random.Random(7))
    assert len(sel) == 200
    assert len({s.question_id for s in sel}) == 200
    assert Counter(s.module_number for s in sel) == {1: 50, 2: 50, 3: 50, 4: 50}
    per_group = Counter(s.conceptual_group for s in sel)
    assert set(per_group.values()) == {2} and len(per_group) == 100  # cada concepto exactamente dos veces
    assert all(a.conceptual_group != b.conceptual_group for a, b in zip(sel, sel[1:], strict=False))
    assert all(sorted(s.options_order) == ["A", "B", "C", "D"] for s in sel)


def test_selection_differs_between_students():
    a = select(_pool(), [1, 2, 3, 4], 50, 2, random.Random(1))
    b = select(_pool(), [1, 2, 3, 4], 50, 2, random.Random(2))
    assert [s.question_id for s in a] != [s.question_id for s in b]


def test_selection_one_per_group_is_infeasible_and_raises():
    assert feasibility(_pool(), [1, 2, 3, 4], 50, 1) == {1: 25, 2: 25, 3: 25, 4: 25}
    with pytest.raises(SelectionError):
        select(_pool(), [1, 2, 3, 4], 50, 1)


def test_uneven_groups_still_balanced():
    pool = _pool(groups_per_module=3, variants=4, modules=1)
    sel = select(pool, [1], quota=7, max_per_group=4, rng=random.Random(3))
    counts = sorted(Counter(s.conceptual_group for s in sel).values())
    assert counts == [2, 2, 3]
