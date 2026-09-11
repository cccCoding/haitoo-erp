from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import Role, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer()


def hash_password(value: str) -> str:
    return pwd_context.hash(value)


def verify_password(value: str, password_hash: str) -> bool:
    return pwd_context.verify(value, password_hash)


def create_access_token(user: User) -> str:
    settings = get_settings()
    access_token_minutes = (
        settings.super_admin_access_token_minutes
        if user.role == Role.SUPER_ADMIN
        else settings.access_token_minutes
    )
    expires = datetime.now(timezone.utc) + timedelta(minutes=access_token_minutes)
    return jwt.encode({
        "sub": str(user.id),
        "role": user.role.value,
        "company_id": user.company_id,
        "ver": user.token_version,
        "exp": expires,
    }, settings.secret_key, algorithm="HS256")


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
        token_version = int(payload["ver"])
    except (JWTError, KeyError, TypeError, ValueError):
        user = None
    if not user or not user.is_active or user.token_version != token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效")
    return user


def require_roles(*roles: Role):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="当前账号没有此操作权限")
        if user.role == Role.SUPER_ADMIN and user.company_id is not None:
            raise HTTPException(status_code=403, detail="超级管理员账号归属异常")
        return user
    return checker
