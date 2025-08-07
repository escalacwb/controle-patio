import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz

MS_TZ = pytz.timezone('America/Campo_Grande')

def processar_historico_veiculo(group, intervalo_revisao_km, min_visitas, debug_placa=None):
    """
    Processa o histórico de um veículo com uma lógica de validação aprimorada
    e um modo de diagnóstico detalhado para uma placa específica.
    """
    placa = group.iloc[0]['placa']
    is_debug_target = (debug_placa and placa == debug_placa)

    if is_debug_target:
        st.subheader(f"🔍 Rastreando Cálculos para a Placa: {placa}")
        st.write("Histórico Bruto Recebido:", group)

    # 1. Limpeza e Validação
    group = group.dropna(subset=['quilometragem'])
    group = group[group['quilometragem'] > 0]
    group = group.sort_values('fim_execucao').reset_index(drop=True)
    group = group.drop_duplicates(subset=['quilometragem'], keep='last')

    if len(group) == 0:
        return None

    last_valid_km = -1
    valid_indices = []
    for index, row in group.iterrows():
        if row['quilometragem'] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row['quilometragem']
    
    valid_group = group.loc[valid_indices].reset_index(drop=True)

    if is_debug_target:
        st.write("Histórico Válido (após limpeza e filtro de KM crescente):", valid_group)

    if len(valid_group) < min_visitas:
        if is_debug_target:
            st.error(f"REJEITADO: Possui apenas {len(valid_group)} visitas válidas, o mínimo necessário é {min_visitas}.")
        return None

    # 2. Cálculo da Média
    primeira_visita = valid_group.iloc[0]
    ultima_visita = valid_group.iloc[-1]
    
    delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
    delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

    if is_debug_target:
        st.write(f"Primeira Visita Válida: {primeira_visita['fim_execucao'].date()} com {primeira_visita['quilometragem']} km")
        st.write(f"Última Visita Válida: {ultima_visita['fim_execucao'].date()} com {ultima_visita['quilometragem']} km")
        st.write(f"Delta KM: {delta_km} | Delta Dias: {delta_dias}")

    if delta_dias <= 0:
        if is_debug_target:
            st.error("REJEITADO: Intervalo de dias entre a primeira e última visita é zero ou negativo.")
        return None
        
    media_km_diaria = delta_km / delta_dias

    # 3. Estimativa
    dias_desde_ultima_visita = (pd.Timestamp.now(tz=MS_TZ) - ultima_visita['fim_execucao']).days
    km_rodados_estimados = dias_desde_ultima_visita * media_km_diaria
    km_atual_estimada = ultima_visita['quilometragem'] + km_rodados_estimados
    proxima_revisao_km = ultima_visita['quilometragem'] + intervalo_revisao_km

    if is_debug_target:
        st.metric("Média KM/dia Calculada", f"{media_km_diaria:.2f}")
        st.metric("Dias Desde a Última Visita", dias_desde_ultima_visita)
        st.metric("KM Estimada Atual", f"{int(km_atual_estimada)}")
        st.metric("Próxima Revisão (KM)", f"{int(proxima_revisao_km)}")

    # 4. Verificação Final
    if km_atual_estimada >= proxima_revisao_km:
        if is_debug_target:
            st.success("APROVADO: A KM estimada é maior ou igual à KM de revisão.")
        return pd.Series({
            'placa': ultima_visita['placa'], 'empresa': ultima_visita['empresa'], 'modelo': ultima_visita['modelo'],
            'nome_motorista': ultima_visita['nome_motorista'], 'contato_motorista': ultima_visita['contato_motorista'],
            'km_ultima_visita': int(ultima_visita['quilometragem']),
            'data_ultima_visita': ultima_visita['fim_execucao'].strftime('%d/%m/%Y'),
            'km_atual_estimada': int(km_atual_estimada), 'proxima_revisao_km': int(proxima_revisao_km),
            'media_km_diaria': round(media_km_diaria)
        })
    else:
        if is_debug_target:
            st.warning("REJEITADO (Normal): O veículo possui dados válidos, mas ainda não atingiu a KM de revisão.")
        return None

def app():
    st.title("📞 Revisão Proativa de Clientes")
    st.markdown("Identifique veículos que provavelmente precisam de uma nova revisão com base no histórico de KM.")
    
    # --- MUDANÇA: Adicionado campo para rastrear uma placa específica ---
    st.markdown("---")
    debug_placa_input = st.text_input("Rastrear Placa Específica (Opcional)", help="Digite uma placa aqui para ver todos os cálculos detalhados para ela.").upper()
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        intervalo_revisao_km = st.number_input( "Avisar a cada (KM)", value=1000, min_value=1000, max_value=100000, step=1000)
    with col2:
        min_visitas = st.number_input("Mínimo de Visitas Válidas para Análise", value=3, min_value=2, max_value=10, step=1)
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        with st.spinner("Analisando histórico e calculando previsões..."):
            query = """
                SELECT es.veiculo_id, v.placa, v.empresa, v.modelo, v.nome_motorista, v.contato_motorista,
                       es.fim_execucao, es.quilometragem
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                WHERE es.status = 'finalizado' AND es.quilometragem IS NOT NULL AND es.quilometragem > 0
                ORDER BY es.veiculo_id, es.fim_execucao;
            """
            df_historico = pd.read_sql(query, conn)

        if df_historico.empty:
            st.info("Não há histórico de serviços suficiente para gerar previsões.")
            st.stop()
            
        # Aplica a função de processamento
        veiculos_para_contatar = df_historico.groupby('veiculo_id').apply(processar_historico_veiculo, intervalo_revisao_km, min_visitas, debug_placa_input).dropna()
        
        # A exibição normal só aparece se não estivermos rastreando uma placa específica
        if not debug_placa_input:
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
                        
                        st.caption(f"Última visita em {veiculo['data_ultima_visita']} com {int(veiculo['km_ultima_visita']):,} km. Média de {int(veiculo['media_km_diaria'])} km/dia.".replace(',', '.'))
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os dados: {e}")
    finally:
        release_connection(conn)