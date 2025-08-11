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

# --- CSS PARA REMOVER ELEMENTOS DO STREAMLIT ---
st.markdown("""
<style>
    /* Esconde o menu 'hamburger' e o botão 'fork' no topo direito */
    [data-testid="stToolbar"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }
    /* Esconde o rodapé "Made with Streamlit" */
    footer {
        visibility: hidden;
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

if IS_MOBILE:
    # --- VISUALIZAÇÃO PARA ANDROID: MENU FLUTUANTE INFERIOR ---
    
    st.markdown("""
        <style>
            /* Adiciona espaço no final da página para o menu não cobrir o conteúdo */
            .main .block-container { 
                padding-bottom: 6rem !important; /* Aumenta o espaço para segurança */
            }
            /* Cria a barra flutuante na base da tela */
            .mobile-menu-container {
                position: fixed;
                bottom: 0;
                left: 0;
                width: 100%;
                background-color: #292929; /* Cor de fundo escura */
                border-top: 1px solid #444;
                z-index: 101; /* Garante que o menu fique sobre todos os outros elementos */
            }
        </style>
    """, unsafe_allow_html=True)
    
    mobile_options = [
        "Cadastro de Serviço", "Alocar Serviços", "Filas de Serviço", "Visão dos Boxes"
    ]
    mobile_icons = [
        "truck-front", "card-list", "card-checklist", "view-stacked"
    ]

    if st.session_state.get('user_role') == 'admin':
        mobile_options.extend(["Controle de Feedback", "Revisão Proativa"])
        mobile_icons.extend(["telephone-outbound", "arrow-repeat"])

    with st.container():
        st.markdown('<div class="mobile-menu-container">', unsafe_allow_html=True)
        selected_page = option_menu(
            menu_title=None, 
            options=mobile_options, 
            icons=mobile_icons,
            menu_icon="cast", 
            default_index=0, 
            orientation="horizontal",
            styles={
                "container": {"padding": "5px 0", "background-color": "transparent"},
                "nav-link": {
                    "display": "flex", "flex-direction": "column", "align-items": "center",
                    "justify-content": "center", "font-size": "11px", "text-align": "center",
                    "height": "60px"
                },
                "nav-link-selected": {"background-color": "#333"},
                "icon": {"font-size": "22px", "margin-bottom": "4px"}
            }
        )
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # --- VISUALIZAÇÃO PARA PC: MENU SUPERIOR PADRÃO ---
    
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

    if st.session_state.get('user_role') == 'admin':
        options.extend(["Gerenciar Usuários", "Relatórios", "Mesclar Históricos"])
        icons.extend(["people-fill", "graph-up", "sign-merge-left-fill"])

    selected_page = option_menu(
        menu_title=None, 
        options=options, 
        icons=icons, 
        menu_icon="cast", 
        default_index=0, 
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#292929"},
            "icon": {"color": "#22a7f0", "font-size": "25px"},
            "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
            "nav-link-selected": {"background-color": "#1a1a1a"},
        }
    )

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