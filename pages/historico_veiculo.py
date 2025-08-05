import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import get_service_details_for_execution

def app():
    st.title("📋 Histórico por Veículo")
    st.header("🔍 Buscar Histórico por Placa")
    search_placa = st.text_input("Digite a placa do veículo", key="search_placa_hist").upper()

    if not search_placa:
        return

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        query_veiculo = "SELECT id FROM veiculos WHERE placa = %s"
        df_veiculo = pd.read_sql(query_veiculo, conn, params=(search_placa,))
        if df_veiculo.empty:
            st.warning(f"Nenhum veículo encontrado com a placa '{search_placa}'.")
            return
        veiculo_id = int(df_veiculo.iloc[0]['id'])

        # --- QUERY CORRIGIDA ---
        # A coluna 'observacao_execucao' foi removida da tabela principal 'es'
        # e agora é buscada da subquery 'serv'
        execucoes_query = """
            SELECT 
                es.id as execucao_id, es.quilometragem, es.inicio_execucao, es.fim_execucao, 
                es.status as status_execucao,
                serv.observacao_execucao
            FROM execucao_servico es
            LEFT JOIN (
                SELECT execucao_id, observacao_execucao FROM servicos_solicitados_borracharia UNION ALL
                SELECT execucao_id, observacao_execucao FROM servicos_solicitados_alinhamento UNION ALL
                SELECT execucao_id, observacao_execucao FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            WHERE veiculo_id = %s
            ORDER BY inicio_execucao DESC;
        """
        df_execucoes = pd.read_sql(execucoes_query, conn, params=(veiculo_id,))
        df_execucoes = df_execucoes.drop_duplicates(subset=['execucao_id'])


        if df_execucoes.empty:
            st.info("Nenhum histórico encontrado para esta placa.")
            return
            
        st.write(f"**Total de visitas encontradas:** {len(df_execucoes)}")

        for _, execucao in df_execucoes.iterrows():
            inicio_execucao = pd.to_datetime(execucao['inicio_execucao'])
            
            titulo_expander = f"Visita de {inicio_execucao.strftime('%d/%m/%Y')} (KM: {execucao['quilometragem']:,}) | Status: {execucao['status_execucao'].upper()}".replace(',', '.')
            
            with st.expander(titulo_expander):
                if pd.notna(execucao['observacao_execucao']) and execucao['observacao_execucao']:
                    st.markdown("**Observações da Visita:**")
                    st.info(execucao['observacao_execucao'])

                st.markdown("##### Serviços realizados nesta visita:")
                df_detalhes = get_service_details_for_execution(conn, execucao['execucao_id'])
                if not df_detalhes.empty:
                    st.table(df_detalhes.rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status': 'Status', 'funcionario_nome': 'Executado por'}))
                else:
                    st.warning("Nenhum detalhe de serviço encontrado para esta execução.")

    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        release_connection(conn)