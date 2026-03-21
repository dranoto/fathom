# app/routers/auth_routes.py
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session as SQLAlchemySession
from pydantic import BaseModel, EmailStr, Field

import bcrypt
import jwt as pyjwt

from .. import database
from .. import config as app_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

security = HTTPBearer(auto_error=False)

_rate_limit_store: dict[str, tuple[int, float]] = {}
_RATE_LIMIT_WINDOW_SECONDS = 60
_RATE_LIMIT_MAX_ATTEMPTS = 5

_jwt_secret = os.getenv("JWT_SECRET_KEY") if os.getenv("JWT_SECRET_KEY") else app_config.OPENAI_API_KEY
if not _jwt_secret:
    _jwt_secret = secrets.token_hex(32)
    logger.warning("AUTH: JWT_SECRET_KEY not set, using generated secret. Set JWT_SECRET_KEY env var for production.")
JWT_SECRET_KEY = _jwt_secret
JWT_ALGORITHM = "HS256"


def _check_rate_limit(identifier: str) -> tuple[bool, int]:
    import time
    current_time = time.time()
    if identifier in _rate_limit_store:
        attempts, first_attempt_time = _rate_limit_store[identifier]
        if current_time - first_attempt_time > _RATE_LIMIT_WINDOW_SECONDS:
            _rate_limit_store[identifier] = (1, current_time)
            return True, _RATE_LIMIT_MAX_ATTEMPTS - 1
        if attempts >= _RATE_LIMIT_MAX_ATTEMPTS:
            return False, 0
        _rate_limit_store[identifier] = (attempts + 1, first_attempt_time)
        return True, _RATE_LIMIT_MAX_ATTEMPTS - attempts - 1
    _rate_limit_store[identifier] = (1, current_time)
    return True, _RATE_LIMIT_MAX_ATTEMPTS - 1

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4, max_length=128)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    email: str
    is_admin: bool = False

class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool = False
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DeleteAccountRequest(BaseModel):
    confirm: str = Field(min_length=1)

class MessageResponse(BaseModel):
    message: str

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_access_token(user_id: int, email: str) -> str:
    import time
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + (365 * 24 * 60 * 60)
    }
    return pyjwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = pyjwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except pyjwt.InvalidTokenError as e:
        logger.error(f"JWT decode error: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT decode unexpected error: {e}")
        return None

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: SQLAlchemySession = Depends(database.get_db)
) -> database.User:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(database.User).filter(database.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: SQLAlchemySession = Depends(database.get_db)
) -> Optional[database.User]:
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        return None
    
    user_id = payload.get("user_id")
    if not user_id:
        return None
    
    user = db.query(database.User).filter(database.User.id == user_id).first()
    return user

@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, db: SQLAlchemySession = Depends(database.get_db)):
    existing = db.query(database.User).filter(database.User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    password_hash = hash_password(request.password)
    user = database.User(
        email=request.email,
        password_hash=password_hash
    )
    
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
        
        user_settings = database.UserSettings(user_id=user.id)
        db.add(user_settings)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"AUTH: Error registering user {request.email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed. Please try again.")
    
    token = create_access_token(user.id, user.email)
    
    logger.info(f"AUTH: New user registered: {user.email}")
    
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email
    )

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: SQLAlchemySession = Depends(database.get_db)):
    allowed, remaining = _check_rate_limit(request.email)
    if not allowed:
        logger.warning(f"AUTH: Rate limit exceeded for login attempt: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later."
        )
    
    user = db.query(database.User).filter(database.User.email == request.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"AUTH: Error updating last_login_at for user {user.email}: {e}", exc_info=True)
    
    token = create_access_token(user.id, user.email)
    
    logger.info(f"AUTH: User logged in: {user.email}")
    
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        is_admin=getattr(user, 'is_admin', False)
    )

@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: database.User = Depends(get_current_user)):
    return MessageResponse(message="Logged out successfully")

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: database.User = Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        is_admin=getattr(current_user, 'is_admin', False),
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at
    )

@router.delete("/delete-account", response_model=MessageResponse)
async def delete_account(
    request: DeleteAccountRequest,
    current_user: database.User = Depends(get_current_user),
    db: SQLAlchemySession = Depends(database.get_db)
):
    if request.confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must confirm with 'DELETE'"
        )
    
    user_id = current_user.id
    user_email = current_user.email
    
    try:
        db.delete(current_user)
        db.commit()
        logger.info(f"AUTH: User deleted account: {user_email}")
    except Exception as e:
        db.rollback()
        logger.error(f"AUTH: Error deleting account for user {user_email}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete account. Please try again.")
    
    return MessageResponse(message="Account deleted successfully")