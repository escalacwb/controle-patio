# /pages/servicos_concluidos.py (VERSÃO FINAL CORRIGIDA)

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import date, timedelta

# --- Função auxiliar para atualizar o tipo de atendimento ---
def update_tipo_atendimento(conn, service_id, area, novo_tipo):
    """Atualiza o tipo de atendimento de um serviço específico na tabela correta."""
    tabela_map = {
        'Borracharia': 'servicos_solicitados_borracharia',
        'Alinhamento': 'servicos_solicitados_alinhamento',
        'Manutenção Mecânica': 'servicos_solicitados_manutencao'
    }
    tabela = tabela_map.get(area)
    if not tabela:
        st.error(f"Área de serviço desconhecida: {area}")
        return False
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE {tabela} SET tipo_atendimento = %s WHERE id = %s",
                (novo_tipo, service_id)
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao atualizar o serviço: {e}")
        return False

def reverter_visita(conn, veiculo_id, quilometragem):
    """Reverte os serviços de uma visita para o status 'pendente'."""
    try:
        p_veiculo_id = int(veiculo_id)
        p_quilometragem = int(quilometragem)

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM execucao_servico WHERE veiculo_id = %s AND quilometragem = %s AND status = 'finalizado'",
                (p_veiculo_id, p_quilometragem)
            )
            execucao_ids_tuples = cursor.fetchall()
            if not execucao_ids_tuples:
                st.error("Nenhuma execução finalizada encontrada para reverter.")
                return

            execucao_ids = [item[0] for item in execucao_ids_tuples]

            tabelas = ["servicos_solicitados_borracharia", "servicos_solicitados_alinhamento", "servicos_solicitados_manutencao"]
            for tabela in tabelas:
                cursor.execute(
                    f"UPDATE {tabela} SET status = 'pendente', box_id = NULL, funcionario_id = NULL, execucao_id = NULL WHERE execucao_id = ANY(%s)",
                    (execucao_ids,)
                )
            
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
        start_date = selected_dates[0] - timedelta(days=30)
        end_date_inclusive = selected_dates[0] + timedelta(days=1)
    
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        # Query atualizada para buscar o ID do serviço e o tipo de atendimento
        query = """
            SELECT
                es.id as execucao_id,
                es.veiculo_id, es.quilometragem, es.fim_execucao,
                es.nome_motorista, es.contato_motorista,
                v.placa, v.empresa,
                serv.service_id, -- ID ÚNICO DO SERVIÇO
                serv.area, serv.tipo, serv.quantidade, serv.status, f.nome as funcionario_nome,
                serv.observacao_execucao,
                serv.tipo_atendimento -- NOVO CAMPO
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN (
                SELECT id as service_id, execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_borracharia UNION ALL
                SELECT id as service_id, execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_alinhamento UNION ALL
                SELECT id as service_id, execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_manutencao
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
            execucao_id_principal = info_visita['execucao_id']
            
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([0.4, 0.3, 0.15, 0.15])
                with col1:
                    st.markdown(f"#### Veículo: **{placa or 'N/A'}** ({empresa or 'N/A'})")
                    if pd.notna(info_visita['nome_motorista']) and info_visita['nome_motorista']:
                        st.caption(f"Motorista: {info_visita['nome_motorista']} ({info_visita['contato_motorista'] or 'N/A'})")
                with col2:
                    data_str = "N/A"
                    if pd.notna(info_visita['fim_execucao']):
                        data_str = pd.to_datetime(info_visita['fim_execucao']).strftime('%d/%m/%Y')
                    st.write(f"**Data de Conclusão:** {data_str}")
                    km_str = "N/A"
                    if pd.notna(quilometragem):
                        km_str = f"{int(quilometragem):,} km".replace(',', '.')
                    st.write(f"**Quilometragem:** {km_str}")
                with col3:
                    st.link_button("📄 Gerar Termo", url=f"/gerar_termos?execucao_id={execucao_id_principal}", use_container_width=True)
                with col4:
                    if st.session_state.get('user_role') == 'admin':
                        if st.button("Reverter", key=f"revert_{veiculo_id}_{quilometragem}", use_container_width=True):
                            reverter_visita(conn, veiculo_id, quilometragem)

                observacoes = grupo_visita['observacao_execucao'].dropna().unique()
                if len(observacoes) > 0 and any(obs for obs in observacoes):
                    st.markdown("**Observações da Visita:**")
                    for obs in observacoes:
                        if obs: st.info(obs)

                st.markdown("##### Serviços realizados nesta visita:")
                
                servicos_da_visita = grupo_visita[['service_id', 'area', 'tipo', 'quantidade', 'funcionario_nome', 'tipo_atendimento']].rename(columns={
                    'service_id': 'ID do Serviço',
                    'area': 'Área', 
                    'tipo': 'Tipo de Serviço', 
                    'quantidade': 'Qtd.', 
                    'funcionario_nome': 'Executado por',
                    'tipo_atendimento': 'Tipo de Atendimento'
                })
                servicos_da_visita.dropna(subset=['Tipo de Serviço'], inplace=True)
                
                original_df = servicos_da_visita.copy()

                # --- MUDANÇA PRINCIPAL: Usando st.data_editor para a tabela interativa ---
                servicos_editados = st.data_editor(
                    servicos_da_visita,
                    key=f"editor_{execucao_id_principal}",
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ID do Serviço": None, # Esconde a coluna de ID
                        "Tipo de Atendimento": st.column_config.SelectboxColumn(
                            "Tipo de Atendimento",
                            help="Selecione se o serviço é Normal ou um Retorno",
                            options=["Normal", "Retorno"],
                            required=True,
                        )
                    },
                    disabled=['Área', 'Tipo de Serviço', 'Qtd.', 'Executado por']
                )

                # --- Lógica para detectar e salvar as mudanças ---
                if not original_df.equals(servicos_editados):
                    diff = original_df.compare(servicos_editados)
                    
                    for index in diff.index:
                        linha_alterada = servicos_editados.loc[index]
                        # --- CORREÇÃO APLICADA AQUI ---
                        # Converte o ID do serviço de numpy.int64 para um int padrão do Python
                        service_id = int(linha_alterada["ID do Serviço"])
                        area_servico = linha_alterada["Área"]
                        novo_tipo = linha_alterada["Tipo de Atendimento"]
                        
                        if update_tipo_atendimento(conn, service_id, area_servico, novo_tipo):
                            st.toast(f"✔️ Serviço '{linha_alterada['Tipo de Serviço']}' atualizado para '{novo_tipo}'.", icon="🎉")
                            st.rerun()
                        else:
                            st.toast("❌ Falha ao atualizar o serviço.", icon="🔥")

    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        release_connection(conn)
