# pages/ajustar_media_km_por_placa.py
"""
✅ VERSÃO CORRIGIDA: Remove visitas duplicadas por data/KM
- Problema: Múltiplos serviços na mesma data resultavam em registros duplicados
- Solução: Usar ROW_NUMBER para manter apenas 1 registro por visita
"""

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime


def app():
    st.set_page_config(layout="wide")
    st.title("🔍 Ajuste de Média de KM por Placa")
    
    # PASSO 1: Obter conexão UMA VEZ no início
    conn = get_connection()
    if not conn:
        st.error("❌ Falha ao conectar ao banco de dados")
        st.stop()
    
    # PASSO 2: Input de placa
    st.subheader("📋 Buscar Veículo")
    placa_input = st.text_input(
        "Digite a Placa do Veículo (Ex: HRO8161)",
        placeholder="Ex: HRO8161 ou OOG4552"
    ).upper()
    
    # Se não digitou placa, parar aqui
    if not placa_input:
        st.info("Digite uma placa para começar")
        release_connection(conn)
        return
    
    # PASSO 3: Buscar veículo com a placa
    try:
        df_veiculo = pd.read_sql(
            "SELECT id, placa, modelo FROM veiculos WHERE placa = %s",
            conn,
            params=(placa_input,)
        )
    except Exception as e:
        st.error(f"❌ Erro ao buscar veículo: {str(e)}")
        release_connection(conn)
        return
    
    if df_veiculo.empty:
        st.error(f"❌ Veículo com placa '{placa_input}' não encontrado!")
        st.info("Dica: Verifique se a placa está correta")
        release_connection(conn)
        return
    
    # PASSO 4: Extrai veiculo_id
    veiculo_id = int(df_veiculo.iloc[0]['id'])
    placa = df_veiculo.iloc[0]['placa']
    modelo = df_veiculo.iloc[0]['modelo']
    
    # PASSO 5: Exibe informações
    st.markdown("---")
    st.header(f"🚗 {placa} - {modelo}")
    
    # PASSO 6: Gerenciar estado de sessão para visitas
    session_key = f"visitas_veiculo_{veiculo_id}"
    
    if session_key not in st.session_state:
        # ✅ QUERY CORRIGIDA: Remove duplicatas por data/KM usando ROW_NUMBER
        query = """
SELECT id, fim_execucao, quilometragem
FROM (
    SELECT 
        id,
        fim_execucao,
        quilometragem,
        ROW_NUMBER() OVER (PARTITION BY fim_execucao, quilometragem ORDER BY id) as rn
    FROM execucao_servico
    WHERE veiculo_id = %s AND status = 'finalizado'
      AND quilometragem IS NOT NULL AND quilometragem > 0
) as ranked
WHERE rn = 1
ORDER BY fim_execucao ASC;
"""
        try:
            df_visitas = pd.read_sql(query, conn, params=(veiculo_id,))
            df_visitas['fim_execucao'] = pd.to_datetime(df_visitas['fim_execucao']).dt.date
            st.session_state[session_key] = df_visitas.to_dict('records')
        except Exception as e:
            st.error(f"❌ Erro ao buscar visitas: {str(e)}")
            release_connection(conn)
            return
    
    # PASSO 7: Pega visitas do session state
    visitas = st.session_state[session_key]
    
    if len(visitas) < 2:
        st.warning("⚠️ São necessárias pelo menos duas visitas com KM válida para calcular a média.")
        release_connection(conn)
        return
    
    # PASSO 8: Buscar média atual
    try:
        df_media = pd.read_sql(
            "SELECT media_km_diaria FROM veiculos WHERE id = %s",
            conn,
            params=(veiculo_id,)
        )
        media_atual = float(df_media.iloc[0]['media_km_diaria']) if not df_media.empty and df_media.iloc[0]['media_km_diaria'] else None
    except Exception as e:
        st.error(f"❌ Erro ao buscar média: {str(e)}")
        media_atual = None
    
    # PASSO 9: Mostrar métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Visitas", len(visitas))
    with col2:
        if media_atual:
            st.metric("Média Atual", f"{media_atual:.2f} km/dia")
        else:
            st.metric("Média Atual", "Não calculada")
    with col3:
        st.write(f"**Primeira Visita:** {visitas[0]['fim_execucao']}")
    
    # PASSO 10: Seção de edição
    st.markdown("---")
    st.subheader("✏️ Histórico de Visitas Editável")
    st.info("Altere as datas ou quilometragens abaixo. A nova média será calculada em tempo real.")
    
    # PASSO 11: Renderizar campos editáveis
    for i, visita in enumerate(visitas):
        cols = st.columns([0.5, 1.5, 1.5, 1])
        
        with cols[0]:
            st.write(f"{i + 1}")
        
        with cols[1]:
            # Converter data com o mesmo padrão que funciona
            data_visita = visita['fim_execucao']
            if not isinstance(data_visita, datetime):
                data_visita = datetime.strptime(str(data_visita), '%Y-%m-%d').date()
            
            nova_data = st.date_input(
                "Data",
                value=data_visita,
                key=f"data_{visita['id']}"
            )
            st.session_state[session_key][i]['fim_execucao'] = nova_data
        
        with cols[2]:
            novo_km = st.number_input(
                "KM",
                value=int(visita['quilometragem']),
                min_value=0,
                step=100,
                key=f"km_{visita['id']}"
            )
            st.session_state[session_key][i]['quilometragem'] = novo_km
        
        with cols[3]:
            st.write("✅" if novo_km > 0 else "⚠️")
    
    # PASSO 12: Cálculo da média
    st.markdown("---")
    st.subheader("📊 Previsão da Nova Média")
    
    visitas_calculo = sorted(st.session_state[session_key], key=lambda x: x['fim_execucao'])
    
    # Pegar apenas as 3 últimas visitas
    ultimas_3 = visitas_calculo[-3:] if len(visitas_calculo) >= 3 else visitas_calculo
    
    primeira_visita = ultimas_3[0]
    ultima_visita = ultimas_3[-1]
    
    delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
    delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days
    
    # Mostrar informações
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"📊 Baseado em **{len(ultimas_3)}** visitas")
    with col2:
        st.info(f"📅 Período: {delta_dias} dias")
    with col3:
        st.info(f"📈 Delta KM: {delta_km:,.0f} km")
    
    if delta_dias > 0 and delta_km >= 0:
        nova_media = delta_km / delta_dias
        
        st.metric("Nova Média Calculada", f"{nova_media:.2f} km/dia")
        
        # Botão para salvar
        if st.button("💾 Salvar Média e Corrigir Histórico", type="primary", use_container_width=True):
            try:
                with conn.cursor() as cursor:
                    # 1. Atualiza TODAS as visitas
                    for v in st.session_state[session_key]:
                        cursor.execute(
                            "UPDATE execucao_servico SET fim_execucao = %s, quilometragem = %s WHERE id = %s",
                            (v['fim_execucao'], v['quilometragem'], v['id'])
                        )
                    
                    # 2. Atualiza a média final
                    cursor.execute(
                        "UPDATE veiculos SET media_km_diaria = %s WHERE id = %s",
                        (nova_media, veiculo_id)
                    )
                
                conn.commit()
                st.success("✅ Média e histórico atualizados com sucesso!")
                
                # Limpar estado
                del st.session_state[session_key]
                st.rerun()
            
            except Exception as e:
                conn.rollback()
                st.error(f"❌ Erro ao salvar: {str(e)}")
    else:
        st.error("❌ Não é possível calcular a média. Verifique se as datas são diferentes e se a quilometragem é crescente.")
    
    # Botão de nova busca
    st.markdown("---")
    if st.button("🔄 Buscar Outro Veículo", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    
    # CRUCIAL: Liberar conexão no final
    release_connection(conn)


if __name__ == "__main__":
    app()
