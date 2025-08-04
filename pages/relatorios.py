import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

def app():
    st.title("📊 Relatórios e BI (Modo de Diagnóstico - Teste 2)")
    st.markdown("Use os filtros para analisar a operação do pátio.")

    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    st.markdown("---")
    
    # Filtro de Data
    st.subheader("Filtrar por Período de Conclusão")
    today = date.today()
    col1, col2 = st.columns(2)
    start_date = col1.date_input("Data de Início", today - timedelta(days=30), key="bi_start_date")
    end_date = col2.date_input("Data de Fim", today, key="bi_end_date")

    if start_date > end_date:
        st.error("A data de início não pode ser posterior à data de fim.")
        st.stop()
    
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        # --- QUERY DE TESTE 2: Adicionamos o JOIN com as tabelas de SERVIÇOS ---
        query_teste = """
            SELECT
                es.id as execucao_id,
                es.quilometragem,
                es.inicio_execucao,
                es.fim_execucao,
                v.placa,
                v.empresa,
                serv.tipo as tipo_servico
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN (
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_borracharia
                UNION ALL
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_alinhamento
                UNION ALL
                SELECT execucao_id, tipo, funcionario_id FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            WHERE
                es.status = 'finalizado'
                AND es.fim_execucao BETWEEN %s AND %s;
        """
        end_date_inclusive = end_date + timedelta(days=1)
        df_teste = pd.read_sql(query_teste, conn, params=(start_date, end_date_inclusive))
        
        st.subheader("Resultado do Teste de Diagnóstico 2")

        if df_teste.empty:
            st.info("A consulta de teste (com serviços) funcionou, mas não encontrou dados.")
        else:
            st.success("A consulta de teste (com serviços) funcionou! A ligação com as tabelas de serviços está OK.")
            st.write("Dados encontrados:")
            st.dataframe(df_teste)

    except Exception as e:
        st.error("O teste com a consulta de SERVIÇOS falhou. O erro está na ligação com as tabelas 'servicos_solicitados_*'.")
        st.exception(e) # Isso vai mostrar o erro completo do banco de dados
    finally:
        release_connection(conn)