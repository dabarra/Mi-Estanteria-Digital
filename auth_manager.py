import re
import sqlite3
from typing import Any, Optional

from passlib.context import CryptContext

from database_manager import (
    create_user_record,
    get_user_by_email,
    get_user_by_username,
    update_user_password_by_email,
)

EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PASSWORD_SPECIAL_PATTERN = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]""")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def validate_email(email: str) -> tuple[bool, str]:
    clean = email.strip().lower()
    if not clean:
        return False, "El correo electronico es obligatorio."
    if not EMAIL_PATTERN.match(clean):
        return False, "Correo invalido. Usa formato estandar (ejemplo: nombre@dominio.com)."
    return True, ""


def validate_password_owasp(password: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("La contrasena debe tener minimo 8 caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("La contrasena debe incluir al menos una mayuscula.")
    if not re.search(r"[a-z]", password):
        errors.append("La contrasena debe incluir al menos una minuscula.")
    if not re.search(r"\d", password):
        errors.append("La contrasena debe incluir al menos un numero.")
    if not PASSWORD_SPECIAL_PATTERN.search(password):
        errors.append("La contrasena debe incluir al menos un caracter especial.")
    return len(errors) == 0, errors


def create_user(username: str, email: str, password: str) -> None:
    password_hash = pwd_context.hash(password)
    create_user_record(username, email, password_hash)


def authenticate_user(login_mode: str, identifier: str, password: str) -> Optional[dict[str, Any]]:
    if login_mode == "Email":
        row = get_user_by_email(identifier)
    else:
        row = get_user_by_username(identifier)
    if row and pwd_context.verify(password, row["password"]):
        return row
    return None


def recover_password(email: str, new_password: str) -> bool:
    new_hash = pwd_context.hash(new_password)
    return update_user_password_by_email(email, new_hash)


def create_user_with_feedback(username: str, email: str, password: str) -> tuple[bool, str]:
    try:
        create_user(username, email, password)
        return True, ""
    except sqlite3.IntegrityError as err:
        txt = str(err).lower()
        if "username" in txt:
            return False, "Ese nombre de usuario ya esta registrado."
        if "email" in txt:
            return False, "Ese correo ya esta registrado."
        return False, "No se pudo crear la cuenta por conflicto de datos."
    except sqlite3.Error as err:
        return False, f"Error al guardar el usuario: {err}"


def recover_password_with_feedback(email: str, new_password: str) -> tuple[bool, str]:
    try:
        if recover_password(email, new_password):
            return True, ""
        return False, "No hay ninguna cuenta con ese email."
    except sqlite3.Error as err:
        return False, f"No se pudo actualizar la contrasena: {err}"
