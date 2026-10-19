import asyncio
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage as StdEmailMessage
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import OutboxEmail

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class RenderedEmail:
    to: str
    subject: str
    text: str


class EmailProvider(Protocol):
    async def send(self, message: RenderedEmail) -> None: ...


def render(template: str, payload: dict[str, Any], to: str) -> RenderedEmail:
    if template == "verify_email":
        link = f"{settings.frontend_url}/verificar?token={payload['token']}"
        return RenderedEmail(
            to=to,
            subject="Confirma tu correo en Mi Dinero",
            text=(
                "Bienvenido a Mi Dinero.\n\n"
                f"Confirma tu correo abriendo este enlace:\n{link}\n\n"
                "Si no creaste esta cuenta, ignora este mensaje."
            ),
        )
    if template == "existing_account":
        link = f"{settings.frontend_url}/recuperar"
        return RenderedEmail(
            to=to,
            subject="Ya tienes una cuenta en Mi Dinero",
            text=(
                "Alguien intento registrarse con este correo, pero ya tienes "
                "una cuenta en Mi Dinero.\n\n"
                f"Si olvidaste tu contrasena, restablecela aqui:\n{link}"
            ),
        )
    if template == "welcome":
        return RenderedEmail(
            to=to,
            subject="¡Bienvenido a Mi Dinero!",
            text=(
                "¡Bienvenido a Mi Dinero!\n\n"
                "Tu correo fue confirmado y tu cuenta esta lista. Registra tus "
                "ingresos y gastos para ver en que se va tu dinero."
            ),
        )
    if template == "reset_password":
        link = f"{settings.frontend_url}/restablecer?token={payload['token']}"
        return RenderedEmail(
            to=to,
            subject="Restablece tu contrasena de Mi Dinero",
            text=(
                "Recibimos una solicitud para restablecer tu contrasena.\n\n"
                f"Usa este enlace (expira pronto):\n{link}\n\n"
                "Si no lo solicitaste, ignora este mensaje."
            ),
        )
    raise ValueError(f"plantilla de correo desconocida: {template}")


class MemoryEmailProvider:
    def __init__(self) -> None:
        self.sent: list[RenderedEmail] = []
        self.fail_next = 0

    async def send(self, message: RenderedEmail) -> None:
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("fallo simulado del proveedor de correo")
        self.sent.append(message)


class SmtpEmailProvider:
    async def send(self, message: RenderedEmail) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: RenderedEmail) -> None:
        email = StdEmailMessage()
        email["From"] = settings.email_from
        email["To"] = message.to
        email["Subject"] = message.subject
        email.set_content(message.text)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
            smtp.send_message(email)


class ResendEmailProvider:
    async def send(self, message: RenderedEmail) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.email_provider_api_key}"},
                json={
                    "from": settings.email_from,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.text,
                },
            )
            response.raise_for_status()


def build_email_provider() -> EmailProvider:
    if settings.email_provider == "resend":
        return ResendEmailProvider()
    return SmtpEmailProvider()


def enqueue_email(
    session: AsyncSession, to: str, template: str, payload: dict[str, Any]
) -> OutboxEmail:
    email = OutboxEmail(to_email=to, template=template, payload=payload)
    session.add(email)
    return email


async def flush_outbox(
    session: AsyncSession, provider: EmailProvider, limit: int = 50
) -> int:
    result = await session.execute(
        select(OutboxEmail)
        .where(OutboxEmail.status == "pending")
        .where(OutboxEmail.attempts < MAX_ATTEMPTS)
        .order_by(OutboxEmail.created_at)
        .limit(limit)
    )
    sent = 0
    for email in result.scalars().all():
        email.attempts += 1
        try:
            await provider.send(render(email.template, email.payload, email.to_email))
        except Exception as exc:  # noqa: BLE001 - se registra para reintento
            email.last_error = str(exc)[:500]
            if email.attempts >= MAX_ATTEMPTS:
                email.status = "failed"
        else:
            email.status = "sent"
            email.sent_at = datetime.now(timezone.utc)
            email.last_error = None
            sent += 1
    await session.commit()
    return sent
