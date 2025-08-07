import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")
    
    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = {
            "placa_input": "", "veiculo_id": None, "veiculo_info": None,
            "search_triggered": False 
        }
    state = st.session_state.cadastro_servico_state

    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []
    
    st.markdown("---")
    st.header("1️⃣ Identificação do Veículo")

    placa_input = st.text_input("Digite a placa do veículo", value=state.get("placa_input", ""), key="placa_input_key").upper()

    if st.button("Verificar Placa", use_container_width=True, type="primary"):
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        state["veiculo_id"] = None
        state["veiculo_info"] = None
        # Limpa estados temporários
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # --- LÓGICA PRINCIPAL EXECUTADA APÓS O BOTÃO SER PRESSIONADO ---
    if state.get("search_triggered"):
        # Passo 1: Buscar no banco de dados local
        conn = get_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = "SELECT id, empresa, modelo, ano_modelo, nome_motorista, contato_motorista FROM veiculos WHERE placa = %s"
                    cursor.execute(query, (formatar_placa(state["placa_input"]),))
                    resultado = cursor.fetchone()
                    if resultado:
                        state["veiculo_id"] = resultado["id"]
                        state["veiculo_info"] = resultado
            finally:
                release_connection(conn)

        # --- FLUXO 1: VEÍCULO FOI ENCONTRADO NO BANCO DE DADOS ---
        if state.get("veiculo_id"):
            # Exibe os dados do veículo
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.success(
                    f"**Veículo Encontrado:** {state['veiculo_info']['modelo']} | **Ano:** {state['veiculo_info']['ano_modelo'] or 'N/A'}\n\n"
                    f"**Empresa:** {state['veiculo_info']['empresa']}\n\n"
                    f"**Motorista:** {state['veiculo_info']['nome_motorista'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_motorista'] or 'N/A'}"
                )
            with col2:
                if st.button("🔄 Alterar Dados", use_container_width=True):
                    st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                    st.rerun()

            # Lógica para o formulário de edição
            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    # (código do formulário de edição permanece o mesmo)
                    pass

            # Exibe a seção de seleção de serviços
            st.markdown("---")
            st.header("2️⃣ Seleção de Serviços")
            # (código da seleção de serviços permanece o mesmo)
            pass
        
        # --- FLUXO 2: VEÍCULO NÃO FOI ENCONTRADO NO BANCO ---
        else:
            st.warning("Veículo não encontrado no seu banco de dados.")
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso: st.session_state.api_vehicle_data = resultado
                    else: st.error(resultado)
                st.rerun()

            # Lógica de confirmação da API
            if 'api_vehicle_data' in st.session_state:
                # (código da caixa de diálogo de confirmação permanece o mesmo)
                pass

            # Formulário de cadastro de novo veículo
            if not st.session_state.get('api_vehicle_data'):
                with st.expander("Cadastrar Novo Veículo", expanded=True):
                    with st.form("form_novo_veiculo_rapido"):
                        # (código do formulário de novo cadastro permanece o mesmo)
                        pass

    # Botão para limpar a tela
    if st.button("Limpar tela e iniciar nova busca"):
        # (lógica de limpeza permanece a mesma)
        pass