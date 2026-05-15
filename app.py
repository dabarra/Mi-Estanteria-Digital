import base64
import html
import os
import time
from datetime import date
from typing import Any, Optional

import streamlit as st

from auth_manager import (
    authenticate_user,
    create_user_with_feedback,
    recover_password_with_feedback,
    validate_email,
    validate_password_owasp,
)
from database_manager import (
    add_book_to_user_library,
    add_catalog_book_and_link_user,
    find_book_by_isbn,
    get_finished_books_detail_for_year,
    get_reading_statistics,
    get_user_library,
    init_db,
    update_libro_comun_metadata,
    update_library_row_safe,
)
from utils import (
    initial_dates_for_estado,
    parse_iso_date,
    save_cover_file,
    transition_updates,
    validate_isbn10,
    validate_isbn13,
)

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


def _login_lock_key(login_mode_label: str, identifier: str) -> str:
    ident = identifier.strip()
    if not ident:
        return ""
    if login_mode_label == "Email":
        return f"email:{ident.lower()}"
    return f"user:{ident}"


def _login_is_locked(lock_key: str) -> bool:
    if not lock_key:
        return False
    until = st.session_state.locks_dict.get(lock_key, 0.0)
    return time.time() < until


def _login_failed_increment(lock_key: str) -> int:
    c = st.session_state.login_failed_counts.get(lock_key, 0) + 1
    st.session_state.login_failed_counts[lock_key] = c
    return c


def _login_clear_lock(lock_key: str) -> None:
    st.session_state.login_failed_counts.pop(lock_key, None)
    st.session_state.locks_dict.pop(lock_key, None)


def _cover_gallery_html(cover_path: str, alt: str) -> str:
    safe_alt = html.escape(alt)
    with open(cover_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("ascii")
    ext = cover_path.lower().rsplit(".", 1)[-1]
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return (
        f'<div class="gallery-tile">'
        f'<div class="gallery-frame">'
        f'<img src="data:{mime};base64,{b64}" alt="{safe_alt}" class="gallery-cover-img" />'
        f'</div>'
        f'<div class="gallery-book-title">{safe_alt}</div>'
        f'</div>'
    )




def _inject_gallery_css() -> None:
    st.markdown(
        """
        <style>
        .gallery-tile { margin-bottom: 1rem; }
        .gallery-frame {
            height: 250px;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #f4f4f5;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            overflow: hidden;
        }
        .gallery-cover-img {
            max-height: 100%;
            max-width: 100%;
            width: auto;
            height: auto;
            object-fit: contain;
            display: block;
        }
        .gallery-book-title {
            font-weight: 600;
            margin-top: 0.4rem;
            font-size: 0.95rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_book_list_row(book: dict[str, Any]) -> None:
    """Fila compacta reutilizada en vista Lista y detalle de estadísticas."""
    total_pags = book.get("paginas")
    tiene_paginas = total_pags is not None and int(total_pags) > 0
    ptxt = f"{int(total_pags)} pág." if tiene_paginas else "Páginas: —"
    idioma = book.get("idioma") or "—"
    estado = book.get("estado") or "—"
    col_cover, col_info = st.columns([0.2, 0.8])
    with col_cover:
        cover = book.get("cover_path")
        if cover and os.path.exists(cover):
            st.image(cover, width=100)
        else:
            st.caption("Sin\nportada")
    with col_info:
        st.markdown(
            f"**{book['title']}**  \n"
            f"{book['author']} · {idioma} · {ptxt} · *{estado}*"
        )


def init_session_state() -> None:
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "login_failed_counts" not in st.session_state:
        st.session_state.login_failed_counts = {}
    if "locks_dict" not in st.session_state:
        st.session_state.locks_dict = {}
    if "book_flow" not in st.session_state:
        st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
    if "library_editing_id" not in st.session_state:
        st.session_state.library_editing_id = None
    if "editing_book_id" not in st.session_state:
        st.session_state.editing_book_id = None


def login_register_view() -> None:
    st.title("Mi Estanteria Digital")
    tab_login, tab_register, tab_recover = st.tabs(["Iniciar sesion", "Registro", "Recuperar contrasena"])

    with tab_login:
        login_mode = st.radio(
            "Acceder con",
            ["Nombre de usuario", "Email"],
            horizontal=True,
            key="auth_login_mode",
        )
        ident_preview = (st.session_state.get("auth_login_identifier") or "").strip()
        lock_key_preview = _login_lock_key(login_mode, ident_preview)
        locked = _login_is_locked(lock_key_preview)

        if locked and lock_key_preview:
            wait = int(st.session_state.locks_dict[lock_key_preview] - time.time())
            st.warning(f"Cuenta bloqueada temporalmente. Vuelve a intentarlo en {max(wait, 0)} segundos.")

        label_ident = "Email" if login_mode == "Email" else "Nombre de usuario"
        with st.form("auth_login_form"):
            identifier = st.text_input(label_ident, key="auth_login_identifier")
            password = st.text_input("Contrasena", type="password", key="auth_login_password")
            submit = st.form_submit_button("Entrar")
        if submit:
            if not identifier.strip() or not password:
                st.error("Completa el campo de acceso y la contrasena.")
                return
            lk = _login_lock_key(login_mode, identifier)
            if _login_is_locked(lk):
                st.error("Esta cuenta sigue bloqueada por intentos fallidos. Espera antes de volver a intentarlo.")
                return
            mode = "Email" if login_mode == "Email" else "Username"
            user = authenticate_user(mode, identifier, password)
            if user:
                _login_clear_lock(lk)
                st.session_state.user_id = user["id"]
                st.session_state.username = user["username"]
                st.success("Sesion iniciada correctamente.")
                st.rerun()
            attempts = _login_failed_increment(lk)
            if attempts >= 5:
                st.session_state.locks_dict[lk] = time.time() + LOCK_SECONDS
                st.session_state.login_failed_counts[lk] = 0
                st.error("Demasiados intentos fallidos. Esta cuenta queda bloqueada temporalmente.")
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
            ok_reg, reg_msg = create_user_with_feedback(new_username, new_email, new_password)
            if ok_reg:
                st.success("Cuenta creada. Ya puedes iniciar sesion.")
            else:
                st.error(reg_msg)

    with tab_recover:
        st.caption(
            "Obligatorio: email y nombre de usuario deben coincidir con la misma cuenta registrada."
        )
        with st.form("auth_recover_form"):
            recover_username = st.text_input("Nombre de usuario *", key="auth_recover_username")
            email = st.text_input("Email vinculado a la cuenta *", key="auth_recover_email")
            new_password = st.text_input("Nueva contrasena", type="password", key="auth_recover_password")
            submit_recover = st.form_submit_button("Actualizar contrasena")
        if submit_recover:
            ok_email, msg_email = validate_email(email)
            if not ok_email:
                st.error(msg_email)
                return
            if len(recover_username.strip()) < 1:
                st.error("Indica el nombre de usuario asociado a la cuenta.")
                return
            ok_password, password_errors = validate_password_owasp(new_password)
            if not ok_password:
                for msg in password_errors:
                    st.error(msg)
                return
            ok_rec, rec_msg = recover_password_with_feedback(email, recover_username, new_password)
            if ok_rec:
                st.success("Contrasena actualizada. Ya puedes iniciar sesion.")
            else:
                st.error(rec_msg)


def add_book_section(user_id: int) -> None:
    st.subheader("Añadir libro")
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

    nav1, nav2 = st.columns(2)
    with nav1:
        if st.button("Nueva búsqueda", key="books_reset_lookup"):
            st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
            st.rerun()
    with nav2:
        if st.button("Cancelar", key="books_cancel_flow"):
            st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
            st.rerun()

    if flow["step"] == "found":
        book = flow["existing"]
        st.info("Este titulo ya esta en el catalogo comun. Solo se añadirá a tu biblioteca.")
        if st.button("Añadir a mi biblioteca", key="books_link_existing"):
            fi, ff = initial_dates_for_estado(flow["estado"])
            linked = add_book_to_user_library(user_id, book["id"], flow["estado"], fi, ff, None)
            if linked:
                st.success("Libro añadido a tu biblioteca.")
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
        create_clicked = st.form_submit_button("Guardar libro y añadir a mi biblioteca")

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
        fi, ff = initial_dates_for_estado(flow["estado"])
        outcome, detail = add_catalog_book_and_link_user(
            user_id,
            flow["isbn10"],
            flow["isbn13"],
            title,
            author,
            genre,
            idioma,
            paginas_value,
            cover_path,
            flow["estado"],
            fi,
            ff,
        )
        if outcome == "success":
            st.success("Libro creado y añadido a tu biblioteca.")
            st.session_state.book_flow = {"step": "idle", "isbn10": None, "isbn13": None, "estado": "Pendiente"}
            st.rerun()
        elif outcome == "duplicate_library":
            st.warning(detail)
        else:
            st.error(detail)


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Aun no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galeria"], horizontal=True, key="library_view_mode")
    if view_mode != "Lista":
        _inject_gallery_css()
        cols = st.columns(4)
        for i, book in enumerate(books):
            with cols[i % 4]:
                if book["cover_path"] and os.path.exists(book["cover_path"]):
                    st.markdown(
                        _cover_gallery_html(book["cover_path"], book["title"]),
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="gallery-tile" style="height:250px;display:flex;align-items:center;'
                        'justify-content:center;border:1px dashed #888;border-radius:8px;">Sin portada</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(f'<div class="gallery-book-title">{html.escape(book["title"])}</div>', unsafe_allow_html=True)
                st.caption(f"{book['author']} · {book['estado']}")
        return

    for book in books:
        bid = book["book_id"]
        total_pags = book.get("paginas")
        tiene_paginas_totales = total_pags is not None and int(total_pags) > 0

        with st.container(border=True):
            render_book_list_row(book)
            act1, act2 = st.columns(2)
            with act1:
                if st.button("Editar metadatos", key=f"library_edit_open_{bid}"):
                    st.session_state.library_editing_id = bid
                    st.session_state.editing_book_id = None
                    st.rerun()
            with act2:
                if st.button("Gestionar estado y fechas", key=f"library_state_open_{bid}"):
                    st.session_state.editing_book_id = bid
                    st.session_state.library_editing_id = None
                    st.rerun()

            if st.session_state.library_editing_id == bid:
                idioma_idx = (
                    LANGUAGE_OPTIONS.index(book["idioma"])
                    if book["idioma"] in LANGUAGE_OPTIONS
                    else 0
                )
                with st.form(f"library_edit_meta_form_{bid}"):
                    st.caption("Los cambios actualizan la ficha del libro en el catalogo comun.")
                    etitle = st.text_input("Titulo", value=book["title"], key=f"library_edit_title_{bid}")
                    eauthor = st.text_input("Autor", value=book["author"], key=f"library_edit_author_{bid}")
                    egenre = st.text_input("Genero", value=book["genre"] or "", key=f"library_edit_genre_{bid}")
                    eidioma = st.selectbox(
                        "Idioma",
                        LANGUAGE_OPTIONS,
                        index=idioma_idx,
                        key=f"library_edit_idioma_{bid}",
                    )
                    ep_def = int(book["paginas"]) if book["paginas"] is not None else 0
                    epag = st.number_input(
                        "Paginas totales (0 = sin registrar)",
                        min_value=0,
                        value=max(ep_def, 0),
                        step=1,
                        key=f"library_edit_paginas_{bid}",
                    )
                    ecover = st.file_uploader(
                        "Nueva portada (opcional)",
                        type=["jpg", "jpeg", "png"],
                        key=f"library_edit_cover_{bid}",
                    )
                    save_meta = st.form_submit_button("Guardar ficha")
                if st.button("Cancelar", key=f"library_edit_cancel_{bid}"):
                    st.session_state.library_editing_id = None
                    st.rerun()
                if save_meta:
                    pag_val = int(epag) if epag > 0 else None
                    ref = book.get("isbn_13") or book.get("isbn_10") or str(bid)
                    cover_path_new, cover_err = save_cover_file(ref, ecover)
                    if cover_err:
                        st.error(cover_err)
                    else:
                        upd_cover = ecover is not None and cover_path_new is not None
                        ok_m, err_m = update_libro_comun_metadata(
                            user_id,
                            bid,
                            etitle,
                            eauthor,
                            egenre,
                            eidioma,
                            pag_val,
                            cover_path_new,
                            upd_cover,
                        )
                        if ok_m:
                            st.session_state.library_editing_id = None
                            st.success("Ficha actualizada.")
                            st.rerun()
                        else:
                            st.error(err_m)

            with st.expander(
                "Gestionar estado y fechas",
                expanded=st.session_state.editing_book_id == bid,
            ):
                cur = book["estado"]
                idx = READING_STATES.index(cur) if cur in READING_STATES else 0
                new_est = st.selectbox("Estado", READING_STATES, index=idx, key=f"library_estado_sel_{bid}")

                fin_bloqueada = new_est == "Leyendo"
                has_ini = st.checkbox(
                    "Registrar fecha de inicio",
                    value=bool(book["fecha_inicio"]),
                    key=f"library_use_ini_{bid}",
                )
                d_ini = parse_iso_date(book["fecha_inicio"]) or date.today()
                edit_ini = st.date_input(
                    "Fecha inicio",
                    value=d_ini,
                    key=f"library_date_ini_{bid}",
                    disabled=not has_ini,
                )
                has_fin = st.checkbox(
                    "Registrar fecha de fin",
                    value=bool(book["fecha_fin"]) and not fin_bloqueada,
                    key=f"library_use_fin_{bid}",
                    disabled=fin_bloqueada,
                )
                d_fin = parse_iso_date(book["fecha_fin"]) or date.today()
                edit_fin = st.date_input(
                    "Fecha fin",
                    value=d_fin,
                    key=f"library_date_fin_{bid}",
                    disabled=not has_fin or fin_bloqueada,
                )

                abandon_pages: Optional[int] = None
                allow_abandon_pages = tiene_paginas_totales and (
                    new_est == "Abandonado" or cur == "Abandonado"
                )
                if allow_abandon_pages:
                    abandon_pages = st.number_input(
                        "Paginas leidas (abandono)",
                        min_value=0,
                        value=int(book["paginas_leidas_abandono"] or 0),
                        step=1,
                        key=f"library_abandon_pages_{bid}",
                    )
                elif new_est == "Abandonado" or cur == "Abandonado":
                    st.info(
                        "Para registrar paginas leidas en abandono, indica antes las paginas totales del libro "
                        "en la ficha (Editar metadatos)."
                    )

                btn_save, btn_cancel = st.columns(2)
                with btn_save:
                    save_lib = st.button("Guardar cambios", key=f"library_save_{bid}")
                with btn_cancel:
                    if st.button("Cancelar", key=f"library_state_cancel_{bid}"):
                        st.session_state.editing_book_id = None
                        st.rerun()

                if save_lib:
                    fi_w = edit_ini.isoformat() if has_ini else None
                    ff_w = edit_fin.isoformat() if has_fin and not fin_bloqueada else None
                    ap_val: Optional[int] = None
                    if allow_abandon_pages:
                        ap_val = int(abandon_pages or 0)

                    if new_est != cur:
                        delta = transition_updates(
                            cur,
                            new_est,
                            book["fecha_inicio"],
                            book["fecha_fin"],
                            ap_val,
                            fi_w,
                            ff_w,
                        )
                        ok_save, err_save = update_library_row_safe(
                            user_id,
                            bid,
                            delta["estado"],
                            delta["fecha_inicio"],
                            delta["fecha_fin"],
                            delta["paginas_leidas_abandono"],
                        )
                    else:
                        pab: Optional[int]
                        if cur == "Abandonado" and tiene_paginas_totales:
                            pab = ap_val
                        elif cur == "Abandonado":
                            pab = None
                        else:
                            pab = book["paginas_leidas_abandono"]
                        ok_save, err_save = update_library_row_safe(
                            user_id, bid, cur, fi_w, ff_w, pab
                        )
                    if ok_save:
                        st.session_state.editing_book_id = None
                        st.success("Cambios guardados correctamente.")
                        st.rerun()
                    else:
                        st.error(err_save)


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

    st.markdown("**Detalle por año**")
    for y in sorted(years, reverse=True):
        with st.expander(f"Libros terminados en {y}"):
            detalle = get_finished_books_detail_for_year(user_id, y)
            if not detalle:
                st.caption("Sin titulos registrados para este año.")
            else:
                for item in detalle:
                    with st.container(border=True):
                        render_book_list_row(item)


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
        st.session_state.library_editing_id = None
        st.session_state.editing_book_id = None
        st.rerun()

    add_book_section(st.session_state.user_id)
    st.divider()
    library_view(st.session_state.user_id)
    st.divider()
    statistics_section(st.session_state.user_id)


if __name__ == "__main__":
    main()
