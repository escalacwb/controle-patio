import streamlit as st
import pandas as pd
from database import get_connection, release_connection

def app():
    st.title("✅ Histórico de Serviços Concluídos")
    # ... (código idêntico até a query) ...
    # O código completo e correto está abaixo:
    
    st.markdown("Uma lista de todas as visitas finalizadas, agrupadas por veículo e quilometragem.")
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return
    try:
        # --- ALTERAÇÃO AQUI: Buscamos a observação de cada serviço ---
        query = """
            SELECT
                es.veiculo_id, es.quilometragem, es.fim_execucao, v.placa, v.empresa,
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
            WHERE es.status = 'finalizado'
            ORDER BY es.fim_execucao DESC, serv.area;
        """
        df_completo = pd.read_sql(query, conn)
        if df_completo.empty:
            st.info("ℹ️ Nenhum serviço foi concluído no sistema ainda.")
            return
        
        visitas_agrupadas = df_completo.groupby(['placa', 'quilometragem'], sort=False)
        st.subheader(f"Total de visitas finalizadas: {len(visitas_agrupadas)}")
        st.markdown("---")
        for (placa, quilometragem), grupo_visita in visitas_agrupadas:
            info_visita = grupo_visita.iloc[0]
            with st.container(border=True):
                col1, col2 = st.columns(2)
                with col1: st.markdown(f"#### Veículo: **{placa}** ({info_visita['empresa']})")
                with col2:
                    st.write(f"**Data de Conclusão:** {pd.to_datetime(info_visita['fim_execucao']).strftime('%d/%m/%Y')}")
                    st.write(f"**Quilometragem:** {quilometragem:,} km".replace(',', '.'))
                
                # --- ALTERAÇÃO AQUI: Exibimos todas as observações da visita ---
                observacoes = grupo_visita['observacao_execucao'].dropna().unique()
                if len(observacoes) > 0:
                    st.markdown("**Observações da Visita:**")
                    for obs in observacoes:
                        if obs: st.info(obs)

                st.markdown("##### Serviços realizados nesta visita:")
                servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status': 'Status', 'funcionario_nome': 'Executado por'})
                servicos_da_visita.dropna(subset=['Tipo de Serviço'], inplace=True)
                st.table(servicos_da_visita)
    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
    finally:
        release_connection(conn)