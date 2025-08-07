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
    cadastro_veiculo,
    feedback_servicos,
    revisao_proativa,
    gerenciar_usuarios,
    relatorios
)

st.set_page_config(page_title="Controle de Pátio PRO", layout="wide")

if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

# --- INICIALIZAÇÃO CENTRALIZADA DO ESTADO DA SESSÃO ---
# Este bloco garante que todas as variáveis de memória necessárias existam
# logo após o login, antes de qualquer página ser carregada.
if 'box_states' not in st.session_state:
    st.session_state.box_states = {}
# (No futuro, se outras páginas precisarem de memória, adicionamos aqui)


# --- APLICATIVO PRINCIPAL ---
with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

options = ["Cadastro de Serviço", "Alocar Serviços", "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", "Histórico por Veículo", "Controle de Feedback", "Revisão Proativa"]
icons = ["truck-front", "card-list", "card-checklist", "view-stacked", "check-circle", "clock-history"]

if st.session_state.get('user_role') == 'admin':
    options.append("Gerenciar Usuários")
    icons.append("people-fill")
    options.append("Relatórios")
    icons.append("graph-up")

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

# Lógica de Roteamento
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
elif selected_page == "Controle de Feedback": # <-- ADICIONE ESTE BLOCO
    feedback_servicos.app()
elif selected_page == "Revisão Proativa": # <-- ADICIONE ESTE BLOCO
    revisao_proativa.app()
elif selected_page == "Gerenciar Usuários":
    gerenciar_usuarios.app()
elif selected_page == "Relatórios":
    relatorios.app()