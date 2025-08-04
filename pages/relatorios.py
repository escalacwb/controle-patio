import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta
import plotly.express as px

# Função de busca de dados foi melhorada para calcular a duração dos serviços
@st.cache_data(ttl=600)
def buscar_dados_relatorio(start_date, end_date):
    """Busca e une todos os dados necessários para os relatórios, já calculando a duração."""
    conn = get_connection()
    if not conn:
        st.error("Falha ao obter conexão para o relatório.")
        return pd.DataFrame()

    try:
        # Query final e completa com todos os JOINs
        query = """
            SELECT
                es.quilometragem, es.inicio_execucao, es.fim_execucao,
                EXTRACT(EPOCH FROM (es.fim_execucao - es.inicio_execucao)) / 60 AS duracao_minutos,
                es.box_id, v.placa, v.empresa,
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
                AND es.fim_execucao BETWEEN %s AND %s;
        """
        end_date_inclusive = end_date + timedelta(days=1)
        df = pd.read_sql(query, conn, params=(start_date, end_date_inclusive))
        return df
    finally:
        release_connection(conn)

def app():
    st.title("📊 Dashboard de Gestão")
    st.markdown("Use os filtros para analisar a operação do pátio.")

    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    st.markdown("---")
    
    st.subheader("Filtro de Período")
    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Data de Início", today - timedelta(days=30), key="bi_start_date")
    end_date = col2.date_input("Data de Fim", today, key="bi_end_date")

    if start_date > end_date:
        st.error("A data de início não pode ser posterior à data de fim.")
        st.stop()

    df_relatorio = buscar_dados_relatorio(start_date, end_date)
    st.markdown("---")

    if df_relatorio.empty:
        st.info(f"Nenhum serviço finalizado no período selecionado.")
    else:
        # Abas para cada área de análise
        tab_op, tab_com, tab_eq = st.tabs(["Visão Operacional", "Visão Comercial", "Visão de Equipe"])

        with tab_op:
            st.header("Análise de Eficiência do Pátio")
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Serviços por Box")
                servicos_por_box = df_relatorio['box_id'].value_counts()
                st.bar_chart(servicos_por_box)

            with col2:
                st.subheader("Tempo Médio por Serviço (minutos)")
                tempo_por_servico = df_relatorio.groupby('tipo_servico')['duracao_minutos'].mean().sort_values(ascending=False)
                st.bar_chart(tempo_por_servico)

        with tab_com:
            st.header("Análise de Clientes e Serviços")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Top 10 Clientes por Volume")
                top_clientes = df_relatorio['empresa'].value_counts().head(10)
                st.bar_chart(top_clientes)
            
            with col2:
                st.subheader("Serviços Mais Realizados")
                top_servicos = df_relatorio['tipo_servico'].value_counts().head(10)
                fig = px.pie(top_servicos, names=top_servicos.index, values=top_servicos.values, title="Distribuição de Serviços")
                st.plotly_chart(fig, use_container_width=True)

        with tab_eq:
            st.header("Análise de Performance da Equipe")
            st.subheader("Especialização por Funcionário")
            
            tabela_cruzada = pd.crosstab(df_relatorio['funcionario_nome'], df_relatorio['tipo_servico'])
            
            if not tabela_cruzada.empty:
                fig = px.imshow(tabela_cruzada, text_auto=True, aspect="auto",
                                title="Contagem de Serviços por Funcionário e Tipo")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Não há dados suficientes para gerar a análise de especialização.")