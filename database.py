import streamlit as st
from psycopg2 import pool
import psycopg2 # Adicionado para a nova função de conexão direta
import os
from dotenv import load_dotenv

# --- FUNÇÕES PARA O APLICATIVO STREAMLIT (NÃO MUDAM) ---

def get_db_url():
    """
    Busca a URL do banco de dados de forma inteligente.
    Primeiro, tenta os Secrets do Streamlit (para a nuvem).
    Se não encontrar, tenta o arquivo .env (para o computador local).
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

# --- MUDANÇA: NOVA FUNÇÃO PARA SCRIPTS INDEPENDENTES ---

def get_script_connection():
    """
    Cria uma conexão DIRETA com o banco de dados para scripts.
    Lê a URL exclusivamente do arquivo .env e não usa cache do Streamlit.
    """
    load_dotenv() # Garante que o arquivo .env seja lido
    db_url = os.getenv("DB_URL")
    
    if not db_url:
        print("ERRO CRÍTICO: A variável DB_URL não foi encontrada no seu arquivo .env")
        return None
        
    try:
        # Cria uma conexão simples, sem pool
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"ERRO CRÍTICO: Falha ao conectar ao banco de dados: {e}")
        return None