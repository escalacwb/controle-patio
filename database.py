import os
import streamlit as st
from dotenv import load_dotenv
from psycopg2 import pool

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# A anotação @st.cache_resource garante que o pool de conexões seja criado apenas uma vez.
@st.cache_resource
def init_connection_pool():
    """
    Inicializa e retorna um pool de conexões com o banco de dados.
    """
    try:
        db_url = os.getenv("DB_URL")
        if not db_url:
            raise ValueError("A variável de ambiente DB_URL não foi encontrada.")
        
        # Cria um pool de conexões com no mínimo 1 e no máximo 10 conexões.
        connection_pool = pool.SimpleConnectionPool(1, 10, dsn=db_url)
        return connection_pool
    except Exception as e:
        # Se a conexão falhar, exibe uma mensagem de erro clara no Streamlit.
        st.error(f"Erro ao inicializar o pool de conexões com o banco de dados: {e}")
        return None

def get_connection():
    """
    Obtém uma conexão do pool.
    Esta função será chamada por outras partes do aplicativo.
    """
    connection_pool = init_connection_pool()
    if connection_pool:
        return connection_pool.getconn()
    return None

def release_connection(conn):
    """
    Devolve uma conexão ao pool.
    """
    connection_pool = init_connection_pool()
    if connection_pool and conn:
        connection_pool.putconn(conn)