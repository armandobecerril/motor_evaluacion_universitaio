"""Reloj autoritativo del servidor (UTC). Se sustituye en pruebas para simular el paso del tiempo."""

from __future__ import annotations

from datetime import UTC, datetime

_override: datetime | None = None


def now() -> datetime:
    return _override if _override is not None else datetime.now(UTC)


def set_now(value: datetime | None) -> None:
    """Solo pruebas."""
    global _override
    _override = value
