# calcular_medias_antigas.py
from database import get_script_connection # MUDANÇA: Importa a nova função
from core_utils import recalcular_media_veiculo
import pandas as pd

def calcular_tudo():
    print("Iniciando cálculo de médias para todo o histórico...")
    conn = get_script_connection() # MUDANÇA: Usa a nova função de conexão
    if not conn:
        # A mensagem de erro específica já será mostrada pela função de conexão
        return

    try:
        df_veiculos = pd.read_sql("SELECT DISTINCT veiculo_id FROM execucao_servico", conn)
        veiculo_ids = df_veiculos['veiculo_id'].tolist()
        
        print(f"Encontrados {len(veiculo_ids)} veículos com histórico. Iniciando recálculo...")
        
        sucesso = 0
        falha = 0
        for i, veiculo_id in enumerate(veiculo_ids):
            print(f"[{i+1}/{len(veiculo_ids)}] Processando veículo ID: {veiculo_id}", end=" ... ")
            if recalcular_media_veiculo(conn, veiculo_id):
                print("OK")
                sucesso += 1
            else:
                print("FALHA")
                falha += 1
            
        print("\n--- CÁLCULO DE MÉDIAS ANTIGAS CONCLUÍDO ---")
        print(f"Sucesso: {sucesso} veículos")
        print(f"Falha: {falha} veículos")

    finally:
        if conn:
            conn.close() # MUDANÇA: Fecha a conexão direta
            print("\nConexão com o banco de dados fechada.")

if __name__ == "__main__":
    calcular_tudo()