from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from .config import get_settings
from .database import get_db
from .models import Company, Role, User
from .supply_accounts import supply_user_is_expired

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
    validate_supply_user_access(user, db)
    return user


def validate_supply_user_access(user: User, db: Session) -> None:
    """登录和令牌认证共用校验，账号续期不会绕过人工停用。"""
    if user.role != Role.SUPPLY_USER:
        return
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="货盘账号已停用")
    if supply_user_is_expired(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="货盘账号使用有效期已到期")
    company = db.get(Company, user.company_id) if user.company_id is not None else None
    if not company or not company.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="公司已停用或不存在")


def current_internal_user(user: User = Depends(current_user)) -> User:
    """旧业务接口明确允许内部角色，外部货盘用户不能落入默认公司权限。"""
    if user.role not in {Role.SUPER_ADMIN, Role.COMPANY_ADMIN, Role.MEMBER, Role.TEAM_LEADER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号仅可使用公开货盘")
    return user


def require_roles(*roles: Role):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="当前账号没有此操作权限")
        if user.role == Role.SUPER_ADMIN and user.company_id is not None:
            raise HTTPException(status_code=403, detail="超级管理员账号归属异常")
        return user
    return checker
