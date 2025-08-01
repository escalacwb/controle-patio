import streamlit as st
from psycopg2 import pool
# A importação do 'os' e 'dotenv' não é mais necessária para a nuvem,
# então foram removidas para deixar o código mais limpo.

# O Streamlit vai gerenciar o cache desta função na nuvem.
@st.cache_resource
def init_connection_pool():
    """
    Inicializa e retorna um pool de conexões com o banco de dados.
    Esta versão é específica para o Streamlit Community Cloud.
    """
    try:
        # st.connection busca a URL do banco de dados diretamente dos "Secrets"
        # que você configurou no painel do Streamlit, em vez de um arquivo .env.
        # É mais seguro e a forma correta de fazer na nuvem.
        db_url = st.connection("postgres", type="sql")._engine.url
        
        # Cria um pool de conexões com no mínimo 1 e no máximo 10 conexões.
        connection_pool = pool.SimpleConnectionPool(1, 10, dsn=str(db_url))
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