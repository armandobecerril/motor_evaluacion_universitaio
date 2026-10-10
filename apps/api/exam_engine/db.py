"""Engine de SQLAlchemy con pool limitado y contexto de universidad (RLS).

Cada unidad de trabajo abre una transacción y fija ``app.institution_id`` con
``set_config(..., is_local => true)``: el valor vive solo dentro de la transacción,
así una conexión reutilizada del pool nunca hereda el tenant de otra petición.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        s = get_settings()
        _engine = create_engine(
            s.database_url.get_secret_value(),
            pool_size=s.db_pool_size,
            max_overflow=s.db_max_overflow,
            pool_timeout=s.db_pool_timeout_s,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args={"options": f"-c statement_timeout={s.db_statement_timeout_ms}"},
        )
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Solo para pruebas."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine, _factory = None, None


@contextmanager
def tenant_session(institution_id: uuid.UUID | None, *, platform_admin: bool = False) -> Iterator[Session]:
    """Transacción atómica con contexto RLS.

    - ``institution_id``: universidad del actor; las políticas RLS filtran por este valor.
    - ``platform_admin``: solo para endpoints de administración de plataforma (acceso entre universidades).
    """
    get_engine()
    assert _factory is not None
    session = _factory()
    try:
        with session.begin():
            session.execute(
                text(
                    "SELECT set_config('app.institution_id', :tid, true), set_config('app.platform_admin', :pa, true)"
                ),
                {"tid": str(institution_id) if institution_id else "", "pa": "on" if platform_admin else "off"},
            )
            yield session
    finally:
        session.close()


def ping() -> bool:
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one() == 1


def current_migration() -> str | None:
    with get_engine().connect() as conn:
        try:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except ProgrammingError:  # tabla inexistente antes de migrar
            return None
