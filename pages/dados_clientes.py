# /pages/dados_clientes.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import formatar_telefone
import psycopg2.extras

def app():
    st.title("📇 Dados de Clientes")
    st.markdown("Pesquise, visualize e edite os dados dos clientes e seus veículos.")

    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
    if 'dc_search_term' not in st.session_state:
        st.session_state.dc_search_term = ""
    if 'dc_editing_client_id' not in st.session_state:
        st.session_state.dc_editing_client_id = None
    if 'dc_selected_client_id' not in st.session_state:
        st.session_state.dc_selected_client_id = None
    if 'dc_selected_vehicle_placa' not in st.session_state:
        st.session_state.dc_selected_vehicle_placa = None

    # --- BARRA DE PESQUISA ---
    search_term = st.text_input(
        "🔎 Pesquisar por Nome, Fantasia, ID ou Código Antigo",
        value=st.session_state.dc_search_term,
        key="dc_search_input"
    )

    # Se o termo de busca mudou, reseta a seleção
    if search_term != st.session_state.dc_search_term:
        st.session_state.dc_search_term = search_term
        st.session_state.dc_selected_client_id = None
        st.session_state.dc_selected_vehicle_placa = None
        st.session_state.dc_editing_client_id = None
        st.rerun()

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        # --- BUSCA DE CLIENTES ---
        query_params = {}
        where_clauses = []
        if search_term:
            like_term = f"%{search_term}%"
            query_params['like_term'] = like_term
            where_clauses.append("(nome_empresa ILIKE %(like_term)s OR nome_fantasia ILIKE %(like_term)s)")
            # Tenta converter para número para buscar por ID ou código
            try:
                num_term = int(search_term)
                query_params['num_term'] = num_term
                where_clauses.append("(id = %(num_term)s OR codigo_antigo = %(num_term)s)")
            except ValueError:
                pass # Não é um número, busca apenas por texto
        
        query = "SELECT id, codigo_antigo, nome_empresa, nome_fantasia, cidade, uf, nome_responsavel, contato_responsavel FROM clientes"
        if where_clauses:
            query += " WHERE " + " OR ".join(where_clauses)
        query += " ORDER BY nome_empresa"
        
        df_clientes = pd.read_sql(query, conn, params=query_params)

        if df_clientes.empty and search_term:
            st.info("Nenhum cliente encontrado com os critérios de busca.")
        
        # --- EXIBIÇÃO DOS CLIENTES ---
        for _, cliente in df_clientes.iterrows():
            cliente_id = cliente['id']
            with st.container(border=True):
                # Se o cliente está em modo de edição
                if st.session_state.dc_editing_client_id == cliente_id:
                    with st.form(key=f"form_edit_{cliente_id}"):
                        st.subheader(f"Editando: {cliente['nome_empresa']}")
                        
                        edit_cols1, edit_cols2 = st.columns(2)
                        # Campos priorizados
                        novo_nome_resp = edit_cols1.text_input("Nome do Responsável*", value=cliente['nome_responsavel'])
                        novo_contato_resp = edit_cols2.text_input("Contato do Responsável*", value=cliente['contato_responsavel'])
                        
                        st.markdown("---")
                        
                        edit_cols3, edit_cols4 = st.columns(2)
                        novo_nome_empresa = edit_cols3.text_input("Nome da Empresa", value=cliente['nome_empresa'])
                        novo_nome_fantasia = edit_cols4.text_input("Nome Fantasia", value=cliente['nome_fantasia'])
                        
                        edit_cols5, edit_cols6 = st.columns(2)
                        nova_cidade = edit_cols5.text_input("Cidade", value=cliente['cidade'])
                        nova_uf = edit_cols6.text_input("UF", value=cliente['uf'], max_chars=2)
                        
                        submit_col, cancel_col = st.columns(2)
                        if submit_col.form_submit_button("✅ Salvar Alterações", use_container_width=True, type="primary"):
                            try:
                                with conn.cursor() as cursor:
                                    update_query = """
                                        UPDATE clientes SET 
                                        nome_empresa = %s, nome_fantasia = %s, cidade = %s, uf = %s,
                                        nome_responsavel = %s, contato_responsavel = %s
                                        WHERE id = %s
                                    """
                                    cursor.execute(update_query, (
                                        novo_nome_empresa, novo_nome_fantasia, nova_cidade, nova_uf.upper(),
                                        novo_nome_resp, formatar_telefone(novo_contato_resp), cliente_id
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
                
                # Modo de visualização normal
                else:
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
                            st.session_state.dc_selected_client_id = cliente_id
                            st.session_state.dc_selected_vehicle_placa = None # reseta a placa
                            st.rerun()
        
        # --- SEÇÃO DE VEÍCULOS (DRILL-DOWN 1) ---
        if st.session_state.dc_selected_client_id:
            st.markdown("---")
            st.header(f"🚛 Veículos do Cliente ID: {st.session_state.dc_selected_client_id}")
            df_veiculos = pd.read_sql(
                "SELECT id, placa, modelo, media_km_diaria FROM veiculos WHERE cliente_id = %s ORDER BY placa",
                conn,
                params=(st.session_state.dc_selected_client_id,)
            )

            if df_veiculos.empty:
                st.warning("Nenhum veículo cadastrado para este cliente.")
            else:
                for _, veiculo in df_veiculos.iterrows():
                    v_col1, v_col2 = st.columns([0.7, 0.3])
                    with v_col1:
                        st.markdown(f"**Placa:** `{veiculo['placa']}` | **Modelo:** {veiculo['modelo'] or 'N/A'}")
                        media_km = f"{veiculo['media_km_diaria']:.2f}" if pd.notna(veiculo['media_km_diaria']) else "N/A"
                        st.caption(f"ID do Veículo: {veiculo['id']} | Média: {media_km} km/dia")
                    with v_col2:
                        if st.button("📋 Ver Histórico Completo", key=f"history_{veiculo['id']}", use_container_width=True):
                            st.session_state.dc_selected_vehicle_placa = veiculo['placa']
                            st.rerun()
        
        # --- SEÇÃO DE HISTÓRICO (DRILL-DOWN 2) ---
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
                visitas_agrupadas = df_historico.groupby('quilometragem', sort=False)
                for quilometragem, grupo_visita in visitas_agrupadas:
                    info_visita = grupo_visita.iloc[0]
                    inicio_visita = pd.to_datetime(grupo_visita['inicio_execucao'].min())
                    titulo_expander = f"Visita de {inicio_visita.strftime('%d/%m/%Y')} (KM: {quilometragem:,}) | Status: {info_visita['status_execucao'].upper()}".replace(',', '.')
                    
                    with st.expander(titulo_expander, expanded=True):
                        st.markdown(f"**Motorista na ocasião:** {info_visita['nome_motorista'] or 'N/A'} ({info_visita['contato_motorista'] or 'N/A'})")
                        servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status_servico', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status_servico': 'Status', 'funcionario_nome': 'Executado por'})
                        st.table(servicos_da_visita.dropna(subset=['Tipo de Serviço']))

    except Exception as e:
        st.error(f"Ocorreu um erro: {e}")
    finally:
        release_connection(conn)