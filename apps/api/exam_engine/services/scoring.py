"""Calificación del intento (solo servidor).

raw = correctas·w_c + incorrectas·w_w (+ omitidas/expiradas con su peso, normalmente 0)
nota = max(0, raw / (total · w_c) · 100), acotada a [0, 100]. Con +1/−1/0 y 200 preguntas:
nota = max(0, (correctas − incorrectas) / 200 · 100).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True)
class Score:
    total: int
    correct: int
    wrong: int
    omitted: int
    expired: int
    raw: int
    grade: Decimal  # 4 decimales; se muestra con 2

    @property
    def grade_display(self) -> str:
        return str(self.grade.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute(outcomes: list[str], total: int, scoring: dict[str, Any]) -> Score:
    c = outcomes.count("correct")
    w = outcomes.count("wrong")
    o = outcomes.count("omitted")
    e = outcomes.count("expired")
    missing = total - (c + w + o + e)
    if missing < 0:
        raise ValueError("más respuestas que preguntas")
    e += missing  # preguntas no servidas al cerrar la ventana cuentan como expiradas (0 puntos)
    wc, ww = int(scoring.get("correct", 1)), int(scoring.get("wrong", -1))
    wo, we = int(scoring.get("omitted", 0)), int(scoring.get("expired", 0))
    raw = c * wc + w * ww + o * wo + e * we
    max_raw = total * wc if wc > 0 else 1
    grade = Decimal(raw * 100) / Decimal(max_raw)
    grade = min(Decimal(100), max(Decimal(0), grade)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Score(total=total, correct=c, wrong=w, omitted=o, expired=e, raw=raw, grade=grade)
