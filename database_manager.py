import os
import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Optional

import bcrypt

from utils import COVERS_DIR, normalize_isbn

DB_PATH = "biblioteca.db"


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


_SEED_FINISHED_DATE = "2026-02-15"
_SEED_STARTED_DATE = "2025-11-01"

_SEED_CATALOG: list[dict[str, Any]] = [
    {
        "title": "O último barco",
        "author": "Domingo Villar",
        "isbn_13": "9788417624279",
        "isbn_10": "8417624276",
        "paginas": 712,
        "genre": "Novela negra",
        "idioma": "Gallego",
        "cover_path": "portadas/o_ultimo_barco.jpg",
        "estado": "Leyendo",
        "fecha_inicio": None,
        "fecha_fin": None,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Os dous de sempre",
        "author": "Castelao",
        "isbn_13": "9788498658125",
        "isbn_10": "8498658126",
        "paginas": 252,
        "genre": "Narrativa",
        "idioma": "Gallego",
        "cover_path": "portadas/os_dous_de_sempre.jpg",
        "estado": "Leyendo",
        "fecha_inicio": None,
        "fecha_fin": None,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Si el mar no regresa",
        "author": "Sara Búho",
        "isbn_13": "9791387761639",
        "isbn_10": None,
        "paginas": 224,
        "genre": "Poesia",
        "idioma": "Espanol",
        "cover_path": "portadas/si_el_mar_no_regresa.jpg",
        "estado": "Terminado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": _SEED_FINISHED_DATE,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "La península de las casas vacías",
        "author": "David Uclés",
        "isbn_13": "9788419942319",
        "isbn_10": "8419942313",
        "paginas": 700,
        "genre": "Narrativa histórica",
        "idioma": "Espanol",
        "cover_path": "portadas/la_peninsula_de_las_casas_vacias.jpg",
        "estado": "Terminado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": _SEED_FINISHED_DATE,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Lo inesperado",
        "author": "Pedro Simón",
        "isbn_13": "9788467082159",
        "isbn_10": "8467082159",
        "paginas": 360,
        "genre": "Novela contemporánea",
        "idioma": "Espanol",
        "cover_path": "portadas/lo_inesperado.jpg",
        "estado": "Terminado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": _SEED_FINISHED_DATE,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Me crie como un fascista",
        "author": "Antonio Maestre",
        "isbn_13": "9788432249662",
        "isbn_10": "843224966X",
        "paginas": 240,
        "genre": "Ensayo",
        "idioma": "Espanol",
        "cover_path": "portadas/me_crie_como_un_fascista.jpg",
        "estado": "Terminado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": _SEED_FINISHED_DATE,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "La amiga estupenda",
        "author": "Elena Ferrante",
        "isbn_13": "9788426420787",
        "isbn_10": "8426420788",
        "paginas": 392,
        "genre": "Novela literaria",
        "idioma": "Espanol",
        "cover_path": "portadas/la_amiga_estupenda.jpg",
        "estado": "Terminado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": _SEED_FINISHED_DATE,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Lluvia fina",
        "author": "Luis Landero",
        "isbn_13": "9788490666562",
        "isbn_10": "8490666562",
        "paginas": 272,
        "genre": "Narrativa",
        "idioma": "Espanol",
        "cover_path": "portadas/lluvia_fina.jpg",
        "estado": "Pendiente",
        "fecha_inicio": None,
        "fecha_fin": None,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Más allá del mapa",
        "author": "Amarna Miller",
        "isbn_13": "9788402424563",
        "isbn_10": "8402424562",
        "paginas": 288,
        "genre": "Viajes y Crónica",
        "idioma": "Espanol",
        "cover_path": "portadas/mas_alla_del_mapa.jpg",
        "estado": "Pendiente",
        "fecha_inicio": None,
        "fecha_fin": None,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "Rayuela",
        "author": "Julio Cortázar",
        "isbn_13": "9788437624747",
        "isbn_10": "843762474X",
        "paginas": 756,
        "genre": "Clásico contemporáneo",
        "idioma": "Espanol",
        "cover_path": "portadas/rayuela.jpg",
        "estado": "Pendiente",
        "fecha_inicio": None,
        "fecha_fin": None,
        "paginas_leidas_abandono": None,
    },
    {
        "title": "La diva",
        "author": "Reyes Monforte",
        "isbn_13": "9788401035784",
        "isbn_10": "8401035787",
        "paginas": 568,
        "genre": "Novela histórica",
        "idioma": "Espanol",
        "cover_path": "portadas/la_diva.jpg",
        "estado": "Abandonado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": "2026-01-20",
        "paginas_leidas_abandono": 120,
    },
    {
        "title": "En defense de la memoria",
        "author": "Elvira Sastre",
        "isbn_13": "9788410190849",
        "isbn_10": "841019084X",
        "paginas": 184,
        "genre": "Poesía",
        "idioma": "Espanol",
        "cover_path": "portadas/en_defensa_de_la_memoria.jpg",
        "estado": "Abandonado",
        "fecha_inicio": _SEED_STARTED_DATE,
        "fecha_fin": "2026-03-10",
        "paginas_leidas_abandono": 50,
    },
]


def _seed_evaluator_data(conn: sqlite3.Connection) -> None:
    """Carga usuario de prueba, catálogo y biblioteca si la BD está vacía o sin vincular."""
    now = datetime.now(timezone.utc).isoformat()
    today = date.today().isoformat()

    profesor_row = conn.execute(
        "SELECT id FROM usuarios WHERE username = ?",
        ("profesor",),
    ).fetchone()
    if profesor_row is not None:
        return

    password_bytes = "Profesor2026*".encode("utf-8")
    salt = bcrypt.gensalt()
    token_hash = bcrypt.hashpw(password_bytes, salt).decode("utf-8")
    conn.execute(
        """
        INSERT INTO usuarios (username, email, password, created_at)
        VALUES (?, ?, ?, ?)
        """,
        ("profesor", "profesor@tfm.com", token_hash, now),
    )

    catalog_count = conn.execute("SELECT COUNT(*) AS c FROM libros_comunes").fetchone()["c"]
    if catalog_count == 0:
        for book in _SEED_CATALOG:
            conn.execute(
                """
                INSERT INTO libros_comunes (
                    isbn_10, isbn_13, title, author, genre, idioma, paginas, cover_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book["isbn_10"],
                    book["isbn_13"],
                    book["title"],
                    book["author"],
                    book["genre"],
                    book["idioma"],
                    book["paginas"],
                    book["cover_path"],
                    now,
                ),
            )

    profesor_row = conn.execute(
        "SELECT id FROM usuarios WHERE username = ?",
        ("profesor",),
    ).fetchone()
    if profesor_row is None:
        return
    user_id = int(profesor_row["id"])

    library_count = conn.execute(
        "SELECT COUNT(*) AS c FROM biblioteca_usuario WHERE user_id = ?",
        (user_id,),
    ).fetchone()["c"]
    if library_count > 0:
        return

    for book in _SEED_CATALOG:
        isbn13 = book["isbn_13"]
        isbn10 = book["isbn_10"]
        if isbn13 and isbn10:
            row = conn.execute(
                "SELECT id FROM libros_comunes WHERE isbn_13 = ? OR isbn_10 = ? LIMIT 1",
                (isbn13, isbn10),
            ).fetchone()
        elif isbn13:
            row = conn.execute(
                "SELECT id FROM libros_comunes WHERE isbn_13 = ? LIMIT 1",
                (isbn13,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM libros_comunes WHERE isbn_10 = ? LIMIT 1",
                (isbn10,),
            ).fetchone()
        if row is None:
            continue

        estado = book["estado"]
        fecha_inicio = book["fecha_inicio"]
        fecha_fin = book["fecha_fin"]
        if estado == "Leyendo":
            fecha_inicio = today
            fecha_fin = None
        paginas_abandono = book["paginas_leidas_abandono"]
        if estado != "Abandonado":
            paginas_abandono = None

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
                int(row["id"]),
                estado,
                fecha_inicio,
                fecha_fin,
                paginas_abandono,
                now,
            ),
        )


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
        _seed_evaluator_data(conn)
        conn.commit()


def create_user_record(username: str, email: str, password_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO usuarios (username, email, password, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (username.strip(), email.strip().lower(), password_hash, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_user_by_username(username: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, email, password FROM usuarios WHERE username = ?",
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_email(email: str) -> Optional[dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, email, password FROM usuarios WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_email_and_username(email: str, username: str) -> Optional[dict[str, Any]]:
    """Devuelve el usuario solo si email y username pertenecen a la misma fila."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, username, email, password
            FROM usuarios
            WHERE email = ? AND username = ?
            """,
            (email.strip().lower(), username.strip()),
        ).fetchone()
    return dict(row) if row else None


def update_user_password_by_email(email: str, password_hash: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM usuarios WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "UPDATE usuarios SET password = ? WHERE id = ?",
            (password_hash, row["id"]),
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
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        return cursor.lastrowid


def add_book_to_user_library(
    user_id: int,
    book_id: int,
    estado: str,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    paginas_abandono: Optional[int],
) -> bool:
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
                    fecha_inicio,
                    fecha_fin,
                    paginas_abandono if estado == "Abandonado" else None,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


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


def add_catalog_book_and_link_user(
    user_id: int,
    isbn10: Optional[str],
    isbn13: Optional[str],
    title: str,
    author: str,
    genre: str,
    idioma: str,
    paginas: Optional[int],
    cover_path: Optional[str],
    estado: str,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
) -> tuple[str, str]:
    """
    Crea fila en libros_comunes si no existe y vincula a biblioteca_usuario.
    Retorna ("success", ""), ("duplicate_library", mensaje) o ("error", mensaje).
    """
    try:
        exists = find_book_by_isbn(isbn10, isbn13)
        if exists:
            book_id = exists["id"]
        else:
            book_id = insert_libro_comun(
                isbn10, isbn13, title, author, genre, idioma, paginas, cover_path
            )
        linked = add_book_to_user_library(
            user_id, book_id, estado, fecha_inicio, fecha_fin, None
        )
        if linked:
            return "success", ""
        return "duplicate_library", "El libro ya estaba vinculado a tu biblioteca."
    except (sqlite3.IntegrityError, ValueError):
        return "error", "Conflicto de ISBN o datos invalidos. Vuelve a buscar antes de guardar."
    except sqlite3.Error as err:
        return "error", f"Error al guardar en el catalogo: {err}"


def update_library_row_safe(
    user_id: int,
    book_id: int,
    estado: str,
    fecha_inicio: Optional[str],
    fecha_fin: Optional[str],
    paginas_abandono: Optional[int],
) -> tuple[bool, str]:
    if estado == "Terminado" and (not fecha_fin or not str(fecha_fin).strip()):
        fecha_fin = date.today().isoformat()
    try:
        update_biblioteca_row(
            user_id, book_id, estado, fecha_inicio, fecha_fin, paginas_abandono
        )
        return True, ""
    except sqlite3.Error as err:
        return False, f"No se pudo guardar en la base de datos: {err}"


def user_owns_book(user_id: int, book_id: int) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM biblioteca_usuario
            WHERE user_id = ? AND book_id = ?
            LIMIT 1
            """,
            (user_id, book_id),
        ).fetchone()
    return row is not None


def update_libro_comun_metadata(
    user_id: int,
    book_id: int,
    title: str,
    author: str,
    genre: str,
    idioma: str,
    paginas: Optional[int],
    cover_path: Optional[str],
    update_cover: bool,
) -> tuple[bool, str]:
    """
    Actualiza metadatos del catalogo comun solo si el libro esta en la biblioteca del usuario.
    Si update_cover es False, no modifica cover_path.
    """
    if not user_owns_book(user_id, book_id):
        return False, "No se encontro el libro en tu biblioteca."
    try:
        with get_connection() as conn:
            if update_cover and cover_path is not None:
                conn.execute(
                    """
                    UPDATE libros_comunes
                    SET title = ?, author = ?, genre = ?, idioma = ?, paginas = ?, cover_path = ?
                    WHERE id = ?
                    """,
                    (
                        title.strip(),
                        author.strip(),
                        genre.strip() or "Sin especificar",
                        idioma,
                        paginas,
                        cover_path,
                        book_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE libros_comunes
                    SET title = ?, author = ?, genre = ?, idioma = ?, paginas = ?
                    WHERE id = ?
                    """,
                    (
                        title.strip(),
                        author.strip(),
                        genre.strip() or "Sin especificar",
                        idioma,
                        paginas,
                        book_id,
                    ),
                )
            conn.commit()
        return True, ""
    except sqlite3.Error as err:
        return False, f"Error al actualizar el libro: {err}"


def get_finished_books_detail_for_year(user_id: int, year: str) -> list[dict[str, Any]]:
    """Libros terminados en un año (mismos campos visuales que la vista Lista)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                b.id AS book_id,
                b.title,
                b.author,
                b.idioma,
                b.paginas,
                b.cover_path,
                bu.estado,
                bu.fecha_fin
            FROM biblioteca_usuario bu
            JOIN libros_comunes b ON b.id = bu.book_id
            WHERE bu.user_id = ?
              AND bu.estado = 'Terminado'
              AND bu.fecha_fin IS NOT NULL AND bu.fecha_fin != ''
              AND strftime('%Y', bu.fecha_fin) = ?
            ORDER BY bu.fecha_fin
            """,
            (user_id, year),
        ).fetchall()
    return [dict(r) for r in rows]


def get_abandoned_books_detail_for_year(user_id: int, year: str) -> list[dict[str, Any]]:
    """Libros abandonados en un año (mismos campos visuales que la vista Lista)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                b.id AS book_id,
                b.title,
                b.author,
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
              AND bu.estado = 'Abandonado'
              AND bu.fecha_fin IS NOT NULL AND bu.fecha_fin != ''
              AND strftime('%Y', bu.fecha_fin) = ?
            ORDER BY bu.fecha_fin
            """,
            (user_id, year),
        ).fetchall()
    return [dict(r) for r in rows]
