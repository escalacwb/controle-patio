import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

def app():
    st.title("📝 Controle de Feedback de Serviços")
    st.markdown("Acompanhe e registre o feedback dos serviços concluídos há 7 dias ou mais.")

    # --- LÓGICA DO BOTÃO DE FEEDBACK ---
    # Verifica se um botão de feedback foi pressionado
    for key in st.session_state:
        if key.startswith("feedback_ok_"):
            if st.session_state[key]: # Se o botão foi pressionado
                execucao_id = int(key.split("_")[2])
                conn = get_connection()
                if conn:
                    try:
                        with conn.cursor() as cursor:
                            cursor.execute(
                                "UPDATE execucao_servico SET data_feedback = NOW() WHERE id = %s",
                                (execucao_id,)
                            )
                            conn.commit()
                            st.toast(f"Feedback para serviço {execucao_id} registrado com sucesso!", icon="✅")
                            # Limpa o estado do botão para evitar re-execução
                            st.session_state[key] = False
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao registrar feedback: {e}")
                    finally:
                        release_connection(conn)

    # --- FILTRO DE DATA ---
    st.markdown("---")
    st.subheader("Filtro de Período")
    today = date.today()
    
    # O filtro de data define a partir de qual data os serviços concluídos devem ser mostrados.
    start_date = st.date_input(
        "Mostrar serviços concluídos a partir de:",
        value=today - timedelta(days=30), # Padrão para os últimos 30 dias
        max_value=today - timedelta(days=7), # Não permite selecionar datas muito recentes
        help="A lista mostrará apenas os serviços concluídos entre esta data e 7 dias atrás."
    )
    st.markdown("---")


    # --- BUSCA E EXIBIÇÃO DOS DADOS ---
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        # Query para buscar os serviços que precisam de feedback
        query = """
            WITH servicos_agrupados AS (
                SELECT 
                    execucao_id, 
                    STRING_AGG(tipo || ' (Qtd: ' || quantidade || ')', '; ') as lista_servicos
                FROM (
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_borracharia
                    UNION ALL
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_alinhamento
                    UNION ALL
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_manutencao
                ) s
                GROUP BY execucao_id
            )
            SELECT
                es.id as execucao_id,
                es.fim_execucao,
                v.placa,
                v.modelo,
                es.nome_motorista,
                es.contato_motorista,
                sa.lista_servicos
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN servicos_agrupados sa ON es.id = sa.execucao_id
            WHERE 
                es.status = 'finalizado'
                AND es.data_feedback IS NULL
                AND es.fim_execucao <= NOW() - INTERVAL '7 days'
                AND es.fim_execucao >= %s
            ORDER BY es.fim_execucao ASC;
        """
        df_feedback = pd.read_sql(query, conn, params=(start_date,))

        if df_feedback.empty:
            st.info("🎉 Nenhum serviço pendente de feedback para o período selecionado.")
            st.stop()
        
        st.subheader(f"Encontrados: {len(df_feedback)} serviços pendentes de feedback")

        # Exibe cada serviço como um "card"
        for _, row in df_feedback.iterrows():
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.markdown(f"**Veículo:** `{row['placa']}` - {row['modelo']}")
                    st.markdown(f"**Motorista:** {row['nome_motorista'] or 'Não informado'} | **Contato:** {row['contato_motorista'] or 'N/A'}")
                    st.markdown(f"**Serviços:** *{row['lista_servicos']}*")
                    st.caption(f"Data de Conclusão: {pd.to_datetime(row['fim_execucao']).strftime('%d/%m/%Y')}")
                
                with col2:
                    st.button(
                        "✅ Feedback Realizado", 
                        key=f"feedback_ok_{row['execucao_id']}",
                        use_container_width=True
                    )

    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
    finally:
        release_connection(conn)