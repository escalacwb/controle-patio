# diagnostico_media.py
from database import get_script_connection
import pandas as pd
import re

def analisar_veiculo_detalhadamente(conn, veiculo_id):
    """
    Função de diagnóstico que mostra cada passo do cálculo da média para um único veículo.
    """
    print("\n" + "="*50)
    print(f"INICIANDO DIAGNÓSTICO PROFUNDO PARA VEÍCULO ID: {veiculo_id}")
    print("="*50)

    # 1. Busca dos Dados Brutos
    query = """
        SELECT fim_execucao, quilometragem
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado' 
              AND quilometragem IS NOT NULL AND quilometragem > 0
        ORDER BY fim_execucao;
    """
    df_veiculo = pd.read_sql(query, conn, params=(veiculo_id,))
    
    if df_veiculo.empty:
        print("RESULTADO: Nenhuma visita válida (com KM > 0) encontrada no histórico. Análise encerrada.")
        return

    print("\n--- PASSO 1: DADOS BRUTOS DO BANCO ---")
    print(df_veiculo.to_string())

    # 2. Limpeza de Duplicatas
    df_sem_duplicatas = df_veiculo.drop_duplicates(subset=['quilometragem'], keep='last').reset_index(drop=True)
    print("\n--- PASSO 2: DADOS APÓS REMOVER QUILOMETRAGENS DUPLICADAS ---")
    print(df_sem_duplicatas.to_string())

    # 3. Lógica de Validação (KM crescente)
    print("\n--- PASSO 3: VERIFICAÇÃO DE QUILOMETRAGEM CRESCENTE (VISITA A VISITA) ---")
    last_valid_km = -1
    valid_indices = []
    for index, row in df_sem_duplicatas.iterrows():
        print(f"  - Verificando linha {index}: Data={row['fim_execucao'].date()}, KM={int(row['quilometragem'])}")
        if row['quilometragem'] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row['quilometragem']
            print(f"    -> OK: {int(row['quilometragem'])} > {int(last_valid_km) if last_valid_km != row['quilometragem'] else 'início'}. Linha mantida.")
        else:
            print(f"    -> DESCARTADO: {int(row['quilometragem'])} não é maior que a última KM válida ({int(last_valid_km)}).")
    
    valid_group = df_sem_duplicatas.loc[valid_indices]
    print("\n--- PASSO 4: DADOS FINAIS VÁLIDOS PARA O CÁLCULO ---")
    print(valid_group.to_string())

    # 4. Decisão Final
    print("\n--- PASSO 5: DECISÃO FINAL ---")
    if len(valid_group) < 2:
        print(f"RESULTADO: Média será NULA. Motivo: O número de visitas válidas ({len(valid_group)}) é menor que o mínimo de 2 necessário.")
    else:
        primeira_visita = valid_group.iloc[0]
        ultima_visita = valid_group.iloc[-1]
        delta_km = ultima_visita['quilometragem'] - primeira_visita['quilometragem']
        delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

        print(f"  - Usando {len(valid_group)} visitas para o cálculo.")
        print(f"  - Primeira Visita: {primeira_visita['fim_execucao'].date()} ({int(primeira_visita['quilometragem'])} km)")
        print(f"  - Última Visita:   {ultima_visita['fim_execucao'].date()} ({int(ultima_visita['quilometragem'])} km)")
        print(f"  - Delta KM: {delta_km}")
        print(f"  - Delta Dias: {delta_dias}")

        if delta_dias > 0:
            media_km_diaria = float(delta_km / delta_dias)
            print(f"\nRESULTADO: Média calculada com sucesso: {media_km_diaria:.2f} km/dia.")
        else:
            print("\nRESULTADO: Média será NULA. Motivo: O intervalo de dias entre a primeira e a última visita é zero.")

def run_diagnostico():
    veiculo_id_para_analisar = input("Digite o ID do veículo que deseja diagnosticar (ex: 134): ")
    if not veiculo_id_para_analisar.isdigit():
        print("ID inválido. Por favor, insira apenas números.")
        return

    conn = get_script_connection()
    if not conn:
        return

    try:
        analisar_veiculo_detalhadamente(conn, int(veiculo_id_para_analisar))
    finally:
        if conn:
            conn.close()
            print("\nConexão com o banco de dados fechada.")

if __name__ == "__main__":
    run_diagnostico()