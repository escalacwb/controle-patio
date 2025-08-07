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
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # --- LÓGICA PRINCIPAL EXECUTADA APÓS O BOTÃO SER PRESSIONADO ---
    if state.get("search_triggered"):
        # Busca no banco de dados local (só roda uma vez por busca)
        if state.get("veiculo_info") is None and state.get("placa_input"):
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

        # --- FLUXO 1: VEÍCULO FOI ENCONTRADO NO BANCO ---
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
                    novo_ano_val = state['veiculo_info']['ano_modelo'] or datetime.now().year
                    novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(novo_ano_val), step=1)
                    novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                    novo_contato = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                    
                    if st.form_submit_button("✅ Salvar Alterações"):
                        contato_formatado = formatar_telefone(novo_contato)
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query = "UPDATE veiculos SET empresa = %s, modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s"
                                    cursor.execute(query, (nova_empresa, novo_modelo, novo_ano if novo_ano > 0 else None, novo_motorista, contato_formatado, state['veiculo_id']))
                                    conn.commit()
                                
                                state['veiculo_info'].update({
                                    'empresa': nova_empresa, 'modelo': novo_modelo, 'ano_modelo': novo_ano,
                                    'nome_motorista': novo_motorista, 'contato_motorista': contato_formatado
                                })
                                st.session_state.show_edit_form = False
                                st.success("Dados do veículo atualizados!")
                                st.rerun()
                            finally:
                                release_connection(conn)
            
            # --- SEÇÃO DE SELEÇÃO DE SERVIÇOS (AGORA DENTRO DO BLOCO CORRETO) ---
            st.markdown("---")
            st.header("2️⃣ Seleção de Serviços")
            km_value = state.get("quilometragem") if state.get("quilometragem") else None
            state["quilometragem"] = st.number_input("Quilometragem (Obrigatório)", min_value=1, step=1, value=km_value, key="km_servico", placeholder="Digite a KM...")
            
            servicos_do_banco = get_catalogo_servicos()
            
            def area_de_servico(nome_area, chave_area):
                st.subheader(nome_area)
                servicos_disponiveis = servicos_do_banco.get(chave_area, [])
                col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
                with col1:
                    servico_selecionado = st.selectbox(f"Selecione o serviço de {nome_area}", options=[""] + servicos_disponiveis, key=f"select_{chave_area}", label_visibility="collapsed")
                with col2:
                    quantidade = st.number_input("Qtd", min_value=1, value=1, step=1, key=f"qtd_{chave_area}", label_visibility="collapsed")
                with col3:
                    if st.button("➕ Adicionar", key=f"add_{chave_area}", use_container_width=True):
                        if servico_selecionado:
                            st.session_state.servicos_para_adicionar.append({"area": nome_area, "tipo": servico_selecionado, "qtd": quantidade})
                            st.rerun()
                        else:
                            st.warning("Por favor, selecione um serviço para adicionar.")

            area_de_servico("Borracharia", "borracharia")
            area_de_servico("Alinhamento", "alinhamento")
            area_de_servico("Mecânica", "manutencao")

            st.markdown("---")

            if st.session_state.servicos_para_adicionar:
                st.subheader("Serviços na Lista para Cadastro:")
                for i, servico in enumerate(st.session_state.servicos_para_adicionar):
                    col_serv, col_qtd, col_del = st.columns([0.7, 0.15, 0.15])
                    col_serv.write(f"**{servico['area']}**: {servico['tipo']}")
                    col_qtd.write(f"Qtd: {servico['qtd']}")
                    if col_del.button("❌ Remover", key=f"del_{i}", use_container_width=True):
                        st.session_state.servicos_para_adicionar.pop(i)
                        st.rerun()
            
            observacao_geral = st.text_area("Observações gerais para todos os serviços")
            
            st.markdown("---")
            if st.button("Registrar todos os serviços da lista", type="primary"):
                if not st.session_state.servicos_para_adicionar:
                    st.warning("⚠️ Nenhum serviço foi adicionado à lista.")
                elif not state["quilometragem"] or state["quilometragem"] <= 0:
                    st.error("❌ A quilometragem é obrigatória e deve ser maior que zero.")
                else:
                    # Lógica de salvar no banco
                    pass # Mantenha sua lógica de salvar aqui

        # --- FLUXO 2: VEÍCULO NÃO FOI ENCONTRADO NO BANCO ---
        else:
            st.warning("Veículo não encontrado no seu banco de dados.")
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso: st.session_state.api_vehicle_data = resultado
                    else: st.error(resultado)
                st.rerun()

            if 'api_vehicle_data' in st.session_state and st.session_state.api_vehicle_data:
                api_data = st.session_state.api_vehicle_data
                with st.container(border=True):
                    st.subheader("Dados Encontrados na API")
                    st.markdown(f"**Marca/Modelo:** `{api_data.get('modelo', 'N/A')}`")
                    st.markdown(f"**Ano do Modelo:** `{api_data.get('anoModelo', 'N/A')}`")
                    
                    confirm_col, cancel_col = st.columns(2)
                    with confirm_col:
                        if st.button("✅ Aceitar Dados", use_container_width=True, type="primary"):
                            st.session_state.modelo_aceito = api_data.get('modelo')
                            st.session_state.ano_aceito = api_data.get('anoModelo')
                            del st.session_state.api_vehicle_data 
                            st.rerun()
                    with cancel_col:
                        if st.button("❌ Cancelar", use_container_width=True):
                            del st.session_state.api_vehicle_data
                            st.rerun()
            
            if not st.session_state.get('api_vehicle_data'):
                with st.expander("Cadastrar Novo Veículo Manualmente", expanded=True):
                    with st.form("form_novo_veiculo_rapido"):
                        empresa = st.text_input("Empresa *")
                        modelo_aceito = st.session_state.get('modelo_aceito', '')
                        ano_aceito_str = st.session_state.get('ano_aceito', '')
                        modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                        try:
                            default_year = int(ano_aceito_str)
                        except (ValueError, TypeError):
                            default_year = datetime.now().year
                        
                        ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=default_year, step=1)
                        nome_motorista = st.text_input("Nome do Motorista")
                        contato_motorista = st.text_input("Contato do Motorista")

                        if st.form_submit_button("Cadastrar e Continuar"):
                             # Lógica para salvar novo veículo no banco
                            pass
                            
    # Botão para limpar a tela e começar de novo
    if state["placa_input"]:
        if st.button("Limpar e Iniciar Nova Busca"):
            # Limpa todos os estados da sessão
            for key in list(st.session_state.keys()):
                if key in ['cadastro_servico_state', 'servicos_para_adicionar', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form']:
                    del st.session_state[key]
            st.rerun()