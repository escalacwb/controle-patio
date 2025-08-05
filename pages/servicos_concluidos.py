import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

def reverter_visita(conn, veiculo_id, quilometragem):
    """
    Reverte todos os serviços de uma visita (agrupada por km) de 'finalizado' para 'pendente'.
    """
    try:
        # CORREÇÃO: Converte os tipos de dados para o padrão do Python
        p_veiculo_id = int(veiculo_id)
        p_quilometragem = int(quilometragem)

        with conn.cursor() as cursor:
            # Passo 1: Encontra todos os IDs de execução para esta visita específica
            cursor.execute(
                "SELECT id FROM execucao_servico WHERE veiculo_id = %s AND quilometragem = %s AND status = 'finalizado'",
                (p_veiculo_id, p_quilometragem)
            )
            execucao_ids_tuples = cursor.fetchall()
            if not execucao_ids_tuples:
                st.error("Nenhuma execução finalizada encontrada para reverter.")
                return

            execucao_ids = [item[0] for item in execucao_ids_tuples]

            # Passo 2: Para cada tabela de serviço, reverte os serviços para 'pendente'
            tabelas = ["servicos_solicitados_borracharia", "servicos_solicitados_alinhamento", "servicos_solicitados_manutencao"]
            for tabela in tabelas:
                cursor.execute(
                    f"UPDATE {tabela} SET status = 'pendente', box_id = NULL, funcionario_id = NULL, execucao_id = NULL WHERE execucao_id = ANY(%s)",
                    (execucao_ids,)
                )
            
            # Passo 3: Marca as execuções como 'canceladas' para manter o histórico da reversão
            cursor.execute(
                "UPDATE execucao_servico SET status = 'cancelado' WHERE id = ANY(%s)",
                (execucao_ids,)
            )

            conn.commit()
            st.success("Visita revertida com sucesso! Os serviços estão pendentes novamente na tela de alocação.")
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao reverter a visita: {e}")

def app():
    st.title("✅ Histórico de Serviços Concluídos")
    st.markdown("Uma lista de todas as visitas finalizadas, agrupadas por veículo e quilometragem.")
    st.markdown("---")

    st.subheader("Filtrar por Período de Conclusão")
    today = date.today()
    
    selected_dates = st.date_input(
        "Selecione um dia ou um intervalo de datas",
        value=(today - timedelta(days=30), today),
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
                            reverter_visita(conn, veiculo_id, quilometragem)

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