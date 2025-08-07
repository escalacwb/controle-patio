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
            "search_triggered": False # Novo estado para controlar a busca
        }
    state = st.session_state.cadastro_servico_state

    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []
    
    st.markdown("---")
    st.header("1️⃣ Identificação do Veículo")

    # --- NOVO FLUXO DE BUSCA ---
    placa_input = st.text_input("Digite a placa do veículo", value=state.get("placa_input", ""), key="placa_input_key").upper()

    # Botão principal para iniciar a verificação
    if st.button("Verificar Placa no Sistema", use_container_width=True, type="primary"):
        # Atualiza o estado com a placa digitada e dispara a busca
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        # Limpa os dados de buscas anteriores para garantir consistência
        state["veiculo_id"] = None
        state["veiculo_info"] = None
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # A lógica principal da página só é executada se uma busca foi disparada
    if state.get("search_triggered"):
        
        # Passo 1: Tenta buscar o veículo no banco de dados local (apenas uma vez)
        if state.get("veiculo_info") is None:
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

        # --- FLUXO 1: SE O VEÍCULO FOI ENCONTRADO NO BANCO ---
        if state.get("veiculo_id"):
            # Exibe os dados do veículo e o botão para alterar
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

            # Formulário de edição
            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    st.info("Altere os dados do veículo e salve.")
                    nova_empresa = st.text_input("Empresa", value=state['veiculo_info']['empresa'])
                    novo_modelo = st.text_input("Modelo", value=state['veiculo_info']['modelo'])
                    novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(state['veiculo_info']['ano_modelo'] or datetime.now().year), step=1)
                    novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                    novo_contato = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                    
                    if st.form_submit_button("✅ Salvar Alterações"):
                        contato_formatado = formatar_telefone(novo_contato)
                        conn = get_connection()
                        if conn:
                            # (Lógica para salvar a edição no banco)
                            pass
            
            # SEÇÃO DE SELEÇÃO DE SERVIÇOS (aparece junto com os dados do veículo)
            st.markdown("---")
            st.header("2️⃣ Seleção de Serviços")
            # (O código para selecionar serviços, adicionar à lista, etc., entra aqui)
            pass

        # --- FLUXO 2: SE O VEÍCULO NÃO FOI ENCONTRADO NO BANCO ---
        else:
            st.warning("Veículo não encontrado no seu banco de dados. Para cadastrá-lo, busque os dados na API ou preencha manualmente abaixo.")
            
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso:
                        st.session_state.api_vehicle_data = resultado
                    else:
                        st.error(resultado)
                st.rerun()

            # Lógica de confirmação da API
            if 'api_vehicle_data' in st.session_state and st.session_state.api_vehicle_data:
                # (código da caixa de diálogo de confirmação permanece o mesmo)
                pass

            # Formulário de cadastro de novo veículo
            if not st.session_state.get('api_vehicle_data'):
                with st.expander("Cadastrar Novo Veículo Manualmente", expanded=True):
                    with st.form("form_novo_veiculo_rapido"):
                        # (código do formulário de novo cadastro permanece o mesmo)
                        pass

    # Botão de limpar a tela (visível se algo foi digitado)
    if state["placa_input"]:
        if st.button("Limpar e Iniciar Nova Busca"):
            # Limpa todos os estados da sessão
            for key in list(st.session_state.keys()):
                if key.startswith("cadastro_servico") or key in ['servicos_para_adicionar', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form']:
                    del st.session_state[key]
            st.rerun()