import os
import sqlite3
import time
from datetime import date
from typing import Any, Optional

import streamlit as st

from auth_manager import (
    authenticate_user,
    create_user,
    recover_password,
    validate_email,
    validate_password_owasp,
)
from database_manager import (
    add_book_to_user_library,
    find_book_by_isbn,
    get_reading_statistics,
    get_user_library,
    init_db,
    insert_libro_comun,
    update_biblioteca_row,
)
from utils import save_cover_file, validate_isbn10, validate_isbn13

READING_STATES = ["Pendiente", "Leyendo", "Terminado", "Abandonado", "Relectura"]
LANGUAGE_OPTIONS = [
    "Espanol",
    "Ingles",
    "Frances",
    "Aleman",
    "Italiano",
    "Portugues",
    "Catalan",
    "Gallego",
    "Euskera",
    "Otro",
]
LOCK_SECONDS = 120


def today_iso() -> str:
    return date.today().isoformat()


def initial_dates_for_estado(estado: str) -> tuple[Optional[str], Optional[str]]:
    t = today_iso()
    if estado == "Leyendo":
        return t, None
    if estado == "Terminado":
        return t, t
    if estado == "Abandonado":
        return None, t
    return None, None


def transition_updates(
    old: str,
    new: str,
    cur_fi: Optional[str],
    cur_ff: Optional[str],
    today: str,
    abandon_pages: Optional[int],
) -> dict[str, Any]:
    out: dict[str, Any] = {"estado": new}
    fi, ff = cur_fi, cur_ff

    if new == "Relectura":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Leyendo":
        out["fecha_inicio"] = fi if old == "Leyendo" else today
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Terminado":
        out["fecha_inicio"] = fi or today
        out["fecha_fin"] = today
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Abandonado":
        out["fecha_inicio"] = fi
        out["fecha_fin"] = ff or today
        out["paginas_leidas_abandono"] = abandon_pages
        return out
    if new == "Pendiente":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    out["fecha_inicio"] = fi
    out["fecha_fin"] = ff
    out["paginas_leidas_abandono"] = None
    return out


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def init_session_state() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "failed_login_attempts" not in st.session_state:
        st.session_state.failed_login_attempts = 0
    if "login_lock_until" not in st.session_state:
        st.session_state.login_lock_until = 0.0
    if "book_flow" not in st.session_state:
        st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}


def login_register_view() -> None:
    st.title("Mi Estanteria Digital")
    tab_login, tab_register, tab_recover = st.tabs(["Iniciar sesion", "Registro", "Recuperar contrasena"])

    with tab_login:
        locked = time.time() < st.session_state.login_lock_until
        if locked:
            wait = int(st.session_state.login_lock_until - time.time())
            st.warning(f"Cuenta bloqueada temporalmente. Vuelve a intentarlo en {wait} segundos.")

        login_mode = st.radio(
            "Acceder con",
            ["Nombre de usuario", "Email"],
            horizontal=True,
            key="auth_login_mode",
        )
        label_ident = "Email" if login_mode == "Email" else "Nombre de usuario"
        with st.form("auth_login_form"):
            identifier = st.text_input(label_ident, key="auth_login_identifier")
            password = st.text_input("Contrasena", type="password", key="auth_login_password")
            submit = st.form_submit_button("Entrar", disabled=locked)
        if submit:
            if not identifier.strip() or not password:
                st.error("Completa el campo de acceso y la contrasena.")
                return
            mode = "Email" if login_mode == "Email" else "Username"
            user = authenticate_user(mode, identifier, password)
            if user:
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.session_state.failed_login_attempts = 0
                st.session_state.login_lock_until = 0.0
                st.success("Sesion iniciada correctamente.")
                st.rerun()
            st.session_state.failed_login_attempts += 1
            attempts = st.session_state.failed_login_attempts
            if attempts >= 5:
                st.session_state.login_lock_until = time.time() + LOCK_SECONDS
                st.session_state.failed_login_attempts = 0
                st.error("Demasiados intentos fallidos. Espera unos minutos antes de volver a intentarlo.")
            else:
                st.error(f"Credenciales incorrectas. Te quedan {5 - attempts} intentos antes del bloqueo.")

    with tab_register:
        with st.form("auth_register_form"):
            new_username = st.text_input("Usuario", key="auth_register_username")
            new_email = st.text_input("Email", key="auth_register_email")
            new_password = st.text_input("Contrasena", type="password", key="auth_register_password")
            submit_register = st.form_submit_button("Crear cuenta")
        if submit_register:
            if len(new_username.strip()) < 3:
                st.error("El usuario debe tener al menos 3 caracteres.")
                return
            ok_email, msg_email = validate_email(new_email)
            if not ok_email:
                st.error(msg_email)
                return
            ok_password, password_errors = validate_password_owasp(new_password)
            if not ok_password:
                for msg in password_errors:
                    st.error(msg)
                return
            try:
                create_user(new_username, new_email, new_password)
                st.success("Cuenta creada. Ya puedes iniciar sesion.")
            except sqlite3.IntegrityError as err:
                txt = str(err).lower()
                if "username" in txt:
                    st.error("Ese nombre de usuario ya esta registrado.")
                elif "email" in txt:
                    st.error("Ese correo ya esta registrado.")
                else:
                    st.error("No se pudo crear la cuenta por conflicto de datos.")
            except sqlite3.Error as err:
                st.error(f"Error al guardar el usuario: {err}")

    with tab_recover:
        with st.form("auth_recover_form"):
            email = st.text_input("Email registrado", key="auth_recover_email")
            new_password = st.text_input("Nueva contrasena", type="password", key="auth_recover_password")
            submit_recover = st.form_submit_button("Actualizar contrasena")
        if submit_recover:
            ok_email, msg_email = validate_email(email)
            if not ok_email:
                st.error(msg_email)
                return
            ok_password, password_errors = validate_password_owasp(new_password)
            if not ok_password:
                for msg in password_errors:
                    st.error(msg)
                return
            try:
                if recover_password(email, new_password):
                    st.success("Contrasena actualizada. Ya puedes iniciar sesion.")
                else:
                    st.error("No hay ninguna cuenta con ese email.")
            except sqlite3.Error as err:
                st.error(f"No se pudo actualizar la contrasena: {err}")


def add_book_section(user_id: int) -> None:
    st.subheader("Anadir libro")
    st.caption("No se admiten libros sin ISBN. Introduce ISBN-10, ISBN-13 o ambos.")
    with st.form("books_lookup_form"):
        a, b, c = st.columns([2, 2, 1])
        with a:
            isbn_10_input = st.text_input("ISBN-10", key="books_lookup_isbn10")
        with b:
            isbn_13_input = st.text_input("ISBN-13", key="books_lookup_isbn13")
        with c:
            estado = st.selectbox("Estado inicial", READING_STATES, index=0, key="books_lookup_estado")
        lookup_clicked = st.form_submit_button("Buscar / Continuar")
    if lookup_clicked:
        ok10, msg10, isbn10 = validate_isbn10(isbn_10_input)
        ok13, msg13, isbn13 = validate_isbn13(isbn_13_input)
        if not ok10:
            st.error(msg10)
            return
        if not ok13:
            st.error(msg13)
            return
        if not isbn10 and not isbn13:
            st.error("Debes introducir al menos un ISBN (10 o 13) valido.")
            return
        existing = find_book_by_isbn(isbn10, isbn13)
        st.session_state.book_flow = {
            "step": "found" if existing else "new",
            "isbn10": isbn10,
            "isbn13": isbn13,
            "estado": estado,
            "existing": existing,
        }
        st.rerun()

    flow: dict[str, Any] = st.session_state.book_flow
    if flow["step"] == "idle":
        return
    if st.button("Nueva busqueda", key="books_reset_lookup"):
        st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
        st.rerun()

    if flow["step"] == "found":
        book = flow["existing"]
        st.info("Este titulo ya esta en el catalogo comun. Solo se anadira a tu biblioteca.")
        if st.button("Anadir a mi biblioteca", key="books_link_existing"):
            fi, ff = initial_dates_for_estado(flow["estado"])
            linked = add_book_to_user_library(user_id, book["id"], flow["estado"], fi, ff, None)
            if linked:
                st.success("Libro anadido a tu biblioteca.")
                st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
                st.rerun()
            else:
                st.warning("Este libro ya estaba en tu biblioteca.")
        return

    st.warning("Alta de libro nuevo en el catalogo comun con ISBN obligatorio.")
    with st.form("books_new_book_form"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Titulo *", key="books_new_title")
            author = st.text_input("Autor *", key="books_new_author")
            genre = st.text_input("Genero (opcional)", key="books_new_genre")
        with c2:
            idioma = st.selectbox("Idioma *", LANGUAGE_OPTIONS, index=0, key="books_new_idioma")
            paginas = st.number_input("Paginas (opcional)", min_value=0, value=0, step=1, key="books_new_paginas")
            cover = st.file_uploader("Portada (opcional, JPG/PNG)", type=["jpg", "jpeg", "png"], key="books_new_cover")
        create_clicked = st.form_submit_button("Guardar libro y anadir a mi biblioteca")

    if create_clicked:
        if not title.strip() or not author.strip():
            st.error("Titulo y autor son obligatorios.")
            return
        if not idioma:
            st.error("Selecciona un idioma.")
            return
        paginas_value = int(paginas) if paginas > 0 else None
        ref = flow["isbn13"] or flow["isbn10"] or "isbn"
        cover_path, cover_error = save_cover_file(ref, cover)
        if cover_error:
            st.error(cover_error)
            return
        try:
            exists_now = find_book_by_isbn(flow["isbn10"], flow["isbn13"])
            book_id = exists_now["id"] if exists_now else insert_libro_comun(
                flow["isbn10"], flow["isbn13"], title, author, genre, idioma, paginas_value, cover_path
            )
        except (sqlite3.IntegrityError, ValueError):
            st.error("Conflicto de ISBN o datos invalidos. Vuelve a buscar antes de guardar.")
            return
        except sqlite3.Error as err:
            st.error(f"Error al guardar en el catalogo: {err}")
            return
        fi, ff = initial_dates_for_estado(flow["estado"])
        linked = add_book_to_user_library(user_id, book_id, flow["estado"], fi, ff, None)
        if linked:
            st.success("Libro creado y anadido a tu biblioteca.")
            st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
            st.rerun()
        else:
            st.warning("El libro ya estaba vinculado a tu biblioteca.")


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Aun no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galeria"], horizontal=True, key="library_view_mode")
    if view_mode != "Lista":
        cols = st.columns(4)
        for i, book in enumerate(books):
            with cols[i % 4]:
                if book["cover_path"] and os.path.exists(book["cover_path"]):
                    st.image(book["cover_path"], use_container_width=True)
                else:
                    st.markdown("*Sin portada*")
                st.write(f"**{book['title']}**")
                st.caption(f"{book['author']} · {book['estado']}")
        return

    for book in books:
        bid = book["book_id"]
        with st.container(border=True):
            st.write(f"**{book['title']}** — {book['author']}")
            with st.expander("Gestionar estado y fechas", expanded=False):
                cur = book["estado"]
                idx = READING_STATES.index(cur) if cur in READING_STATES else 0
                new_est = st.selectbox("Estado", READING_STATES, index=idx, key=f"library_estado_sel_{bid}")
                abandon_pages: Optional[int] = None
                if new_est == "Abandonado" or cur == "Abandonado":
                    abandon_pages = st.number_input(
                        "Paginas leidas (abandono)",
                        min_value=0,
                        value=int(book["paginas_leidas_abandono"] or 0),
                        step=1,
                        key=f"library_abandon_pages_{bid}",
                    )
                edit_ini = st.date_input("Fecha inicio", value=_parse_date(book["fecha_inicio"]) or date.today(), key=f"library_date_ini_{bid}")
                edit_fin = st.date_input("Fecha fin", value=_parse_date(book["fecha_fin"]) or date.today(), key=f"library_date_fin_{bid}")
                if st.button("Guardar cambios", key=f"library_save_{bid}"):
                    today = today_iso()
                    fi_w = edit_ini.isoformat()
                    ff_w = edit_fin.isoformat()
                    try:
                        if new_est != cur:
                            d = transition_updates(cur, new_est, book["fecha_inicio"], book["fecha_fin"], today, abandon_pages)
                            fi, ff, pab = fi_w, ff_w, book.get("paginas_leidas_abandono")
                            if new_est == "Relectura":
                                fi, ff, pab = None, None, None
                            elif new_est == "Leyendo":
                                fi, ff, pab = today, None, None
                            elif new_est == "Terminado":
                                fi, ff, pab = book["fecha_inicio"] or fi_w or today, today, None
                            elif new_est == "Abandonado":
                                fi, ff, pab = book["fecha_inicio"] or fi_w, ff_w or d.get("fecha_fin") or today, int(abandon_pages or 0)
                            elif new_est == "Pendiente":
                                fi, ff, pab = None, None, None
                            update_biblioteca_row(user_id, bid, new_est, fi, ff, pab)
                        else:
                            pab = int(abandon_pages or 0) if new_est == "Abandonado" else book.get("paginas_leidas_abandono")
                            update_biblioteca_row(user_id, bid, cur, fi_w, ff_w, pab)
                        st.success("Cambios guardados correctamente.")
                        st.rerun()
                    except sqlite3.Error as err:
                        st.error(f"No se pudo guardar en la base de datos: {err}")


def statistics_section(user_id: int) -> None:
    st.subheader("Estadisticas")
    finished, pages_done, abandoned = get_reading_statistics(user_id)
    years: set[str] = set()
    for row in finished + pages_done + abandoned:
        if row["anio"]:
            years.add(row["anio"])
    if not years:
        st.info("Aun no hay datos para estadisticas.")
        return
    libros_por_anio = {r["anio"]: r["libros"] for r in finished if r["anio"]}
    paginas_terminados = {r["anio"]: int(r["paginas"] or 0) for r in pages_done if r["anio"]}
    paginas_abandonados = {r["anio"]: int(r["paginas"] or 0) for r in abandoned if r["anio"]}
    rows = []
    for y in sorted(years, reverse=True):
        pt = paginas_terminados.get(y, 0)
        pa = paginas_abandonados.get(y, 0)
        rows.append(
            {
                "Anio": y,
                "Libros terminados": libros_por_anio.get(y, 0),
                "Paginas (terminados)": pt,
                "Paginas (abandonados)": pa,
                "Paginas totales": pt + pa,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def main() -> None:
    st.set_page_config(page_title="Mi Estanteria Digital", page_icon="📚", layout="wide")
    init_db()
    init_session_state()
    if st.session_state.user_id is None:
        login_register_view()
        return

    st.title("Mi Estanteria Digital")
    if st.button("Cerrar sesion", key="layout_logout_button"):
        st.session_state.user_id = None
        st.session_state.username = None
        st.rerun()

    add_book_section(st.session_state.user_id)
    st.divider()
    library_view(st.session_state.user_id)
    st.divider()
    statistics_section(st.session_state.user_id)


if __name__ == "__main__":
    main()
import os
import re
import sqlite3
import time
import uuid
from io import BytesIO
from datetime import date, datetime
from typing import Any, Optional

import streamlit as st
from passlib.context import CryptContext
from PIL import Image, UnidentifiedImageError

DB_PATH = "biblioteca.db"
COVERS_DIR = "portadas"
READING_STATES = ["Pendiente", "Leyendo", "Terminado", "Abandonado", "Relectura"]
LANGUAGE_OPTIONS = [
    "Espanol",
    "Ingles",
    "Frances",
    "Aleman",
    "Italiano",
    "Portugues",
    "Catalan",
    "Gallego",
    "Euskera",
    "Otro",
]
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
PASSWORD_SPECIAL_PATTERN = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]""")
LOCK_SECONDS = 120
MAX_COVER_SIZE_BYTES = 2 * 1024 * 1024

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def today_iso() -> str:
    return date.today().isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _migrate_legacy_users(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "users") and not _table_exists(conn, "usuarios"):
        conn.execute("ALTER TABLE users RENAME TO usuarios")
    cols = _table_columns(conn, "usuarios")
    if not cols:
        return
    if "password_hash" in cols and "password" not in cols:
        conn.execute("ALTER TABLE usuarios ADD COLUMN password TEXT")
        conn.execute("UPDATE usuarios SET password = password_hash WHERE password IS NULL")
    if "email" not in cols:
        conn.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_username ON usuarios(username)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email)")


def _migrate_legacy_books(conn: sqlite3.Connection) -> None:
    cols = _table_columns(conn, "libros_comunes")
    if not cols:
        return
    if "isbn" in cols and "isbn_10" not in cols and "isbn_13" not in cols:
        conn.execute("ALTER TABLE libros_comunes ADD COLUMN isbn_10 TEXT")
        conn.execute("ALTER TABLE libros_comunes ADD COLUMN isbn_13 TEXT")
        rows = conn.execute("SELECT id, isbn FROM libros_comunes").fetchall()
        for row in rows:
            normalized = normalize_isbn(row["isbn"])
            if len(normalized) == 10:
                conn.execute(
                    "UPDATE libros_comunes SET isbn_10 = ? WHERE id = ?",
                    (normalized, row["id"]),
                )
            elif len(normalized) == 13:
                conn.execute(
                    "UPDATE libros_comunes SET isbn_13 = ? WHERE id = ?",
                    (normalized, row["id"]),
                )
    if "idioma" not in cols:
        conn.execute("ALTER TABLE libros_comunes ADD COLUMN idioma TEXT NOT NULL DEFAULT 'Espanol'")
    if "paginas" not in cols:
        conn.execute("ALTER TABLE libros_comunes ADD COLUMN paginas INTEGER")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_libros_isbn10 ON libros_comunes(isbn_10)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_libros_isbn13 ON libros_comunes(isbn_13)")


def _migrate_legacy_library(conn: sqlite3.Connection) -> None:
    if _table_exists(conn, "user_books") and not _table_exists(conn, "biblioteca_usuario"):
        conn.execute("ALTER TABLE user_books RENAME TO biblioteca_usuario")
    cols = _table_columns(conn, "biblioteca_usuario")
    if not cols:
        return
    if "estado" not in cols and "status" in cols:
        conn.execute("ALTER TABLE biblioteca_usuario ADD COLUMN estado TEXT DEFAULT 'Pendiente'")
        conn.execute(
            "UPDATE biblioteca_usuario SET estado = status WHERE status IS NOT NULL AND status != ''"
        )
    elif "estado" not in cols:
        conn.execute("ALTER TABLE biblioteca_usuario ADD COLUMN estado TEXT DEFAULT 'Pendiente'")
    conn.execute(
        "UPDATE biblioteca_usuario SET estado = 'Pendiente' WHERE estado IS NULL OR estado = ''"
    )
    if "fecha_inicio" not in cols:
        conn.execute("ALTER TABLE biblioteca_usuario ADD COLUMN fecha_inicio TEXT")
    if "fecha_fin" not in cols:
        conn.execute("ALTER TABLE biblioteca_usuario ADD COLUMN fecha_fin TEXT")
    if "paginas_leidas_abandono" not in cols:
        conn.execute("ALTER TABLE biblioteca_usuario ADD COLUMN paginas_leidas_abandono INTEGER")


def init_db() -> None:
    os.makedirs(COVERS_DIR, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS libros_comunes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn_10 TEXT UNIQUE,
                isbn_13 TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT NOT NULL DEFAULT 'Sin especificar',
                idioma TEXT NOT NULL,
                paginas INTEGER,
                cover_path TEXT,
                created_at TEXT NOT NULL,
                CHECK (isbn_10 IS NOT NULL OR isbn_13 IS NOT NULL)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS biblioteca_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                estado TEXT NOT NULL DEFAULT 'Pendiente',
                fecha_inicio TEXT,
                fecha_fin TEXT,
                paginas_leidas_abandono INTEGER,
                added_at TEXT NOT NULL,
                UNIQUE(user_id, book_id),
                FOREIGN KEY(user_id) REFERENCES usuarios(id),
                FOREIGN KEY(book_id) REFERENCES libros_comunes(id)
            )
            """
        )
        _migrate_legacy_users(conn)
        _migrate_legacy_books(conn)
        _migrate_legacy_library(conn)
        conn.commit()


def normalize_isbn(raw_isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", raw_isbn).upper()


def isbn10_check_digit(isbn10: str) -> bool:
    if len(isbn10) != 10:
        return False
    total = 0
    for i in range(9):
        if not isbn10[i].isdigit():
            return False
        total += (10 - i) * int(isbn10[i])
    last = isbn10[9]
    if last == "X":
        total += 10
    elif last.isdigit():
        total += int(last)
    else:
        return False
    return total % 11 == 0


def isbn13_check_digit(isbn13: str) -> bool:
    if len(isbn13) != 13 or not isbn13.isdigit():
        return False
    total = 0
    for i in range(12):
        mult = 1 if i % 2 == 0 else 3
        total += int(isbn13[i]) * mult
    check = (10 - (total % 10)) % 10
    return check == int(isbn13[12])


def validate_isbn10(value: str) -> tuple[bool, str, Optional[str]]:
    normalized = normalize_isbn(value)
    if not normalized:
        return True, "", None
    if len(normalized) != 10:
        return False, "El ISBN-10 debe tener 10 caracteres tras limpiar guiones/espacios.", None
    if not isbn10_check_digit(normalized):
        return False, "ISBN-10 invalido: el digito de control no coincide.", None
    return True, "", normalized


def validate_isbn13(value: str) -> tuple[bool, str, Optional[str]]:
    normalized = normalize_isbn(value)
    if not normalized:
        return True, "", None
    if len(normalized) != 13:
        return False, "El ISBN-13 debe tener 13 digitos tras limpiar guiones/espacios.", None
    if not isbn13_check_digit(normalized):
        return False, "ISBN-13 invalido: el digito de control no coincide.", None
    return True, "", normalized


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


def save_cover_file(reference_isbn: str, uploaded_file) -> tuple[Optional[str], Optional[str]]:
    if uploaded_file is None:
        return None, None

    raw_bytes = uploaded_file.getvalue()
    if len(raw_bytes) > MAX_COVER_SIZE_BYTES:
        return None, "La imagen supera el limite de 2 MB."

    try:
        with Image.open(BytesIO(raw_bytes)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError):
        return None, "El archivo no es una imagen valida o esta corrupto."

    try:
        with Image.open(BytesIO(raw_bytes)) as img:
            internal_format = (img.format or "").upper()
            if internal_format not in {"JPEG", "PNG"}:
                return None, "Solo se aceptan imagenes reales en formato JPEG o PNG."

            if internal_format == "JPEG" and img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif internal_format == "PNG" and img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")

            safe_ref = re.sub(r"[^A-Z0-9]", "", normalize_isbn(reference_isbn)) or "ISBN"
            ext = ".jpg" if internal_format == "JPEG" else ".png"
            filename = f"{safe_ref}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:8]}{ext}"
            filename = os.path.basename(filename)
            target_path = os.path.join(COVERS_DIR, filename)

            covers_root = os.path.realpath(COVERS_DIR)
            final_path = os.path.realpath(target_path)
            if not final_path.startswith(covers_root + os.sep):
                return None, "Ruta de guardado invalida para la portada."

            save_kwargs: dict[str, Any] = {"format": internal_format}
            if internal_format == "JPEG":
                save_kwargs.update({"quality": 90, "optimize": True})
            img.save(target_path, **save_kwargs)
            return target_path, None
    except OSError:
        return None, "No se pudo procesar la imagen. Intenta con otro archivo JPEG o PNG."



def create_user(username: str, email: str, password: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO usuarios (username, email, password, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                username.strip(),
                email.strip().lower(),
                pwd_context.hash(password),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def authenticate_user(login_mode: str, identifier: str, password: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        if login_mode == "Email":
            row = conn.execute(
                "SELECT id, username, email, password FROM usuarios WHERE email = ?",
                (identifier.strip().lower(),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, username, email, password FROM usuarios WHERE username = ?",
                (identifier.strip(),),
            ).fetchone()
    if row and pwd_context.verify(password, row["password"]):
        return dict(row)
    return None


def recover_password(email: str, new_password: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM usuarios WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE usuarios SET password = ? WHERE id = ?",
            (pwd_context.hash(new_password), row["id"]),
        )
        conn.commit()
    return True


def find_book_by_isbn(isbn10: Optional[str], isbn13: Optional[str]) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        if isbn10 and isbn13:
            row = conn.execute(
                """
                SELECT * FROM libros_comunes
                WHERE isbn_10 IN (?, ?) OR isbn_13 IN (?, ?)
                LIMIT 1
                """,
                (isbn10, isbn13, isbn10, isbn13),
            ).fetchone()
        elif isbn10:
            row = conn.execute(
                "SELECT * FROM libros_comunes WHERE isbn_10 = ? OR isbn_13 = ? LIMIT 1",
                (isbn10, isbn10),
            ).fetchone()
        elif isbn13:
            row = conn.execute(
                "SELECT * FROM libros_comunes WHERE isbn_13 = ? OR isbn_10 = ? LIMIT 1",
                (isbn13, isbn13),
            ).fetchone()
        else:
            return None
    return dict(row) if row else None


def insert_libro_comun(
    isbn10: Optional[str],
    isbn13: Optional[str],
    title: str,
    author: str,
    genre: str,
    idioma: str,
    paginas: Optional[int],
    cover_path: Optional[str],
) -> int:
    if not isbn10 and not isbn13:
        raise ValueError("Debes indicar ISBN-10 o ISBN-13 para crear un libro.")
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO libros_comunes
            (isbn_10, isbn_13, title, author, genre, idioma, paginas, cover_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                isbn10,
                isbn13,
                title.strip(),
                author.strip(),
                (genre.strip() or "Sin especificar"),
                idioma,
                paginas,
                cover_path,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def initial_dates_for_estado(estado: str) -> tuple[Optional[str], Optional[str]]:
    t = today_iso()
    if estado == "Leyendo":
        return t, None
    if estado == "Terminado":
        return t, t
    if estado == "Abandonado":
        return None, t
    return None, None


def add_book_to_user_library(
    user_id: int,
    book_id: int,
    estado: str,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    paginas_abandono: Optional[int] = None,
) -> bool:
    fi, ff = initial_dates_for_estado(estado)
    if fecha_inicio is not None:
        fi = fecha_inicio
    if fecha_fin is not None:
        ff = fecha_fin
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO biblioteca_usuario (
                    user_id, book_id, estado, fecha_inicio, fecha_fin,
                    paginas_leidas_abandono, added_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    book_id,
                    estado,
                    fi,
                    ff,
                    paginas_abandono if estado == "Abandonado" else None,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def transition_updates(
    old: str,
    new: str,
    cur_fi: Optional[str],
    cur_ff: Optional[str],
    today: str,
    abandon_pages: Optional[int],
) -> dict[str, Any]:
    out: dict[str, Any] = {"estado": new}
    fi, ff = cur_fi, cur_ff

    if new == "Relectura":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out

    if new == "Leyendo":
        if old == "Leyendo":
            out["fecha_inicio"] = fi
        else:
            out["fecha_inicio"] = today
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out

    if new == "Terminado":
        out["fecha_inicio"] = fi or today
        out["fecha_fin"] = today
        out["paginas_leidas_abandono"] = None
        return out

    if new == "Abandonado":
        out["fecha_inicio"] = fi
        out["fecha_fin"] = ff or today
        out["paginas_leidas_abandono"] = abandon_pages
        return out

    if new == "Pendiente":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out

    out["fecha_inicio"] = fi
    out["fecha_fin"] = ff
    out["paginas_leidas_abandono"] = None
    return out


def update_biblioteca_row(
    user_id: int,
    book_id: int,
    estado: str,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    paginas_abandono: Optional[int],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE biblioteca_usuario
            SET estado = ?, fecha_inicio = ?, fecha_fin = ?, paginas_leidas_abandono = ?
            WHERE user_id = ? AND book_id = ?
            """,
            (estado, fecha_inicio, fecha_fin, paginas_abandono, user_id, book_id),
        )
        conn.commit()


def get_user_library(user_id: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                b.id AS book_id,
                b.isbn_10,
                b.isbn_13,
                b.title,
                b.author,
                b.genre,
                b.idioma,
                b.paginas,
                b.cover_path,
                bu.estado,
                bu.fecha_inicio,
                bu.fecha_fin,
                bu.paginas_leidas_abandono
            FROM biblioteca_usuario bu
            JOIN libros_comunes b ON b.id = bu.book_id
            WHERE bu.user_id = ?
            ORDER BY b.title COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_reading_statistics(
    user_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with get_connection() as conn:
        finished = conn.execute(
            """
            SELECT strftime('%Y', bu.fecha_fin) AS anio, COUNT(*) AS libros
            FROM biblioteca_usuario bu
            WHERE bu.user_id = ?
              AND bu.estado = 'Terminado'
              AND bu.fecha_fin IS NOT NULL AND bu.fecha_fin != ''
            GROUP BY anio
            ORDER BY anio DESC
            """,
            (user_id,),
        ).fetchall()
        pages_done = conn.execute(
            """
            SELECT strftime('%Y', bu.fecha_fin) AS anio,
                   SUM(COALESCE(b.paginas, 0)) AS paginas
            FROM biblioteca_usuario bu
            JOIN libros_comunes b ON b.id = bu.book_id
            WHERE bu.user_id = ?
              AND bu.estado = 'Terminado'
              AND bu.fecha_fin IS NOT NULL AND bu.fecha_fin != ''
            GROUP BY anio
            ORDER BY anio DESC
            """,
            (user_id,),
        ).fetchall()
        abandoned = conn.execute(
            """
            SELECT strftime('%Y', bu.fecha_fin) AS anio,
                   SUM(COALESCE(bu.paginas_leidas_abandono, 0)) AS paginas
            FROM biblioteca_usuario bu
            WHERE bu.user_id = ?
              AND bu.estado = 'Abandonado'
              AND bu.fecha_fin IS NOT NULL AND bu.fecha_fin != ''
            GROUP BY anio
            ORDER BY anio DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in finished], [dict(r) for r in pages_done], [dict(r) for r in abandoned]


def init_session_state() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "failed_login_attempts" not in st.session_state:
        st.session_state.failed_login_attempts = 0
    if "login_lock_until" not in st.session_state:
        st.session_state.login_lock_until = 0.0
    if "book_flow" not in st.session_state:
        st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}


def login_register_view() -> None:
    st.title("Mi Estanteria Digital")
    tab_login, tab_register, tab_recover = st.tabs(["Iniciar sesion", "Registro", "Recuperar contrasena"])

    with tab_login:
        now = time.time()
        locked = now < st.session_state.login_lock_until
        if locked:
            wait = int(st.session_state.login_lock_until - now)
            st.warning(f"Cuenta bloqueada temporalmente. Vuelve a intentarlo en {wait} segundos.")

        login_mode = st.radio(
            "Acceder con",
            ["Nombre de usuario", "Email"],
            horizontal=True,
            key="auth_login_mode",
        )
        label_ident = "Email" if login_mode == "Email" else "Nombre de usuario"

        with st.form("auth_login_form"):
            identifier = st.text_input(label_ident, key="auth_login_identifier")
            password = st.text_input("Contrasena", type="password", key="auth_login_password")
            submit = st.form_submit_button("Entrar", disabled=locked)

        if submit:
            if not identifier.strip() or not password:
                st.error("Completa el campo de acceso y la contrasena.")
                return
            mode = "Email" if login_mode == "Email" else "Username"
            user = authenticate_user(mode, identifier, password)
            if user:
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.session_state.failed_login_attempts = 0
                st.session_state.login_lock_until = 0.0
                st.success("Sesion iniciada correctamente.")
                st.rerun()
            st.session_state.failed_login_attempts += 1
            attempts = st.session_state.failed_login_attempts
            if attempts >= 5:
                st.session_state.login_lock_until = time.time() + LOCK_SECONDS
                st.session_state.failed_login_attempts = 0
                st.error("Demasiados intentos fallidos. Espera unos minutos antes de volver a intentarlo.")
            else:
                st.error(f"Credenciales incorrectas. Te quedan {5 - attempts} intentos antes del bloqueo.")

    with tab_register:
        with st.form("auth_register_form"):
            new_username = st.text_input("Usuario", key="auth_register_username")
            new_email = st.text_input("Email", key="auth_register_email")
            new_password = st.text_input("Contrasena", type="password", key="auth_register_password")
            submit_register = st.form_submit_button("Crear cuenta")
        if submit_register:
            if len(new_username.strip()) < 3:
                st.error("El usuario debe tener al menos 3 caracteres.")
                return
            ok_email, msg_email = validate_email(new_email)
            if not ok_email:
                st.error(msg_email)
                return
            ok_password, password_errors = validate_password_owasp(new_password)
            if not ok_password:
                for msg in password_errors:
                    st.error(msg)
                return
            try:
                create_user(new_username, new_email, new_password)
                st.success("Cuenta creada. Ya puedes iniciar sesion.")
            except sqlite3.IntegrityError as err:
                text = str(err).lower()
                if "username" in text:
                    st.error("Ese nombre de usuario ya esta registrado.")
                elif "email" in text:
                    st.error("Ese correo ya esta registrado.")
                else:
                    st.error("No se pudo crear la cuenta por un conflicto de datos.")
            except sqlite3.Error as err:
                st.error(f"Error al guardar el usuario: {err}")

    with tab_recover:
        with st.form("auth_recover_form"):
            email = st.text_input("Email registrado", key="auth_recover_email")
            new_password = st.text_input("Nueva contrasena", type="password", key="auth_recover_password")
            submit_recover = st.form_submit_button("Actualizar contrasena")
        if submit_recover:
            ok_email, msg_email = validate_email(email)
            if not ok_email:
                st.error(msg_email)
                return
            ok_password, password_errors = validate_password_owasp(new_password)
            if not ok_password:
                for msg in password_errors:
                    st.error(msg)
                return
            try:
                if recover_password(email, new_password):
                    st.success("Contrasena actualizada. Ya puedes iniciar sesion.")
                else:
                    st.error("No hay ninguna cuenta con ese email.")
            except sqlite3.Error as err:
                st.error(f"No se pudo actualizar la contrasena: {err}")


def add_book_section(user_id: int) -> None:
    st.subheader("Anadir libro")
    st.caption("No se admiten libros sin ISBN. Indica al menos ISBN-10 o ISBN-13 valido para continuar.")

    with st.form("books_lookup_form"):
        col_a, col_b, col_c = st.columns([2, 2, 1])
        with col_a:
            isbn_10_input = st.text_input("ISBN-10", key="books_lookup_isbn10")
        with col_b:
            isbn_13_input = st.text_input("ISBN-13", key="books_lookup_isbn13")
        with col_c:
            estado = st.selectbox("Estado inicial", READING_STATES, index=0, key="books_lookup_estado")
        lookup_clicked = st.form_submit_button("Buscar / Continuar")

    if lookup_clicked:
        ok10, msg10, isbn10 = validate_isbn10(isbn_10_input)
        ok13, msg13, isbn13 = validate_isbn13(isbn_13_input)
        if not ok10:
            st.error(msg10)
            return
        if not ok13:
            st.error(msg13)
            return
        if not isbn10 and not isbn13:
            st.error("Debes introducir al menos un ISBN (10 o 13) valido para crear o buscar un libro.")
            return
        existing = find_book_by_isbn(isbn10, isbn13)
        st.session_state.book_flow = {
            "step": "found" if existing else "new",
            "isbn10": isbn10,
            "isbn13": isbn13,
            "estado": estado,
            "existing": existing,
        }
        st.rerun()

    flow: dict[str, Any] = st.session_state.book_flow
    if flow["step"] == "idle":
        return

    if st.button("Nueva busqueda", key="books_reset_lookup"):
        st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
        st.rerun()

    if flow["step"] == "found":
        book = flow["existing"]
        st.info("Este titulo ya esta en el catalogo comun. Solo se anadira a tu biblioteca.")
        left, right = st.columns([1, 3])
        with left:
            if book["cover_path"] and os.path.exists(book["cover_path"]):
                st.image(book["cover_path"], width=120)
        with right:
            st.write(f"**Titulo:** {book['title']}")
            st.write(f"**Autor:** {book['author']}")
            st.write(f"**Genero:** {book['genre']}")
            st.write(f"**Idioma:** {book['idioma']}")
            st.write(f"**Paginas:** {book['paginas'] if book['paginas'] is not None else '-'}")
            st.write(f"**ISBN-10:** {book['isbn_10'] if book['isbn_10'] else '-'}")
            st.write(f"**ISBN-13:** {book['isbn_13'] if book['isbn_13'] else '-'}")
        if st.button("Anadir a mi biblioteca", key="books_link_existing"):
            try:
                fi, ff = initial_dates_for_estado(flow["estado"])
                linked = add_book_to_user_library(
                    user_id, book["id"], flow["estado"], fi, ff, None
                )
                if linked:
                    st.success("Libro anadido a tu biblioteca.")
                    st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
                    st.rerun()
                else:
                    st.warning("Este libro ya estaba en tu biblioteca.")
            except sqlite3.Error as err:
                st.error(f"No se pudo anadir el libro: {err}")
    else:
        st.warning(
            "Alta de libro nuevo en el catalogo comun con ISBN obligatorio."
        )
        with st.form("books_new_book_form"):
            c1, c2 = st.columns(2)
            with c1:
                title = st.text_input("Titulo *", key="books_new_title")
                author = st.text_input("Autor *", key="books_new_author")
                genre = st.text_input("Genero (opcional)", key="books_new_genre")
            with c2:
                idioma = st.selectbox("Idioma *", LANGUAGE_OPTIONS, index=0, key="books_new_idioma")
                paginas = st.number_input("Paginas (opcional)", min_value=0, value=0, step=1, key="books_new_paginas")
                cover = st.file_uploader("Portada (opcional, JPG/PNG)", type=["jpg", "jpeg", "png"], key="books_new_cover")
            create_clicked = st.form_submit_button("Guardar libro y anadir a mi biblioteca")

        if create_clicked:
            if not title.strip() or not author.strip():
                st.error("Titulo y autor son obligatorios.")
                return
            if not idioma:
                st.error("Selecciona un idioma.")
                return
            paginas_value = int(paginas) if paginas > 0 else None
            ref = flow["isbn13"] or flow["isbn10"] or "sin_isbn"
            cover_path, cover_error = save_cover_file(ref, cover)
            if cover_error:
                st.error(cover_error)
                return
            try:
                exists_now = find_book_by_isbn(flow["isbn10"], flow["isbn13"])
                if exists_now:
                    book_id = exists_now["id"]
                else:
                    book_id = insert_libro_comun(
                        flow["isbn10"],
                        flow["isbn13"],
                        title,
                        author,
                        genre,
                        idioma,
                        paginas_value,
                        cover_path,
                    )
            except sqlite3.IntegrityError:
                st.error("Conflicto de ISBN. Vuelve a buscar; puede que el libro ya exista.")
                return
            except sqlite3.Error as err:
                st.error(f"Error al guardar en el catalogo: {err}")
                return

            try:
                fi, ff = initial_dates_for_estado(flow["estado"])
                linked = add_book_to_user_library(user_id, book_id, flow["estado"], fi, ff, None)
                if linked:
                    st.success("Libro creado y anadido a tu biblioteca.")
                    st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
                    st.rerun()
                else:
                    st.warning("El libro esta en el catalogo pero ya lo tenias en tu biblioteca.")
            except sqlite3.Error as err:
                st.error(f"El libro se guardo pero no se pudo vincular a tu biblioteca: {err}")


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Aun no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galeria"], horizontal=True, key="library_view_mode")
    if view_mode == "Lista":
        for book in books:
            bid = book["book_id"]
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                with c1:
                    if book["cover_path"] and os.path.exists(book["cover_path"]):
                        st.image(book["cover_path"], width=85)
                with c2:
                    st.write(f"**{book['title']}**")
                    st.caption(
                        f"{book['author']} · {book['genre']} · {book['idioma']} · "
                        f"Pags. catalogo: {book['paginas'] if book['paginas'] is not None else '-'}"
                    )
                    st.caption(
                        f"ISBN-10: {book['isbn_10'] or '-'} | ISBN-13: {book['isbn_13'] or '-'}"
                    )
                    st.caption(
                        f"Inicio: {book['fecha_inicio'] or '-'} · Fin: {book['fecha_fin'] or '-'} · "
                        f"Estado: **{book['estado']}**"
                    )
                    if book["estado"] == "Abandonado" and book.get("paginas_leidas_abandono") is not None:
                        st.caption(f"Paginas leidas (abandono): {book['paginas_leidas_abandono']}")

                with st.expander("Gestionar estado y fechas", expanded=False):
                    cur = book["estado"]
                    idx = READING_STATES.index(cur) if cur in READING_STATES else 0
                    new_est = st.selectbox(
                        "Estado",
                        READING_STATES,
                        index=idx,
                        key=f"library_estado_sel_{bid}",
                    )
                    abandon_pages: Optional[int] = None
                    if new_est == "Abandonado" or cur == "Abandonado":
                        abandon_pages = st.number_input(
                            "Paginas leidas (abandono)",
                            min_value=0,
                            value=int(book["paginas_leidas_abandono"] or 0),
                            step=1,
                            key=f"library_abandon_pages_{bid}",
                            help="Obligatorio al pasar a Abandonado. Tambien puedes ajustarlo si el libro ya estaba abandonado.",
                        )
                    d_ini = _parse_date(book["fecha_inicio"])
                    d_fin = _parse_date(book["fecha_fin"])
                    cdi, cdf = st.columns(2)
                    with cdi:
                        edit_ini = st.date_input(
                            "Fecha de inicio (editable)",
                            value=d_ini or date.today(),
                            key=f"library_date_ini_{bid}",
                        )
                    with cdf:
                        edit_fin = st.date_input(
                            "Fecha de fin (editable)",
                            value=d_fin or date.today(),
                            key=f"library_date_fin_{bid}",
                        )
                    st.caption(
                        "**Pendiente -> Leyendo**: se guarda hoy como inicio. **Leyendo -> Terminado**: hoy como fin. "
                        "**Relectura**: se borran inicio y fin para un nuevo ciclo (luego puedes editarlas). "
                        "Las fechas de los calendarios prevalecen si solo actualizas fechas sin cambiar estado."
                    )
                    if st.button("Guardar cambios", key=f"library_save_{bid}"):
                        today = today_iso()
                        fi_w = edit_ini.isoformat()
                        ff_w = edit_fin.isoformat()
                        ap_val = int(book.get("paginas_leidas_abandono") or 0)
                        if new_est == "Abandonado":
                            ap_val = int(abandon_pages if abandon_pages is not None else 0)

                        try:
                            if new_est != cur:
                                d = transition_updates(
                                    cur,
                                    new_est,
                                    book["fecha_inicio"],
                                    book["fecha_fin"],
                                    today,
                                    ap_val if new_est == "Abandonado" else None,
                                )
                                fi: Optional[str] = fi_w
                                ff: Optional[str] = ff_w
                                pab: Optional[int] = book.get("paginas_leidas_abandono")

                                if new_est == "Relectura":
                                    fi, ff, pab = None, None, None
                                elif new_est == "Leyendo":
                                    fi = today
                                    ff = None
                                    pab = None
                                elif new_est == "Terminado":
                                    fi = book["fecha_inicio"] or fi_w or today
                                    ff = today
                                    pab = None
                                elif new_est == "Abandonado":
                                    pab = ap_val
                                    fi = book["fecha_inicio"] or fi_w
                                    ff = ff_w or d.get("fecha_fin") or today
                                elif new_est == "Pendiente":
                                    fi, ff, pab = None, None, None
                                else:
                                    fi = d.get("fecha_inicio", fi_w)
                                    ff = d.get("fecha_fin", ff_w)
                                    pab = d.get("paginas_leidas_abandono")

                                update_biblioteca_row(user_id, bid, new_est, fi, ff, pab)
                                st.success("Estado y fechas actualizados correctamente.")
                            else:
                                if new_est == "Abandonado":
                                    pab_out = int(
                                        abandon_pages
                                        if abandon_pages is not None
                                        else book.get("paginas_leidas_abandono") or 0
                                    )
                                else:
                                    pab_out = book.get("paginas_leidas_abandono")
                                update_biblioteca_row(user_id, bid, cur, fi_w, ff_w, pab_out)
                                st.success("Fechas guardadas correctamente.")
                            st.rerun()
                        except sqlite3.Error as e:
                            st.error(f"No se pudo guardar en la base de datos: {e}")
    else:
        cols = st.columns(4)
        for i, book in enumerate(books):
            with cols[i % 4]:
                if book["cover_path"] and os.path.exists(book["cover_path"]):
                    st.image(book["cover_path"], use_container_width=True)
                else:
                    st.markdown("*Sin portada*")
                st.write(f"**{book['title']}**")
                st.caption(f"{book['author']} · {book['estado']}")


def statistics_section(user_id: int) -> None:
    st.subheader("Estadisticas")
    finished, pages_done, abandoned = get_reading_statistics(user_id)
    years: set[str] = set()
    for row in finished:
        if row["anio"]:
            years.add(row["anio"])
    for row in pages_done:
        if row["anio"]:
            years.add(row["anio"])
    for row in abandoned:
        if row["anio"]:
            years.add(row["anio"])
    libros_por_anio = {r["anio"]: r["libros"] for r in finished if r["anio"]}
    paginas_terminados = {r["anio"]: int(r["paginas"] or 0) for r in pages_done if r["anio"]}
    paginas_abandonados = {r["anio"]: int(r["paginas"] or 0) for r in abandoned if r["anio"]}

    if not years:
        st.info(
            "Aun no hay datos para estadisticas. Marca libros como **Terminado** (con fecha de fin) "
            "o **Abandonado** (con paginas leidas y fecha de fin) para ver resumenes por ano."
        )
        return

    rows_out = []
    for y in sorted(years, reverse=True):
        lt = libros_por_anio.get(y, 0)
        pt = paginas_terminados.get(y, 0)
        pa = paginas_abandonados.get(y, 0)
        rows_out.append(
            {
                "Anio": y,
                "Libros terminados": lt,
                "Paginas (terminados)": pt,
                "Paginas (abandonados)": pa,
                "Paginas totales": pt + pa,
            }
        )
    st.dataframe(rows_out, use_container_width=True, hide_index=True)
    st.caption(
        "Los libros terminados cuentan por **fecha_fin**. Las paginas de abandonos usan el valor "
        "que indicaste al marcar **Abandonado**, tambien asignadas al ano de **fecha_fin**."
    )


def main() -> None:
    st.set_page_config(page_title="Mi Estanteria Digital", page_icon="📚", layout="wide")
    init_db()
    init_session_state()

    if st.session_state.user_id is None:
        login_register_view()
        return

    st.title("Mi Estanteria Digital")
    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.caption(f"Usuario: {st.session_state.username}")
    with top_right:
        if st.button("Cerrar sesion", key="layout_logout_button"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.rerun()

    add_book_section(st.session_state.user_id)
    st.divider()
    library_view(st.session_state.user_id)
    st.divider()
    statistics_section(st.session_state.user_id)

    with st.expander("Nota de migracion"):
        st.markdown(
            "Si algo falla al abrir la base de datos antigua, haz copia de seguridad y borra "
            "`biblioteca.db` para regenerar el esquema."
        )


if __name__ == "__main__":
    main()
