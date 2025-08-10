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
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form', 'show_edit_responsavel_form', 'servicos_para_adicionar']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if state.get("search_triggered"):
        if state.get("veiculo_info") is None and not state.get("veiculo_id"):
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = "SELECT v.id, v.empresa, v.modelo, v.ano_modelo, v.nome_motorista, v.contato_motorista, v.cliente_id, c.nome_responsavel, c.contato_responsavel FROM veiculos v LEFT JOIN clientes c ON v.cliente_id = c.id WHERE v.placa = %s"
                        cursor.execute(query, (formatar_placa(state["placa_input"]),))
                        resultado = cursor.fetchone()
                        if resultado:
                            state["veiculo_id"] = resultado["id"]
                            state["veiculo_info"] = resultado
                finally:
                    release_connection(conn)

        if state.get("veiculo_id"):
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.subheader("Dados do Veículo")
                    st.markdown(
                        f"**Modelo:** {state['veiculo_info']['modelo']} | **Ano:** {state['veiculo_info']['ano_modelo'] or 'N/A'}\n\n"
                        f"**Motorista:** {state['veiculo_info']['nome_motorista'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_motorista'] or 'N/A'}"
                    )
                with col2:
                    if st.button("✏️ Alterar Veículo", use_container_width=True):
                        st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                        st.rerun()
            
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.subheader("Dados da Empresa")
                    st.markdown(
                        f"**Empresa:** {state['veiculo_info']['empresa']}\n\n"
                        f"**Responsável Frota:** {state['veiculo_info']['nome_responsavel'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_responsavel'] or 'N/A'}"
                    )
                with col2:
                    if st.button("✏️ Alterar Responsável", use_container_width=True):
                        st.session_state.show_edit_responsavel_form = not st.session_state.get('show_edit_responsavel_form', False)
                        st.rerun()

            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    st.info("Altere os dados específicos deste veículo.")
                    novo_modelo = st.text_input("Modelo", value=state['veiculo_info']['modelo'])
                    novo_ano_val = state['veiculo_info']['ano_modelo'] or datetime.now().year
                    novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(novo_ano_val), step=1)
                    novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                    novo_contato_motorista = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                    
                    if st.form_submit_button("✅ Salvar Dados do Veículo"):
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query_veiculo = "UPDATE veiculos SET modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s"
                                    cursor.execute(query_veiculo, (novo_modelo, novo_ano if novo_ano > 0 else None, novo_motorista, formatar_telefone(novo_contato_motorista), state['veiculo_id']))
                                    conn.commit()
                                st.success("Dados do veículo atualizados!")
                                st.session_state.show_edit_form = False
                                st.rerun()
                            finally:
                                release_connection(conn)

            if st.session_state.get('show_edit_responsavel_form', False):
                with st.form("form_edit_responsavel"):
                    st.info("Altere os dados do cliente (afeta todos os veículos desta empresa).")
                    nova_empresa = st.text_input("Nome da Empresa", value=state['veiculo_info']['empresa'])
                    novo_responsavel = st.text_input("Nome do Responsável pela Frota", value=state['veiculo_info']['nome_responsavel'])
                    novo_contato_responsavel = st.text_input("Contato do Responsável", value=state['veiculo_info']['contato_responsavel'])

                    if st.form_submit_button("✅ Salvar Dados da Empresa"):
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    if state['veiculo_info']['cliente_id']:
                                        query_cliente = "UPDATE clientes SET nome_empresa = %s, nome_responsavel = %s, contato_responsavel = %s WHERE id = %s"
                                        cursor.execute(query_cliente, (nova_empresa, novo_responsavel, formatar_telefone(novo_contato_responsavel), state['veiculo_info']['cliente_id']))
                                        # Atualiza também o nome da empresa na tabela de veículos para manter consistência
                                        cursor.execute("UPDATE veiculos SET empresa = %s WHERE cliente_id = %s", (nova_empresa, state['veiculo_info']['cliente_id']))
                                        conn.commit()
                                        st.success("Dados da empresa atualizados com sucesso!")
                                    else:
                                        st.warning("Este veículo não está vinculado a um cliente para atualizar os dados da empresa.")
                                st.session_state.show_edit_responsavel_form = False
                                st.rerun()
                            finally:
                                release_connection(conn)
            
            st.markdown("---")
            st.header("2️⃣ Seleção de Serviços")
            state["quilometragem"] = st.number_input("Quilometragem (Obrigatório)", min_value=1, step=1, value=state.get("quilometragem", 0) or None, key="km_servico", placeholder="Digite a KM...")
            
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
                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor() as cursor:
                                table_map = {"Borracharia": "servicos_solicitados_borracharia", "Alinhamento": "servicos_solicitados_alinhamento", "Mecânica": "servicos_solicitados_manutencao"}
                                for s in st.session_state.servicos_para_adicionar:
                                    table_name = table_map.get(s['area'])
                                    query = f"INSERT INTO {table_name} (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)"
                                    cursor.execute(query, (state["veiculo_id"], s['tipo'], s['qtd'], observacao_geral, state["quilometragem"], datetime.now(MS_TZ), datetime.now(MS_TZ)))
                                conn.commit()
                                st.success("✅ Serviços cadastrados com sucesso!")
                                state["search_triggered"] = False
                                state["placa_input"] = ""
                                st.session_state.servicos_para_adicionar = []
                                st.balloons()
                                st.rerun()
                        finally:
                            release_connection(conn)

        else: # Se o veículo não foi encontrado no banco
            st.warning("Veículo não encontrado no seu banco de dados.")
            if st.button("🔎 Buscar Dados Externos (API)", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso: st.session_state.api_vehicle_data = resultado
                    else: st.error(resultado)
                st.rerun()

            if 'api_vehicle_data' in st.session_state:
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
                with st.expander("Cadastrar Novo Veículo", expanded=True):
                    with st.form("form_novo_veiculo_rapido"):
                        st.subheader("Vincular a uma Empresa Cliente")
                        busca_empresa = st.text_input("Digite para buscar a empresa", help="Digite pelo menos 3 letras.")
                        
                        cliente_id_selecionado = None
                        nome_empresa_final = busca_empresa

                        if len(busca_empresa) >= 3:
                            resultados_busca = buscar_clientes_por_similaridade(busca_empresa)
                            if resultados_busca:
                                opcoes_cliente = {}
                                for id_cliente, nome_empresa, nome_fantasia in resultados_busca:
                                    texto_exibicao = nome_empresa
                                    if nome_fantasia and nome_fantasia.strip() and nome_fantasia.lower() != nome_empresa.lower():
                                        texto_exibicao += f" (Fantasia: {nome_fantasia})"
                                    opcoes_cliente[texto_exibicao] = id_cliente
                                
                                opcoes_cliente[f"Nenhum destes. Cadastrar '{busca_empresa}' como nova."] = None
                                
                                cliente_selecionado_str = st.selectbox("Selecione a empresa ou confirme o novo cadastro:", options=list(opcoes_cliente.keys()))
                                cliente_id_selecionado = opcoes_cliente[cliente_selecionado_str]
                                if cliente_id_selecionado:
                                    nome_empresa_final = next((item[1] for item in resultados_busca if item[0] == cliente_id_selecionado), busca_empresa)
                            else:
                                st.warning("Nenhuma empresa encontrada com nome similar. O nome digitado será usado para um novo cadastro de cliente.")
                        
                        st.markdown("---")
                        st.subheader("Dados do Veículo")
                        modelo_aceito = st.session_state.get('modelo_aceito', '')
                        ano_aceito_str = st.session_state.get('ano_aceito', '')
                        modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                        try:
                            default_year = int(ano_aceito_str) if ano_aceito_str else datetime.now().year
                        except (ValueError, TypeError): default_year = datetime.now().year
                        
                        ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=default_year, step=1)
                        nome_motorista = st.text_input("Nome do Motorista")
                        contato_motorista = st.text_input("Contato do Motorista")

                        if st.form_submit_button("Cadastrar e Continuar"):
                            if not all([nome_empresa_final, modelo]):
                                st.warning("É necessário selecionar ou digitar uma Empresa e preencher o Modelo do veículo.")
                            else:
                                placa_formatada = formatar_placa(state["placa_input"])
                                contato_formatado = formatar_telefone(contato_motorista)
                                conn = get_connection()
                                if conn:
                                    try:
                                        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                                            if not cliente_id_selecionado and nome_empresa_final:
                                                cursor.execute("INSERT INTO clientes (nome_empresa) VALUES (%s) RETURNING id", (nome_empresa_final,))
                                                cliente_id_selecionado = cursor.fetchone()['id']

                                            query_insert = """
                                                INSERT INTO veiculos (placa, empresa, modelo, ano_modelo, nome_motorista, contato_motorista, cliente_id, data_entrada) 
                                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                                            """
                                            cursor.execute(query_insert, (placa_formatada, nome_empresa_final, modelo, ano_modelo if ano_modelo > 1950 else None, nome_motorista, contato_formatado, cliente_id_selecionado, datetime.now(MS_TZ)))
                                            conn.commit()
                                            
                                            st.success("🚚 Veículo cadastrado com sucesso! A página será recarregada.")
                                            state['search_triggered'] = False
                                            for key in ['modelo_aceito', 'ano_aceito']:
                                                if key in st.session_state: del st.session_state[key]
                                            st.rerun()
                                    finally:
                                        release_connection(conn)

    if state.get("placa_input"):
        if st.button("Limpar e Iniciar Nova Busca"):
            keys_to_delete = ['cadastro_servico_state', 'servicos_para_adicionar', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form']
            for key in keys_to_delete:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()