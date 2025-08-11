# /pages/ajustar_media_km.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime

def app():
    st.set_page_config(layout="centered")
    st.title("🛠️ Ajuste de Média de KM")

    # --- Pega o ID do veículo da URL ---
    try:
        veiculo_id = int(st.query_params.get("veiculo_id"))
    except (ValueError, TypeError):
        st.error("ID do veículo não encontrado na URL. Por favor, acesse esta página através do botão 'Ajustar Média' na tela de Revisão Proativa.")
        st.stop()

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    # --- Lógica de Estado da Sessão ---
    session_key = f"visitas_veiculo_{veiculo_id}"
    if session_key not in st.session_state:
        query = """
            SELECT id, fim_execucao, quilometragem
            FROM execucao_servico
            WHERE veiculo_id = %s AND status = 'finalizado'
                  AND quilometragem IS NOT NULL AND quilometragem > 0
            ORDER BY fim_execucao ASC;
        """
        df_visitas = pd.read_sql(query, conn, params=(veiculo_id,))
        df_visitas['fim_execucao'] = pd.to_datetime(df_visitas['fim_execucao']).dt.date
        st.session_state[session_key] = df_visitas.to_dict('records')

    # --- Exibe informações do Veículo ---
    df_veiculo_info = pd.read_sql("SELECT placa, modelo FROM veiculos WHERE id = %s", conn, params=(veiculo_id,))
    if not df_veiculo_info.empty:
        placa = df_veiculo_info.iloc[0]['placa']
        modelo = df_veiculo_info.iloc[0]['modelo']
        st.header(f"Veículo: `{placa}` - {modelo}")
    
    st.markdown("---")
    st.subheader("Histórico de Visitas Editável")
    st.info("Altere as datas ou quilometragens abaixo. A nova média será calculada em tempo real.")

    # --- Loop para renderizar os campos editáveis ---
    visitas = st.session_state[session_key]
    if len(visitas) < 2:
        st.warning("São necessárias pelo menos duas visitas com KM válida para calcular a média.")
        st.stop()
        
    for i, visita in enumerate(visitas):
        cols = st.columns([0.5, 0.5])
        # Converte a data do BD (que pode ser timestamp) para um objeto date
        data_visita = visita['fim_execucao']
        if not isinstance(data_visita, datetime):
            data_visita = datetime.strptime(str(data_visita), '%Y-%m-%d').date()
            
        nova_data = cols[0].date_input("Data da Visita", value=data_visita, key=f"data_{visita['id']}")
        novo_km = cols[1].number_input("Quilometragem", value=int(visita['quilometragem']), min_value=0, step=100, key=f"km_{visita['id']}")
        
        # Atualiza o estado da sessão se houver mudanças
        st.session_state[session_key][i]['fim_execucao'] = nova_data
        st.session_state[session_key][i]['quilometragem'] = novo_km

    # --- Cálculo e Exibição da Média em Tempo Real ---
    st.markdown("---")
    st.subheader("Previsão da Nova Média")

    visitas_calculo = sorted(st.session_state[session_key], key=lambda x: x['fim_execucao'])
    
    primeira_visita = visitas_calculo[0]
    ultima_visita = visitas_calculo[-1]
    
    delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
    delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

    if delta_dias > 0 and delta_km >= 0:
        nova_media = delta_km / delta_dias
        st.metric("Nova Média Calculada", f"{nova_media:.2f} km/dia")

        if st.button("💾 Salvar Média e Corrigir Histórico", type="primary", use_container_width=True):
            try:
                with conn.cursor() as cursor:
                    # 1. Atualiza o histórico de cada visita
                    for v in st.session_state[session_key]:
                        cursor.execute(
                            "UPDATE execucao_servico SET fim_execucao = %s, quilometragem = %s WHERE id = %s",
                            (v['fim_execucao'], v['quilometragem'], v['id'])
                        )
                    # 2. Atualiza a média final na tabela de veículos
                    cursor.execute(
                        "UPDATE veiculos SET media_km_diaria = %s WHERE id = %s",
                        (nova_media, veiculo_id)
                    )
                conn.commit()
                st.success("Média e histórico atualizados com sucesso!")
                # Limpa o estado da sessão para forçar a recarga dos dados na próxima visita
                del st.session_state[session_key]
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao salvar: {e}")

    else:
        st.error("Não é possível calcular a média. Verifique se as datas são diferentes e se a quilometragem é crescente.")

    release_connection(conn)


# Garante que a função app() seja chamada ao rodar o script
if __name__ == "__main__":
    app()