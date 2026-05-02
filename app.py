import os
import re
import sqlite3
from datetime import datetime
from typing import Optional

import streamlit as st
from passlib.context import CryptContext

DB_PATH = "biblioteca.db"
COVERS_DIR = "portadas"
READING_STATES = ["Pendiente", "Leyendo", "Terminado", "Abandonado", "Relectura"]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(COVERS_DIR, exist_ok=True)
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                genre TEXT NOT NULL,
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
                FOREIGN KEY(book_id) REFERENCES books(id)
            )
            """
        )
        conn.commit()


def normalize_isbn(raw_isbn: str) -> str:
    return re.sub(r"[^0-9Xx]", "", raw_isbn).upper()


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


def create_user(username: str, password: str) -> bool:
    hashed = pwd_context.hash(password)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username.strip(), hashed, datetime.utcnow().isoformat()),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


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
        return conn.execute("SELECT * FROM books WHERE isbn = ?", (isbn,)).fetchone()


def create_book(isbn: str, title: str, author: str, genre: str, cover_path: Optional[str]) -> int:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO books (isbn, title, author, genre, cover_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (isbn, title.strip(), author.strip(), genre.strip(), cover_path, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cursor.lastrowid


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
                b.cover_path,
                ub.status
            FROM user_books ub
            JOIN books b ON b.id = ub.book_id
            WHERE ub.user_id = ?
            ORDER BY b.title COLLATE NOCASE
            """,
            (user_id,),
        ).fetchall()


def login_register_view() -> None:
    st.title("Mi Estanteria Digital")
    st.caption("Red social de libros tipo Goodreads (version personal)")

    tab_login, tab_register = st.tabs(["Iniciar sesion", "Registro"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contrasena", type="password")
            submit_login = st.form_submit_button("Entrar")

        if submit_login:
            if not username.strip() or not password:
                st.error("Debes completar usuario y contrasena.")
                return
            user = authenticate_user(username, password)
            if user:
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.success("Sesion iniciada.")
                st.rerun()
            else:
                st.error("Credenciales invalidas.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Nuevo usuario")
            new_password = st.text_input("Nueva contrasena", type="password")
            submit_register = st.form_submit_button("Crear cuenta")

        if submit_register:
            if len(new_username.strip()) < 3:
                st.error("El usuario debe tener al menos 3 caracteres.")
                return
            if len(new_password) < 6:
                st.error("La contrasena debe tener al menos 6 caracteres.")
                return
            if create_user(new_username, new_password):
                st.success("Cuenta creada correctamente. Ya puedes iniciar sesion.")
            else:
                st.error("Ese nombre de usuario ya existe.")


def add_book_section(user_id: int) -> None:
    st.subheader("Anadir libro por ISBN")
    with st.form("book_form", clear_on_submit=False):
        isbn_input = st.text_input("ISBN", placeholder="9788497592208")
        status = st.selectbox("Estado de lectura", options=READING_STATES, index=1)
        fetch = st.form_submit_button("Buscar ISBN")

    if not fetch:
        return

    isbn = normalize_isbn(isbn_input)
    if not isbn:
        st.error("Introduce un ISBN valido.")
        return

    existing = get_book_by_isbn(isbn)
    if existing:
        st.info("ISBN encontrado en la base comun. Se recuperaron los datos.")
        st.write(f"**Titulo:** {existing['title']}")
        st.write(f"**Autor:** {existing['author']}")
        st.write(f"**Genero:** {existing['genre']}")
        if existing["cover_path"] and os.path.exists(existing["cover_path"]):
            st.image(existing["cover_path"], width=140)

        if st.button("Anadir a mi biblioteca", key=f"add_existing_{isbn}"):
            if add_book_to_user_library(user_id, existing["id"], status):
                st.success("Libro anadido a tu biblioteca.")
            else:
                st.warning("Ese libro ya esta en tu biblioteca.")
        return

    st.warning("ISBN no encontrado. Completa los datos para crearlo en la base comun.")
    with st.form(f"new_book_{isbn}"):
        title = st.text_input("Titulo")
        author = st.text_input("Autor")
        genre = st.text_input("Genero")
        cover = st.file_uploader("Portada (JPG/PNG)", type=["jpg", "jpeg", "png"])
        create_and_add = st.form_submit_button("Guardar libro y anadir a mi biblioteca")

    if create_and_add:
        if not title.strip() or not author.strip() or not genre.strip():
            st.error("Titulo, autor y genero son obligatorios.")
            return
        cover_path = save_cover_file(isbn, cover)
        if cover is not None and cover_path is None:
            st.error("Formato de imagen no valido. Usa JPG o PNG.")
            return
        try:
            book_id = create_book(isbn, title, author, genre, cover_path)
        except sqlite3.IntegrityError:
            st.error("Otro usuario acaba de registrar este ISBN. Vuelve a buscarlo.")
            return
        add_book_to_user_library(user_id, book_id, status)
        st.success("Libro creado en base comun y anadido a tu biblioteca.")


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Todavia no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galeria"], horizontal=True)

    if view_mode == "Lista":
        for book in books:
            with st.container(border=True):
                col1, col2, col3 = st.columns([1, 4, 2])
                with col1:
                    if book["cover_path"] and os.path.exists(book["cover_path"]):
                        st.image(book["cover_path"], width=90)
                with col2:
                    st.write(f"**{book['title']}**")
                    st.write(f"{book['author']} - {book['genre']}")
                    st.caption(f"ISBN: {book['isbn']}")
                with col3:
                    new_status = st.selectbox(
                        "Estado",
                        READING_STATES,
                        index=READING_STATES.index(book["status"]) if book["status"] in READING_STATES else 0,
                        key=f"status_{book['book_id']}",
                    )
                    if new_status != book["status"]:
                        update_user_book_status(user_id, book["book_id"], new_status)
                        st.success("Estado actualizado.")
                        st.rerun()
    else:
        cols = st.columns(4)
        for i, book in enumerate(books):
            col = cols[i % 4]
            with col:
                if book["cover_path"] and os.path.exists(book["cover_path"]):
                    st.image(book["cover_path"], use_container_width=True)
                else:
                    st.markdown("🟫 *Sin portada*")
                st.write(f"**{book['title']}**")
                st.caption(f"{book['author']} - {book['status']}")


def main() -> None:
    st.set_page_config(page_title="Mi Estanteria Digital", page_icon="📚", layout="wide")
    init_db()

    if "user_id" not in st.session_state:
        st.session_state.user_id = None
        st.session_state.username = None

    if not st.session_state.user_id:
        login_register_view()
        return

    st.title("Mi Estanteria Digital")
    top_col1, top_col2 = st.columns([5, 1])
    with top_col1:
        st.caption(f"Usuario: {st.session_state.username}")
    with top_col2:
        if st.button("Cerrar sesion"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.rerun()

    add_book_section(st.session_state.user_id)
    st.divider()
    library_view(st.session_state.user_id)


if __name__ == "__main__":
    main()
