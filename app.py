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
