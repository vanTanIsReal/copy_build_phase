from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import get_current_user
from src.auth.security import (
    create_access_token,
    create_password_reset_token,
    hash_password,
    hash_password_reset_token,
    verify_password,
)
from src.config import get_settings
from src.db.models import PasswordResetToken, User
from src.db.session import get_db
from src.models.auth_schemas import (
    AuthResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserPublic,
)
from src.services.email import send_password_reset_email

router = APIRouter()


def _to_public(user: User) -> UserPublic:
    return UserPublic(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    existing = (await db.execute(select(User).where(User.email == request.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    settings = get_settings()
    initial_admin_email = settings.initial_admin_email.strip().lower()
    role = "admin" if initial_admin_email and request.email.lower() == initial_admin_email else "user"

    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        display_name=request.display_name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_to_public(user))


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    user = (await db.execute(select(User).where(User.email == request.email))).scalar_one_or_none()
    if user is None or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_to_public(user))


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> ForgotPasswordResponse:
    """Start a password reset without revealing whether an email is registered."""
    user = (await db.execute(select(User).where(User.email == request.email))).scalar_one_or_none()
    raw_token = None

    if user is not None:
        await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
        raw_token, token_hash = create_password_reset_token()
        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(minutes=get_settings().password_reset_expire_minutes),
        )
        db.add(reset_token)
        await db.commit()

    settings = get_settings()
    if raw_token and settings.app_env == "production":
        reset_url = f"{settings.frontend_url.rstrip('/')}/reset-password?token={quote(raw_token)}"
        await send_password_reset_email(user.email, reset_url)

    response_token = raw_token if raw_token and settings.app_env != "production" else None
    return ForgotPasswordResponse(
        message="If an account exists for that email, a password reset link has been created.",
        reset_token=response_token,
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    reset_record = (
        await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_password_reset_token(request.token))
        )
    ).scalar_one_or_none()
    if reset_record is None or reset_record.used_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    now = datetime.now(UTC)
    expires_at = reset_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user = await db.get(User, reset_record.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

    user.password_hash = hash_password(request.password)
    reset_record.used_at = now
    await db.commit()
    return MessageResponse(message="Password has been reset. You can now sign in.")


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return _to_public(current_user)
