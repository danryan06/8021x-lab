from datetime import UTC, datetime, timedelta

from Crypto.Hash import MD4
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.schemas.common import TokenPayload

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
settings = get_settings()

ALGORITHM = "HS256"


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def nt_hash_password(password: str) -> str:
    """Return FreeRADIUS NT-Password value: 0x + uppercase MD4(UTF-16LE).

    Required for PEAP/MSCHAPv2. Never log the returned value.
    Uses PyCryptodome because OpenSSL 3 often disables MD4 in hashlib.
    """
    digest = MD4.new(password.encode("utf-16-le")).digest()
    return "0x" + digest.hex().upper()


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def authenticate_admin(username: str, password: str) -> bool:
    return username == settings.admin_username and password == settings.admin_password


async def get_current_admin(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        sub = data.get("sub")
        if not sub:
            raise credentials_exception
        return TokenPayload(sub=sub)
    except JWTError as exc:
        raise credentials_exception from exc
