import re
import pandas as pd
import hashlib

# FUNÇÕES PURAS QUE NÃO DEPENDEM DO STREAMLIT

def hash_password(password):
    """Gera o hash de uma senha para armazenamento seguro."""
    return hashlib.sha256(password.encode()).hexdigest()

def formatar_telefone(numero: str) -> str:
    """Formata um número de telefone no padrão (XX)XXXXX-XXXX."""
    if not numero:
        return ""
    numeros = re.sub(r'\D', '', numero)
    if len(numeros) == 11:
        return f"({numeros[:2]}){numeros[2:7]}-{numeros[7:]}"
    elif len(numeros) == 10:
        return f"({numeros[:2]}){numeros[2:6]}-{numeros[6:]}"
    else:
        return numero

def formatar_placa(placa: str) -> str:
    """Formata uma placa no padrão antigo (AAA-1234). Placas Mercosul não são alteradas."""
    if not placa:
        return ""
    placa_limpa = re.sub(r'[^A-Z0-9]', '', placa.upper())
    if len(placa_limpa) == 7 and placa_limpa[4].isdigit():
        return f"{placa_limpa[:3]}-{placa_limpa[3:]}"
    else:
        return placa_limpa

def recalcular_media_veiculo(conn, veiculo_id):
    """
    Busca todo o histórico de um veículo, recalcula sua média de KM/dia
    e a salva na tabela 'veiculos'.
    """
    query = """
        SELECT fim_execucao, quilometragem
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado' 
              AND quilometragem IS NOT NULL AND quilometragem > 0
        ORDER BY fim_execucao;
    """
    df_veiculo = pd.read_sql(query, conn, params=(veiculo_id,))

    df_veiculo = df_veiculo.drop_duplicates(subset=['quilometragem'], keep='last')
    
    last_valid_km = -1
    valid_indices = []
    for index, row in df_veiculo.iterrows():
        if row['quilometragem'] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row['quilometragem']
    
    valid_group = df_veiculo.loc[valid_indices]

    if len(valid_group) < 2:
        media_km_diaria = None
    else:
        primeira_visita = valid_group.iloc[0]
        ultima_visita = valid_group.iloc[-1]
        
        # --- MUDANÇA CRÍTICA: Garantir que os tipos são padrão do Python ---
        # Converte os valores de quilometragem para int nativo do Python
        delta_km = int(ultima_visita['quilometragem']) - int(primeira_visita['quilometragem'])
        # A diferença de datas já retorna um int nativo
        delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days

        if delta_dias > 0:
            # O resultado da divisão de dois ints será um float padrão
            media_km_diaria = delta_km / delta_dias
        else:
            media_km_diaria = None

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE veiculos SET media_km_diaria = %s WHERE id = %s",
                (media_km_diaria, veiculo_id)
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        # Imprime o erro para o log, mas não quebra a execução para os outros veículos
        print(f"Erro ao atualizar a média para o veículo {veiculo_id}: {e}")
        return False