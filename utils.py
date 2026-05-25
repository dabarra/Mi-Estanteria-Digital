import os
import re
import uuid
from datetime import date, datetime, timezone
from io import BytesIO
from typing import Any, Optional

from PIL import Image, UnidentifiedImageError


def today_iso() -> str:
    return date.today().isoformat()


def parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def initial_dates_for_estado(estado: str) -> tuple[Optional[str], Optional[str]]:
    """Fechas sugeridas al dar de alta un libro; solo Terminado fija inicio y fin por defecto."""
    t = today_iso()
    if estado == "Terminado":
        return t, t
    return None, None


def transition_updates(
    old: str,
    new: str,
    cur_fi: Optional[str],
    cur_ff: Optional[str],
    abandon_pages: Optional[int],
    fi_input: Optional[str],
    ff_input: Optional[str],
) -> dict[str, Any]:
    """
    Calcula estado y fechas tras un cambio de estado de lectura.

    fi_input / ff_input: fechas ISO desde el formulario; None indica que el usuario
    dejó la fecha vacía (sin registrar). Leyendo fuerza siempre fecha_fin nula.
    """
    out: dict[str, Any] = {"estado": new}
    fi, ff = cur_fi, cur_ff

    if new == "Relectura":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Leyendo":
        out["fecha_inicio"] = fi_input if fi_input is not None else (fi if old == "Leyendo" else None)
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Terminado":
        out["fecha_inicio"] = fi_input if fi_input is not None else fi
        out["fecha_fin"] = ff_input if ff_input is not None else ff
        out["paginas_leidas_abandono"] = None
        return out
    if new == "Abandonado":
        out["fecha_inicio"] = fi_input if fi_input is not None else fi
        out["fecha_fin"] = ff_input if ff_input is not None else ff
        out["paginas_leidas_abandono"] = abandon_pages
        return out
    if new == "Pendiente":
        out["fecha_inicio"] = None
        out["fecha_fin"] = None
        out["paginas_leidas_abandono"] = None
        return out
    out["fecha_inicio"] = fi_input if fi_input is not None else fi
    out["fecha_fin"] = ff_input if ff_input is not None else ff
    out["paginas_leidas_abandono"] = None
    return out


COVERS_DIR = "portadas"
MAX_COVER_SIZE_BYTES = 2 * 1024 * 1024


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
            filename = f"{safe_ref}_{int(datetime.now(timezone.utc).timestamp())}_{uuid.uuid4().hex[:8]}{ext}"
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
