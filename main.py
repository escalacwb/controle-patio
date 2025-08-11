# /main.py

import streamlit as st
from streamlit_option_menu import option_menu
import login
from pages import (
    cadastro_servico,
    alocar_servicos,
    filas_servico,
    visao_boxes,
    servicos_concluidos,
    historico_veiculo,
    feedback_servicos,
    revisao_proativa,
    gerenciar_usuarios,
    relatorios,
    dados_clientes,
    mesclar_historico,
    gerar_termos,
    ajustar_media_km
)

st.set_page_config(page_title="Controle de Pátio PRO", layout="wide")

# --- CSS PARA LAYOUT RESPONSIVO E PROFISSIONAL ---
st.markdown("""
<style>
    /* Esconde o menu 'hamburger', o botão 'fork' e o rodapé do Streamlit */
    [data-testid="stToolbar"], footer, #fork-link {
        display: none !important;
        visibility: hidden !important;
    }
    .st-emotion-cache-1oe5cao { /* Oculta o header que contém os botões */
        display: none !important;
        visibility: hidden !important;
    }

    /* Estilos base para o nosso contêiner de menu */
    .menu-container {
        width: 100%;
    }

    /* --- ESTILOS PARA TELAS GRANDES (PC) --- */
    @media (min-width: 768px) {
        .menu-container {
            background-color: #292929;
            padding: 0 !important;
        }
    }

    /* --- ESTILOS PARA TELAS PEQUENAS (CELULAR) --- */
    @media (max-width: 767px) {
        /* Adiciona espaço no final da página para não cobrir o conteúdo */
        .main .block-container {
            padding-bottom: 5rem !important;
        }
        /* Transforma o menu em uma barra fixa e flutuante na base */
        .menu-container {
            position: fixed;
            bottom: 0;
            left: 0;
            background-color: #1a1a1a;
            border-top: 1px solid #333;
            z-index: 999;
            padding: 5px 0;
            box-shadow: 0 -2px 10px rgba(0,0,0,0.5);
        }
    }
</style>
""", unsafe_allow_html=True)


if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

# --- INICIALIZAÇÃO CENTRALIZADA DO ESTADO DA SESSÃO ---
def initialize_session_state():
    if 'box_states' not in st.session_state:
        st.session_state.box_states = {}

initialize_session_state()

# --- APLICATIVO PRINCIPAL ---
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# --- LÓGICA DO MENU UNIFICADO E RESPONSIVO ---

# Define as opções para todos os usuários
options = [
    "Cadastro de Serviço", "Dados de Clientes", "Alocar Serviços", 
    "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", 
    "Histórico por Veículo", "Controle de Feedback", "Revisão Proativa"
]
icons = [
    "truck-front", "people", "card-list", "card-checklist", 
    "view-stacked", "check-circle", "clock-history", 
    "telephone-outbound", "arrow-repeat"
]

# Adiciona opções de admin
if st.session_state.get('user_role') == 'admin':
    options.extend(["Gerenciar Usuários", "Relatórios", "Mesclar Históricos"])
    icons.extend(["people-fill", "graph-up", "sign-merge-left-fill"])

# Renderiza o menu dentro do nosso contêiner customizado
with st.container():
    st.markdown('<div class="menu-container">', unsafe_allow_html=True)
    selected_page = option_menu(
        menu_title=None, 
        options=options, 
        icons=icons, 
        menu_icon="cast", 
        default_index=0, 
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "#22a7f0", "font-size": "24px"},
            "nav-link": {"font-size": "14px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
            "nav-link-selected": {"background-color": "#111"},
        }
    )
    st.markdown('</div>', unsafe_allow_html=True)

# --- LÓGICA DE ROTEAMENTO (permanece a mesma) ---
if selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()
elif selected_page == "Cadastro de Serviço":
    cadastro_servico.app()
elif selected_page == "Dados de Clientes":
    dados_clientes.app()
# ... (demais rotas aqui, sem alteração)
# ...
elif selected_page == "Mesclar Históricos":
    mesclar_historico.app()