# /pages/dados_clientes.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import formatar_telefone
import psycopg2.extras
from datetime import datetime

def app():
    st.title("📇 Dados de Clientes")
    st.markdown("Pesquise, visualize e edite os dados dos clientes e seus veículos.")

    # --- INICIALIZAÇÃO E LÓGICA DE ESTADO ---
    if 'dc_search_term' not in st.session_state:
        st.session_state.dc_search_term = ""
    if 'dc_editing_client_id' not in st.session_state:
        st.session_state.dc_editing_client_id = None
    if 'dc_selected_client_id' not in st.session_state:
        st.session_state.dc_selected_client_id = None
    if 'dc_viewing_vehicles_for_client' not in st.session_state:
        st.session_state.dc_viewing_vehicles_for_client = None
    if 'dc_selected_vehicle_placa' not in st.session_state:
        st.session_state.dc_selected_vehicle_placa = None
    if 'dc_editing_vehicle_id' not in st.session_state:
        st.session_state.dc_editing_vehicle_id = None


    def search_changed():
        st.session_state.dc_search_term = st.session_state.dc_search_input
        st.session_state.dc_selected_client_id = None
        st.session_state.dc_editing_client_id = None
        st.session_state.dc_viewing_vehicles_for_client = None
        st.session_state.dc_selected_vehicle_placa = None
        st.session_state.dc_editing_vehicle_id = None
    
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
        
        # Este select agora busca todos os dados para evitar uma segunda consulta
        query = "SELECT * FROM clientes WHERE " + " OR ".join(where_clauses) + " ORDER BY nome_empresa"
        df_clientes_results = pd.read_sql(query, conn, params=query_params)

        if df_clientes_results.empty:
            st.warning("Nenhum cliente encontrado com os critérios de busca.")
            st.stop()

        client_options_map = {"Selecione um cliente da lista...": None}
        for _, row in df_clientes_results.iterrows():
            display_text = f"{row['nome_empresa']} (ID: {row['id']})"
            if row['nome_fantasia']:
                display_text += f" | Fantasia: {row['nome_fantasia']}"
            client_options_map[display_text] = row['id']

        def on_client_select():
            st.session_state.dc_selected_client_id = client_options_map.get(st.session_state.dc_client_selector)
            st.session_state.dc_editing_client_id = None
            st.session_state.dc_viewing_vehicles_for_client = None
            st.session_state.dc_selected_vehicle_placa = None
            st.session_state.dc_editing_vehicle_id = None

        st.selectbox(
            "Clientes encontrados:",
            options=client_options_map.keys(),
            key="dc_client_selector",
            on_change=on_client_select
        )

        selected_id = st.session_state.dc_selected_client_id
        if selected_id:
            # Pega os detalhes do cliente do DataFrame já carregado
            cliente_details_df = df_clientes_results[df_clientes_results['id'] == selected_id]
            if not cliente_details_df.empty:
                cliente = cliente_details_df.iloc[0]
                cliente_id = cliente['id']

                with st.container(border=True):
                    if st.session_state.dc_editing_client_id == cliente_id:
                        with st.form(key=f"form_edit_{cliente_id}"):
                            st.subheader(f"Editando Cliente: {cliente['nome_empresa']}")
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
                            if submit_col.form_submit_button("✅ Salvar Alterações do Cliente", use_container_width=True, type="primary"):
                                try:
                                    with conn.cursor() as cursor:
                                        # ATUALIZADO: Adicionado data_atualizacao_contato = NOW()
                                        update_query = """
                                            UPDATE clientes 
                                            SET nome_empresa = %s, nome_fantasia = %s, cidade = %s, uf = %s, 
                                                nome_responsavel = %s, contato_responsavel = %s,
                                                data_atualizacao_contato = NOW()
                                            WHERE id = %s
                                        """
                                        cursor.execute(update_query, (
                                            novo_nome_empresa, novo_nome_fantasia, nova_cidade, nova_uf.upper(), 
                                            novo_nome_resp, formatar_telefone(novo_contato_resp), 
                                            int(cliente_id)
                                        ))
                                        conn.commit()
                                        st.success(f"Cliente {novo_nome_empresa} atualizado com sucesso!")
                                        st.session_state.dc_editing_client_id = None
                                        st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erro ao salvar: {e}")
                            if cancel_col.form_submit_button("❌ Cancelar", use_container_width=True):
                                st.session_state.dc_editing_client_id = None
                                st.rerun()
                    else:
                        col1, col2 = st.columns([0.7, 0.3])
                        with col1:
                            st.subheader(cliente['nome_empresa'])
                            if cliente['nome_fantasia']: st.write(f"**Fantasia:** {cliente['nome_fantasia']}")
                            st.write(f"**ID:** {cliente['id']} | **Cód. Antigo:** {cliente['codigo_antigo'] or 'N/A'} | **Local:** {cliente['cidade'] or 'N/A'} - {cliente['uf'] or 'N/A'}")
                            st.info(f"**Responsável:** {cliente['nome_responsavel'] or 'Não definido'} | **Contato:** {cliente['contato_responsavel'] or 'Não definido'}")
                        with col2:
                            if st.button("✏️ Alterar Dados do Cliente", key=f"edit_client_{cliente_id}", use_container_width=True):
                                st.session_state.dc_editing_client_id = cliente_id
                                st.rerun()
                            if st.button("🚛 Ver Veículos", key=f"select_vehicles_{cliente_id}", use_container_width=True, type="secondary"):
                                st.session_state.dc_viewing_vehicles_for_client = cliente_id
                                st.session_state.dc_selected_vehicle_placa = None
                                st.session_state.dc_editing_vehicle_id = None
                                st.rerun()
            
            if st.session_state.dc_viewing_vehicles_for_client == selected_id:
                st.markdown("---")
                st.header(f"🚛 Veículos do Cliente: {cliente['nome_empresa']}")
                
                df_veiculos = pd.read_sql(
                    "SELECT id, placa, modelo, ano_modelo, nome_motorista, contato_motorista, media_km_diaria FROM veiculos WHERE cliente_id = %s ORDER BY placa",
                    conn,
                    params=(int(st.session_state.dc_viewing_vehicles_for_client),)
                )

                if df_veiculos.empty:
                    st.warning("Nenhum veículo cadastrado para este cliente.")
                else:
                    for _, veiculo in df_veiculos.iterrows():
                        with st.container(border=True):
                            v_col1, v_col2, v_col3 = st.columns([0.5, 0.25, 0.25])
                            with v_col1:
                                st.markdown(f"**Placa:** `{veiculo['placa']}` | **Modelo:** {veiculo['modelo'] or 'N/A'}")
                                media_km = f"{veiculo['media_km_diaria']:.2f}" if pd.notna(veiculo['media_km_diaria']) else "N/A"
                                st.caption(f"ID: {veiculo['id']} | Ano: {veiculo['ano_modelo'] or 'N/A'} | Média: {media_km} km/dia")
                            with v_col2:
                                if st.button("✏️ Alterar Veículo", key=f"edit_vehicle_{veiculo['id']}", use_container_width=True):
                                    st.session_state.dc_editing_vehicle_id = veiculo['id']
                                    st.session_state.dc_selected_vehicle_placa = None
                                    st.rerun()
                            with v_col3:
                                if st.button("📋 Ver Histórico", key=f"history_{veiculo['id']}", use_container_width=True):
                                    st.session_state.dc_selected_vehicle_placa = veiculo['placa']
                                    st.session_state.dc_editing_vehicle_id = None
                                    st.rerun()
            
            if st.session_state.dc_editing_vehicle_id:
                st.markdown("---")
                vehicle_to_edit_df = pd.read_sql("SELECT * FROM veiculos WHERE id = %s", conn, params=(int(st.session_state.dc_editing_vehicle_id),))
                if not vehicle_to_edit_df.empty:
                    v_edit = vehicle_to_edit_df.iloc[0]
                    st.header(f"Editando Veículo: {v_edit['placa']}")
                    with st.form("form_edit_vehicle"):
                        ve_col1, ve_col2 = st.columns(2)
                        novo_modelo = ve_col1.text_input("Modelo", value=v_edit['modelo'] or '')
                        novo_ano = ve_col2.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(v_edit['ano_modelo'] or datetime.now().year), step=1)
                        ve_col3, ve_col4 = st.columns(2)
                        novo_motorista = ve_col3.text_input("Nome do Motorista", value=v_edit['nome_motorista'] or '')
                        novo_contato_motorista = ve_col4.text_input("Contato do Motorista", value=v_edit['contato_motorista'] or '')

                        submit_v_col, cancel_v_col = st.columns(2)
                        if submit_v_col.form_submit_button("✅ Salvar Alterações do Veículo", type="primary", use_container_width=True):
                            try:
                                with conn.cursor() as cursor:
                                    # ATUALIZADO: Adicionado data_atualizacao_contato = NOW()
                                    query_update_v = """
                                        UPDATE veiculos 
                                        SET modelo = %s, ano_modelo = %s, nome_motorista = %s, 
                                            contato_motorista = %s, data_atualizacao_contato = NOW()
                                        WHERE id = %s
                                    """
                                    cursor.execute(query_update_v, (novo_modelo, novo_ano, novo_motorista, formatar_telefone(novo_contato_motorista), int(v_edit['id'])))
                                    conn.commit()
                                    st.success(f"Veículo {v_edit['placa']} atualizado com sucesso!")
                                    st.session_state.dc_editing_vehicle_id = None
                                    st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao atualizar veículo: {e}")
                        if cancel_v_col.form_submit_button("❌ Cancelar Edição", use_container_width=True):
                            st.session_state.dc_editing_vehicle_id = None
                            st.rerun()


            if st.session_state.dc_selected_vehicle_placa:
                st.markdown("---")
                st.header(f"📋 Histórico do Veículo: {st.session_state.dc_selected_vehicle_placa}")
                history_query = """
                    SELECT
                        es.quilometragem, es.inicio_execucao, es.fim_execucao, es.status as status_execucao,
                        es.nome_motorista, es.contato_motorista,
                        serv.area, serv.tipo, serv.quantidade, serv.status as status_servico, f.nome as funcionario_nome,
                        serv.observacao_execucao
                    FROM execucao_servico es
                    LEFT JOIN (
                        SELECT execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_borracharia UNION ALL
                        SELECT execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_alinhamento UNION ALL
                        SELECT execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_manutencao
                    ) serv ON es.id = serv.execucao_id
                    LEFT JOIN funcionarios f ON serv.funcionario_id = f.id
                    JOIN veiculos v ON es.veiculo_id = v.id
                    WHERE v.placa = %s
                    ORDER BY es.inicio_execucao DESC, serv.area;
                """
                df_historico = pd.read_sql(history_query, conn, params=(st.session_state.dc_selected_vehicle_placa,))
                if df_historico.empty:
                    st.info("Nenhum histórico de serviço encontrado para esta placa.")
                else:
                    st.write(f"**Total de visitas encontradas:** {len(df_historico.groupby('quilometragem', sort=False))}")
                    visitas_agrupadas = df_historico.groupby('quilometragem', sort=False)
                    for quilometragem, grupo_visita in visitas_agrupadas:
                        info_visita = grupo_visita.iloc[0]
                        inicio_visita = pd.to_datetime(grupo_visita['inicio_execucao'].min())
                        titulo_expander = f"Visita de {inicio_visita.strftime('%d/%m/%Y')} (KM: {int(quilometragem)}) | Status: {info_visita['status_execucao'].upper()}"
                        with st.expander(titulo_expander, expanded=False):
                            st.markdown(f"**Motorista na ocasião:** {info_visita['nome_motorista'] or 'N/A'} ({info_visita['contato_motorista'] or 'N/A'})")
                            servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status_servico', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status_servico': 'Status', 'funcionario_nome': 'Executado por'})
                            st.table(servicos_da_visita.dropna(subset=['Tipo de Serviço']))

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        if conn:
            release_connection(conn)

