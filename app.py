import base64
import html
import os
import time
from datetime import date
from textwrap import dedent
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
    get_abandoned_books_detail_for_year,
    get_finished_books_detail_for_year,
    get_reading_statistics,
    get_user_library,
    init_db,
    update_libro_comun_metadata,
    update_library_row_safe,
)
from utils import (
    format_iso_date_display,
    initial_dates_for_estado,
    parse_iso_date,
    save_cover_file,
    today_iso,
    transition_updates,
    validate_isbn10,
    validate_isbn13,
)

READING_STATES = ["Pendiente", "Leyendo", "Terminado", "Abandonado", "Relectura"]
NAV_LIBRARY = "📚 Mi biblioteca"
NAV_ADD_BOOK = "✨ Añadir libro"
NAV_STATISTICS = "📊 Estadísticas"
NAV_OPTIONS = [NAV_LIBRARY, NAV_ADD_BOOK, NAV_STATISTICS]
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

def inject_app_theme() -> None:
    """Inyecta el tema visual global (HTML/CSS invisible en pantalla)."""
    st.markdown(
        dedent(
            """
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            :root {
                --text-primary: #1e3a5f;
                --text-secondary: #4a6278;
                --bg-page: #f4f1eb;
                --card-bg: #fffdf9;
                --card-border: #e8e2d6;
                --accent-bronze: #b8860b;
                --accent-gold: #c9a227;
                --accent-slate: #5c7a9a;
                --shadow-soft: 0 4px 14px rgba(30, 58, 95, 0.08);
                --shadow-hover: 0 10px 24px rgba(30, 58, 95, 0.14);
                --radius-card: 12px;
                --radius-btn: 10px;
                --bg-sidebar: #e8e4dc;
                --bg-sidebar-active: #dce4ed;
                --sidebar-active-border: #1e3a5f;
                --sidebar-hover: rgba(30, 58, 95, 0.06);
            }
            .stApp {
                background: linear-gradient(165deg, #f7f5f0 0%, #ebe6dc 45%, #f4f1eb 100%);
                color: var(--text-primary);
            }
            .stApp h1, .stApp h2, .stApp h3, [data-testid="stHeader"] {
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
                color: var(--text-primary) !important;
                letter-spacing: -0.02em;
            }
            .stApp h1 {
                font-weight: 700 !important;
                border-bottom: 2px solid var(--accent-gold);
                padding-bottom: 0.35rem;
                margin-bottom: 1.25rem !important;
            }
            .stApp h2, .stApp h3 {
                font-weight: 600 !important;
                color: var(--accent-slate) !important;
            }
            p, label, .stMarkdown div p, .stCaption,
            [data-testid="stWidgetLabel"] p,
            .stTextInput label, .stNumberInput label, .stSelectbox label,
            .stDateInput label, .stCheckbox label, .stRadio label {
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
            }
            [data-testid="stMainBlockContainer"] {
                padding-top: 1.5rem;
                padding-bottom: 2.5rem;
                max-width: 1200px;
            }
            [data-testid="stVerticalBlock"] > div:has(> [data-testid="stVerticalBlockBorderWrapper"]) {
                margin-bottom: 1rem;
            }
            [data-testid="stVerticalBlockBorderWrapper"] {
                background: var(--card-bg) !important;
                border: 1px solid var(--card-border) !important;
                border-radius: var(--radius-card) !important;
                box-shadow: var(--shadow-soft) !important;
                padding: 1.1rem 1.25rem 1.25rem !important;
                margin-bottom: 1rem !important;
                transition: box-shadow 0.25s ease, transform 0.25s ease;
            }
            [data-testid="stVerticalBlockBorderWrapper"]:hover {
                box-shadow: var(--shadow-hover) !important;
            }
            hr {
                margin: 2rem 0 !important;
                border: none !important;
                height: 1px !important;
                background: linear-gradient(90deg, transparent, rgba(184, 134, 11, 0.35) 20%, rgba(92, 122, 154, 0.35) 80%, transparent) !important;
            }
            [data-baseweb="tab-list"] {
                gap: 0.75rem !important;
                border-bottom: 2px solid var(--card-border) !important;
                padding-bottom: 0.25rem !important;
            }
            [data-baseweb="tab"] {
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
                font-size: 1.05rem !important;
                font-weight: 600 !important;
                color: var(--text-secondary) !important;
                padding: 0.65rem 1.25rem !important;
                border-radius: 8px 8px 0 0 !important;
            }
            [data-baseweb="tab"][aria-selected="true"] {
                color: var(--text-primary) !important;
                border-bottom: 3px solid var(--accent-bronze) !important;
                background: rgba(255, 253, 249, 0.85) !important;
            }
            .stButton > button {
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
                font-weight: 600 !important;
                border-radius: var(--radius-btn) !important;
                border: 1px solid var(--accent-slate) !important;
                color: var(--text-primary) !important;
                background: #fff !important;
                padding: 0.45rem 1.1rem !important;
                transition: all 0.2s ease !important;
            }
            .stButton > button:hover {
                border-color: var(--accent-bronze) !important;
                color: var(--accent-bronze) !important;
                box-shadow: var(--shadow-soft) !important;
            }
            .stButton > button[kind="primary"],
            .stFormSubmitButton > button,
            button[data-testid="baseButton-primary"] {
                background: linear-gradient(135deg, #2c4a6e 0%, #1e3a5f 100%) !important;
                color: #fffdf9 !important;
                border: none !important;
                box-shadow: 0 4px 12px rgba(30, 58, 95, 0.25) !important;
            }
            .stButton > button[kind="primary"]:hover,
            .stFormSubmitButton > button:hover {
                background: linear-gradient(135deg, #3d5f82 0%, #2c4a6e 100%) !important;
                box-shadow: var(--shadow-hover) !important;
                transform: translateY(-1px);
            }
            .gallery-tile {
                margin-bottom: 1.25rem;
                background: var(--card-bg);
                border: 1px solid var(--card-border);
                border-radius: var(--radius-card);
                box-shadow: var(--shadow-soft);
                padding: 0.75rem 0.75rem 1rem;
                transition: transform 0.28s ease, box-shadow 0.28s ease;
                cursor: default;
            }
            .gallery-tile:hover {
                transform: translateY(-4px);
                box-shadow: var(--shadow-hover);
            }
            .gallery-frame {
                height: 250px;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(180deg, #faf8f4 0%, #f0ebe3 100%);
                border-radius: 10px;
                border: 1px solid var(--card-border);
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
                margin-top: 0.55rem;
                font-size: 0.95rem;
                color: var(--text-primary);
                line-height: 1.35;
            }
            .gallery-placeholder {
                height: 250px;
                display: flex;
                align-items: center;
                justify-content: center;
                border: 1px dashed var(--accent-slate);
                border-radius: 10px;
                color: var(--text-secondary);
                font-size: 0.9rem;
                background: #faf8f4;
            }
            [data-testid="stDataFrame"] {
                border-radius: var(--radius-card);
                overflow: hidden;
                box-shadow: var(--shadow-soft);
            }
            [data-testid="stRadio"] label,
            [data-testid="stSelectbox"] label {
                color: var(--text-secondary) !important;
                font-weight: 500 !important;
            }
            .lista-cover-slot,
            .placeholder-lista {
                width: 80px;
                height: 115px;
                flex-shrink: 0;
                box-sizing: border-box;
            }
            .lista-cover-slot {
                display: flex;
                align-items: center;
                justify-content: center;
                background: #faf8f4;
                border: 1px solid var(--card-border);
                border-radius: 8px;
                overflow: hidden;
            }
            .lista-cover-img {
                width: 80px;
                height: 115px;
                object-fit: contain;
                display: block;
            }
            .placeholder-lista {
                display: flex;
                align-items: center;
                justify-content: center;
                background: #f5f0e8;
                border: 1px solid var(--card-border);
                border-radius: 8px;
                color: var(--text-secondary);
                font-family: "Inter", "Segoe UI", Roboto, sans-serif;
                font-size: 0.72rem;
                font-weight: 500;
                letter-spacing: 0.02em;
                text-align: center;
                line-height: 1.3;
                margin: 0;
            }
            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, var(--bg-sidebar) 0%, #e2ded6 100%) !important;
                border-right: 1px solid var(--card-border) !important;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
                padding: 0.25rem 0.5rem 1rem;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
                display: flex;
                flex-direction: column;
                min-height: calc(100vh - 5rem);
                padding: 1.35rem 0.85rem 1.5rem;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                gap: 0.15rem;
            }
            section[data-testid="stSidebar"] .sidebar-welcome {
                font-family: "Inter", "Segoe UI", Roboto, sans-serif;
                font-size: 1.05rem;
                font-weight: 500;
                color: var(--text-primary);
                margin: 0 0 1.35rem 0;
                line-height: 1.45;
                letter-spacing: -0.01em;
            }
            section[data-testid="stSidebar"] .sidebar-welcome strong {
                font-weight: 700;
                color: var(--accent-slate);
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] {
                margin-bottom: 0.5rem;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] {
                display: flex;
                flex-direction: column;
                gap: 0.4rem;
                width: 100%;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label {
                display: flex !important;
                align-items: center;
                width: 100%;
                margin: 0 !important;
                padding: 0.72rem 0.9rem 0.72rem 0.75rem !important;
                border-radius: 10px !important;
                border-left: 3px solid transparent !important;
                background: transparent !important;
                cursor: pointer !important;
                transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease !important;
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
                font-size: 0.95rem !important;
                font-weight: 500 !important;
                color: var(--text-primary) !important;
                box-sizing: border-box;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:hover {
                background: var(--sidebar-hover) !important;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label:has(input:checked) {
                background: var(--bg-sidebar-active) !important;
                border-left-color: var(--sidebar-active-border) !important;
                box-shadow: inset 0 0 0 1px rgba(30, 58, 95, 0.08) !important;
                font-weight: 600 !important;
                color: var(--text-primary) !important;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
                position: absolute !important;
                opacity: 0 !important;
                width: 0 !important;
                height: 0 !important;
                margin: 0 !important;
                pointer-events: none !important;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] [data-baseweb="radio"] {
                display: none !important;
            }
            section[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"] > label > div:first-child {
                display: none !important;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]:last-child {
                margin-top: auto !important;
                padding-top: 1.75rem !important;
                border-top: 1px solid rgba(30, 58, 95, 0.12);
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]:last-child .stButton > button {
                width: 100%;
                font-family: "Inter", "Segoe UI", Roboto, sans-serif !important;
                font-weight: 600 !important;
                font-size: 0.9rem !important;
                padding: 0.55rem 1rem !important;
                border-radius: var(--radius-btn) !important;
                border: 1px solid var(--card-border) !important;
                background: var(--card-bg) !important;
                color: var(--text-secondary) !important;
                box-shadow: var(--shadow-soft) !important;
            }
            section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"]:last-child .stButton > button:hover {
                color: var(--text-primary) !important;
                border-color: var(--accent-slate) !important;
                background: #fffdf9 !important;
            }
            </style>
            """
        ).strip(),
        unsafe_allow_html=True,
    )



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




def _list_cover_placeholder_html() -> str:
    return '<div class="placeholder-lista">Sin portada</div>'


def _list_cover_image_html(cover_path: str, alt: str) -> str:
    safe_alt = html.escape(alt)
    with open(cover_path, "rb") as f:
        b64 = base64.standard_b64encode(f.read()).decode("ascii")
    ext = cover_path.lower().rsplit(".", 1)[-1]
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return (
        f'<div class="lista-cover-slot">'
        f'<img src="data:{mime};base64,{b64}" alt="{safe_alt}" class="lista-cover-img" />'
        f"</div>"
    )


def render_book_list_row(book: dict[str, Any]) -> None:
    """Fila compacta reutilizada en vista Lista y detalle de estadísticas."""
    total_pags = book.get("paginas")
    tiene_paginas = total_pags is not None and int(total_pags) > 0
    ptxt = f"{int(total_pags)} pág." if tiene_paginas else "Páginas: —"
    idioma = book.get("idioma") or "—"
    estado = book.get("estado") or "—"
    col_cover, col_info = st.columns([0.15, 0.85], vertical_alignment="center")
    with col_cover:
        cover = book.get("cover_path")
        if cover and os.path.exists(cover):
            st.markdown(_list_cover_image_html(cover, book["title"]), unsafe_allow_html=True)
        else:
            st.markdown(_list_cover_placeholder_html(), unsafe_allow_html=True)
    with col_info:
        meta = f"{book['author']} · {idioma} · {ptxt} · *{estado}*"
        if book.get("fecha_inicio"):
            meta += f" · Inicio: {format_iso_date_display(book['fecha_inicio'])}"
        if book.get("fecha_fin"):
            meta += f" · Fin: {format_iso_date_display(book['fecha_fin'])}"
        st.markdown(f"**{book['title']}**  \n{meta}")


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
    if "editing_book_id" not in st.session_state:
        st.session_state.editing_book_id = None
    if "managing_status_book_id" not in st.session_state:
        st.session_state.managing_status_book_id = None


def login_register_view() -> None:
    col_izq, col_centro, col_der = st.columns([1, 2, 1])
    with col_centro:
        st.title("Mi Estanteria Digital")
        tab_login, tab_register, tab_recover = st.tabs(
            ["Iniciar sesion", "Registro", "Recuperar contrasena"]
        )

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
                st.warning(
                    f"Cuenta bloqueada temporalmente. Vuelve a intentarlo en {max(wait, 0)} segundos."
                )

            label_ident = "Email" if login_mode == "Email" else "Nombre de usuario"
            with st.form("auth_login_form"):
                identifier = st.text_input(label_ident, key="auth_login_identifier")
                password = st.text_input("Contrasena", type="password", key="auth_login_password")
                submit = st.form_submit_button("Entrar", use_container_width=True)
            if submit:
                if not identifier.strip() or not password:
                    st.error("Completa el campo de acceso y la contrasena.")
                    return
                lk = _login_lock_key(login_mode, identifier)
                if _login_is_locked(lk):
                    st.error(
                        "Esta cuenta sigue bloqueada por intentos fallidos. "
                        "Espera antes de volver a intentarlo."
                    )
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
                    st.error(
                        "Demasiados intentos fallidos. Esta cuenta queda bloqueada temporalmente."
                    )
                else:
                    st.error(
                        f"Credenciales incorrectas. Te quedan {5 - attempts} intentos antes del bloqueo."
                    )

        with tab_register:
            with st.form("auth_register_form"):
                new_username = st.text_input("Usuario", key="auth_register_username")
                new_email = st.text_input("Email", key="auth_register_email")
                new_password = st.text_input("Contrasena", type="password", key="auth_register_password")
                submit_register = st.form_submit_button("Crear cuenta", use_container_width=True)
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
                submit_recover = st.form_submit_button("Actualizar contrasena", use_container_width=True)
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


def _render_status_management_panel(user_id: int, book: dict[str, Any]) -> None:
    """Panel reactivo de estado/fechas inline debajo de la tarjeta del libro."""
    bid = book["book_id"]
    cur = book["estado"]
    total_pags = book.get("paginas")
    tiene_paginas_totales = total_pags is not None and int(total_pags) > 0
    idx = READING_STATES.index(cur) if cur in READING_STATES else 0

    est_key = f"library_estado_sel_{bid}"
    prev_key = f"library_status_prev_est_{bid}"
    ini_chk_key = f"library_use_ini_{bid}"
    fin_chk_key = f"library_use_fin_{bid}"
    ini_date_key = f"library_date_ini_{bid}"
    fin_date_key = f"library_date_fin_{bid}"

    prev_est = st.session_state.get(prev_key, cur)

    st.markdown(f"### Gestionar estado y fechas — **{book['title']}**")
    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            new_est = st.selectbox("Estado", READING_STATES, index=idx, key=est_key)
        fin_bloqueada = new_est == "Leyendo"
        allow_abandon_pages = tiene_paginas_totales and (
            new_est == "Abandonado" or cur == "Abandonado"
        )
        abandon_pages: Optional[int] = None
        with col2:
            if allow_abandon_pages:
                abandon_pages = st.number_input(
                    "Paginas leidas",
                    min_value=0,
                    value=int(book["paginas_leidas_abandono"] or 0),
                    step=1,
                    key=f"library_abandon_pages_{bid}",
                )

        if new_est == "Leyendo" and prev_est == "Pendiente":
            st.session_state[ini_chk_key] = True
            st.session_state[ini_date_key] = date.today()
        if new_est == "Terminado" and prev_est != "Terminado":
            st.session_state[fin_chk_key] = True
            st.session_state[fin_date_key] = date.today()
        if fin_bloqueada:
            st.session_state[fin_chk_key] = False

        if ini_chk_key not in st.session_state:
            st.session_state[ini_chk_key] = bool(book["fecha_inicio"])
        if fin_chk_key not in st.session_state:
            st.session_state[fin_chk_key] = bool(book["fecha_fin"]) and not fin_bloqueada
        if ini_date_key not in st.session_state:
            st.session_state[ini_date_key] = parse_iso_date(book["fecha_inicio"]) or date.today()
        if fin_date_key not in st.session_state:
            st.session_state[fin_date_key] = parse_iso_date(book["fecha_fin"]) or date.today()

        col_d1, col_d2, col_d3 = st.columns([2, 2, 1])
        with col_d1:
            has_ini = st.checkbox("Registrar fecha inicio", key=ini_chk_key)
            edit_ini = st.date_input(
                "Fecha inicio",
                key=ini_date_key,
                format="DD/MM/YYYY",
                disabled=not has_ini,
            )
        with col_d2:
            has_fin = st.checkbox(
                "Registrar fecha fin",
                key=fin_chk_key,
                disabled=fin_bloqueada,
            )
            edit_fin = st.date_input(
                "Fecha fin",
                key=fin_date_key,
                format="DD/MM/YYYY",
                disabled=not has_fin or fin_bloqueada,
            )

        if (new_est == "Abandonado" or cur == "Abandonado") and not allow_abandon_pages:
            st.info(
                "Para registrar paginas leidas en abandono, indica antes las paginas totales del libro "
                "en la ficha (Editar metadatos)."
            )

        _, btn_guardar, btn_cancelar = st.columns([2, 2, 1])
        with btn_guardar:
            save_clicked = st.button("Guardar Cambios", key=f"library_status_save_{bid}", use_container_width=True)
        with btn_cancelar:
            cancel_clicked = st.button("Cancelar", key=f"library_status_cancel_{bid}", use_container_width=True)

        st.session_state[prev_key] = new_est

    if cancel_clicked:
        for k in (prev_key, ini_chk_key, fin_chk_key, ini_date_key, fin_date_key):
            st.session_state.pop(k, None)
        st.session_state.managing_status_book_id = None
        st.rerun()

    if save_clicked:
        has_ini = st.session_state.get(ini_chk_key, False)
        has_fin = st.session_state.get(fin_chk_key, False)
        edit_ini = st.session_state.get(ini_date_key, date.today())
        edit_fin = st.session_state.get(fin_date_key, date.today())

        fi_w = edit_ini.isoformat() if has_ini else None
        if new_est == "Terminado":
            has_fin = True
            ff_w = edit_fin.isoformat() if isinstance(edit_fin, date) else today_iso()
        else:
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
            ok_save, err_save = update_library_row_safe(user_id, bid, cur, fi_w, ff_w, pab)

        if ok_save:
            for k in (prev_key, ini_chk_key, fin_chk_key, ini_date_key, fin_date_key):
                st.session_state.pop(k, None)
            st.session_state.managing_status_book_id = None
            st.success("Cambios guardados correctamente.")
            st.rerun()
        st.error(err_save)


def _render_metadata_edit_panel(user_id: int, b: dict[str, Any]) -> None:
    """Formulario inline de metadatos (Lista y Galeria)."""
    bid = b["book_id"]
    with st.container(border=True):
        idioma_idx = (
            LANGUAGE_OPTIONS.index(b["idioma"])
            if b["idioma"] in LANGUAGE_OPTIONS
            else 0
        )
        st.markdown("**Editar metadatos**")
        save_meta = False
        cancel_meta = False
        with st.form(f"library_edit_meta_form_{bid}"):
            st.caption("Los cambios actualizan la ficha del libro en el catalogo comun.")
            etitle = st.text_input("Titulo", value=b["title"], key=f"library_edit_title_{bid}")
            eauthor = st.text_input("Autor", value=b["author"], key=f"library_edit_author_{bid}")
            egenre = st.text_input("Genero", value=b["genre"] or "", key=f"library_edit_genre_{bid}")
            eidioma = st.selectbox(
                "Idioma",
                LANGUAGE_OPTIONS,
                index=idioma_idx,
                key=f"library_edit_idioma_{bid}",
            )
            ep_def = int(b["paginas"]) if b["paginas"] is not None else 0
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
            _, btn_guardar, btn_cancelar = st.columns([2, 2, 1])
            with btn_guardar:
                save_meta = st.form_submit_button("Guardar ficha", use_container_width=True)
            with btn_cancelar:
                cancel_meta = st.form_submit_button("Cancelar", use_container_width=True)
        if cancel_meta:
            st.session_state.editing_book_id = None
            st.rerun()
        if save_meta:
            pag_val = int(epag) if epag > 0 else None
            ref = b.get("isbn_13") or b.get("isbn_10") or str(bid)
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
                    st.session_state.editing_book_id = None
                    st.success("Ficha actualizada.")
                    st.rerun()
                else:
                    st.error(err_m)


def _open_status_management_panel(b: dict[str, Any]) -> None:
    """Inicializa estado de sesion al abrir gestion de estado (Lista o Galeria)."""
    bid = b["book_id"]
    st.session_state.managing_status_book_id = bid
    st.session_state.editing_book_id = None
    st.session_state[f"library_status_prev_est_{bid}"] = b["estado"]
    for _k in (
        f"library_use_ini_{bid}",
        f"library_use_fin_{bid}",
        f"library_date_ini_{bid}",
        f"library_date_fin_{bid}",
    ):
        st.session_state.pop(_k, None)


def _render_gallery_book_tile(book: dict[str, Any]) -> None:
    """Tarjeta de portada para la vista Galeria dentro de un expander por estado."""
    bid = book["book_id"]
    if book["cover_path"] and os.path.exists(book["cover_path"]):
        st.markdown(
            _cover_gallery_html(book["cover_path"], book["title"]),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="gallery-tile">'
            '<div class="gallery-placeholder">Sin portada</div>'
            f'<div class="gallery-book-title">{html.escape(book["title"])}</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    st.caption(f"{book['author']} · {book.get('estado') or '—'}")
    if st.button("Editar metadatos", key=f"gallery_edit_open_{bid}", use_container_width=True):
        st.session_state.editing_book_id = bid
        st.session_state.managing_status_book_id = None
        st.rerun()
    if st.button(
        "Gestionar estado y fechas",
        key=f"gallery_state_open_{bid}",
        use_container_width=True,
    ):
        _open_status_management_panel(book)
        st.rerun()


def _render_gallery_group_panels(user_id: int, group: list[dict[str, Any]]) -> None:
    """Paneles inline de edicion/estado debajo de la cuadricula de un grupo."""
    for b in group:
        bid = b["book_id"]
        if st.session_state.editing_book_id == bid:
            _render_metadata_edit_panel(user_id, b)
        if st.session_state.managing_status_book_id == bid:
            _render_status_management_panel(user_id, b)


def library_view(user_id: int) -> None:
    st.subheader("Mi biblioteca")
    books = get_user_library(user_id)
    if not books:
        st.info("Aun no tienes libros en tu biblioteca.")
        return

    view_mode = st.radio("Vista", ["Lista", "Galeria"], horizontal=True, key="library_view_mode")

    def _render_list_book_card(b: dict[str, Any]) -> None:
        bid = b["book_id"]
        with st.container(border=True):
            render_book_list_row(b)
            act1, act2 = st.columns(2)
            with act1:
                if st.button("Editar metadatos", key=f"library_edit_open_{bid}"):
                    st.session_state.editing_book_id = bid
                    st.session_state.managing_status_book_id = None
                    st.rerun()
            with act2:
                if st.button("Gestionar estado y fechas", key=f"library_state_open_{bid}"):
                    _open_status_management_panel(b)
                    st.rerun()

        if st.session_state.editing_book_id == b["book_id"]:
            _render_metadata_edit_panel(user_id, b)

        if st.session_state.managing_status_book_id == b["book_id"]:
            _render_status_management_panel(user_id, b)

    for estado in READING_STATES:
        group = [b for b in books if (b.get("estado") or "Pendiente") == estado]
        with st.expander(f"{estado} ({len(group)})", expanded=False):
            if not group:
                st.caption("No hay titulos en esta seccion.")
                continue
            if view_mode == "Lista":
                for b in group:
                    _render_list_book_card(b)
            else:
                cols = st.columns(4)
                for i, b in enumerate(group):
                    with cols[i % 4]:
                        _render_gallery_book_tile(b)
                _render_gallery_group_panels(user_id, group)


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

        with st.expander(f"Libros abandonados en {y}"):
            detalle_abandonados = get_abandoned_books_detail_for_year(user_id, y)
            if not detalle_abandonados:
                st.caption("Sin títulos abandonados para este año.")
            else:
                for item in detalle_abandonados:
                    with st.container(border=True):
                        render_book_list_row(item)


def main() -> None:
    st.set_page_config(
        page_title="Mi Estanteria Digital",
        page_icon="📚",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_app_theme()
    init_db()
    init_session_state()
    if st.session_state.user_id is None:
        login_register_view()
        return

    user_id = st.session_state.user_id
    username = st.session_state.username or "usuario"

    with st.sidebar:
        st.markdown(
            f'<p class="sidebar-welcome">Bienvenido, <strong>{html.escape(username)}</strong></p>',
            unsafe_allow_html=True,
        )
        section = st.radio(
            "",
            NAV_OPTIONS,
            key="main_nav_section",
            label_visibility="collapsed",
        )
        if st.button("Cerrar sesion", key="layout_logout_button"):
            st.session_state.user_id = None
            st.session_state.username = None
            st.session_state.editing_book_id = None
            st.session_state.managing_status_book_id = None
            st.rerun()

    st.title("Mi Estanteria Digital")
    if section == NAV_LIBRARY:
        library_view(user_id)
    elif section == NAV_ADD_BOOK:
        add_book_section(user_id)
    else:
        statistics_section(user_id)


if __name__ == "__main__":
    main()
