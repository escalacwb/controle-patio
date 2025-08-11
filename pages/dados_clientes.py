# /pages/dados_clientes.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import formatar_telefone
import psycopg2.extras

def app():
    st.title("📇 Dados de Clientes")
    st.markdown("Pesquise, visualize e edite os dados dos clientes e seus veículos.")

    # --- INICIALIZAÇÃO E LÓGICA DE ESTADO ---
    if 'dc_search_term' not in st.session_state:
        st.session_state.dc_search_term = ""
    if 'dc_editing_client_id' not in st.session_state:
        st.session_state.dc_editing_client_id = None
    if 'dc_selected_client_id' not in st.session_state: # ID do cliente selecionado no selectbox
        st.session_state.dc_selected_client_id = None
    if 'dc_viewing_vehicles_for_client' not in st.session_state: # ID do cliente cujos veículos estão sendo vistos
        st.session_state.dc_viewing_vehicles_for_client = None
    if 'dc_selected_vehicle_placa' not in st.session_state:
        st.session_state.dc_selected_vehicle_placa = None

    def search_changed():
        st.session_state.dc_search_term = st.session_state.dc_search_input
        # Reseta todas as seleções anteriores ao iniciar uma nova busca
        st.session_state.dc_selected_client_id = None
        st.session_state.dc_editing_client_id = None
        st.session_state.dc_viewing_vehicles_for_client = None
        st.session_state.dc_selected_vehicle_placa = None
    
    st.text_input(
        "🔎 Pesquisar por Nome, Fantasia, ID ou Código Antigo",
        key="dc_search_input",
        on_change=search_changed
    )

    search_term = st.session_state.dc_search_term

    if len(search_term) < 3:
        st.info("ℹ️ Digite 3 ou mais caracteres para iniciar a busca de clientes.")
        st.stop()

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        # --- ETAPA 1: BUSCAR RESULTADOS PARA O SELECTBOX ---
        query_params = {}
        where_clauses = []
        like_term = f"%{search_term}%"
        query_params['like_term'] = like_term
        where_clauses.append("(nome_empresa ILIKE %(like_term)s OR nome_fantasia ILIKE %(like_term)s)")
        try:
            num_term = int(search_term)
            query_params['num_term'] = num_term
            where_clauses.append("(id = %(num_term)s OR codigo_antigo = %(num_term)s)")
        except ValueError:
            pass
        
        query = "SELECT id, nome_empresa, nome_fantasia FROM clientes WHERE " + " OR ".join(where_clauses) + " ORDER BY nome_empresa"
        df_clientes_results = pd.read_sql(query, conn, params=query_params)

        if df_clientes_results.empty:
            st.warning("Nenhum cliente encontrado com os critérios de busca.")
            st.stop()

        # --- ETAPA 2: CRIAR E EXIBIR O SELECTBOX ---
        client_options_map = {"Selecione um cliente da lista...": None}
        for _, row in df_clientes_results.iterrows():
            display_text = f"{row['nome_empresa']} (ID: {row['id']})"
            if row['nome_fantasia']:
                display_text += f" | Fantasia: {row['nome_fantasia']}"
            client_options_map[display_text] = row['id']

        def on_client_select():
            st.session_state.dc_selected_client_id = client_options_map[st.session_state.dc_client_selector]
            # Reseta as seleções de drill-down mais profundas ao trocar de cliente
            st.session_state.dc_editing_client_id = None
            st.session_state.dc_viewing_vehicles_for_client = None
            st.session_state.dc_selected_vehicle_placa = None

        st.selectbox(
            "Clientes encontrados:",
            options=client_options_map.keys(),
            key="dc_client_selector",
            on_change=on_client_select
        )

        # --- ETAPA 3: EXIBIR O BLOCO DO CLIENTE SELECIONADO ---
        selected_id = st.session_state.dc_selected_client_id
        if selected_id:
            cliente_details_df = pd.read_sql("SELECT * FROM clientes WHERE id = %s", conn, params=(selected_id,))
            if not cliente_details_df.empty:
                cliente = cliente_details_df.iloc[0]
                cliente_id = cliente['id']

                with st.container(border=True):
                    if st.session_state.dc_editing_client_id == cliente_id:
                        # Lógica de edição (permanece a mesma)
                        with st.form(key=f"form_edit_{cliente_id}"):
                            st.subheader(f"Editando: {cliente['nome_empresa']}")
                            edit_cols1, edit_cols2 = st.columns(2)
                            novo_nome_resp = edit_cols1.text_input("Nome do Responsável*", value=cliente['nome_responsavel'] or '')
                            novo_contato_resp = edit_cols2.text_input("Contato do Responsável*", value=cliente['contato_responsavel'] or '')
                            st.markdown("---")
                            edit_cols3, edit_cols4 = st.columns(2)
                            novo_nome_empresa = edit_cols3.text_input("Nome da Empresa", value=cliente['nome_empresa'] or '')
                            novo_nome_fantasia = edit_cols4.text_input("Nome Fantasia", value=cliente['nome_fantasia'] or '')
                            edit_cols5, edit_cols6 = st.columns(2)
                            nova_cidade = edit_cols5.text_input("Cidade", value=cliente['cidade'] or '')
                            nova_uf = edit_cols6.text_input("UF", value=cliente['uf'] or '', max_chars=2)
                            submit_col, cancel_col = st.columns(2)
                            if submit_col.form_submit_button("✅ Salvar Alterações", use_container_width=True, type="primary"):
                                # ... (código de salvar permanece o mesmo)
                                st.rerun() # Recarrega para mostrar os dados atualizados
                            if cancel_col.form_submit_button("❌ Cancelar", use_container_width=True):
                                st.session_state.dc_editing_client_id = None
                                st.rerun()
                    else:
                        # Lógica de visualização (permanece a mesma)
                        col1, col2 = st.columns([0.7, 0.3])
                        with col1:
                            st.subheader(cliente['nome_empresa'])
                            if cliente['nome_fantasia']: st.write(f"**Fantasia:** {cliente['nome_fantasia']}")
                            st.write(f"**ID:** {cliente['id']} | **Cód. Antigo:** {cliente['codigo_antigo'] or 'N/A'} | **Local:** {cliente['cidade'] or 'N/A'} - {cliente['uf'] or 'N/A'}")
                            st.info(f"**Responsável:** {cliente['nome_responsavel'] or 'Não definido'} | **Contato:** {cliente['contato_responsavel'] or 'Não definido'}")
                        with col2:
                            if st.button("✏️ Alterar Dados", key=f"edit_{cliente_id}", use_container_width=True):
                                st.session_state.dc_editing_client_id = cliente_id
                                st.rerun()
                            if st.button("🚛 Ver Veículos", key=f"select_{cliente_id}", use_container_width=True, type="secondary"):
                                st.session_state.dc_viewing_vehicles_for_client = cliente_id
                                st.session_state.dc_selected_vehicle_placa = None
                                st.rerun()
            
            # --- SEÇÃO DE VEÍCULOS E HISTÓRICO (DRILL-DOWN) ---
            # A lógica aqui permanece a mesma, pois depende do estado que já foi setado pelos botões acima
            if st.session_state.dc_viewing_vehicles_for_client == selected_id:
                st.markdown("---")
                st.header(f"🚛 Veículos do Cliente: {cliente['nome_empresa']}")
                # ... (código para mostrar veículos permanece o mesmo)
            
            if st.session_state.dc_selected_vehicle_placa:
                st.markdown("---")
                st.header(f"📋 Histórico do Veículo: {st.session_state.dc_selected_vehicle_placa}")
                # ... (código para mostrar histórico permanece o mesmo)

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        if conn:
            release_connection(conn)