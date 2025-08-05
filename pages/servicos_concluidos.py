import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

def app():
    st.title("✅ Histórico de Serviços Concluídos")
    st.markdown("Uma lista de todas as visitas finalizadas, agrupadas por veículo e quilometragem.")
    st.markdown("---")

    st.subheader("Filtrar por Período de Conclusão")
    today = date.today()
    
    selected_dates = st.date_input(
        "Selecione um dia ou um intervalo de datas",
        value=(today - timedelta(days=30), today), # Padrão para os últimos 30 dias
        max_value=today,
        key="date_filter_concluidos"
    )

    if len(selected_dates) == 2:
        start_date, end_date = selected_dates
        end_date_inclusive = end_date + timedelta(days=1)
    else:
        start_date = today - timedelta(days=30)
        end_date_inclusive = today + timedelta(days=1)
    
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        # --- QUERY CORRIGIDA ---
        # A coluna 'observacao_execucao' agora é buscada da subquery 'serv'
        query = """
            SELECT
                es.veiculo_id, es.quilometragem, es.fim_execucao,
                v.placa, v.empresa,
                serv.area, serv.tipo, serv.quantidade, serv.status, f.nome as funcionario_nome,
                serv.observacao_execucao
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN (
                SELECT execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_borracharia UNION ALL
                SELECT execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_alinhamento UNION ALL
                SELECT execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            LEFT JOIN funcionarios f ON serv.funcionario_id = f.id
            WHERE 
                es.status = 'finalizado'
                AND es.fim_execucao >= %s 
                AND es.fim_execucao < %s
            ORDER BY es.fim_execucao DESC, serv.area;
        """
        df_completo = pd.read_sql(query, conn, params=(start_date, end_date_inclusive))

        if df_completo.empty:
            st.info(f"ℹ️ Nenhum serviço foi concluído no período selecionado.")
            return
            
        visitas_agrupadas = df_completo.groupby(['veiculo_id', 'placa', 'empresa', 'quilometragem'], sort=False)
        
        st.subheader(f"Total de visitas encontradas no período: {len(visitas_agrupadas)}")
        
        for (veiculo_id, placa, empresa, quilometragem), grupo_visita in visitas_agrupadas:
            info_visita = grupo_visita.iloc[0]
            with st.container(border=True):
                col1, col2, col3 = st.columns([0.5, 0.3, 0.2])
                with col1:
                    st.markdown(f"#### Veículo: **{placa}** ({empresa})")
                with col2:
                    st.write(f"**Data de Conclusão:** {pd.to_datetime(info_visita['fim_execucao']).strftime('%d/%m/%Y')}")
                    st.write(f"**Quilometragem:** {quilometragem:,} km".replace(',', '.'))
                
                with col3:
                    if st.session_state.get('user_role') == 'admin':
                        if st.button("Reverter Visita", key=f"revert_{veiculo_id}_{quilometragem}", type="secondary", use_container_width=True):
                            # A função de reverter precisa ser criada ou ajustada
                            st.warning("Função de reverter ainda não implementada.")

                observacoes = grupo_visita['observacao_execucao'].dropna().unique()
                if len(observacoes) > 0 and any(obs for obs in observacoes):
                    st.markdown("**Observações da Visita:**")
                    for obs in observacoes:
                        if obs: st.info(obs)

                st.markdown("##### Serviços realizados nesta visita:")
                servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status': 'Status', 'funcionario_nome': 'Executado por'})
                servicos_da_visita.dropna(subset=['Tipo de Serviço'], inplace=True)
                st.table(servicos_da_visita)
                
    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        release_connection(conn)