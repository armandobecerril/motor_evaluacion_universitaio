"""Configuración por variables de entorno. Nunca se registran ni exponen valores secretos."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(default="local", alias="APP_ENV")
    build_sha: str = Field(default="dev", alias="BUILD_SHA")

    # Conexión del rol de aplicación (DML, sujeto a RLS). Formato SQLAlchemy:
    # postgresql+psycopg://exam_app:***@host:5432/exam?sslmode=require
    database_url: SecretStr = Field(alias="DATABASE_URL")

    # Pool pequeño: B1ms admite 35 conexiones de usuario. Instancias máx × (pool + overflow) < 35.
    db_pool_size: int = Field(default=3, alias="DB_POOL_SIZE", ge=1, le=20)
    db_max_overflow: int = Field(default=2, alias="DB_MAX_OVERFLOW", ge=0, le=20)
    db_pool_timeout_s: int = Field(default=10, alias="DB_POOL_TIMEOUT_S", ge=1, le=60)
    db_statement_timeout_ms: int = Field(default=5000, alias="DB_STATEMENT_TIMEOUT_MS", ge=100)

    # Secreto para HMAC de códigos de acceso (Key Vault en Azure). Cambiarlo invalida los códigos vigentes.
    access_code_pepper: SecretStr = Field(alias="ACCESS_CODE_PEPPER")

    # Sesiones de docentes
    admin_session_hours: int = Field(default=8, alias="ADMIN_SESSION_HOURS", ge=1, le=24)
    admin_max_failed_logins: int = Field(default=5, alias="ADMIN_MAX_FAILED_LOGINS", ge=3, le=20)
    admin_lockout_minutes: int = Field(default=15, alias="ADMIN_LOCKOUT_MINUTES", ge=1, le=1440)

    # Límite de carga del banco
    max_bank_upload_bytes: int = Field(default=5_000_000, alias="MAX_BANK_UPLOAD_BYTES", ge=10_000)

    @property
    def is_local(self) -> bool:
        return self.environment == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
