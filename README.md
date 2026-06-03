# Mi estantería digital — TFM

## Acceso Rápido para la Evaluación Técnica

Para facilitar una auditoría inmediata de la aplicación sin necesidad de realizar registros manuales, se ha configurado un perfil de pruebas con un catálogo de doce libros y analíticas históricas ya precargadas.

**Credenciales de acceso:** el usuario de pruebas (nombre de usuario y correo electrónico asociado) se encuentra especificado en la presentación del proyecto en formato PPTX, en la diapositiva **Seguridad y Acceso** (`Presentacion_TFM_Daniel_Barrasa.pptx`). La contraseña de acceso **no se incluye en el repositorio** por seguridad y se indica en el **formulario de envío** del TFM.

Nota importante sobre la infraestructura: Al estar desplegada en la capa gratuita de Streamlit Cloud, la aplicación entra en modo de hibernación tras periodos de inactividad, lo que provoca la regeneración del contenedor efímero y el vaciado de los datos locales introducidos en las sesiones de usuario. Para mitigar esta limitación, el sistema incorpora un mecanismo automatizado de semillero de datos (data seeding). Si al ingresar nota que la estantería se ha restablecido, no se preocupe: el sistema detectará el reinicio e inyectará de forma automática y limpia este mismo perfil de pruebas junto con sus doce libros de muestra para asegurar la continuidad de su evaluación.

## URL de despliegue oficial
La aplicación se encuentra desplegada en la nube y disponible para su uso e inspección directa en la siguiente dirección pública:
https://mi-estanteria-digital.streamlit.app/

## a. Descripción general del proyecto

Aplicación web para gestionar una biblioteca personal inspirada en redes de lectura compartida. El sistema permite administrar un catálogo común de libros identificados por su código ISBN, gestionar una biblioteca individual por cada usuario con estados de lectura personalizados, portadas digitalizadas, control de fechas de seguimiento y generación de estadísticas anuales de rendimiento lector. Cada usuario accede de forma estricta y exclusiva a sus propios registros de actividad; el entorno de acceso está protegido mediante autenticación cifrada, mitigación de ataques por bloqueo temporal tras intentos fallidos y un módulo seguro de reconfiguración de credenciales.

## b. Stack tecnológico utilizado

- Lenguaje: Python 3.12
- Interfaz y entorno gráfico: Streamlit
- Motor de persistencia de datos: SQLite
- Seguridad y cifrado de credenciales: passlib con esquema bcrypt (dependencia nativa de la librería bcrypt)
- Procesamiento y validación de medios gráficos: Pillow (auditoría binaria de archivos, restricción de tamaño y saneamiento de rutas de almacenamiento)
- Estructuración de datos tabulares para estadísticas: Pandas
- Sistema de control de versiones: Git

## c. Instalación y ejecución

1. Clonar el repositorio localmente.
2. Crear y activar un entorno virtual limpio: usar el comando *python -m venv venv* seguido de *source venv/bin/activate* en sistemas Linux/macOS o *venv\Scripts\activate* en entornos Windows.
3. Instalar la totalidad de los requerimientos del sistema: *pip install -r requirements.txt*
4. Lanzar el servidor local de la aplicación: *streamlit run app.py*

El archivo que contiene la persistencia de datos (*biblioteca.db*) se inicializa de forma automática en la raíz del espacio de trabajo al arrancar el software por primera vez. Las imágenes de portada validadas se transfieren al directorio interno denominado *portadas/*. En caso de realizar pruebas de migración desde esquemas de desarrollo heredados, se recomienda eliminar el archivo *biblioteca.db* para permitir una regeneración limpia del esquema relacional.

## d. Arquitectura del proyecto (Estructura modular)

- *app.py* — Capa de presentación, control de interfaz y gestión del estado de la sesión Streamlit. Centraliza los formularios interactivos, el enrutamiento dinámico de la barra lateral, los mensajes de feedback al usuario y la orquestación global de las vistas del sistema. Está diseñado siguiendo el principio de separación de responsabilidades, por lo que carece de consultas SQL explícitas o capturas de excepciones del motor de base de datos.
- *database_manager.py* — Capa de persistencia y abstracción de datos en SQLite. Administra los hilos de conexión, la ejecución de migraciones de esquemas, las operaciones CRUD de usuarios, libros del catálogo común y registros específicos de bibliotecas individuales. Implementa transacciones atómicas seguras como el guardado doble coordinado y la actualización protegida de filas de biblioteca.
- *auth_manager.py* — Módulo especializado en seguridad y gestión de identidades. Centraliza la conversión y verificación de contraseñas mediante el algoritmo bcrypt, aplica validaciones sintácticas de correos electrónicos y comprueba criterios de complejidad tipográfica alineados con las directrices de seguridad OWASP. Administra los mecanismos de autenticación y el restablecimiento verificado de credenciales.
- *utils.py* — Componente de utilidades transversales del sistema. Ejecuta la normalización de cadenas de texto y la validación matemática de dígitos de control para formatos ISBN-10 e ISBN-13 mediante aritmética de módulos. Controla la lógica de fechas temporales, las reglas de transición de estados de lectura y el almacenamiento blindado de portadas (verificando el tipo real del flujo binario con la librería Pillow, restringiendo el peso a un máximo de 2 MB y previniendo inyecciones de ruta por salto de directorio).
- *requirements.txt* — Catálogo explícito de dependencias y librerías externas del proyecto.
- *README.md* — Guía de documentación técnica del software.

## e. Diseño de la Base de Datos (Modelo Relacional)

La base de datos *biblioteca.db* implementa un diseño relacional estructurado en tres tablas principales con restricciones de integridad y claves foráneas habilitadas:

- Tabla usuarios: Almacena las identidades del sistema. Campos: id (clave primaria), username (único), email (único), password (hash criptográfico bcrypt) y created_at.
- Tabla libros_comunes: Catálogo global compartido. Campos: id (clave primaria), isbn_10 (único), isbn_13 (único), title, author, genre, idioma, paginas, cover_path y created_at. Cuenta con una restricción de verificación que exige la presencia de al menos uno de los dos formatos de ISBN.
- Tabla biblioteca_usuario: Tabla de ruptura relacional de muchos a muchos que vincula a un usuario con sus libros. Campos: id (clave primaria), user_id (clave foránea), book_id (clave foránea), estado, fecha_inicio, fecha_fin, paginas_leidas_abandono y added_at. Aplica una restricción de unicidad combinada para evitar la duplicidad de un mismo libro en la estantería de un mismo usuario.

## f. Funcionalidades y mecanismos principales

- Autenticación y Control de Acceso: Registro de cuentas con evaluación estricta de complejidad de contraseña (longitud, mayúsculas, minúsculas, números y caracteres especiales). El inicio de sesión acepta indistintamente el nombre de usuario o el correo electrónico. Incluye un sistema de mitigación de ataques de fuerza bruta que congela la cuenta de forma temporal por un periodo de 120 segundos tras acumular 5 intentos fallidos consecutivos en la sesión.
- Restablecimiento Seguro de Credenciales: Flujo defensivo contra la enumeración de usuarios. El formulario exige la coincidencia matemática exacta en la misma fila de base de datos del nombre de usuario y el correo electrónico registrado para autorizar el cambio de contraseña, bloqueando intentos de usurpación de cuenta.
- Gestión de Catálogo mediante ISBN: Validación matemática rigurosa de los códigos de barra de libros mediante algoritmos estándar de la industria editorial. El sistema rechaza cualquier alta que no cuente con un código ISBN-10 o ISBN-13 estructurado de forma correcta.
- Registro Lector e Interfaz Fluida: Soporta las etiquetas de seguimiento Pendiente, Leyendo, Terminado, Abandonado y Relectura. Los formularios de actualización de progreso se despliegan de forma interactiva e inline directamente debajo de la tarjeta de cada libro utilizando una distribución de columnas proporcionales, eliminando el uso de desplegables colapsables redundantes y mejorando la experiencia de usuario.
- Lógica de Abandono y Transiciones: Al cambio de estado de un libro a Abandonado, el sistema calcula las fechas correspondientes y permite al lector registrar el número exacto de páginas leídas hasta ese momento, datos que se conservan de forma acotada para no alterar el cómputo de páginas de la ficha técnica original del libro.
- Sistema de Enrutamiento en Barra Lateral: Navegación limpia gestionada desde un menú lateral dinámico que ha sido rediseñado mediante inyección de CSS. Se ocultan los selectores nativos de Streamlit para ofrecer una botonera vertical interactiva que resalta la sección activa con bordes y variaciones cromáticas de fondo al pasar el cursor.
- Visualización en Galería y Estadísticas: Doble alternativa de visualización en la estantería (vista de lista simétrica con un marcador de posición estándar para títulos sin portada, o vista de galería estética en cuadrícula con efectos de elevación visual hover al posicionar el ratón). El módulo de analítica agrupa de forma automática el total de libros concluidos y las páginas acumuladas año por año, permitiendo desglosar los títulos leídos en cada periodo.
- Seguridad de Medios: El cargador de portadas analiza la firma interna del archivo cargado para confirmar que se trata de un flujo de imagen real (JPEG o PNG) y no de un script malicioso camuflado con una extensión falsa. Resguarda el servidor contra desbordamientos limitando las subidas a 2 MB y sanitiza los nombres de archivo generándolos mediante combinaciones aleatorias basadas en UUID para evitar la sobrescritura voluntaria de elementos en el disco.