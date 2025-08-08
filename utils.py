import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests
import re

def hash_password(password):
    # ... (código existente)
    pass

def enviar_notificacao_telegram(mensagem, chat_id_destino):
    # ... (código existente)
    pass

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Não foi possível configurar a localidade para pt_BR.")

def get_catalogo_servicos():
    # ... (código existente)
    pass

def get_service_details_for_execution(conn, execucao_id):
    # ... (código existente)
    pass

def consultar_placa_comercial(placa: str):
    # ... (código existente)
    pass

def formatar_telefone(numero: str) -> str:
    # ... (código existente)
    pass

def formatar_placa(placa: str) -> str:
    # ... (código existente)
    pass

# --- FUNÇÃO DE CÁLCULO COM DIAGNÓSTICO DETALHADO ---
def recalcular_media_veiculo(conn, veiculo_id):
    """
    Versão de diagnóstico da função de recálculo. Imprime cada passo.
    """
    print(f"--- Iniciando análise para Veículo ID: {veiculo_id} ---")
    query = """
        SELECT fim_execucao, quilometragem
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado' 
              AND quilometragem IS NOT NULL AND quilometragem > 0
        ORDER BY fim_execucao;
    """
    df_veiculo = pd.read_sql(query, conn, params=(veiculo_id,))
    print(f"   - Passo 1: Encontradas {len(df_veiculo)} visitas no banco de dados.")

    df_veiculo = df_veiculo.drop_duplicates(subset=['quilometragem'], keep='last')
    
    last_valid_km = -1
    valid_indices = []
    for index, row in df_veiculo.iterrows():
        if row['quilometragem'] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row['quilometragem']
    
    valid_group = df_veiculo.loc[valid_indices]
    print(f"   - Passo 2: Após limpeza de KMs duplicadas e não crescentes, restaram {len(valid_group)} visitas válidas.")

    if len(valid_group) < 2:
        media_km_diaria = None
        print(f"   - DECISÃO: Média definida como NULA (motivo: menos de 2 visitas válidas).")
    else:
        primeira_visita = valid_group.iloc[0]
        ultima_visita = valid_group.iloc[-1]
        delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
        delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

        print(f"   - Passo 3: Calculando com {len(valid_group)} visitas. Delta KM = {delta_km}, Delta Dias = {delta_dias}.")

        if delta_dias > 0:
            media_km_diaria = delta_km / delta_dias
            print(f"   - Passo 4: Média calculada: {media_km_diaria:.2f} km/dia.")
        else:
            media_km_diaria = None
            print(f"   - DECISÃO: Média definida como NULA (motivo: intervalo de dias é zero ou negativo).")

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE veiculos SET media_km_diaria = %s WHERE id = %s",
                (media_km_diaria, veiculo_id)
            )
        conn.commit()
        print(f"   - Passo 5: Resultado salvo no banco de dados: {media_km_diaria}")
        print("-" * 30)
        return True
    except Exception as e:
        conn.rollback()
        print(f"   - ERRO ao salvar no banco para o veículo {veiculo_id}: {e}")
        print("-" * 30)
        return False