import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

def app():
    st.title("📊 Relatórios e BI (Modo de Diagnóstico)")
    st.markdown("Use os filtros para analisar a operação do pátio.")

    if st.session_state.get('user_role') != 'admin':
        st.error("Acesso negado. Apenas administradores podem acessar esta página.")
        st.stop()
    
    st.markdown("---")
    
    # --- Filtro de Data ---
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
        # --- QUERY SUPER SIMPLIFICADA PARA TESTE ---
        # Estamos buscando dados apenas de 'execucao_servico' e 'veiculos'
        query_teste = """
            SELECT
                es.id as execucao_id,
                es.quilometragem,
                es.inicio_execucao,
                es.fim_execucao,
                v.placa,
                v.empresa
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            WHERE
                es.status = 'finalizado'
                AND es.fim_execucao BETWEEN %s AND %s;
        """
        end_date_inclusive = end_date + timedelta(days=1)
        df_teste = pd.read_sql(query_teste, conn, params=(start_date, end_date_inclusive))
        
        st.subheader("Resultado do Teste de Diagnóstico")

        if df_teste.empty:
            st.info("A consulta de teste funcionou, mas não encontrou dados para o período.")
        else:
            st.success("A consulta de teste funcionou! A conexão com as tabelas 'execucao_servico' e 'veiculos' está OK.")
            st.write("Dados encontrados:")
            st.dataframe(df_teste)

    except Exception as e:
        st.error("O teste com a consulta simplificada falhou. O erro é o seguinte:")
        st.exception(e) # Isso vai mostrar o erro completo do banco de dados
    finally:
        release_connection(conn)