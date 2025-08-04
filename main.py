import streamlit as st
from streamlit_option_menu import option_menu
import login
from pages import (
    alocar_servicos,
    cadastro_servico,
    cadastro_veiculo,
    filas_servico,
    visao_boxes,
    servicos_concluidos,
    historico_veiculo,
    gerenciar_usuarios,
    relatorios # Importa a nova página
)

st.set_page_config(page_title="Controle de Pátio PRO", layout="wide")

if not st.session_state.get('logged_in'):
    login.render_login_page()
    st.stop()

with st.sidebar:
    st.success(f"Logado como: **{st.session_state.get('user_name')}**")
    if st.button("Logout", use_container_width=True, type="secondary"):
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

# --- LÓGICA DE MENU DINÂMICO ---
options = ["Alocar Serviços", "Cadastro de Serviço", "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", "Histórico por Veículo"]
icons = ["truck-front", "card-list", "card-checklist", "view-stacked", "check-circle", "clock-history"]

if st.session_state.get('user_role') == 'admin':
    options.append("Gerenciar Usuários")
    icons.append("people-fill")
    options.append("Relatórios") # Adiciona a opção de Relatórios
    icons.append("graph-up")     # Ícone para Relatórios

selected_page = option_menu(
    menu_title=None, options=options, icons=icons, menu_icon="cast",
    default_index=0, orientation="horizontal",
    styles={ # (seus estilos aqui, sem alteração)
        "container": {"padding": "0!important", "background-color": "#292929"},
        "icon": {"color": "#22a7f0", "font-size": "25px"},
        "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
        "nav-link-selected": {"background-color": "#1a1a1a"},
    }
)

# --- LÓGICA DE EXIBIÇÃO DE PÁGINA ATUALIZADA ---
if selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()
elif selected_page == "Cadastro de Serviço":
    cadastro_servico.app()
# ... (elif para as outras páginas sem alteração) ...
elif selected_page == "Histórico por Veículo":
    historico_veiculo.app()
elif selected_page == "Gerenciar Usuários":
    gerenciar_usuarios.app()
elif selected_page == "Relatórios": # Adiciona o roteamento para a nova página
    relatorios.app()

# O código completo do main.py está abaixo para garantir
# (Copie a partir daqui para substituir o seu arquivo inteiro)

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
elif selected_page == "Relatórios":
    relatorios.app()