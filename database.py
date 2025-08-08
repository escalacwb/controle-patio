import streamlit as st
from psycopg2 import pool
import psycopg2
import os
from dotenv import load_dotenv

# --- FUNÇÕES PARA O APLICATIVO STREAMLIT (NÃO MUDAM) ---

def get_db_url():
    if hasattr(st, 'secrets') and st.secrets.get("DB_URL"):
        return st.secrets["DB_URL"]
    else:
        load_dotenv()
        return os.getenv("DB_URL")

@st.cache_resource
def init_connection_pool():
    db_url = get_db_url()
    if not db_url:
        raise ValueError("URL do banco de dados não encontrada.")
    return pool.SimpleConnectionPool(1, 10, dsn=db_url)

def get_connection():
    connection_pool = init_connection_pool()
    if connection_pool:
        return connection_pool.getconn()
    return None

def release_connection(conn):
    connection_pool = init_connection_pool()
    if connection_pool and conn:
        connection_pool.putconn(conn)

# --- NOVA FUNÇÃO PARA SCRIPTS INDEPENDENTES ---

def get_script_connection():
    load_dotenv()
    db_url = os.getenv("DB_URL")
    if not db_url:
        print("ERRO: A variável DB_URL não foi encontrada no arquivo .env")
        return None
    try:
        conn = psycopg2.connect(db_url)
        return conn
    except Exception as e:
        print(f"Erro ao tentar conectar ao banco de dados: {e}")
        return None