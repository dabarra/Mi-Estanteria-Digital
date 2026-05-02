iimport streamlit as st
import sqlite3
import pandas as pd

# Configuración de la base de datos SQLite
def conectar_db():
    conn = sqlite3.connect('biblioteca.db')
    return conn

def crear_tabla():
    conn = conectar_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS libros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            autor TEXT NOT NULL,
            genero TEXT,
            estado TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Funcionalidades principales
def añadir_libro(titulo, autor, genero, estado):
    conn = conectar_db()
    c = conn.cursor()
    c.execute('INSERT INTO libros (titulo, autor, genero, estado) VALUES (?, ?, ?, ?)',
              (titulo, autor, genero, estado))
    conn.commit()
    conn.close()

def listar_libros():
    conn = conectar_db()
    df = pd.read_sql_query('SELECT * FROM libros', conn)
    conn.close()
    return df

def eliminar_libro(id_libro):
    conn = conectar_db()
    c = conn.cursor()
    c.execute('DELETE FROM libros WHERE id = ?', (id_libro,))
    conn.commit()
    conn.close()

# Interfaz de Usuario con Streamlit
crear_tabla()
st.set_page_config(page_title="Mi Estantería Digital", layout="wide")
st.title("📚 Mi Estantería Digital")
st.write("Gestión personal de lecturas para el TFM de BigSchool.")

# Formulario lateral para añadir libros
with st.sidebar:
    st.header("Añadir Nuevo Libro")
    titulo = st.text_input("Título del libro")
    autor = st.text_input("Autor")
    genero = st.selectbox("Género", ["Novela", "Ensayo", "Ciencia Ficción", "Fantasía", "Otros"])
    estado = st.radio("Estado de lectura", ["Pendiente", "Leyendo", "Terminado"])
    
    if st.button("Guardar en Biblioteca"):
        if titulo and autor:
            añadir_libro(titulo, autor, genero, estado)
            st.success(f"¡'{titulo}' añadido!")
        else:
            st.error("Por favor, rellena título y autor.")

# Sección principal: Visualización y Gestión
libros_df = listar_libros()

if not libros_df.empty:
    st.subheader("Tu Colección")
    # Mostramos la tabla (sin la columna ID para el usuario)
    st.dataframe(libros_df.drop(columns=['id']), use_container_width=True)
    
    st.subheader("Gestionar libros")
    libro_a_borrar = st.selectbox("Selecciona un libro para eliminar", 
                                  options=libros_df['id'].tolist(),
                                  format_func=lambda x: libros_df[libros_df['id'] == x]['titulo'].values[0])
    
    if st.button("Eliminar libro seleccionado"):
        eliminar_libro(libro_a_borrar)
        st.warning("Libro eliminado correctamente.")
        st.rerun()
else:
    st.info("Aún no hay libros en tu estantería. ¡Añade el primero desde el panel lateral!")