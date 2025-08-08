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
            # Query agora é muito mais rápida: busca a média pré-calculada e a última visita
            query = """
                WITH ultima_visita AS (
                    SELECT 
                        veiculo_id,
                        MAX(fim_execucao) as data_ultima_visita,
                        MAX(quilometragem) as km_ultima_visita
                    FROM execucao_servico
                    WHERE status = 'finalizado'
                    GROUP BY veiculo_id
                )
                SELECT
                    v.placa, v.empresa, v.modelo,
                    v.nome_motorista, v.contato_motorista,
                    v.media_km_diaria,
                    uv.data_ultima_visita,
                    uv.km_ultima_visita
                FROM veiculos v
                JOIN ultima_visita uv ON v.id = uv.veiculo_id
                WHERE v.media_km_diaria IS NOT NULL AND v.media_km_diaria > 0;
            """
            df = pd.read_sql(query, conn)

        if df.empty:
            st.info("Não há veículos com média de KM calculada. Finalize novos serviços ou execute o script de cálculo do histórico.")
            st.stop()

        # O cálculo em Python é feito sobre um conjunto de dados já pequeno e rápido
        df['dias_desde_ultima_visita'] = (pd.Timestamp.now(tz=MS_TZ) - pd.to_datetime(df['data_ultima_visita'], utc=True).dt.tz_convert(MS_TZ)).dt.days
        df['km_atual_estimada'] = df['km_ultima_visita'] + (df['dias_desde_ultima_visita'] * df['media_km_diaria'])
        
        veiculos_para_contatar = df[df['km_atual_estimada'] >= (df['km_ultima_visita'] + intervalo_revisao_km)]

        st.subheader(f"Veículos Sugeridos para Contato ({len(veiculos_para_contatar)}):")

        if veiculos_para_contatar.empty:
            st.success("🎉 Nenhum veículo atendeu aos critérios para o contato proativo no momento.")
        else:
            veiculos_para_contatar = veiculos_para_contatar.sort_values(by='km_atual_estimada', ascending=False)
            for _, veiculo in veiculos_para_contatar.iterrows():
                with st.container(border=True):
                    col1, col2 = st.columns([0.7, 0.3])
                    with col1:
                        st.markdown(f"**Veículo:** `{veiculo['placa']}` - {veiculo['modelo']} ({veiculo['empresa']})")
                        st.markdown(f"**Motorista:** {veiculo['nome_motorista'] or 'Não informado'} | **Contato:** {veiculo['contato_motorista'] or 'N/A'}")
                    with col2:
                        st.metric("KM Estimada Atual", f"{int(veiculo['km_atual_estimada']):,}".replace(',', '.'))
                    
                    st.caption(f"Última visita em {veiculo['data_ultima_visita'].strftime('%d/%m/%Y')} com {int(veiculo['km_ultima_visita']):,} km. Média de {int(veiculo['media_km_diaria'])} km/dia.".replace(',', '.'))
    
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os dados: {e}")
    finally:
        release_connection(conn)