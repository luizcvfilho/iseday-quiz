from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from fastapi import HTTPException
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import database_now
from app.models import AdminAuditLog, AdminSession, AdminUser
from app.participants.security import token_hash

passwords = PasswordHash.recommended()
# Unknown accounts still perform an Argon2 verification.
DUMMY_HASH = passwords.hash(token_urlsafe(32))


def cookie_name(production: bool) -> str:
    return "__Host-iseday_admin" if production else "iseday_admin"


def audit(session: Session, user: AdminUser, action: str, target=None) -> None:
    session.add(AdminAuditLog(admin_user_id=user.id, action=action, target_participation_id=target))


def authenticate(session: Session, token: str | None) -> tuple[AdminUser, AdminSession]:
    hashed = token_hash(token)
    if hashed is not None:
        row = session.execute(
            select(AdminUser, AdminSession)
            .join(AdminSession, AdminSession.admin_user_id == AdminUser.id)
            .where(
                AdminSession.token_hash == hashed,
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > database_now(),
                AdminUser.is_active.is_(True),
            )
        ).one_or_none()
        if row is not None:
            return row[0], row[1]
    raise HTTPException(401, "Sua sessão administrativa expirou. Entre novamente.")


def login(session: Session, email: str, password: str, minutes: int, previous: str | None):
    user = session.scalar(
        select(AdminUser).where(AdminUser.email == email.lower()).with_for_update()
    )
    valid = passwords.verify(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid or not user.is_active:
        raise HTTPException(401, "E-mail ou senha inválidos.")
    # Replace this browser's previous session without affecting other devices.
    old_hash = token_hash(previous)
    if old_hash:
        old = session.scalar(select(AdminSession).where(AdminSession.token_hash == old_hash))
        if old is not None and old.revoked_at is None:
            old.revoked_at = datetime.now(UTC)
    token = token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(minutes=minutes)
    session.add(
        AdminSession(admin_user_id=user.id, token_hash=token_hash(token), expires_at=expires)
    )
    audit(session, user, "login")
    return user, token, expires
