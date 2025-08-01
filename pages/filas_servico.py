import streamlit as st
import pandas as pd
from database import get_connection, release_connection

def app():
    st.title("🚦 Filas de Serviço Ativas")
    st.markdown("Visualize os veículos aguardando (`PENDENTE`) ou já em execução (`EM ANDAMENTO`) por área de serviço.")

    # Função interna para buscar e exibir a fila de uma área específica
    def show_queue(area_title, table_name):
        st.subheader(f"Fila: {area_title}")
        
        conn = get_connection()
        if not conn:
            st.error(f"Não foi possível conectar ao banco para buscar a fila de {area_title}.")
            return

        # Query para buscar todos os serviços pendentes ou em andamento de uma tabela
        query = f"""
            SELECT
                v.placa AS "Placa",
                v.empresa AS "Empresa",
                s.tipo AS "Serviço Solicitado",
                s.quantidade AS "Qtd.",
                s.status AS "Status",
                s.data_solicitacao AS "Data da Solicitação"
            FROM
                {table_name} s
            JOIN
                veiculos v ON s.veiculo_id = v.id
            WHERE
                s.status IN ('pendente', 'em_andamento')
            ORDER BY
                s.status ASC, s.data_solicitacao ASC;
        """
        
        try:
            df = pd.read_sql(query, conn)
            
            if not df.empty:
                # Formatação dos dados para melhor visualização
                df_display = df.copy()
                df_display['Data da Solicitação'] = pd.to_datetime(df_display['Data da Solicitação']).dt.strftime('%d/%m/%Y %H:%M:%S')
                df_display['Status'] = df_display['Status'].apply(lambda s: s.replace('_', ' ').upper())
                
                # Exibe o DataFrame estilizado
                st.dataframe(df_display, use_container_width=True)
            else:
                st.info(f"Nenhum serviço na fila de {area_title} no momento.")
        except Exception as e:
            st.error(f"❌ Erro ao carregar a fila de {area_title}: {e}")
        finally:
            release_connection(conn)

    # Chama a função para cada área de serviço
    show_queue("Borracharia", "servicos_solicitados_borracharia")
    st.markdown("---")
    show_queue("Alinhamento", "servicos_solicitados_alinhamento")
    st.markdown("---")
    show_queue("Manutenção Mecânica", "servicos_solicitados_manutencao")