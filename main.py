import streamlit as st
from pages import (
    alocar_servicos,
    cadastro_servico,
    cadastro_veiculo,
    filas_servico,
    visao_boxes,
    historico_veiculo,
    servicos_concluidos
)

# --- CORREÇÃO DA LISTA VAZIA ---
# Esta linha limpa o cache de dados toda vez que o app é iniciado.
st.cache_data.clear()

# Configuração da página
st.set_page_config(
    page_title="Controle de Pátio PRO", 
    page_icon="🚚",
    layout="wide"
)

def load_css(file_name):
    try:
        with open(file_name, encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Arquivo de estilo '{file_name}' não encontrado.")

load_css("style.css")

st.sidebar.title("Menu de Navegação")

PAGES = {
    "Página Principal": None,
    "Alocar Serviços": alocar_servicos,
    "Cadastro de Serviço": cadastro_servico,
    "Cadastro de Veículo": cadastro_veiculo,
    "Filas de Serviço": filas_servico,
    "Visão dos Boxes": visao_boxes,
    "Serviços Concluídos": servicos_concluidos,
    "Histórico por Veículo": historico_veiculo
}

selection = st.sidebar.radio("Ir para:", list(PAGES.keys()), key="menu_principal")

page = PAGES[selection]

if page:
    if hasattr(page, 'app'):
        page.app()
    elif hasattr(page, 'alocar_servicos'):
        page.alocar_servicos()
    elif hasattr(page, 'visao_boxes'):
        page.visao_boxes()
    else:
        st.error(f"A página '{selection}' não tem uma função de inicialização conhecida.")
else:
    st.title("Bem-vindo ao Sistema de Controle de Pátio PRO")
    st.markdown("---")
    st.header("Funcionalidades Principais:")
    st.write("""
    - Cadastro de Veículos e Serviços
    - Alocação de Serviços
    - Visão dos Boxes
    - Filas de Serviço
    - Serviços Concluídos
    - Histórico por Veículo
    """)
    st.info("Utilize o menu na barra lateral para navegar.")