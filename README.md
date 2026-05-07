# Mi estantería digital — TFM

## a. Descripción general del proyecto

Aplicación web tipo red social de lectura (inspirada en Goodreads) para gestionar una biblioteca personal: catálogo común de libros identificados por ISBN, biblioteca por usuario con estados de lectura, portadas, fechas de lectura y estadísticas anuales. Cada usuario solo accede a sus propios datos; el acceso está protegido con autenticación, bloqueo tras intentos fallidos y recuperación de contraseña.

## b. Stack tecnológico utilizado

- **Lenguaje:** Python 3.12
- **Interfaz:** Streamlit
- **Base de datos:** SQLite
- **Seguridad de contraseñas:** passlib con esquema bcrypt (dependencia directa `bcrypt`)
- **Imágenes:** Pillow (validación de contenido, límites de tamaño, saneado de rutas)
- **Datos tabulares (estadísticas):** Pandas (declarado en dependencias)
- **Control de versiones:** Git

## c. Instalación y ejecución

1. Clonar el repositorio.
2. Crear y activar un entorno virtual: `python -m venv venv` y `source venv/bin/activate` (Linux/macOS) o `venv\Scripts\activate` (Windows).
3. Instalar dependencias: `pip install -r requirements.txt`
4. Ejecutar la aplicación: `streamlit run app.py`

La base de datos `biblioteca.db` se crea en la raíz del proyecto al iniciar la aplicación. Las portadas válidas se guardan en la carpeta `portadas/`. Si migras desde un esquema muy antiguo y aparecen errores de esquema, puede ser necesario eliminar `biblioteca.db` y volver a generarla.

## d. Estructura del proyecto (arquitectura modular)

- **`app.py`** — Capa de interfaz y sesión Streamlit: formularios, navegación, mensajes al usuario y orquestación de llamadas a los demás módulos. Sin consultas SQL directas ni manejo de excepciones de SQLite.
- **`database_manager.py`** — SQLite: conexión, migraciones, CRUD de usuarios, libros comunes, biblioteca por usuario, estadísticas y operaciones combinadas con manejo de errores (`add_catalog_book_and_link_user`, `update_library_row_safe`).
- **`auth_manager.py`** — Autenticación: hashing con passlib/bcrypt, validación de email y contraseña alineada con criterios OWASP, login por nombre de usuario o email, recuperación de contraseña y registro con feedback ante conflictos de base de datos (`create_user_with_feedback`, `recover_password_with_feedback`).
- **`utils.py`** — Utilidades transversales: normalización y validación de ISBN-10/ISBN-13, fechas y transiciones de estado de lectura (`transition_updates`, `initial_dates_for_estado`, etc.), y guardado seguro de portadas (verificación real del binario con Pillow, tope de 2 MB, nombres saneados, reducción de metadatos al regrabar).
- **`requirements.txt`** — Dependencias del proyecto.
- **`README.md`** — Esta documentación.
- **`biblioteca.db`** — Base de datos (generada al ejecutar la app).
- **`portadas/`** — Directorio de imágenes de portada (generado al usar la funcionalidad de subida).

## e. Funcionalidades principales

- **Usuarios:** registro con email validado, contraseña con requisitos OWASP, inicio de sesión indistinto por **nombre de usuario** o **email**, bloqueo temporal tras 5 intentos fallidos y flujo de recuperación de contraseña por email.
- **Catálogo común e ISBN:** los libros se identifican por ISBN; validación algorítmica de ISBN-10 e ISBN-13 (ignorando guiones y espacios); al menos un ISBN obligatorio para dar de alta o vincular un libro.
- **Biblioteca personal:** estados Pendiente, Leyendo, Terminado, Abandonado y Relectura; actualización automática de `fecha_inicio`, `fecha_fin` y páginas leídas en abandono según transiciones definidas en `transition_updates`; en abandono se pueden registrar páginas leídas.
- **Estadísticas anuales:** libros terminados por año, páginas asociadas a lecturas terminadas y páginas declaradas en abandonos, agregadas en una tabla resumen.
- **Galería:** vista en cuadrícula de portadas de la biblioteca del usuario.
- **Seguridad OWASP y medios:** contraseñas con complejidad exigida; subida de imágenes con validación de contenido (no solo extensión), límite de 2 MB y mitigación de path traversal en el nombre de archivo.
