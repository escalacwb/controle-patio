import streamlit as st
import hashlib
from database import get_connection, release_connection

def hash_password(password):
    """Gera o hash de uma senha para verificação."""
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username, password):
    """Verifica as credenciais no banco de dados."""
    conn = get_connection()
    if not conn:
        st.error("Falha na conexão com o banco de dados.")
        return False

    user = None
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome, password_hash, role FROM usuarios WHERE username = %s", (username,))
            user = cursor.fetchone()
    except Exception as e:
        st.error(f"Erro ao consultar usuário: {e}")
    finally:
        release_connection(conn)

    if user:
        # Compara o hash da senha digitada com o hash salvo no banco
        password_hash = user[2]
        if hash_password(password) == password_hash:
            # Salva informações do usuário na sessão
            st.session_state['logged_in'] = True
            st.session_state['user_id'] = user[0]
            st.session_state['user_name'] = user[1]
            st.session_state['user_role'] = user[3]
            return True
    return False

def render_login_page():
    """Renderiza o formulário de login."""
    st.title("Sistema de Controle de Pátio")
    st.write("Por favor, faça o login para continuar.")

    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

        if submitted:
            if check_login(username, password):
                st.rerun() # Recarrega a página para mostrar o app principal
            else:
                st.error("Usuário ou senha inválidos.")