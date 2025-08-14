# pages/gerenciar_usuarios.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
# Importa a função de hash do novo auth_utils
from auth_utils import hash_new_password 
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

    # --- NOVA SEÇÃO: Ferramenta para Gerar Hash ---
    with st.expander("🔑 Gerador de Hash de Senha"):
        st.info("Use esta ferramenta para criar um hash de uma nova senha. Copie o resultado para o campo 'Senha' ao criar um novo usuário ou ao redefinir uma senha.")
        senha_para_hashear = st.text_input("Digite a senha para criptografar", type="password", key="senha_hash_tool")
        if st.button("Gerar Hash"):
            if senha_para_hashear:
                hashed_password = hash_new_password(senha_para_hashear)
                st.success("Hash gerado com sucesso!")
                st.code(hashed_password, language="text")
            else:
                st.warning("Por favor, digite uma senha.")
    
    st.markdown("---")


    # --- Exibir usuários existentes ---
    st.subheader("Usuários Cadastrados")
    try:
        df_users = pd.read_sql("SELECT id, nome, username, role FROM usuarios ORDER BY nome", conn)
        
        # --- NOVO: Interface para redefinir senha ---
        if not df_users.empty:
            selected_user_id = st.selectbox("Selecione um usuário para redefinir a senha (opcional)", options=[""] + df_users['id'].tolist(), format_func=lambda x: "" if x == "" else f"{df_users[df_users['id'] == x]['nome'].iloc[0]} (ID: {x})")

            if selected_user_id:
                st.warning(f"Você selecionou o usuário ID {selected_user_id} para redefinir a senha.")
                new_hashed_password = st.text_input("Cole o NOVO hash da senha aqui", key="new_hash_input")
                if st.button("Redefinir Senha do Usuário Selecionado", type="primary"):
                    if new_hashed_password.startswith('$2b$'): # Validação básica do hash
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (new_hashed_password, selected_user_id))
                                conn.commit()
                            st.success(f"Senha do usuário {selected_user_id} atualizada com sucesso!")
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao atualizar a senha: {e}")
                    else:
                        st.error("O texto inserido não parece ser um hash válido. Use a ferramenta 'Gerador de Hash' acima.")

        st.dataframe(df_users, use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")

    st.markdown("---")

    # --- Formulário para adicionar novo usuário ---
    st.subheader("Adicionar Novo Usuário")
    with st.form("new_user_form", clear_on_submit=True):
        nome = st.text_input("Nome Completo")
        username = st.text_input("Nome de Login (username)")
        # Agora o campo de senha espera o HASH, não a senha em texto plano
        password_hash_input = st.text_input("Senha (COLE O HASH GERADO AQUI)", type="password")
        role = st.selectbox("Permissão (Role)", ["funcionario", "admin"])
        
        submitted = st.form_submit_button("Adicionar Usuário")
        
        if submitted:
            if not all([nome, username, password_hash_input, role]):
                st.warning("Por favor, preencha todos os campos.")
            elif not password_hash_input.startswith('$2b$'):
                 st.error("O campo 'Senha' deve conter um hash válido. Use a ferramenta 'Gerador de Hash' no topo da página.")
            else:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "INSERT INTO usuarios (nome, username, password_hash, role) VALUES (%s, %s, %s, %s)",
                            (nome, username, password_hash_input, role)
                        )
                        conn.commit()
                    st.success(f"Usuário '{username}' adicionado com sucesso!")
                    st.rerun()
                except psycopg2.IntegrityError:
                    conn.rollback()
                    st.error(f"Erro: O nome de login '{username}' já existe.")
                except Exception as e:
                    conn.rollback()
                    st.error(f"Erro ao adicionar usuário: {e}")
    
    release_connection(conn)