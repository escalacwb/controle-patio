# auth_utils.py

import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader
from database import get_connection, release_connection
import pandas as pd

def fetch_users_from_db():
    """
    Busca os usuários do banco de dados e formata para o streamlit-authenticator.
    A senha no banco já deve estar hasheada com o método do streamlit-authenticator.
    """
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados para autenticação.")
        return None
    try:
        # A query busca os campos que o authenticator precisa
        query = "SELECT nome, username, password_hash, role FROM usuarios"
        df_users = pd.read_sql(query, conn)
        
        # Formata os dados para o formato de dicionário exigido pela biblioteca
        credentials = {"usernames": {}}
        for index, row in df_users.iterrows():
            credentials["usernames"][row['username']] = {
                "name": row['nome'],
                "password": row['password_hash'],
                "role": row['role'] # Campo customizado
            }
        return credentials
    except Exception as e:
        st.error(f"Erro ao buscar usuários: {e}")
        return None
    finally:
        release_connection(conn)

def initialize_authenticator():
    """
    Inicializa o objeto de autenticação com os dados do banco.
    """
    # Carrega a configuração do cookie do secrets.toml
    # IMPORTANTE: Você PRECISA criar um arquivo .streamlit/secrets.toml com este conteúdo
    cookie_config = st.secrets.get("cookie", {})
    
    credentials = fetch_users_from_db()
    
    if credentials:
        authenticator = stauth.Authenticate(
            credentials,
            cookie_config.get('name', 'some_cookie_name'),
            cookie_config.get('key', 'some_signature_key'),
            cookie_config.get('expiry_days', 30),
            # preauthorized # Opcional: para pre-autorizar emails/usuários
        )
        return authenticator
    return None

def hash_new_password(password):
    """
    Função utilitária para gerar um hash de senha compatível com a biblioteca.
    Use isso para cadastrar novos usuários ou atualizar senhas.
    """
    return stauth.Hasher([password]).generate()[0]

