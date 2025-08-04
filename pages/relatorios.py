import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta
import plotly.express as px

# Função para buscar e cachear os dados (com adição do box_id)
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
                es.id as execucao_id, es.quilometragem, es.inicio_execucao, es.fim_execucao,
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
    st.title("📊 Construtor de Relatórios (BI)")
    st.markdown("Use os filtros e seletores para explorar os dados da operação.")

    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    st.markdown("---")
    
    # --- Filtro de Data ---
    st.subheader("1. Selecione o Período")
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
        st.info(f"Nenhum serviço finalizado no período de {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}.")
    else:
        # --- Controles do Construtor de Gráficos ---
        st.subheader("2. Monte sua Análise")
        
        # Mapeamento de colunas para nomes amigáveis
        opcoes_analise = {
            'Funcionário': 'funcionario_nome',
            'Tipo de Serviço': 'tipo_servico',
            'Empresa (Cliente)': 'empresa',
            'Box': 'box_id'
        }

        col_analise, col_grafico = st.columns(2)

        # Seletor do Eixo X
        opcao_selecionada = col_analise.selectbox(
            "Analisar por:",
            options=list(opcoes_analise.keys())
        )
        
        # Seletor do Tipo de Gráfico
        tipo_grafico = col_grafico.selectbox(
            "Visualizar como:",
            options=["Gráfico de Barras", "Gráfico de Pizza"]
        )

        # --- Processamento e Exibição dos Dados ---
        st.markdown("---")
        st.header(f"Análise por: {opcao_selecionada}")

        # Pega o nome da coluna no DataFrame com base na seleção do usuário
        coluna_para_analise = opcoes_analise[opcao_selecionada]
        
        # Realiza a contagem dos dados
        dados_agrupados = df_relatorio[coluna_para_analise].value_counts()
        
        # Converte para um DataFrame para o Plotly
        df_grafico = dados_agrupados.reset_index()
        df_grafico.columns = [opcao_selecionada, 'Contagem de Serviços']

        # Exibe o gráfico escolhido
        if tipo_grafico == "Gráfico de Barras":
            fig = px.bar(df_grafico, x=opcao_selecionada, y='Contagem de Serviços',
                         title=f"Total de Serviços por {opcao_selecionada}",
                         text_auto=True)
            st.plotly_chart(fig, use_container_width=True)
        
        elif tipo_grafico == "Gráfico de Pizza":
            fig = px.pie(df_grafico, names=opcao_selecionada, values='Contagem de Serviços',
                         title=f"Distribuição de Serviços por {opcao_selecionada}")
            st.plotly_chart(fig, use_container_width=True)

        # Exibe a tabela com os dados agrupados
        with st.expander("Ver dados da tabela"):
            st.dataframe(df_grafico, use_container_width=True)