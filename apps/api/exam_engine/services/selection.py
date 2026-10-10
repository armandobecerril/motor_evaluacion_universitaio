"""Selección de reactivos por intento (función pura, RNG criptográfico).

Regla (ADR-006): por cada módulo se eligen ``per_module_quota`` reactivos del pool congelado del examen,
repartidos de forma balanceada entre grupos conceptuales y con a lo sumo ``max_variants_per_group``
variantes por grupo. Luego se mezclan todos los módulos (Fisher–Yates) evitando, si es posible, dos
variantes del mismo grupo en posiciones consecutivas. Las opciones de cada reactivo también se barajan.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Hashable
from dataclasses import dataclass

OPTION_CODES = ("A", "B", "C", "D")


@dataclass(frozen=True)
class PoolItem:
    question_id: Hashable
    module_number: int
    conceptual_group: str


@dataclass(frozen=True)
class Selected:
    question_id: Hashable
    module_number: int
    conceptual_group: str
    options_order: tuple[str, ...]


class SelectionError(ValueError):
    pass


def feasibility(pool: list[PoolItem], modules: list[int], quota: int, max_per_group: int) -> dict[int, int]:
    """Máximo seleccionable por módulo dado el tope por grupo."""
    out: dict[int, int] = {}
    for m in modules:
        groups: dict[str, int] = defaultdict(int)
        for it in pool:
            if it.module_number == m:
                groups[it.conceptual_group] += 1
        out[m] = sum(min(c, max_per_group) for c in groups.values())
    return out


def _pick_module(items: list[PoolItem], quota: int, max_per_group: int, rng: random.Random) -> list[PoolItem]:
    by_group: dict[str, list[PoolItem]] = defaultdict(list)
    for it in items:
        by_group[it.conceptual_group].append(it)
    groups = list(by_group)
    rng.shuffle(groups)
    cap = {g: min(len(by_group[g]), max_per_group) for g in groups}
    if sum(cap.values()) < quota:
        raise SelectionError(f"módulo {items[0].module_number if items else '?'}: banco insuficiente")
    # Reparto balanceado: rondas de 1 por grupo hasta completar la cuota.
    take: dict[str, int] = defaultdict(int)
    remaining = quota
    while remaining:
        progressed = False
        for g in groups:
            if remaining and take[g] < cap[g]:
                take[g] += 1
                remaining -= 1
                progressed = True
        if not progressed:  # pragma: no cover — protegido por el chequeo de capacidad
            raise SelectionError("no se pudo completar la cuota")
    chosen: list[PoolItem] = []
    for g, n in take.items():
        chosen.extend(rng.sample(by_group[g], n))
    return chosen


def select(
    pool: list[PoolItem],
    modules: list[int],
    quota: int,
    max_per_group: int,
    rng: random.Random | None = None,
) -> list[Selected]:
    rng = rng or random.SystemRandom()
    picked: list[PoolItem] = []
    for m in modules:
        items = [it for it in pool if it.module_number == m]
        picked.extend(_pick_module(items, quota, max_per_group, rng))
    order = picked[:]
    for _ in range(100):  # evitar el mismo grupo en posiciones consecutivas
        rng.shuffle(order)
        if all(a.conceptual_group != b.conceptual_group for a, b in zip(order, order[1:], strict=False)):
            break
    result = []
    for it in order:
        opts = list(OPTION_CODES)
        rng.shuffle(opts)
        result.append(Selected(it.question_id, it.module_number, it.conceptual_group, tuple(opts)))
    return result
