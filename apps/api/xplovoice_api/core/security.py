# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Password hashing (Argon2id), token signing, secret encryption and hashing helpers."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet

from .config import get_settings

_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id
# A fixed dummy hash so unknown-user logins cost the same time as known-user logins.
_DUMMY_HASH = _hasher.hash("xplovoice-timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    """Keyed hash for storing bearer secrets (refresh tokens, invitations). Never store the raw token."""
    key = get_settings().jwt_secret.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    if not ip:
        return None
    return hmac.new(get_settings().jwt_secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def _fernet() -> Fernet:
    digest = hashlib.sha256(("enc:" + get_settings().jwt_secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def issue_access_token(
    *, user_id: UUID, tenant_id: UUID, membership_id: UUID, session_id: UUID, mfa: bool
) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.access_token_minutes)
    payload = {
        "iss": s.jwt_issuer,
        "sub": str(user_id),
        "tid": str(tenant_id),
        "mid": str(membership_id),
        "sid": str(session_id),
        "amr": ["pwd", "otp"] if mfa else ["pwd"],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256"), exp


def decode_access_token(token: str) -> dict:
    s = get_settings()
    claims = jwt.decode(
        token,
        s.jwt_secret,
        algorithms=["HS256"],
        issuer=s.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "tid", "sid"]},
    )
    if claims.get("typ") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return claims
