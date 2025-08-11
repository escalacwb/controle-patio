# /main.py

import streamlit as st
from streamlit_option_menu import option_menu
from streamlit_js_eval import streamlit_js_eval
import login
from pages import (
    cadastro_servico, alocar_servicos, filas_servico, visao_boxes,
    servicos_concluidos, historico_veiculo, feedback_servicos,
    revisao_proativa, gerenciar_usuarios, relatorios, dados_clientes,
    mesclar_historico, gerar_termos, ajustar_media_km
)

st.set_page_config(
    page_title="Controle de Pátio PRO",
    page_icon="🧰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- CSS DEFINITIVO PARA ESCONDER A UI PADRÃO DO STREAMLIT ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {display: none !important;}
</style>
""", unsafe_allow_html=True)

if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

def initialize_session_state():
    if 'box_states' not in st.session_state:
        st.session_state.box_states = {}
initialize_session_state()

user_agent = streamlit_js_eval(js_expressions='window.navigator.userAgent', key='USER_AGENT', want_output=True) or ""

with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

IS_MOBILE = 'Android' in user_agent or 'iPhone' in user_agent

# --- LÓGICA DE RENDERIZAÇÃO ---
# Se for PC, mostra o menu do PC. Se for mobile, não mostra NENHUM menu aqui.
# O menu mobile será renderizado por cada página individualmente.
if not IS_MOBILE:
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
    # Roteamento para PC
    # (A lógica de roteamento será movida para o final para funcionar para ambos)
else:
    # No celular, a página padrão é Cadastro de Serviço, mas o menu será renderizado pela própria página
    selected_page = st.query_params.get('page', ['Cadastro de Serviço'])[0]


# --- LÓGICA DE ROTEAMENTO (UNIFICADA) ---
# O roteamento aqui é importante para o PC. No mobile, a navegação será por URL.
# Esta lógica precisa existir para o app saber qual função chamar.
# (Esta seção foi simplificada para refletir a nova abordagem)
# A página ativa é definida pelo menu (no PC) ou pela URL (no mobile)
# O Streamlit irá rodar o script da página correspondente ao URL.
# A lógica de roteamento principal do streamlit já cuida disso.
pass