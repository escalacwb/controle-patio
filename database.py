import streamlit as st
from psycopg2 import pool
import psycopg2
import os
from dotenv import load_dotenv

# --- FUNÇÕES PARA O APLICATIVO STREAMLIT ---

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
    # Ajuste o número máximo de conexões se necessário
    return pool.SimpleConnectionPool(1, 30, dsn=db_url)

def get_connection():
    connection_pool = init_connection_pool()
    if connection_pool:
        # st.toast("Obtendo uma conexão...")
        return connection_pool.getconn()
    return None

def release_connection(conn):
    connection_pool = init_connection_pool()
    if connection_pool and conn:
        # st.toast("Liberando a conexão...")
        connection_pool.putconn(conn)

# --- FUNÇÃO PARA SCRIPTS INDEPENDENTES ---

def get_script_connection():
    load_dotenv()
    db_url = os.getenv("DB_URL")
    if not db_url:
        print("ERRO: A variável DB_URL não foi encontrada no arquivo .env")
        return None
    try:
        conn = psycopg2.connect(db_url)
        print("Conexão direta estabelecida com sucesso.")
        return conn
    except Exception as e:
        print(f"Erro ao tentar conectar ao banco de dados: {e}")
        return None

def close_script_connection(conn):
    if conn:
        conn.close()
        print("Conexão direta fechada.")