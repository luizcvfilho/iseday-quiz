"""Local maintenance: python -m app.admin create|reset-password (interactive secrets)."""

import argparse
import sys
from datetime import UTC, datetime
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.admin.security import audit, passwords
from app.core.config import get_settings
from app.db import build_engine
from app.models import AdminSession, AdminUser


def save_account(session: Session, command: str, email: str, password: str, name: str = ""):
    """Caller owns the transaction. Password changes invalidate all existing sessions."""
    user = session.scalar(
        select(AdminUser).where(func.lower(AdminUser.email) == email.lower()).with_for_update()
    )
    if command == "create":
        if user is not None:
            raise ValueError("Já existe um administrador com esse e-mail.")
        user = AdminUser(
            name=name.strip(), email=email.lower(), password_hash=passwords.hash(password)
        )
        session.add(user)
        session.flush()
        audit(session, user, "account.create")
    else:
        if user is None:
            raise ValueError("Administrador não encontrado.")
        user.password_hash = passwords.hash(password)
        session.execute(
            update(AdminSession)
            .where(AdminSession.admin_user_id == user.id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        audit(session, user, "account.password_reset")


def main():
    parser = argparse.ArgumentParser(description="Manutenção de administradores do ISE Day")
    parser.add_argument("command", choices=("create", "reset-password"))
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Execute este comando em um terminal interativo para proteger a senha.")
    try:
        email = str(TypeAdapter(EmailStr).validate_python(input("E-mail: ").strip())).lower()
        name = input("Nome: ").strip() if args.command == "create" else ""
        if args.command == "create" and not 2 <= len(name) <= 200:
            raise ValueError("O nome deve ter de 2 a 200 caracteres.")
        password = getpass("Senha (mínimo 12 caracteres): ")
        if not 12 <= len(password) <= 1024:
            raise ValueError("A senha deve ter de 12 a 1024 caracteres.")
        if getpass("Confirme a senha: ") != password:
            raise ValueError("As senhas não coincidem.")
        engine = build_engine(get_settings())
        try:
            with Session(engine) as session, session.begin():
                save_account(session, args.command, email, password, name)
        finally:
            engine.dispose()
    except (ValidationError, ValueError) as exc:
        # ValidationError may contain input; don't echo it.
        raise SystemExit(
            str(exc) if not isinstance(exc, ValidationError) else "E-mail inválido."
        ) from None
    except IntegrityError:
        raise SystemExit(
            "Conta já existente ou dados inválidos. Nenhuma alteração foi salva."
        ) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Não foi possível acessar o banco. Verifique a conexão e as migrações."
        ) from None
    print(
        "Administrador criado."
        if args.command == "create"
        else "Senha alterada; sessões anteriores revogadas."
    )


if __name__ == "__main__":
    main()
