import streamlit as st
from streamlit_option_menu import option_menu
import login # Importa nosso novo script de login
from pages import (
    alocar_servicos,
    cadastro_servico,
    cadastro_veiculo,
    filas_servico,
    visao_boxes,
    servicos_concluidos,
    historico_veiculo,
    gerenciar_usuarios # Importa a nova página
)

# Configuração da página
st.set_page_config(
    page_title="Controle de Pátio PRO", 
    page_icon="🚚",
    layout="wide"
)

# --- VERIFICAÇÃO DE LOGIN ---
# Se 'logged_in' não for True na memória da sessão, mostra a tela de login.
if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop() # Para a execução aqui para não mostrar o resto do app

# --- APLICATIVO PRINCIPAL (SÓ APARECE APÓS LOGIN) ---

# Adiciona um menu lateral apenas para o nome do usuário e o botão de logout
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# --- LÓGICA DE MENU DINÂMICO ---
# Define as opções e ícones padrão para todos os usuários
options = ["Alocar Serviços", "Cadastro de Serviço", "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", "Histórico por Veículo"]
icons = ["truck-front", "card-list", "card-checklist", "view-stacked", "check-circle", "clock-history"]

# Se o usuário for um admin, adiciona a opção de gerenciar usuários ao menu
if st.session_state.get('user_role') == 'admin':
    options.append("Gerenciar Usuários")
    icons.append("people-fill") # Ícone para gerenciamento de usuários

selected_page = option_menu(
    menu_title=None,
    options=options, # Usa a lista de opções dinâmica
    icons=icons,     # Usa a lista de ícones dinâmica
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#292929"},
        "icon": {"color": "#22a7f0", "font-size": "25px"},
        "nav-link": {
            "font-size": "16px",
            "text-align": "center",
            "margin":"0px",
            "--hover-color": "#444",
            "padding": "10px 0px"
        },
        "nav-link-selected": {"background-color": "#1a1a1a"},
        # --- AJUSTE FINAL APLICADO AQUI ---
        # Esconde o texto dos botões, deixando só os ícones, como no design anterior
        ".nav-link-text": {"display": "none"}
    }
)

# Lógica para exibir a página selecionada
if selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()
elif selected_page == "Cadastro de Serviço":
    cadastro_servico.app()
elif selected_page == "Cadastro de Veículo":
    cadastro_veiculo.app()
elif selected_page == "Filas de Serviço":
    filas_servico.app()
elif selected_page == "Visão dos Boxes":
    visao_boxes.visao_boxes()
elif selected_page == "Serviços Concluídos":
    servicos_concluidos.app()
elif selected_page == "Histórico por Veículo":
    historico_veiculo.app()
elif selected_page == "Gerenciar Usuários":
    gerenciar_usuarios.app()