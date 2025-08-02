import streamlit as st
from streamlit_option_menu import option_menu
from pages import (
    alocar_servicos,
    cadastro_servico,
    cadastro_veiculo,
    filas_servico,
    visao_boxes,
    servicos_concluidos,
    historico_veiculo
)

# Configuração da página
st.set_page_config(
    page_title="Controle de Pátio PRO", 
    page_icon="🚚",
    layout="wide"
)

# --- MENU HORIZONTAL MODIFICADO ---

# 1. Removida a "Página Principal" das opções e dos ícones.
# 2. Adicionado um estilo para esconder o texto do link e ajustar o espaçamento.
selected_page = option_menu(
    menu_title=None,
    options=["Alocar Serviços", "Cadastro de Serviço", "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", "Histórico por Veículo"],
    icons=["truck-front", "card-list", "card-checklist", "view-stacked", "check-circle", "clock-history"],
    menu_icon="cast",
    default_index=0, # O padrão agora será "Alocar Serviços"
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#292929"},
        "icon": {"color": "#22a7f0", "font-size": "25px"}, # Ícones um pouco maiores
        "nav-link": {
            "font-size": "16px",
            "text-align": "center",
            "margin": "0px",
            "--hover-color": "#444",
            "padding": "10px 0px" # Ajusta o padding vertical
        },
        "nav-link-selected": {"background-color": "#1a1a1a"},
        # Este trecho esconde o texto dos botões, deixando só os ícones
        ".nav-link-text": {"display": "none"}
    }
)

# --- LÓGICA DE EXIBIÇÃO DE PÁGINA ATUALIZADA ---
# O bloco da "Página Principal" foi removido.

if selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()

elif selected_page == "Cadastro de Serviço":
    # Supondo que o nome da função em cadastro_servico.py é 'app'
    cadastro_servico.app()

elif selected_page == "Cadastro de Veículo":
    # Supondo que o nome da função em cadastro_veiculo.py seja 'app'
    cadastro_veiculo.app()

elif selected_page == "Filas de Serviço":
    filas_servico.app()

elif selected_page == "Visão dos Boxes":
    visao_boxes.visao_boxes()

elif selected_page == "Serviços Concluídos":
    servicos_concluidos.app()

elif selected_page == "Histórico por Veículo":
    historico_veiculo.app()