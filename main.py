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

if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

# --- INÍCIO DA CORREÇÃO: INICIALIZAÇÃO CENTRALIZADA DO ESTADO DA SESSÃO ---
# Este bloco garante que todas as variáveis de sessão necessárias existam
# logo após o login, antes de qualquer página ser carregada.
def initialize_session_state():
    if 'box_states' not in st.session_state:
        st.session_state.box_states = {}
    # (No futuro, se outras páginas precisarem de estado, adicionamos aqui)

initialize_session_state()
# --- FIM DA CORREÇÃO ---


# --- ETAPA 1: DETECTAR O DISPOSITIVO DO USUÁRIO ---
user_agent = streamlit_js_eval(js_expressions='window.navigator.userAgent', key='USER_AGENT', want_output=True) or ""


# --- APLICATIVO PRINCIPAL ---
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# --- ETAPA 2: LÓGICA PARA RENDERIZAÇÃO CONDICIONAL (PC vs ANDROID) ---

IS_MOBILE = 'Android' in user_agent

if IS_MOBILE:
    # --- VISUALIZAÇÃO PARA ANDROID: MENU FLUTUANTE INFERIOR ---
    
    st.markdown("""
        <style>
            .main .block-container { padding-bottom: 80px; }
            .mobile-menu-container {
                position: fixed; bottom: 0; left: 0; width: 100%;
                background-color: #1a1a1a; border-top: 1px solid #333;
                z-index: 999; padding: 5px 0;
                box-shadow: 0 -2px 10px rgba(0,0,0,0.5);
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
            menu_title=None, options=mobile_options, icons=mobile_icons,
            menu_icon="cast", default_index=0, orientation="horizontal",
            styles={
                "container": {"padding": "0!important", "background-color": "transparent"},
                "nav-link": {"font-size": "10px", "padding": "8px 0", "text-align": "center"},
                "nav-link-selected": {"background-color": "#333"},
                "icon": {"font-size": "20px"}
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
        menu_title=None, options=options, icons=icons, 
        menu_icon="cast", default_index=0, orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#292929"},
            "icon": {"color": "#22a7f0", "font-size": "25px"},
            "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
            "nav-link-selected": {"background-color": "#1a1a1a"},
        }
    )

# --- LÓGICA DE ROTEAMENTO (Funciona para ambos os menus) ---
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

# Rotas que não estão no menu, mas precisam existir para serem acessadas via link
# A navegação para estas páginas é feita pela URL, não pelo menu principal
if 'page' in st.query_params:
    if st.query_params['page'] == "gerar_termos":
        gerar_termos.app()
    elif st.query_params['page'] == "ajustar_media_km":
        ajustar_media_km.app()