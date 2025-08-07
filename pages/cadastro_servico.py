import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, consultar_placa_comercial

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")
    
    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
    # Dicionário principal para o fluxo de busca
    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = { "placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0 }
    state = st.session_state.cadastro_servico_state

    # Lista de serviços a serem adicionados ("carrinho de compras")
    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []
    
    st.markdown("---")
    st.header("1️⃣ Identificação do Veículo")

    # --- CAMPO DE PLACA E BOTÃO DE BUSCA NA API ---
    col_placa, col_botao = st.columns([0.7, 0.3])
    with col_placa:
        placa_input = st.text_input("Digite a placa do veículo", value=state["placa_input"], key="placa_input_cadastro_servico", label_visibility="collapsed").upper()
    
    with col_botao:
        if st.button("🔎 Buscar Dados da Placa", use_container_width=True):
            if placa_input:
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(placa_input)
                    if sucesso:
                        # Guarda os dados da API em um estado temporário para confirmação
                        st.session_state.api_vehicle_data = resultado
                    else:
                        st.error(resultado)
            else:
                st.warning("Digite uma placa para consultar.")
    
    # --- LÓGICA DE LIMPEZA AO MUDAR DE PLACA ---
    if placa_input != state["placa_input"]:
        state["placa_input"] = placa_input
        state["veiculo_id"], state["veiculo_info"] = None, None
        # Limpa todos os estados temporários
        for key in ['show_edit_form', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'servicos_para_adicionar']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    # --- FLUXO DE CONFIRMAÇÃO DOS DADOS DA API ---
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

    # --- FLUXO PRINCIPAL: BUSCA NO BANCO OU MOSTRA CADASTRO ---
    # Só executa se não estivermos no meio de uma confirmação da API
    if state["placa_input"] and not st.session_state.get('api_vehicle_data'):
        # Tenta buscar o veículo no banco de dados local
        if state["veiculo_id"] is None:
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = "SELECT id, empresa, modelo, ano_modelo, nome_motorista, contato_motorista FROM veiculos WHERE placa = %s"
                        cursor.execute(query, (state["placa_input"],))
                        resultado = cursor.fetchone()
                        if resultado:
                            state["veiculo_id"], state["veiculo_info"] = resultado["id"], resultado
                        else:
                            st.info("Veículo não encontrado em seu banco. Cadastre-o abaixo.")
                finally:
                    release_connection(conn)

        # SE O VEÍCULO EXISTE, exibe os dados e o botão de edição
        if state["veiculo_id"]:
            col1, col2 = st.columns([0.7, 0.3])
            with col1:
                st.success(
                    f"Veículo: **{state['veiculo_info']['modelo']}** | Ano: **{state['veiculo_info']['ano_modelo'] or 'N/A'}**\n\n"
                    f"Empresa: **{state['veiculo_info']['empresa']}**\n\n"
                    f"Motorista: **{state['veiculo_info']['nome_motorista'] or 'Não informado'}** | "
                    f"Contato: **{state['veiculo_info']['contato_motorista'] or 'Não informado'}**"
                )
            with col2:
                if st.button("🔄 Alterar Dados", use_container_width=True):
                    st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                    st.rerun()

            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    st.info("Altere os dados do veículo e salve.")
                    nova_empresa = st.text_input("Empresa", value=state['veiculo_info']['empresa'])
                    novo_modelo = st.text_input("Modelo", value=state['veiculo_info']['modelo'])
                    novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(state['veiculo_info']['ano_modelo'] or 0), step=1)
                    novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                    novo_contato = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                    if st.form_submit_button("✅ Salvar Alterações"):
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query = "UPDATE veiculos SET empresa = %s, modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s"
                                    cursor.execute(query, (nova_empresa, novo_modelo, novo_ano if novo_ano > 0 else None, novo_motorista, novo_contato, state['veiculo_id']))
                                    conn.commit()
                                
                                # Atualiza o estado da sessão para refletir na tela
                                state['veiculo_info'].update({
                                    'empresa': nova_empresa, 'modelo': novo_modelo, 'ano_modelo': novo_ano,
                                    'nome_motorista': novo_motorista, 'contato_motorista': novo_contato
                                })
                                st.session_state.show_edit_form = False
                                st.success("Dados do veículo atualizados!")
                                st.rerun()
                            finally:
                                release_connection(conn)
        
        # SE O VEÍCULO NÃO EXISTE, exibe o formulário de cadastro
        else:
            with st.expander("Cadastrar Novo Veículo", expanded=True):
                with st.form("form_novo_veiculo_rapido"):
                    empresa = st.text_input("Empresa *")
                    
                    modelo_aceito = st.session_state.get('modelo_aceito', '')
                    ano_aceito = st.session_state.get('ano_aceito', 0)
                    
                    modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                    ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=int(ano_aceito if ano_aceito else 0), step=1)
                    
                    nome_motorista = st.text_input("Nome do Motorista")
                    contato_motorista = st.text_input("Contato do Motorista")

                    if st.form_submit_button("Cadastrar e Continuar"):
                        if not all([empresa, modelo]):
                            st.warning("Empresa e Modelo são obrigatórios.")
                        else:
                            conn = get_connection()
                            if conn:
                                try:
                                    with conn.cursor() as cursor:
                                        query = """
                                            INSERT INTO veiculos (placa, empresa, modelo, ano_modelo, nome_motorista, contato_motorista, data_entrada) 
                                            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                                        """
                                        cursor.execute(query, (state["placa_input"], empresa, modelo, ano_modelo if ano_modelo > 0 else None, nome_motorista, contato_motorista, datetime.now(MS_TZ)))
                                        new_id = cursor.fetchone()[0]
                                        conn.commit()
                                        
                                        for key in ['modelo_aceito', 'ano_aceito']:
                                            if key in st.session_state: del st.session_state[key]
                                        st.success("🚚 Veículo cadastrado com sucesso!")
                                        st.rerun()
                                finally:
                                    release_connection(conn)

    # --- SEÇÃO 2: SELEÇÃO DE SERVIÇOS ---
    if state["veiculo_id"]:
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
            servicos_a_cadastrar = st.session_state.servicos_para_adicionar
            if not servicos_a_cadastrar:
                st.warning("⚠️ Nenhum serviço foi adicionado à lista.")
            elif not state["quilometragem"] or state["quilometragem"] <= 0:
                st.error("❌ A quilometragem é obrigatória e deve ser maior que zero.")
            else:
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            table_map = {"Borracharia": "servicos_solicitados_borracharia", "Alinhamento": "servicos_solicitados_alinhamento", "Mecânica": "servicos_solicitados_manutencao"}
                            for s in servicos_a_cadastrar:
                                table_name = table_map.get(s['area'])
                                query = f"INSERT INTO {table_name} (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)"
                                cursor.execute(query, (state["veiculo_id"], s['tipo'], s['qtd'], observacao_geral, state["quilometragem"], datetime.now(MS_TZ), datetime.now(MS_TZ)))
                            conn.commit()
                            st.success("✅ Serviços cadastrados com sucesso!")
                            st.session_state.servicos_para_adicionar = []
                            st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
                            st.balloons()
                            st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erro ao salvar serviços: {e}")
                    finally:
                        release_connection(conn)

    # Botão de limpar a tela (só aparece se houver uma placa digitada)
    if state["placa_input"]:
        if st.button("Limpar tela e iniciar novo cadastro"):
            # Limpa todos os estados da sessão relevantes para esta página
            for key in ['cadastro_servico_state', 'servicos_para_adicionar', 'api_vehicle_data', 'modelo_aceito', 'ano_aceito']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()