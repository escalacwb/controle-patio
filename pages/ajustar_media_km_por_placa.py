# pages/ajustar_media_km_por_placa.py
"""
PÁGINA CORRIGIDA: Ajuste de Média de KM por Placa
Agora usa get_connection/release_connection corretamente
"""

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime


def buscar_veiculo_por_placa(placa):
    """Busca veículo no banco por placa"""
    conn = get_connection()
    if not conn:
        st.error("❌ Falha ao conectar ao banco de dados")
        return None, None
    
    try:
        query = "SELECT id, placa, modelo FROM veiculos WHERE placa = %s"
        df = pd.read_sql(query, conn, params=(placa,))
        
        if df.empty:
            return None, None
        
        veiculo_id = int(df.iloc[0]['id'])
        return veiculo_id, {
            'id': veiculo_id,
            'placa': df.iloc[0]['placa'],
            'modelo': df.iloc[0]['modelo']
        }
    except Exception as e:
        st.error(f"❌ Erro ao buscar veículo: {str(e)}")
        return None, None
    finally:
        release_connection(conn)


def buscar_visitas(veiculo_id):
    """Busca todas as visitas do veículo"""
    conn = get_connection()
    if not conn:
        st.error("❌ Falha ao conectar ao banco de dados")
        return []
    
    try:
        query = """
        SELECT id, fim_execucao, quilometragem
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado'
        AND quilometragem IS NOT NULL AND quilometragem > 0
        ORDER BY fim_execucao ASC
        """
        df = pd.read_sql(query, conn, params=(veiculo_id,))
        
        if df.empty:
            return []
        
        # Converter para formato de dicionário
        visitas = []
        for idx, row in df.iterrows():
            data = pd.to_datetime(row['fim_execucao']).date()
            visitas.append({
                'id': int(row['id']),
                'fim_execucao': data,
                'quilometragem': float(row['quilometragem'])
            })
        
        return visitas
    except Exception as e:
        st.error(f"❌ Erro ao buscar visitas: {str(e)}")
        return []
    finally:
        release_connection(conn)


def buscar_media_atual(veiculo_id):
    """Busca a média atual do veículo"""
    conn = get_connection()
    if not conn:
        return None
    
    try:
        query = "SELECT media_km_diaria FROM veiculos WHERE id = %s"
        df = pd.read_sql(query, conn, params=(veiculo_id,))
        
        if not df.empty:
            return float(df.iloc[0]['media_km_diaria']) if df.iloc[0]['media_km_diaria'] else None
        return None
    except Exception as e:
        st.error(f"❌ Erro ao buscar média: {str(e)}")
        return None
    finally:
        release_connection(conn)


def calcular_media_3_ultimas(visitas):
    """Calcula a média usando as 3 últimas visitas"""
    if len(visitas) < 2:
        return None
    
    # Pegar as 3 últimas
    ultimas = visitas[-3:] if len(visitas) >= 3 else visitas
    
    primeira = ultimas[0]
    ultima = ultimas[-1]
    
    delta_km = ultima['quilometragem'] - primeira['quilometragem']
    delta_dias = (ultima['fim_execucao'] - primeira['fim_execucao']).days
    
    if delta_dias > 0 and delta_km >= 0:
        return delta_km / delta_dias
    
    return None


def app():
    st.set_page_config(layout="wide")
    st.title("🔍 Ajuste de Média de KM por Placa")
    
    # Layout com colunas
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Buscar Veículo")
        placa_input = st.text_input(
            "Digite a Placa do Veículo",
            placeholder="Ex: HRO8161 ou OOG4552",
            key="placa_input"
        ).upper()
    
    with col2:
        st.markdown("---")
        if st.button("🔍 Buscar", use_container_width=True):
            if placa_input:
                st.session_state.buscar_placa = True
                st.session_state.placa_digitada = placa_input
            else:
                st.warning("Digite uma placa para buscar")
    
    # Processamento da busca
    if placa_input and hasattr(st.session_state, 'buscar_placa') and st.session_state.buscar_placa:
        veiculo_id, info_veiculo = buscar_veiculo_por_placa(placa_input)
        
        if veiculo_id is None:
            st.error(f"❌ Veículo com placa '{placa_input}' não encontrado!")
            st.info("Dica: Verifique se a placa está correta e tente novamente")
        else:
            st.session_state.veiculo_id = veiculo_id
            st.session_state.veiculo_info = info_veiculo
    
    # Se encontrou veículo, mostrar interface de ajuste
    if hasattr(st.session_state, 'veiculo_id'):
        veiculo_id = st.session_state.veiculo_id
        info_veiculo = st.session_state.veiculo_info
        
        # Título com informações do veículo
        st.markdown("---")
        st.header(f"🚗 {info_veiculo['placa']} - {info_veiculo['modelo']}")
        
        # Buscar visitas
        visitas = buscar_visitas(veiculo_id)
        
        if len(visitas) < 2:
            st.warning("⚠️ São necessárias pelo menos duas visitas com KM válida para calcular a média.")
            if st.button("🔄 Nova Busca"):
                st.session_state.clear()
                st.rerun()
        else:
            # Informações do veículo
            media_atual = buscar_media_atual(veiculo_id)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total de Visitas", len(visitas))
            with col2:
                if media_atual:
                    st.metric("Média Atual", f"{media_atual:.2f} km/dia")
                else:
                    st.metric("Média Atual", "Não calculada")
            with col3:
                st.metric("Primeira Visita", visitas[0]['fim_execucao'])
            
            # Seção de edição
            st.markdown("---")
            st.subheader("✏️ Histórico de Visitas Editável")
            st.info("Altere as datas ou quilometragens abaixo. A nova média será calculada em tempo real usando as 3 ÚLTIMAS visitas.")
            
            # Criar estado para as visitas se não existir
            session_key = f"visitas_veiculo_{veiculo_id}"
            if session_key not in st.session_state:
                st.session_state[session_key] = [v.copy() for v in visitas]
            
            # Renderizar campos editáveis
            st.markdown("**#** | **Data** | **Quilometragem (km)** | **Status**")
            st.markdown("----|---------|----------------------|--------")
            
            for i, visita in enumerate(st.session_state[session_key]):
                col1, col2, col3, col4 = st.columns([0.5, 1.5, 1.5, 1])
                
                with col1:
                    st.write(f"{i + 1}")
                
                with col2:
                    nova_data = st.date_input(
                        "Data",
                        value=visita['fim_execucao'],
                        key=f"data_{visita['id']}"
                    )
                    st.session_state[session_key][i]['fim_execucao'] = nova_data
                
                with col3:
                    novo_km = st.number_input(
                        "KM",
                        value=int(visita['quilometragem']),
                        min_value=0,
                        step=100,
                        key=f"km_{visita['id']}"
                    )
                    st.session_state[session_key][i]['quilometragem'] = float(novo_km)
                
                with col4:
                    st.write("✅" if novo_km > 0 else "⚠️")
            
            # Cálculo da média
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
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown("")
                with col2:
                    if st.button("💾 Salvar Média e Corrigir Histórico", type="primary", use_container_width=True):
                        # Conectar ao banco
                        conn = get_connection()
                        if conn:
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
                            finally:
                                release_connection(conn)
            else:
                st.error("❌ Não é possível calcular a média. Verifique se as datas são diferentes e se a quilometragem é crescente.")
            
            # Botão de nova busca
            st.markdown("---")
            if st.button("🔄 Buscar Outro Veículo", use_container_width=True):
                st.session_state.clear()
                st.rerun()


if __name__ == "__main__":
    app()
