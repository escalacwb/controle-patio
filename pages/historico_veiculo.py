import streamlit as st
import pandas as pd
from database import get_connection, release_connection

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
        # Uma única query para buscar todos os dados daquele veículo
        query = """
            SELECT
                es.quilometragem, es.inicio_execucao, es.fim_execucao, es.status as status_execucao,
                serv.area, serv.tipo, serv.quantidade, serv.status as status_servico, f.nome as funcionario_nome,
                serv.observacao_execucao
            FROM execucao_servico es
            LEFT JOIN (
                SELECT execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_borracharia UNION ALL
                SELECT execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_alinhamento UNION ALL
                SELECT execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id, observacao_execucao FROM servicos_solicitados_manutencao
            ) serv ON es.id = serv.execucao_id
            LEFT JOIN funcionarios f ON serv.funcionario_id = f.id
            JOIN veiculos v ON es.veiculo_id = v.id
            WHERE v.placa = %s
            ORDER BY es.inicio_execucao DESC, serv.area;
        """
        df_completo = pd.read_sql(query, conn, params=(search_placa,))

        if df_completo.empty:
            st.info("Nenhum histórico encontrado para esta placa.")
            return
            
        # Agrupamos as execuções pela quilometragem para definir uma "visita"
        visitas_agrupadas = df_completo.groupby('quilometragem', sort=False)
        st.write(f"**Total de visitas encontradas:** {len(visitas_agrupadas)}")

        for quilometragem, grupo_visita in visitas_agrupadas:
            info_visita = grupo_visita.iloc[0]
            inicio_visita = pd.to_datetime(grupo_visita['inicio_execucao'].min())

            # --- CORREÇÃO APLICADA AQUI: Adicionamos a data ao título ---
            titulo_expander = f"Visita de {inicio_visita.strftime('%d/%m/%Y')} (KM: {quilometragem:,}) | Status: {info_visita['status_execucao'].upper()}".replace(',', '.')
            
            with st.expander(titulo_expander):
                observacoes = grupo_visita['observacao_execucao'].dropna().unique()
                if len(observacoes) > 0 and any(obs for obs in observacoes):
                    st.markdown("**Observações da Visita:**")
                    for obs in observacoes:
                        if obs: st.info(obs)

                st.markdown("##### Serviços realizados nesta visita:")
                servicos_da_visita = grupo_visita[['area', 'tipo', 'quantidade', 'status_servico', 'funcionario_nome']].rename(columns={'area': 'Área', 'tipo': 'Tipo de Serviço', 'quantidade': 'Qtd.', 'status_servico': 'Status', 'funcionario_nome': 'Executado por'})
                servicos_da_visita.dropna(subset=['Tipo de Serviço'], inplace=True)
                st.table(servicos_da_visita)

    except Exception as e:
        st.error(f"❌ Ocorreu um erro: {e}")
        st.exception(e)
    finally:
        release_connection(conn)