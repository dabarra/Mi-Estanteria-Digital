import os
import re
import sqlite3
from datetime import datetime
from typing import Any, Optional

import streamlit as st
from passlib.context import CryptContext

DB_PATH = "biblioteca.db"
COVERS_DIR = "portadas"
READING_STATES = ["Pendiente", "Leyendo", "Terminado", "Abandonado", "Relectura"]

LANGUAGE_OPTIONS = [
    "Español",
    "Inglés",
    "Francés",
    "Alemán",
    "Italiano",
    "Portugués",
    "Catalán",
    "Gallego",
    "Euskera",
    "Otro",
]

EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)
PASSWORD_SPECIAL_PATTERN = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]""")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r["name"] for r in rows}


def _migrate_legacy_books_to_libros_comunes(conn: sqlite3.Connection) -> None:
    legacy = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='books'"
    ).fetchone()
    if not legacy:
        return
    count_new = conn.execute("SELECT COUNT(*) AS c FROM libros_comunes").fetchone()["c"]
    if count_new > 0:
        return
    legacy_cols = _table_columns(conn, "books")
    if not legacy_cols:
        return
    fk_was_on = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        has_lang = "language" in legacy_cols
        has_pages = "page_count" in legacy_cols
        if has_lang and has_pages:
            conn.execute(
                """
                INSERT INTO libros_comunes (id, isbn, title, author, genre, language, page_count, cover_path, created_at)
                SELECT id, isbn, title, author, genre, language, page_count, cover_path, created_at FROM books
                """
            )
        else:
            conn.execute(
                """
                INSERT INTO libros_comunes (id, isbn, title, author, genre, language, page_count, cover_path, created_at)
                SELECT id, isbn, title, author, genre, 'Español', NULL, cover_path, created_at FROM books
                """
            )
        conn.execute("DROP TABLE books")
    finally:
        conn.execute(f"PRAGMA foreign_keys = {fk_was_on}")


def init_db() -> None:
    os.makedirs(COVERS_DIR, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS libros_comunes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT NOT NULL,
                language TEXT NOT NULL,
                page_count INTEGER,
                cover_path TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                added_at TEXT NOT NULL,
                UNIQUE(user_id, book_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(book_id) REFERENCES libros_comunes(id)
            )
            """
        )

        user_cols = _table_columns(conn, "users")
        if "email" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT UNIQUE")

        libro_cols = _table_columns(conn, "libros_comunes")
        if "language" not in libro_cols:
            conn.execute(
                "ALTER TABLE libros_comunes ADD COLUMN language TEXT NOT NULL DEFAULT 'Español'"
            )
        if "page_count" not in libro_cols:
            conn.execute("ALTER TABLE libros_comunes ADD COLUMN page_count INTEGER")

        _migrate_legacy_books_to_libros_comunes(conn)
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


def validate_isbn_format(normalized: str) -> tuple[bool, str]:
    if not normalized:
        return False, "Introduce un ISBN (10 o 13 caracteres, sin contar guiones o espacios)."
    if len(normalized) == 10:
        if isbn10_check_digit(normalized):
            return True, ""
        return False, "ISBN-10 inválido: el dígito de control no coincide."
    if len(normalized) == 13:
        if isbn13_check_digit(normalized):
            return True, ""
        return False, "ISBN-13 inválido: el dígito de control no coincide."
    return (
        False,
        "El ISBN debe tener exactamente 10 caracteres (ISBN-10) o 13 (ISBN-13) tras quitar guiones y espacios.",
    )


def validate_email(email: str) -> tuple[bool, str]:
    e = email.strip()
    if not e:
        return False, "El correo electrónico es obligatorio."
    if not EMAIL_PATTERN.match(e):
        return False, "El correo no tiene un formato válido (ejemplo: nombre@dominio.com)."
    return True, ""


def validate_password_owasp(password: str) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if len(password) < 8:
        errors.append("La contraseña debe tener al menos 8 caracteres.")
    if not re.search(r"[A-Z]", password):
        errors.append("La contraseña debe incluir al menos una letra mayúscula.")
    if not re.search(r"[a-z]", password):
        errors.append("La contraseña debe incluir al menos una letra minúscula.")
    if not re.search(r"\d", password):
        errors.append("La contraseña debe incluir al menos un número.")
    if not PASSWORD_SPECIAL_PATTERN.search(password):
        errors.append(
            "La contraseña debe incluir al menos un carácter especial (por ejemplo: !@#$%&*)."
        )
    return len(errors) == 0, errors


def save_cover_file(isbn: str, uploaded_file) -> Optional[str]:
    if uploaded_file is None:
        return None

    _, ext = os.path.splitext(uploaded_file.name.lower())
    if ext not in [".jpg", ".jpeg", ".png"]:
        return None

    safe_isbn = normalize_isbn(isbn) or "sin_isbn"
    filename = f"{safe_isbn}_{int(datetime.utcnow().timestamp())}{ext}"
    path = os.path.join(COVERS_DIR, filename)

    with open(path, "wb") as output:
        output.write(uploaded_file.getbuffer())
    return path


def create_user(username: str, email: str, password: str) -> None:
    hashed = pwd_context.hash(password)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (username, email, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                username.strip(),
                email.strip().lower(),
                hashed,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


def authenticate_user(username: str, password: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    if row and pwd_context.verify(password, row["password_hash"]):
        return row
    return None


def get_book_by_isbn(isbn: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM libros_comunes WHERE isbn = ?", (isbn,)
        ).fetchone()


def insert_libro_comun(
    isbn: str,
    title: str,
    author: str,
    genre: str,
    language: str,
    page_count: Optional[int],
    cover_path: Optional[str],
) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO libros_comunes (
                isbn, title, author, genre, language, page_count, cover_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                isbn,
                title.strip(),
                author.strip(),
                genre.strip(),
                language,
                page_count,
                cover_path,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        return cur.lastrowid


def add_book_to_user_library(user_id: int, book_id: int, status: str) -> bool:
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_books (user_id, book_id, status, added_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, book_id, status, datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def update_user_book_status(user_id: int, book_id: int, status: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE user_books SET status = ? WHERE user_id = ? AND book_id = ?",
            (status, user_id, book_id),
        )
        conn.commit()


def get_user_library(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                b.id AS book_id,
                b.isbn,
                b.title,
                b.author,
                b.genre,
                b.language,
                b.page_count,
                b.cover_path,
                ub.status
            FROM user_books ub
            JOIN libros_comunes b ON b.id = ub.book_id
            WHERE ub.user_id = ?
            ORDER BY b.title COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()


def _init_book_flow_state() -> None:
    if "book_flow" not in st.session_state:
        st.session_state.book_flow = {
            "step": "lookup",
            "isbn": None,
            "status": READING_STATES[1],
        }


def login_register_view() -> None:
    st.title("Mi Estantería Digital")
    st.caption("Biblioteca personal con catálogo común por ISBN")

    tab_login, tab_register = st.tabs(["Iniciar sesión", "Registro"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Usuario", key="login_user")
            password = st.text_input("Contraseña", type="password", key="login_pass")
            submit_login = st.form_submit_button("Entrar")

        if submit_login:
            if not username.strip() or not password:
                st.error("Debes completar usuario y contraseña.")
                return
            user = authenticate_user(username, password)
            if user:
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.success("Sesión iniciada.")
                st.rerun()
            else:
                st.error("Credenciales inválidas.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Usuario", key="reg_user")
            new_email = st.text_input("Correo electrónico", key="reg_email")
            new_password = st.text_input("Contraseña", type="password", key="reg_pass")
            submit_register = st.form_submit_button("Crear cuenta")

        if submit_register:
            if len(new_username.strip()) < 3:
                st.error("El usuario debe tener al menos 3 caracteres.")
                return
            ok_email, email_err = validate_email(new_email)
            if not ok_email:
                st.error(email_err)
                return
            ok_pw, pw_errors = validate_password_owasp(new_password)
            if not ok_pw:
                for msg in pw_errors:
                    st.error(msg)
                return
            try:
                create_user(new_username, new_email, new_password)
            except sqlite3.IntegrityError as e:
                err = str(e).lower()
                if "username" in err or "users.username" in err:
                    st.error("Ese nombre de usuario ya está registrado.")
                elif "email" in err or "users.email" in err:
                    st.error("Ese correo electrónico ya está registrado.")
                else:
                    st.error("No se pudo crear la cuenta (dato duplicado o error de base de datos).")
                return
            except sqlite3.Error:
                st.error("Error al guardar el usuario. Inténtalo de nuevo.")
                return
            st.success("Cuenta creada correctamente. Ya puedes iniciar sesión.")


def add_book_section(user_id: int) -> None:
    _init_book_flow_state()
    flow: dict[str, Any] = st.session_state.book_flow

    st.subheader("Añadir libro por ISBN")

    with st.form("isbn_lookup_form"):
        c1, c2 = st.columns([2, 1])
        with c1:
            isbn_input = st.text_input(
                "ISBN (ISBN-10 o ISBN-13)",
                placeholder="978-84-9759-220-8 o 8497592207",
                key="isbn_lookup_input",
            )
        with c2:
            status = st.selectbox(
                "Estado de lectura",
                options=READING_STATES,
                index=READING_STATES.index(flow["status"])
                if flow["status"] in READING_STATES
                else 1,
                key="isbn_lookup_status",
            )
        search_clicked = st.form_submit_button("Buscar ISBN")

    if search_clicked:
        normalized = normalize_isbn(isbn_input)
        ok, err_msg = validate_isbn_format(normalized)
        if not ok:
            st.error(err_msg)
            st.session_state.book_flow = {
                "step": "lookup",
                "isbn": None,
                "status": status,
            }
            return
        existing = get_book_by_isbn(normalized)
        st.session_state.book_flow = {
            "step": "found" if existing else "new",
            "isbn": normalized,
            "status": status,
            "existing_row": dict(existing) if existing else None,
        }
        st.rerun()

    flow = st.session_state.book_flow
    if flow.get("step") == "lookup" or not flow.get("isbn"):
        st.caption(
            "Tras buscar, si el ISBN no está en el catálogo común podrás completar los datos "
            "y guardar; el vínculo a tu biblioteca se crea en el mismo paso."
        )
        return

    isbn = flow["isbn"]
    status_sel = flow["status"]

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if st.button("Nueva búsqueda", key="reset_book_flow"):
            st.session_state.book_flow = {
                "step": "lookup",
                "isbn": None,
                "status": READING_STATES[1],
            }
            st.rerun()

    if flow["step"] == "found" and flow.get("existing_row"):
        row = flow["existing_row"]
        st.info("Este ISBN ya está en **libros comunes**. Se muestran los datos guardados.")
        d1, d2 = st.columns([1, 3])
        with d1:
            if row.get("cover_path") and os.path.exists(row["cover_path"]):
                st.image(row["cover_path"], width=120)
        with d2:
            st.write(f"**Título:** {row['title']}")
            st.write(f"**Autor:** {row['author']}")
            st.write(f"**Género:** {row['genre']}")
            st.write(f"**Idioma:** {row.get('language', '—')}")
            pages = row.get("page_count")
            st.write(f"**Páginas:** {pages if pages is not None else '—'}")
        if st.button("Añadir a mi biblioteca", key=f"link_existing_{isbn}"):
            try:
                if add_book_to_user_library(user_id, row["id"], status_sel):
                    st.success("Libro añadido a tu biblioteca.")
                    st.session_state.book_flow = {
                        "step": "lookup",
                        "isbn": None,
                        "status": status_sel,
                    }
                    st.rerun()
                else:
                    st.warning("Ese libro ya está en tu biblioteca.")
            except sqlite3.Error:
                st.error("No se pudo enlazar el libro. Inténtalo de nuevo.")

    elif flow["step"] == "new":
        st.warning(
            "ISBN no encontrado en **libros comunes**. Completa los datos; se creará el registro "
            "común y el vínculo a tu biblioteca."
        )
        with st.form("create_common_book_form"):
            r1, r2 = st.columns(2)
            with r1:
                title = st.text_input("Título", key="new_title")
                author = st.text_input("Autor", key="new_author")
                genre = st.text_input("Género", key="new_genre")
            with r2:
                language = st.selectbox(
                    "Idioma",
                    options=LANGUAGE_OPTIONS,
                    index=0,
                    key="new_language",
                )
                page_count = st.number_input(
                    "Número de páginas",
                    min_value=0,
                    value=0,
                    step=1,
                    help="0 si aún no lo conoces",
                    key="new_pages",
                )
                cover = st.file_uploader(
                    "Portada (JPG/PNG)",
                    type=["jpg", "jpeg", "png"],
                    key="new_cover",
                )
            submit_create = st.form_submit_button(
                "Guardar libro y añadir a mi biblioteca"
            )

        if submit_create:
            if not title.strip() or not author.strip() or not genre.strip():
                st.error("Título, autor y género son obligatorios.")
                return
            pages_val: Optional[int] = int(page_count) if page_count and page_count > 0 else None
            cover_path = save_cover_file(isbn, cover)
            if cover is not None and cover_path is None:
                st.error("Formato de imagen no válido. Usa JPG o PNG.")
                return

            try:
                again = get_book_by_isbn(isbn)
                if again:
                    book_id = again["id"]
                else:
                    book_id = insert_libro_comun(
                        isbn,
                        title,
                        author,
                        genre,
                        language,
                        pages_val,
                        cover_path,
                    )
            except sqlite3.IntegrityError:
                st.error(
                    "Otro usuario registró este ISBN mientras completabas el formulario. "
                    "Pulsa «Nueva búsqueda» y vuelve a buscar el ISBN."
                )
                return
            except sqlite3.Error as e:
                st.error(f"Error al guardar el libro en el catálogo común: {e}")
                return

            try:
                if add_book_to_user_library(user_id, book_id, status_sel):
                    st.success(
                        "Libro guardado en **libros comunes** y añadido a tu biblioteca."
                    )
                    st.session_state.book_flow = {
                        "step": "lookup",
                        "isbn": None,
                        "status": status_sel,
                    }
                    st.rerun()
                else:
                    st.warning(
                        "El libro está en el catálogo común, pero ya figuraba en tu biblioteca."
                    )
            except sqlite3.Error:
                st.error("El libro se guardó en el catálogo, pero no se pudo añadir a tu biblioteca.")


def _format_pages(pages: Optional[int]) -> str:
    if pages is None:
        return "—"
    return str(pages)


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Todavía no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galería"], horizontal=True)

    if view_mode == "Lista":
        for book in books:
            with st.container(border=True):
                col1, col2, col3 = st.columns([1, 4, 2])
                with col1:
                    if book["cover_path"] and os.path.exists(book["cover_path"]):
                        st.image(book["cover_path"], width=90)
                with col2:
                    st.write(f"**{book['title']}**")
                    st.write(
                        f"{book['author']} · {book['genre']} · {book.get('language', '')}"
                    )
                    st.caption(
                        f"ISBN: {book['isbn']} · Págs.: {_format_pages(book.get('page_count'))}"
                    )
                with col3:
                    new_status = st.selectbox(
                        "Estado",
                        READING_STATES,
                        index=READING_STATES.index(book["status"])
                        if book["status"] in READING_STATES
                        else 0,
                        key=f"status_{book['book_id']}",
                    )
                    if new_status != book["status"]:
                        try:
                            update_user_book_status(
                                user_id, book["book_id"], new_status
                            )
                            st.success("Estado actualizado.")
                        except sqlite3.Error:
                            st.error("No se pudo actualizar el estado.")
                        st.rerun()
    else:
        cols = st.columns(4)
        for i, book in enumerate(books):
            col = cols[i % 4]
            with col:
                if book["cover_path"] and os.path.exists(book["cover_path"]):
                    st.image(book["cover_path"], use_container_width=True)
                else:
                    st.markdown("*Sin portada*")
                st.write(f"**{book['title']}**")
                st.caption(
                    f"{book['author']} · {book['status']} · {_format_pages(book.get('page_count'))} pág."
                )


def main() -> None:
    st.set_page_config(
        page_title="Mi Estantería Digital", page_icon="📚", layout="wide"
    )
    init_db()

    if "user_id" not in st.session_state:
        st.session_state.user_id = None
        st.session_state.username = None

    if not st.session_state.user_id:
        login_register_view()
        return

    st.title("Mi Estantería Digital")
    top_col1, top_col2 = st.columns([5, 1])
    with top_col1:
        st.caption(f"Usuario: {st.session_state.username}")
    with top_col2:
        if st.button("Cerrar sesión"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.rerun()

    add_book_section(st.session_state.user_id)
    st.divider()
    library_view(st.session_state.user_id)

    with st.expander("Nota sobre la base de datos"):
        st.markdown(
            "Si actualizas desde una versión muy antigua y ves errores raros de esquema, "
            "cierra la app, elimina `biblioteca.db` y vuelve a ejecutar (perderás datos locales de prueba)."
        )


if __name__ == "__main__":
    main()
