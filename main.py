import streamlit as st
from pages import cadastro_veiculo, filas_servico, execucao_servico

st.set_page_config(page_title="Controle de Pátio", layout="wide")

st.sidebar.title("Menu")
page = st.sidebar.radio("Ir para", ["Cadastro de Veículo", "Filas de Serviço", "Execução de Serviço"])

if page == "Cadastro de Veículo":
    cadastro_veiculo.app()
elif page == "Filas de Serviço":
    filas_servico.app()
elif page == "Execução de Serviço":
    execucao_servico.app()
