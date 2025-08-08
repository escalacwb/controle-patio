import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📞 Revisão Proativa de Clientes")
    st.markdown("Identifique veículos que provavelmente precisam de uma nova revisão com base no histórico de KM.")
    st.markdown("---")

    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO PARA PAGINAÇÃO ---
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 0

    intervalo_revisao_km = st.number_input(
        "Avisar a cada (KM)", 
        min_value=1000, max_value=100000, value=10000, step=1000,
        help="O sistema irá alertar sobre veículos que rodaram aproximadamente esta quilometragem desde a última visita."
    )
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        with st.spinner("Buscando veículos e fazendo previsões..."):
            # --- MUDANÇA: Query agora busca também os serviços da última visita ---
            query = """
                WITH ranked_visits AS (
                    SELECT
                        veiculo_id,
                        id as execucao_id,
                        fim_execucao,
                        quilometragem,
                        ROW_NUMBER() OVER(PARTITION BY veiculo_id ORDER BY fim_execucao DESC) as rn
                    FROM execucao_servico
                    WHERE status = 'finalizado' AND quilometragem IS NOT NULL
                ),
                ultima_visita AS (
                    SELECT veiculo_id, execucao_id, fim_execucao as data_ultima_visita, quilometragem as km_ultima_visita
                    FROM ranked_visits
                    WHERE rn = 1
                ),
                servicos_ultima_visita AS (
                    SELECT 
                        uv.veiculo_id,
                        STRING_AGG(s.tipo, '; ') as servicos_anteriores
                    FROM ultima_visita uv
                    LEFT JOIN (
                        SELECT execucao_id, tipo FROM servicos_solicitados_borracharia
                        UNION ALL
                        SELECT execucao_id, tipo FROM servicos_solicitados_alinhamento
                        UNION ALL
                        SELECT execucao_id, tipo FROM servicos_solicitados_manutencao
                    ) s ON uv.execucao_id = s.execucao_id
                    GROUP BY uv.veiculo_id
                )
                SELECT
                    v.placa, v.empresa, v.modelo,
                    v.nome_motorista, v.contato_motorista,
                    v.media_km_diaria,
                    uv.data_ultima_visita,
                    uv.km_ultima_visita,
                    suv.servicos_anteriores
                FROM veiculos v
                JOIN ultima_visita uv ON v.id = uv.veiculo_id
                LEFT JOIN servicos_ultima_visita suv ON v.id = suv.veiculo_id
                WHERE v.media_km_diaria IS NOT NULL AND v.media_km_diaria > 0;
            """
            df = pd.read_sql(query, conn)

        if df.empty:
            st.info("Não há veículos com média de KM calculada para exibir.")
            st.stop()

        df['dias_desde_ultima_visita'] = (pd.Timestamp.now(tz=MS_TZ) - pd.to_datetime(df['data_ultima_visita'], utc=True).dt.tz_convert(MS_TZ)).dt.days
        df['km_atual_estimada'] = df['km_ultima_visita'] + (df['dias_desde_ultima_visita'] * df['media_km_diaria'])
        
        veiculos_para_contatar = df[df['km_atual_estimada'] >= (df['km_ultima_visita'] + intervalo_revisao_km)].copy()
        veiculos_para_contatar.sort_values(by='km_atual_estimada', ascending=False, inplace=True)
        
        st.subheader(f"Veículos Sugeridos para Contato ({len(veiculos_para_contatar)}):")

        if veiculos_para_contatar.empty:
            st.success("🎉 Nenhum veículo atendeu aos critérios para o contato proativo no momento.")
        else:
            # --- MUDANÇA: Lógica de Paginação ---
            page_size = 20
            start_index = st.session_state.page_number * page_size
            end_index = start_index + page_size
            total_pages = (len(veiculos_para_contatar) + page_size - 1) // page_size
            
            # Exibe apenas a fatia de veículos da página atual
            veiculos_pagina_atual = veiculos_para_contatar.iloc[start_index:end_index]

            for _, veiculo in veiculos_pagina_atual.iterrows():
                with st.container(border=True):
                    col1, col2 = st.columns([0.7, 0.3])
                    with col1:
                        st.markdown(f"**Veículo:** `{veiculo['placa']}` - {veiculo['modelo']} ({veiculo['empresa']})")
                        st.markdown(f"**Motorista:** {veiculo['nome_motorista'] or 'Não informado'} | **Contato:** {veiculo['contato_motorista'] or 'N/A'}")
                        # --- MUDANÇA: Exibe os serviços da última visita ---
                        st.markdown(f"**Últimos Serviços:** *{veiculo['servicos_anteriores'] or 'Nenhum serviço registrado na última visita.'}*")
                    with col2:
                        st.metric("KM Estimada Atual", f"{int(veiculo['km_atual_estimada']):,}".replace(',', '.'))
                    
                    st.caption(f"Última visita em {veiculo['data_ultima_visita'].strftime('%d/%m/%Y')} com {int(veiculo['km_ultima_visita']):,} km. Média de {int(veiculo['media_km_diaria'])} km/dia.".replace(',', '.'))

            st.markdown("---")
            # Controles de Paginação
            col_prev, col_info, col_next = st.columns([1, 2, 1])
            if col_prev.button("⬅️ Anterior", use_container_width=True, disabled=(st.session_state.page_number == 0)):
                st.session_state.page_number -= 1
                st.rerun()
            
            col_info.markdown(f"<div style='text-align: center; font-size: 1.2rem;'>Página {st.session_state.page_number + 1} de {total_pages}</div>", unsafe_allow_html=True)
            
            if col_next.button("Próxima ➡️", use_container_width=True, disabled=(st.session_state.page_number >= total_pages - 1)):
                st.session_state.page_number += 1
                st.rerun()

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os dados: {e}")
        st.exception(e)
    finally:
        release_connection(conn)