import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta # Importamos as ferramentas de data

def app():
    st.title("✅ Histórico de Serviços Concluídos")
    st.markdown("Uma lista de todas as visitas finalizadas, agrupadas por veículo e quilometragem.")
    st.markdown("---")

    # --- NOVO FILTRO DE DATA ---
    st.subheader("Filtrar por Período de Conclusão")
    today = date.today()
    
    # Criamos um seletor de intervalo de datas, que por padrão pega o dia de hoje.
    selected_dates = st.date_input(
        "Selecione um dia ou um intervalo de datas",
        value=(today, today), # O padrão é um intervalo que começa e termina hoje
        max_value=today,      # Opcional: impede a seleção de datas futuras
        key="date_filter_concluidos"
    )

    # Verificamos se o usuário selecionou um intervalo válido
    if len(selected_dates) == 2:
        start_date, end_date = selected_dates
        # Adicionamos 1 dia ao final para incluir todos os horários do último dia na busca
        end_date_inclusive = end_date + timedelta(days=1)
    else:
        # Se o intervalo for inválido, usa apenas o dia de hoje como padrão
        start_date = today
        end_date_inclusive = today + timedelta(days=1)
        st.warning("Por favor, selecione um intervalo de datas válido (início e fim).")
    
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        # --- QUERY ATUALIZADA PARA USAR O FILTRO DE DATA ---
        query = """
            SELECT
                es.veiculo_id, es.quilometragem, es.fim_execucao, es.observacao_execucao,
                v.placa, v.empresa,
                serv.area, serv.tipo, serv.quantidade, serv.status, f.nome as funcionario_nome
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN (
                SELECT execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_borracharia
                UNION ALL
                SELECT execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_alinhamento
                UNION ALL
                SELECT execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            LEFT JOIN funcionarios f ON serv.funcionario_id = f.id
            WHERE 
                es.status = 'finalizado'
                AND es.fim_execucao >= %s 
                AND es.fim_execucao < %s
            ORDER BY es.fim_execucao DESC, serv.area;
        """
        # Passamos as datas selecionadas como parâmetros para a query
        df_completo = pd.read_sql(query, conn, params=(start_date, end_date_inclusive))

        if df_completo.empty:
            st.info(f"ℹ️ Nenhum serviço foi concluído no período selecionado ({start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}).")
            return
            
        visitas_agrupadas = df_completo.groupby(['placa', 'quilometragem'], sort=False)
        
        st.subheader(f"Total de visitas encontradas no período: {len(visitas_agrupadas)}")
        
        for (placa, quilometragem), grupo_visita in visitas_agrupadas:
            info_visita = grupo_visita.iloc[0]
            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"#### Veículo: **{placa}** ({info_visita['empresa']})")
                with col2:
                    st.write(f"**Data de Conclusão:** {pd.to_datetime(info_visita['fim_execucao']).strftime('%d/%m/%Y')}")
                    st.write(f"**Quilometragem:** {quilometragem:,} km".replace(',', '.'))

                observacao = grupo_visita['observacao_execucao'].dropna().unique()
                if len(observacao) > 0 and observacao[0]:
                    st.markdown("**Observações da Visita:**")
                    st.info(observacao[0])

                st.markdown("##### Serviços realizados nesta visita:")
                servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status': 'Status', 'funcionario_nome': 'Executado por'})
                servicos_da_visita.dropna(subset=['Tipo de Serviço'], inplace=True)
                st.table(servicos_da_visita)

    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
    finally:
        release_connection(conn)