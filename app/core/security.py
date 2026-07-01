import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Mots de passe ─────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    payload = data.copy()
    payload.update({
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
        "type": token_type,
    })
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(data: dict) -> str:
    return _create_token(
        data,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )


def create_refresh_token(data: dict) -> str:
    return _create_token(
        data,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError(f"Token invalide : {e}") from e


# ── OTP ───────────────────────────────────────────────────────────────────────

def generate_otp(length: int = 6) -> str:
    return "".join([str(secrets.randbelow(10)) for _ in range(length)])


# ── Webhook signature validation ──────────────────────────────────────────────

def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret: str,
    algorithm: str = "sha256",
) -> bool:
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        getattr(hashlib, algorithm),
    ).hexdigest()
    return hmac.compare_digest(expected, signature.removeprefix(f"sha256="))
