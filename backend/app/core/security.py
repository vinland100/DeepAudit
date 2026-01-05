from datetime import datetime, timedelta, timezone
from typing import Any, Union
from jose import jwt
import bcrypt

from app.core.config import settings

ALGORITHM = settings.ALGORITHM

def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against a hash.
    Explicitly truncate to 72 bytes to avoid bcrypt ValueError and maintain compatibility.
    """
    if not plain_password or not hashed_password:
        return False
        
    try:
        password_bytes = plain_password.encode("utf-8")
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
            
        return bcrypt.checkpw(
            password_bytes,
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """
    Generate a bcrypt hash of the password.
    Explicitly truncate to 72 bytes for consistency.
    """
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
        
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")






