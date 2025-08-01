import streamlit as st
from psycopg2 import pool
import os
from dotenv import load_dotenv

def get_db_url():
    """
    Busca a URL do banco de dados de forma inteligente.
    """
    if hasattr(st, 'secrets') and st.secrets.get("DB_URL"):
        return st.secrets["DB_URL"]
    else:
        load_dotenv()
        return os.getenv("DB_URL")

@st.cache_resource
def init_connection_pool():
    """Inicializa um pool de conexões com o banco de dados."""
    db_url = None
    try:
        db_url = get_db_url()
        
        # --- LINHA DE DIAGNÓSTICO ---
        # Vamos mostrar na tela a URL que estamos tentando usar.
        st.info(f"DEBUG: Tentando conectar com a URL: {db_url}")
        
        if not db_url:
            raise ValueError("URL do banco de dados não encontrada. Verifique seus Secrets no Streamlit Cloud ou o arquivo .env local.")
        
        connection_pool = pool.SimpleConnectionPool(1, 10, dsn=db_url)
        return connection_pool
    except Exception as e:
        st.error(f"Erro ao inicializar o pool de conexões: {e}")
        return None

def get_connection():
    """Obtém uma conexão do pool."""
    connection_pool = init_connection_pool()
    if connection_pool:
        return connection_pool.getconn()
    return None

def release_connection(conn):
    """Devolve uma conexão ao pool."""
    connection_pool = init_connection_pool()
    if connection_pool and conn:
        connection_pool.putconn(conn)