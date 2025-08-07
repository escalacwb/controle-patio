import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz

# Define o fuso horário para garantir que a data "de hoje" seja consistente
MS_TZ = pytz.timezone('America/Campo_Grande')

def processar_historico_veiculo(group, intervalo_revisao_km):
    """
    Esta função processa o histórico de um único veículo para verificar se ele
    está elegível para um contato proativo de revisão.
    """
    # 1. Limpeza e Validação dos Dados
    
    # Remove serviços com KM zerada ou nula e ordena pela data
    group = group.dropna(subset=['quilometragem'])
    group = group[group['quilometragem'] > 0]
    group = group.sort_values('fim_execucao').reset_index(drop=True)

    # Remove registros duplicados na mesma quilometragem, mantendo o mais recente
    group = group.drop_duplicates(subset=['quilometragem'], keep='last')

    # Regra: Precisa de pelo menos 3 visitas válidas
    if len(group) < 3:
        return None

    # Regra: A quilometragem deve ser sempre crescente
    if not group['quilometragem'].is_monotonic_increasing:
        return None

    # 2. Se os dados são válidos, calcula a média
    primeira_visita = group.iloc[0]
    ultima_visita = group.iloc[-1]
    
    delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
    delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

    # Evita divisão por zero se as visitas foram no mesmo dia
    if delta_dias <= 0:
        return None
        
    media_km_diaria = delta_km / delta_dias

    # 3. Estima a quilometragem atual e a próxima revisão
    dias_desde_ultima_visita = (pd.Timestamp.now(tz=MS_TZ) - ultima_visita['fim_execucao']).days
    km_rodados_estimados = dias_desde_ultima_visita * media_km_diaria
    km_atual_estimada = ultima_visita['quilometragem'] + km_rodados_estimados
    
    proxima_revisao_km = ultima_visita['quilometragem'] + intervalo_revisao_km
    
    # 4. Verifica se a KM estimada ultrapassou a meta de revisão
    if km_atual_estimada >= proxima_revisao_km:
        # Retorna um DataFrame com as informações relevantes
        return pd.Series({
            'placa': ultima_visita['placa'],
            'empresa': ultima_visita['empresa'],
            'modelo': ultima_visita['modelo'],
            'nome_motorista': ultima_visita['nome_motorista'],
            'contato_motorista': ultima_visita['contato_motorista'],
            'km_ultima_visita': int(ultima_visita['quilometragem']),
            'data_ultima_visita': ultima_visita['fim_execucao'].strftime('%d/%m/%Y'),
            'km_atual_estimada': int(km_atual_estimada),
            'media_km_diaria': round(media_km_diaria)
        })
    
    return None

def app():
    st.title("📞 Revisão Proativa de Clientes")
    st.markdown("Identifique veículos que provavelmente precisam de uma nova revisão com base no histórico de KM.")
    st.markdown("---")

    # --- CAMPO DE CONFIGURAÇÃO ---
    intervalo_km = st.number_input(
        "Avisar a cada (KM)", 
        min_value=1000, 
        max_value=100000, 
        value=10000, 
        step=1000,
        help="O sistema irá alertar sobre veículos que rodaram aproximadamente esta quilometragem desde a última visita."
    )
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        with st.spinner("Analisando histórico e calculando previsões... Isso pode levar um momento."):
            # Query para buscar todo o histórico necessário de uma só vez
            query = """
                SELECT
                    es.veiculo_id,
                    v.placa,
                    v.empresa,
                    v.modelo,
                    v.nome_motorista, -- Motorista atual (para contato)
                    v.contato_motorista, -- Contato atual
                    es.fim_execucao,
                    es.quilometragem
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                WHERE es.status = 'finalizado' AND es.quilometragem IS NOT NULL AND es.quilometragem > 0
                ORDER BY es.veiculo_id, es.fim_execucao;
            """
            df_historico = pd.read_sql(query, conn)

        if df_historico.empty:
            st.info("Não há histórico de serviços suficiente para gerar previsões.")
            st.stop()
            
        # Agrupa por veículo e aplica a função de processamento
        veiculos_para_contatar = df_historico.groupby('veiculo_id').apply(processar_historico_veiculo, intervalo_revisao_km).dropna()
        
        st.subheader(f"Veículos Sugeridos para Contato ({len(veiculos_para_contatar)}):")

        if veiculos_para_contatar.empty:
            st.success("🎉 Nenhum veículo atingiu a quilometragem estimada para revisão no momento.")
        else:
            for _, veiculo in veiculos_para_contatar.iterrows():
                with st.container(border=True):
                    col1, col2 = st.columns([0.7, 0.3])
                    with col1:
                        st.markdown(f"**Veículo:** `{veiculo['placa']}` - {veiculo['modelo']} ({veiculo['empresa']})")
                        st.markdown(f"**Motorista:** {veiculo['nome_motorista'] or 'Não informado'} | **Contato:** {veiculo['contato_motorista'] or 'N/A'}")
                    with col2:
                        st.metric("KM Estimada Atual", f"{veiculo['km_atual_estimada']:,}".replace(',', '.'))
                    
                    st.caption(f"Última visita em {veiculo['data_ultima_visita']} com {veiculo['km_ultima_visita']:,} km. Média de {veiculo['media_km_diaria']} km/dia.".replace(',', '.'))
    
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os dados: {e}")
    finally:
        release_connection(conn)