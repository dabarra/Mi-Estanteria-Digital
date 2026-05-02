# 📚 Mi Estantería Digital - TFM Desarrollo con IA

## a. Descripción general del proyecto
Este proyecto consiste en una aplicación web diseñada para la gestión personal de bibliotecas. Permite a los usuarios llevar un registro de sus libros, autores, géneros y el estado actual de sus lecturas (pendiente, leyendo o terminado). Es una solución práctica para organizar colecciones físicas o digitales.

## b. Stack tecnológico utilizado
* **Lenguaje:** Python 3.12
* **Interfaz de usuario:** Streamlit
* **Base de datos:** SQLite (Motor ligero y persistente)
* **Gestión de datos:** Pandas
* **Control de versiones:** Git y GitHub

## c. Información sobre su instalación y ejecución
1. Clonar el repositorio: `git clone [TU_URL_AQUÍ]`
2. Crear un entorno virtual: `python -m venv venv`
3. Activar el entorno: `source venv/bin/activate` (Linux/Mac) o `venv\Scripts\activate` (Windows)
4. Instalar dependencias: `pip install -r requirements.txt`
5. Ejecutar la app: `streamlit run app.py`

## d. Estructura del proyecto
* `app.py`: Archivo principal con la lógica de la aplicación y la interfaz.
* `biblioteca.db`: Base de datos SQLite (se genera automáticamente).
* `requirements.txt`: Lista de librerías necesarias para el funcionamiento.
* `README.md`: Documentación técnica del proyecto.

## e. Funcionalidades principales
* **Registro de libros:** Formulario para añadir título, autor, género y estado.
* **Visualización interactiva:** Tabla dinámica con toda la colección almacenada.
* **Persistencia de datos:** Los libros guardados se mantienen al cerrar la app.
* **Gestión de bajas:** Opción para eliminar registros de la base de datos.