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
    ajustar_media_km,
    analise_pneus,
    exportar_contatos
)

st.set_page_config(page_title="Controle de Pátio PRO", layout="wide")

# --- FLAGS DE INTEGRAÇÃO (via secrets do Streamlit) ---
OPENAI_READY   = bool(st.secrets.get("OPENAI_API_KEY"))
TELEGRAM_READY = bool(st.secrets.get("TELEGRAM_BOT_TOKEN")) and bool(st.secrets.get("TELEGRAM_CHAT_ID"))

# --- CSS DEFINITIVO PARA LAYOUT PROFISSIONAL E RESPONSIVO ---
st.markdown("""
<style>
    /* 1. REMOÇÃO DE ELEMENTOS NATIVOS DO STREAMLIT */
    [data-testid="stToolbar"] { visibility: hidden; height: 0%; position: fixed; }
    header[data-testid="stHeader"] { display: none !important; }
    footer { visibility: hidden; height: 0%; }

    /* 2. MENU RESPONSIVO PARA CELULAR */
    @media (max-width: 767px) {
        .main .block-container { padding-bottom: 6rem !important; }
        .menu-container div[data-testid="stOptionMenu"] {
            position: fixed !important; bottom: 0 !important; left: 0 !important; right: 0 !important;
            width: 100% !important; background-color: #292929 !important; border-top: 1px solid #444 !important;
            z-index: 9999 !important; box-shadow: 0 -2px 10px rgba(0,0,0,0.5) !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# --- LOGIN ---
if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

# --- ESTADO DE SESSÃO ---
def initialize_session_state():
    if 'box_states' not in st.session_state:
        st.session_state.box_states = {}
initialize_session_state()

# --- DETECTAR DISPOSITIVO ---
user_agent = streamlit_js_eval(js_expressions='window.navigator.userAgent', key='USER_AGENT', want_output=True) or ""

# --- SIDEBAR ---
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")

    # Status das integrações (meramente informativo)
    st.markdown("### Integrações")
    st.write(f"OpenAI: {'✅' if OPENAI_READY else '❌'}")
    st.write(f"Telegram: {'✅' if TELEGRAM_READY else '❌'}")

    if not OPENAI_READY:
        st.caption("Configure `OPENAI_API_KEY` em Secrets para habilitar **Análise de Pneus**.")
    if not TELEGRAM_READY:
        st.caption("Opcional: `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` para receber laudos no grupo.")

    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- RENDERIZAÇÃO CONDICIONAL ---
IS_MOBILE = 'Android' in user_agent or 'iPhone' in user_agent

# Envolve o menu para aplicar CSS
st.markdown('<div class="menu-container">', unsafe_allow_html=True)

if IS_MOBILE:
    # --- MENU (MOBILE) ---
    mobile_options = ["Cadastro de Serviço", "Alocar Serviços", "Filas de Serviço", "Visão dos Boxes"]
    mobile_icons   = ["truck-front", "card-list", "card-checklist", "view-stacked"]

    # acrescenta Análise de Pneus se OpenAI estiver configurado
    if OPENAI_READY:
        mobile_options.append("Análise de Pneus")
        mobile_icons.append("camera")

    if st.session_state.get('user_role') == 'admin':
        mobile_options.extend(["Controle de Feedback", "Revisão Proativa"])
        mobile_icons.extend(["telephone-outbound", "arrow-repeat"])

    options_to_show = mobile_options
    icons_to_show   = mobile_icons
    menu_styles = {
        "container": {"padding": "5px 0", "background-color": "transparent"},
        "nav-link": {"font-size": "10px", "padding": "8px 0", "text-align": "center", "height": "60px"},
        "nav-link-selected": {"background-color": "#333"},
        "icon": {"font-size": "20px", "margin-bottom": "4px"}
    }
else:
    # --- MENU (PC) ---
    pc_options = [
        "Cadastro de Serviço", "Dados de Clientes", "Alocar Serviços",
        "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos",
        "Histórico por Veículo", "Controle de Feedback", "Revisão Proativa", "Exportar CSV",
    ]
    pc_icons = [
        "truck-front", "people", "card-list",
        "card-checklist", "view-stacked", "check-circle",
        "clock-history", "telephone-outbound", "arrow-repeat",
    ]

    # acrescenta Análise de Pneus se OpenAI estiver configurado
    if OPENAI_READY:
        pc_options.append("Análise de Pneus")
        pc_icons.append("camera")

    if st.session_state.get('user_role') == 'admin':
        pc_options.extend(["Gerenciar Usuários", "Relatórios", "Mesclar Históricos"])
        pc_icons.extend(["people-fill", "graph-up", "sign-merge-left-fill"])

    options_to_show = pc_options
    icons_to_show   = pc_icons
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

# --- ROTEAMENTO ---
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
elif selected_page == "Análise de Pneus":
    # chama a página de análise (só aparece no menu se OPENAI_READY for True)
    analise_pneus.app()
elif selected_page == "Gerenciar Usuários":
    gerenciar_usuarios.app()
elif selected_page == "Relatórios":
    relatorios.app()
elif selected_page == "Mesclar Históricos":
    mesclar_historico.app()
elif selected_page == "Exportar CSV":
    exportar_contatos.app()

# Páginas acessadas via link direto (gerar_termos / ajustar_media_km)
# continuam sem rota direta aqui, seguindo o seu padrão atual.
