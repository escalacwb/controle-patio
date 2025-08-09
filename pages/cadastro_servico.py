import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa, buscar_clientes_por_similaridade

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")

    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = {
            "placa_input": "", "veiculo_id": None, "veiculo_info": None,
            "search_triggered": False, "quilometragem": 0
        }
    state = st.session_state.cadastro_servico_state

    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []

    st.markdown("---")
    st.header("1️⃣ Identificação do Veículo")

    placa_input = st.text_input("Digite a placa do veículo", value=state.get("placa_input", ""), key="placa_input_key").upper()

    if st.button("Verificar Placa no Sistema", use_container_width=True, type="primary"):
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        state["veiculo_id"] = None
        state["veiculo_info"] = None
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form', 'servicos_para_adicionar']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if state.get("search_triggered"):
        if state.get("veiculo_info") is None and not state.get("veiculo_id"):
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = """
                            SELECT 
                                v.id, v.empresa, v.modelo, v.ano_modelo, 
                                v.nome_motorista, v.contato_motorista, v.cliente_id,
                                c.nome_responsavel, c.contato_responsavel
                            FROM veiculos v
                            LEFT JOIN clientes c ON v.cliente_id = c.id
                            WHERE v.placa = %s
                        """
                        cursor.execute(query, (formatar_placa(state["placa_input"]),))
                        resultado = cursor.fetchone()
                        if resultado:
                            state["veiculo_id"] = resultado["id"]
                            state["veiculo_info"] = resultado
                finally:
                    release_connection(conn)

        if state.get("veiculo_id"):
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.success(
                    f"**Veículo Encontrado:** {state['veiculo_info']['modelo']} | **Ano:** {state['veiculo_info']['ano_modelo'] or 'N/A'}\n\n"
                    f"**Empresa:** {state['veiculo_info']['empresa']}\n\n"
                    f"**Motorista:** {state['veiculo_info']['nome_motorista'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_motorista'] or 'N/A'}\n\n"
                    f"**Responsável Frota:** {state['veiculo_info']['nome_responsavel'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_responsavel'] or 'N/A'}"
                )
            with col2:
                if st.button("🔄 Alterar Dados", use_container_width=True):
                    st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                    st.rerun()

            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    # ... (código completo do formulário de edição)
                    pass
            
            st.markdown("---")
            st.header("2️⃣ Seleção de Serviços")
            # ... (código completo da seleção de serviços)
            pass

        else: # Se o veículo não foi encontrado no banco
            st.warning("Veículo não encontrado no seu banco de dados.")
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso: st.session_state.api_vehicle_data = resultado
                    else: st.error(resultado)
                st.rerun()

            if 'api_vehicle_data' in st.session_state:
                # ... (código completo do diálogo de confirmação da API)
                pass
            
            if not st.session_state.get('api_vehicle_data'):
                with st.expander("Cadastrar Novo Veículo", expanded=True):
                    with st.form("form_novo_veiculo_rapido"):
                        # ... (código completo do formulário de novo cadastro)
                        pass

    if state.get("placa_input"):
        if st.button("Limpar e Iniciar Nova Busca"):
            # ... (código completo do botão de limpar)
            pass