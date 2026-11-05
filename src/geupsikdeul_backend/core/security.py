import re
import secrets
import string
from datetime import timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from geupsikdeul_backend.core import clock
from geupsikdeul_backend.core.config import settings

_hasher = PasswordHasher()
# Used to burn equivalent time when the account doesn't exist (no user-enumeration via timing).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")

_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def is_strong_password(password: str) -> bool:
    return bool(_PASSWORD_RE.match(password))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def generate_temporary_password(length: int = 8) -> str:
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if is_strong_password(pw):
            return pw


TokenType = Literal["access", "refresh"]


def create_token(user_id: int, token_version: int, token_type: TokenType) -> str:
    issued = clock.now()
    if token_type == "access":
        expires = issued + timedelta(minutes=settings.access_token_expire_minutes)
    else:
        expires = issued + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "type": token_type,
        "ver": token_version,
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    # Expiry checked against our clock so tests can control time.
    if (
        payload.get("type") != expected_type
        or int(payload.get("exp", 0)) <= clock.now().timestamp()
    ):
        return None
    return payload


def mask_name(name: str) -> str:
    """김철수 -> 김*수, 김수 -> 김*, 남궁민수 -> 남**수."""
    if len(name) <= 1:
        return name
    if len(name) == 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]
