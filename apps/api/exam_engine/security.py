"""Primitivas de seguridad: contraseñas (Argon2id), tokens opacos y códigos de acceso."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_ph = PasswordHasher()  # parámetros por defecto de argon2-cffi (Argon2id, RFC 9106 low-memory)

# Hash ficticio para igualar tiempos cuando el usuario no existe (evita enumeración de usuarios).
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))

# Alfabeto sin caracteres ambiguos (0/O, 1/I/L) para códigos que se dictan o escriben a mano.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str, username: str) -> list[str]:
    """Política mínima para contraseñas definitivas de docentes."""
    problems = []
    if len(password) < 12:
        problems.append("Debe tener al menos 12 caracteres.")
    if username and username.lower() in password.lower():
        problems.append("No debe contener el nombre de usuario.")
    if password.lower() in {"password123$", "password123", "contraseña123", "admin123456!", "123456789012"}:
        problems.append("Es una contraseña común; elige otra.")
    classes = sum(
        [any(c.islower() for c in password), any(c.isupper() for c in password), any(c.isdigit() for c in password)]
    ) + (1 if any(not c.isalnum() for c in password) else 0)
    if classes < 3:
        problems.append("Combina al menos tres de: minúsculas, mayúsculas, dígitos y símbolos.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_access_code(length: int = 8) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def normalize_access_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def access_code_lookup(code: str, pepper: str) -> str:
    """HMAC del código normalizado: permite buscar el examen sin guardar el código en claro."""
    return hmac.new(pepper.encode(), normalize_access_code(code).encode(), hashlib.sha256).hexdigest()
