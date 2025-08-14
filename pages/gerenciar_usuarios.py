import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import hash_password # Importa a função de hash centralizada
import psycopg2

def app():
    st.title("🔑 Gerenciamento de Usuários")

    # Garante que apenas administradores possam ver esta página
    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    # Exibir usuários existentes
    st.subheader("Usuários Cadastrados")
    try:
        # Buscamos os usuários, mas NUNCA a senha_hash
        df_users = pd.read_sql("SELECT id, nome, username, role FROM usuarios ORDER BY nome", conn)
        st.dataframe(df_users, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")

    st.markdown("---")

    # Formulário para adicionar novo usuário
    st.subheader("Adicionar Novo Usuário")
    with st.form("new_user_form", clear_on_submit=True):
        nome = st.text_input("Nome Completo")
        username = st.text_input("Nome de Login (username)")
        password = st.text_input("Senha", type="password")
        role = st.selectbox("Permissão (Role)", ["funcionario", "admin"])
        
        submitted = st.form_submit_button("Adicionar Usuário")
        
        if submitted:
            if not all([nome, username, password, role]):
                st.warning("Por favor, preencha todos os campos.")
            else:
                try:
                    password_hash = hash_password(password) # Criptografa a senha
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO usuarios (nome, username, password_hash, role) VALUES (%s, %s, %s, %s)",
                            (nome, username, password_hash, role)
                        )
                        conn.commit()
                    st.success(f"Usuário '{username}' adicionado com sucesso!")
                    st.rerun() # Recarrega a página para mostrar o novo usuário na lista
                except psycopg2.IntegrityError:
                    conn.rollback()
                    st.error(f"Erro: O nome de login '{username}' já existe.")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao adicionar usuário: {e}")
    
    release_connection(conn)