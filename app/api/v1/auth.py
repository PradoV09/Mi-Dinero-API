from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    get_db,
    get_email_provider,
    require_csrf,
)
from app.core.config import settings
from app.core.errors import ApiError
from app.core.rate_limit import rate_limiter
from app.core.security import (
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import (
    PasswordResetToken,
    PendingRegistration,
    Session,
    User,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.email import EmailProvider, enqueue_email, flush_outbox

router = APIRouter(prefix="/auth", tags=["auth"])

DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")

GENERIC_REGISTER_MESSAGE = (
    "Si el correo es valido, recibiras un mensaje para continuar."
)
GENERIC_RECOVERY_MESSAGE = (
    "Si el correo corresponde a una cuenta, recibiras un mensaje."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


async def _create_session(session: AsyncSession, request: Request, user: User) -> str:
    token = generate_token()
    session.add(
        Session(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=_now() + timedelta(hours=settings.session_ttl_hours),
            user_agent=request.headers.get("user-agent"),
            ip=_client_ip(request),
        )
    )
    return token


async def _user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _pending_by_email(
    session: AsyncSession, email: str
) -> PendingRegistration | None:
    result = await session.execute(
        select(PendingRegistration).where(PendingRegistration.email == email)
    )
    return result.scalar_one_or_none()


@router.post("/register", status_code=202)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    provider: EmailProvider = Depends(get_email_provider),
) -> MessageResponse:
    rate_limiter.check(
        f"register:{_client_ip(request)}",
        settings.rate_limit_register,
        settings.rate_limit_window_seconds,
    )

    existing_user = await _user_by_email(session, payload.email)
    if existing_user is not None:
        enqueue_email(session, payload.email, "existing_account", {})
        await session.commit()
        await flush_outbox(session, provider)
        return MessageResponse(message=GENERIC_REGISTER_MESSAGE)

    pending = await _pending_by_email(session, payload.email)
    token = generate_token()
    expires_at = _now() + timedelta(hours=settings.email_verification_ttl_hours)
    if pending is None:
        session.add(
            PendingRegistration(
                email=payload.email,
                name=payload.name,
                password_hash=hash_password(payload.password),
                token_hash=hash_token(token),
                expires_at=expires_at,
                resend_count=0,
            )
        )
    else:
        pending.name = payload.name
        pending.password_hash = hash_password(payload.password)
        pending.token_hash = hash_token(token)
        pending.expires_at = expires_at
        pending.last_sent_at = _now()
        pending.resend_count += 1

    enqueue_email(session, payload.email, "verify_email", {"token": token})
    await session.commit()
    await flush_outbox(session, provider)
    return MessageResponse(message=GENERIC_REGISTER_MESSAGE)


@router.post("/verify-email", status_code=201)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db),
    provider: EmailProvider = Depends(get_email_provider),
) -> MessageResponse:
    result = await session.execute(
        select(PendingRegistration).where(
            PendingRegistration.token_hash == hash_token(payload.token)
        )
    )
    pending = result.scalar_one_or_none()
    if pending is None:
        raise ApiError(400, "invalid_token", "Token de confirmacion invalido")
    if pending.expires_at <= _now():
        raise ApiError(400, "expired_token", "El token de confirmacion expiro")

    user = User(
        email=pending.email,
        name=pending.name,
        password_hash=pending.password_hash,
        email_verified_at=_now(),
    )
    session.add(user)
    await session.delete(pending)
    enqueue_email(session, user.email, "welcome", {})
    await session.commit()
    await flush_outbox(session, provider)
    return MessageResponse(message="Correo confirmado. Ya puedes iniciar sesion.")


@router.post("/resend-verification", status_code=202)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    provider: EmailProvider = Depends(get_email_provider),
) -> MessageResponse:
    rate_limiter.check(
        f"resend:{_client_ip(request)}:{payload.email}",
        settings.rate_limit_resend,
        settings.rate_limit_window_seconds,
    )

    existing_user = await _user_by_email(session, payload.email)
    if existing_user is not None:
        enqueue_email(session, payload.email, "existing_account", {})
        await session.commit()
        await flush_outbox(session, provider)
        return MessageResponse(message=GENERIC_REGISTER_MESSAGE)

    pending = await _pending_by_email(session, payload.email)
    if pending is not None:
        cooldown = timedelta(seconds=settings.resend_cooldown_seconds)
        if pending.last_sent_at + cooldown <= _now():
            token = generate_token()
            pending.token_hash = hash_token(token)
            pending.resend_count += 1
            pending.last_sent_at = _now()
            pending.expires_at = _now() + timedelta(
                hours=settings.email_verification_ttl_hours
            )
            enqueue_email(session, payload.email, "verify_email", {"token": token})
            await session.commit()
            await flush_outbox(session, provider)
    return MessageResponse(message=GENERIC_REGISTER_MESSAGE)


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserResponse:
    rate_limiter.check(
        f"login:{_client_ip(request)}:{payload.email}",
        settings.rate_limit_login,
        settings.rate_limit_window_seconds,
    )

    user = await _user_by_email(session, payload.email)
    if user is None:
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise ApiError(401, "invalid_credentials", "Credenciales invalidas")
    if not verify_password(payload.password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Credenciales invalidas")

    token = await _create_session(session, request, user)
    csrf_token = generate_token()
    await session.commit()
    _set_auth_cookies(response, token, csrf_token)
    return UserResponse.model_validate(user)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
    _: None = Depends(require_csrf),
    user: User = Depends(get_current_user),
) -> MessageResponse:
    token = request.cookies.get(settings.session_cookie_name, "")
    if token:
        result = await session.execute(
            select(Session).where(Session.token_hash == hash_token(token))
        )
        db_session = result.scalar_one_or_none()
        if db_session is not None and db_session.revoked_at is None:
            db_session.revoked_at = _now()
            await session.commit()
    _clear_auth_cookies(response)
    return MessageResponse(message="Sesion cerrada.")


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/forgot-password", status_code=202)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
    provider: EmailProvider = Depends(get_email_provider),
) -> MessageResponse:
    rate_limiter.check(
        f"forgot:{_client_ip(request)}:{payload.email}",
        settings.rate_limit_forgot,
        settings.rate_limit_window_seconds,
    )

    user = await _user_by_email(session, payload.email)
    if user is not None:
        token = generate_token()
        session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=_now()
                + timedelta(hours=settings.password_reset_ttl_hours),
            )
        )
        enqueue_email(session, user.email, "reset_password", {"token": token})
        await session.commit()
        await flush_outbox(session, provider)
    return MessageResponse(message=GENERIC_RECOVERY_MESSAGE)


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db),
) -> MessageResponse:
    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(payload.token)
        )
    )
    reset_token = result.scalar_one_or_none()
    if reset_token is None or reset_token.used_at is not None:
        raise ApiError(400, "invalid_token", "Token de recuperacion invalido")
    if reset_token.expires_at <= _now():
        raise ApiError(400, "expired_token", "El token de recuperacion expiro")

    user = await session.get(User, reset_token.user_id)
    if user is None:
        raise ApiError(400, "invalid_token", "Token de recuperacion invalido")

    user.password_hash = hash_password(payload.new_password)
    reset_token.used_at = _now()
    user_sessions = await session.execute(
        select(Session)
        .where(Session.user_id == user.id)
        .where(Session.revoked_at.is_(None))
    )
    for db_session in user_sessions.scalars().all():
        db_session.revoked_at = _now()
    await session.commit()
    return MessageResponse(
        message="Contrasena actualizada. Inicia sesion de nuevo."
    )
