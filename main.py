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

# Configuração da página (layout wide é importante para o menu no topo)
st.set_page_config(
    page_title="Controle de Pátio PRO", 
    page_icon="🚚",
    layout="wide"
)

# --- O ANTIGO MENU LATERAL FOI REMOVIDO DAQUI ---

# --- NOVO MENU HORIZONTAL ---
# Usamos o componente 'option_menu' que importamos
# Ele retorna o nome do item selecionado, como o 'radio' fazia
selected_page = option_menu(
    menu_title=None,  # Não queremos um título para o menu
    options=["Página Principal", "Alocar Serviços", "Cadastro de Serviço", "Filas de Serviço", "Visão dos Boxes", "Serviços Concluídos", "Histórico por Veículo"],
    # Ícones da biblioteca Bootstrap Icons: https://icons.getbootstrap.com/
    icons=["house", "truck-front", "card-list", "card-checklist", "view-stacked", "check-circle", "clock-history"],
    menu_icon="cast",
    default_index=0,
    orientation="horizontal",
    styles={
        "container": {"padding": "0!important", "background-color": "#292929"},
        "icon": {"color": "#22a7f0", "font-size": "20px"}, 
        "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#444"},
        "nav-link-selected": {"background-color": "#1a1a1a"},
    }
)

# --- LÓGICA PARA EXIBIR A PÁGINA SELECIONADA ---

if selected_page == "Página Principal":
    st.title("Bem-vindo ao Sistema de Controle de Pátio PRO")
    st.markdown("---")
    st.header("Funcionalidades Principais:")
    st.write("""
    - **Cadastro de Veículos e Serviços:** Registre novos veículos e os serviços necessários.
    - **Alocação de Serviços:** Direcione os veículos para os boxes e funcionários disponíveis.
    - **Visão dos Boxes:** Monitore em tempo real o status de cada box de serviço.
    - **Filas de Serviço:** Acompanhe a ordem de chegada e o andamento dos serviços.
    - **Serviços Concluídos:** Veja um histórico cronológico de todas as visitas finalizadas.
    - **Histórico por Veículo:** Consulte o histórico detalhado de um veículo específico.
    """)
    st.info("Utilize o menu no topo para navegar entre as funcionalidades do sistema.")

elif selected_page == "Alocar Serviços":
    alocar_servicos.alocar_servicos()

elif selected_page == "Cadastro de Serviço":
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