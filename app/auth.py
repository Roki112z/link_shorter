from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import User

optional_bearer = HTTPBearer(auto_error=False)
required_bearer = HTTPBearer(auto_error=True)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    iterations = 390000
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{iterations}${salt.hex()}${password_hash.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        iterations_str, salt_hex, hash_hex = hashed_password.split("$", maxsplit=2)
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        original_hash = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False

    calculated_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(calculated_hash, original_hash)


def create_access_token(user_id: int) -> str:
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def _decode_user_from_token(token: str, db: AsyncSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Некорректный или просроченный токен",
    )

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise credentials_error

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_error
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(required_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _decode_user_from_token(credentials.credentials, db)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return await _decode_user_from_token(credentials.credentials, db)
