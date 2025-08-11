# /main.py

import streamlit as st
from streamlit_option_menu import option_menu
from streamlit_js_eval import streamlit_js_eval
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

# --- CSS DEFINITIVO PARA LAYOUT PROFISSIONAL E RESPONSIVO ---
st.markdown("""
<style>
    /* 1. REMOÇÃO DE ELEMENTOS NATIVOS DO STREAMLIT */
    /* Esconde o menu 'hamburger', botões de 'fork' etc. no topo direito */
    [data-testid="stToolbar"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    /* Esconde o rodapé "Made with Streamlit" */
    footer {
        visibility: hidden;
        height: 0%;
    }

    /* 2. LÓGICA DO MENU RESPONSIVO PARA CELULAR */
    @media (max-width: 767px) {
        /* Adiciona um espaço no final da página para o menu flutuante não cobrir o conteúdo */
        .main .block-container {
            padding-bottom: 6rem !important;
        }

        /* Pega o contêiner do menu e o transforma em uma barra fixa na base */
        /* Usamos um seletor mais específico para garantir a aplicação do estilo */
        .menu-container div[data-testid="stOptionMenu"] {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            width: 100%;
            background-color: #292929;
            border-top: 1px solid #444;
            z-index: 9999;
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

# --- DETECTAR O DISPOSITIVO DO USUÁRIO ---
user_agent = streamlit_js_eval(js_expressions='window.navigator.userAgent', key='USER_AGENT', want_output=True) or ""

# --- APLICATIVO PRINCIPAL ---
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# --- LÓGICA PARA RENDERIZAÇÃO CONDICIONAL (PC vs ANDROID) ---

IS_MOBILE = 'Android' in user_agent

# Envolve o menu em um contêiner div para que o CSS possa encontrá-lo
st.markdown('<div class="menu-container">', unsafe_allow_html=True)

if IS_MOBILE:
    # --- OPÇÕES PARA ANDROID ---
    mobile_options = [
        "Cadastro de Serviço", "Alocar Serviços", "Filas de Serviço", "Visão dos Boxes"
    ]
    mobile_icons = [
        "truck-front", "card-list", "card-checklist", "view-stacked"
    ]
    if st.session_state.get('user_role') == 'admin':
        mobile_options.extend(["Controle de Feedback", "Revisão Proativa"])
        mobile_icons.extend(["telephone-outbound", "arrow-repeat"])
    
    options_to_show = mobile_options
    icons_to_show = mobile_icons
    menu_styles = {
        "container": {"padding": "5px 0", "background-color": "transparent"},
        "nav-link": {"font-size": "10px", "padding": "8px 0", "text-align": "center", "height": "60px"},
        "nav-link-selected": {"background-color": "#333"},
        "icon": {"font-size": "20px", "margin-bottom": "4px"}
    }
else:
    # --- OPÇÕES PARA PC ---
    pc_options = [
        "Cadastro de Serviço", "Dados de Clientes", "Alocar Serviços", 
        "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", 
        "Histórico por Veículo", "Controle de Feedback", "Revisão Proativa"
    ]
    pc_icons = [
        "truck-front", "people", "card-list", "card-checklist", 
        "view-stacked", "check-circle", "clock-history", 
        "telephone-outbound", "arrow-repeat"
    ]
    if st.session_state.get('user_role') == 'admin':
        pc_options.extend(["Gerenciar Usuários", "Relatórios", "Mesclar Históricos"])
        pc_icons.extend(["people-fill", "graph-up", "sign-merge-left-fill"])
        
    options_to_show = pc_options
    icons_to_show = pc_icons
    menu_styles = {
        "container": {"padding": "0!important", "background-color": "#292929"},
        "icon": {"color": "#22a7f0", "font-size": "25px"},
        "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
        "nav-link-selected": {"background-color": "#1a1a1a"},
    }

selected_page = option_menu(
    menu_title=None, 
    options=options_to_show, 
    icons=icons_to_show, 
    menu_icon="cast", 
    default_index=0, 
    orientation="horizontal",
    styles=menu_styles
)

st.markdown('</div>', unsafe_allow_html=True)


# --- LÓGICA DE ROTEAMENTO ---
if selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()
elif selected_page == "Cadastro de Serviço":
    cadastro_servico.app()
elif selected_page == "Dados de Clientes":
    dados_clientes.app()
elif selected_page == "Filas de Serviço":
    filas_servico.app()
elif selected_page == "Visão dos Boxes":
    visao_boxes.visao_boxes()
elif selected_page == "Serviços Concluídos":
    servicos_concluidos.app()
elif selected_page == "Histórico por Veículo":
    historico_veiculo.app()
elif selected_page == "Controle de Feedback":
    feedback_servicos.app()
elif selected_page == "Revisão Proativa":
    revisao_proativa.app()
elif selected_page == "Gerenciar Usuários":
    gerenciar_usuarios.app()
elif selected_page == "Relatórios":
    relatorios.app()
elif selected_page == "Mesclar Históricos":
    mesclar_historico.app()