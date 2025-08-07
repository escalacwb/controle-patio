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
            "placa_input": "", 
            "veiculo_id": None, 
            "veiculo_info": None,
            "search_triggered": False # Novo estado para controlar a busca
        }
    state = st.session_state.cadastro_servico_state

    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []
    
    st.markdown("---")
    st.header("1️⃣ Identificação do Veículo")

    # --- NOVO FLUXO DE BUSCA ---
    placa_input = st.text_input("Digite a placa do veículo", value=state["placa_input"], key="placa_input_key").upper()

    # Botão principal para verificar a placa no banco de dados local
    if st.button("Verificar Placa", use_container_width=True, type="primary"):
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        # Limpa estados antigos para garantir uma busca limpa
        for key in ['veiculo_id', 'veiculo_info', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
            if key in state: state[key] = None
            if key in st.session_state: del st.session_state[key]
        st.rerun()

    # A lógica de busca só é executada após o botão ser clicado
    if state["search_triggered"]:
        # 1. Tenta buscar o veículo no banco de dados local
        if state["veiculo_id"] is None:
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = "SELECT id, empresa, modelo, ano_modelo, nome_motorista, contato_motorista FROM veiculos WHERE placa = %s"
                        cursor.execute(query, (formatar_placa(state["placa_input"]),))
                        resultado = cursor.fetchone()
                        if resultado:
                            state["veiculo_id"], state["veiculo_info"] = resultado["id"], resultado
                finally:
                    release_connection(conn)

        # 2. Se o veículo FOI encontrado no banco, exibe os dados
        if state["veiculo_id"]:
            st.success(
                f"Veículo encontrado no banco!\n\n"
                f"**Modelo:** {state['veiculo_info']['modelo']} | **Ano:** {state['veiculo_info']['ano_modelo'] or 'N/A'}\n\n"
                f"**Empresa:** {state['veiculo_info']['empresa']}"
            )
            # (A lógica de editar dados e adicionar serviços aparecerá mais abaixo)

        # 3. Se o veículo NÃO foi encontrado, oferece a busca na API
        else:
            st.warning("Veículo não encontrado no seu banco de dados.")
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso:
                        st.session_state.api_vehicle_data = resultado
                    else:
                        st.error(resultado)
                st.rerun()

    # --- FLUXO DE CONFIRMAÇÃO DOS DADOS DA API ---
    if 'api_vehicle_data' in st.session_state:
        # (Esta seção permanece a mesma, com a tabela de confirmação)
        ...

    # --- FORMULÁRIO DE CADASTRO DE NOVO VEÍCULO ---
    # Aparece se a busca foi feita, o veículo não foi encontrado e não estamos na tela de confirmação da API
    if state["search_triggered"] and not state["veiculo_id"] and not st.session_state.get('api_vehicle_data'):
        with st.expander("Cadastrar Novo Veículo", expanded=True):
            # CORREÇÃO: Usar st.form_submit_button dentro do form
            with st.form("form_novo_veiculo_rapido"):
                empresa = st.text_input("Empresa *")
                
                modelo_aceito = st.session_state.get('modelo_aceito', '')
                ano_aceito_str = st.session_state.get('ano_aceito', '')

                modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                
                # CORREÇÃO: Lógica segura para o valor padrão do ano
                try:
                    default_year = int(ano_aceito_str)
                except (ValueError, TypeError):
                    default_year = datetime.now().year
                
                ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=default_year, step=1)
                
                nome_motorista = st.text_input("Nome do Motorista")
                contato_motorista = st.text_input("Contato do Motorista")

                # CORREÇÃO: Usando o botão de submissão correto
                if st.form_submit_button("Cadastrar e Continuar"):
                    if not all([empresa, modelo]):
                        st.warning("Empresa e Modelo são obrigatórios.")
                    else:
                        placa_formatada = formatar_placa(state["placa_input"])
                        contato_formatado = formatar_telefone(contato_motorista)
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query = """
                                        INSERT INTO veiculos (placa, empresa, modelo, ano_modelo, nome_motorista, contato_motorista, data_entrada) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                                    """
                                    cursor.execute(query, (placa_formatada, empresa, modelo, ano_modelo if ano_modelo > 1950 else None, nome_motorista, contato_formatado, datetime.now(MS_TZ)))
                                    new_id = cursor.fetchone()[0]
                                    conn.commit()
                                    
                                    for key in ['modelo_aceito', 'ano_aceito']:
                                        if key in st.session_state: del st.session_state[key]
                                    st.success("🚚 Veículo cadastrado com sucesso!")
                                    # Reseta o estado para permitir uma nova busca
                                    st.session_state.cadastro_servico_state = { "placa_input": placa_formatada, "search_triggered": False }
                                    st.rerun()
                            finally:
                                release_connection(conn)

    # --- SEÇÃO 2: SELEÇÃO DE SERVIÇOS ---
    # Só aparece se um veículo do nosso banco estiver selecionado
    if state["veiculo_id"]:
        # (O restante do código, com a seleção de serviços, permanece aqui, sem alterações)
        ...

    # Botão de limpar a tela
    if state["placa_input"]:
        if st.button("Limpar tela e iniciar nova busca"):
            # Limpa todos os estados da sessão
            for key in list(st.session_state.keys()):
                if key in ['cadastro_servico_state', 'servicos_para_adicionar', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
                    del st.session_state[key]
            st.rerun()