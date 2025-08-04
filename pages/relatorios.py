import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

# Função para buscar e cachear os dados
@st.cache_data(ttl=600) # Cache de 10 minutos
def buscar_dados_relatorio(conn, start_date, end_date):
    """Busca e une todos os dados necessários para os relatórios."""
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
            AND es.fim_execucao BETWEEN %s AND %s;
    """
    df = pd.read_sql(query, conn, params=(start_date, end_date))
    return df

def app():
    st.title("📊 Relatórios e BI")
    st.markdown("Analise a performance e os dados operacionais do pátio.")

    # Garante que apenas administradores possam ver esta página
    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    st.markdown("---")
    
    # --- Filtro de Data ---
    st.subheader("Filtrar por Período de Conclusão")
    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Data de Início", today - timedelta(days=30))
    end_date = col2.date_input("Data de Fim", today)

    if start_date > end_date:
        st.error("A data de início não pode ser posterior à data de fim.")
        st.stop()

    # Busca os dados com base nas datas selecionadas
    df_relatorio = buscar_dados_relatorio(conn, start_date, end_date)
    
    release_connection(conn)

    st.markdown("---")

    if df_relatorio.empty:
        st.info(f"Nenhum serviço finalizado no período de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}.")
    else:
        st.header("Dashboard Geral")
        
        # --- KPIs Principais ---
        col1, col2, col3 = st.columns(3)
        total_servicos = len(df_relatorio)
        total_veiculos = df_relatorio['placa'].nunique()
        
        col1.metric("Total de Serviços Realizados", f"{total_servicos}")
        col2.metric("Veículos Únicos Atendidos", f"{total_veiculos}")

        # --- Gráficos ---
        st.markdown("<br>", unsafe_allow_html=True) # Adiciona um espaço

        col_graf1, col_graf2 = st.columns(2)

        with col_graf1:
            st.subheader("Top 5 Serviços Mais Realizados")
            top_servicos = df_relatorio['tipo_servico'].value_counts().head(5)
            st.bar_chart(top_servicos)

        with col_graf2:
            st.subheader("Top 5 Funcionários Mais Ativos")
            top_funcionarios = df_relatorio['funcionario_nome'].value_counts().head(5)
            st.bar_chart(top_funcionarios)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader("Dados Detalhados do Período")
        st.dataframe(df_relatorio, use_container_width=True)