import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

# Função para buscar e cachear os dados
@st.cache_data(ttl=600)
def buscar_dados_relatorio(start_date, end_date):
    """Busca e une todos os dados necessários para os relatórios."""
    conn = get_connection()
    if not conn:
        st.error("Falha ao obter conexão para o relatório.")
        return pd.DataFrame()

    try:
        query = """
            SELECT
                es.id as execucao_id,
                es.quilometragem,
                es.inicio_execucao,
                es.fim_execucao,
                v.placa,
                v.empresa,
                serv.tipo as tipo_servico,
                func.nome as funcionario_nome,
                usr_aloc.nome as alocado_por,
                usr_final.nome as finalizado_por
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN (
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_borracharia UNION ALL
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_alinhamento UNION ALL
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            LEFT JOIN funcionarios func ON serv.funcionario_id = func.id
            LEFT JOIN usuarios usr_aloc ON es.usuario_alocacao_id = usr_aloc.id
            LEFT JOIN usuarios usr_final ON es.usuario_finalizacao_id = usr_final.id
            WHERE
                es.status = 'finalizado'
                AND es.fim_execucao >= %s
                AND es.fim_execucao < %s;
        """
        end_date_inclusive = end_date + timedelta(days=1)
        df = pd.read_sql(query, conn, params=(start_date, end_date_inclusive))
        return df
    finally:
        release_connection(conn)

def app():
    st.title("📊 Relatórios e BI")
    st.markdown("Analise a performance e os dados operacionais do pátio.")

    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()
    
    st.markdown("---")
    
    # --- FILTROS DA PÁGINA ---
    st.subheader("Filtros")
    
    # Filtro de Data
    col_data1, col_data2 = st.columns(2)
    today = date.today()
    start_date = col_data1.date_input("Data de Início", today - timedelta(days=30), key="bi_start_date")
    end_date = col_data2.date_input("Data de Fim", today, key="bi_end_date")

    if start_date > end_date:
        st.error("A data de início não pode ser posterior à data de fim.")
        st.stop()

    # Busca os dados brutos com base apenas nas datas
    df_bruto = buscar_dados_relatorio(start_date, end_date)

    # --- NOVOS FILTROS INTERATIVOS ---
    col_empresa, col_func = st.columns(2)
    
    # Filtro de Empresa
    lista_empresas = sorted(df_bruto['empresa'].dropna().unique())
    empresas_selecionadas = col_empresa.multiselect("Filtrar por Empresa", options=lista_empresas)

    # Filtro de Funcionário
    lista_funcionarios = sorted(df_bruto['funcionario_nome'].dropna().unique())
    funcionarios_selecionados = col_func.multiselect("Filtrar por Funcionário", options=lista_funcionarios)

    # --- APLICANDO OS FILTROS NOS DADOS ---
    df_filtrado = df_bruto.copy()
    if empresas_selecionadas:
        df_filtrado = df_filtrado[df_filtrado['empresa'].isin(empresas_selecionadas)]
    if funcionarios_selecionados:
        df_filtrado = df_filtrado[df_filtrado['funcionario_nome'].isin(funcionarios_selecionados)]

    release_connection(conn)
    st.markdown("---")

    if df_filtrado.empty:
        st.info(f"Nenhum serviço encontrado para os filtros selecionados.")
    else:
        st.header("Dashboard Geral")
        
        # --- KPIs Principais ---
        col1, col2 = st.columns(2)
        total_servicos = len(df_filtrado.dropna(subset=['tipo_servico']))
        total_veiculos = df_filtrado['placa'].nunique()
        
        col1.metric("Total de Serviços Realizados", f"{total_servicos}")
        col2.metric("Veículos Únicos Atendidos", f"{total_veiculos}")

        # --- Gráficos ---
        st.markdown("<br>", unsafe_allow_html=True)
        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("Top 5 Serviços Mais Realizados")
            top_servicos = df_filtrado['tipo_servico'].value_counts().head(5)
            st.bar_chart(top_servicos)

        with col_graf2:
            st.subheader("Top 5 Funcionários Mais Ativos")
            top_funcionarios = df_filtrado['funcionario_nome'].value_counts().head(5)
            st.bar_chart(top_funcionarios)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("Dados Detalhados do Período")
        df_display = df_filtrado.fillna("N/A")
        st.dataframe(df_display, use_container_width=True)