#!/usr/bin/env python3
"""
SCRIPT: extrair_problemas_detalhado_FIXO.py
============================================
Extrai problemas de quilometragem - VISITA POR VISITA
VERSÃO CORRIGIDA: km_dia anterior e proximo
"""

import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from statistics import median

load_dotenv()

db_url = os.getenv("DB_URL")
if not db_url:
    print("❌ DB_URL não encontrada em .env")
    exit(1)

print("🔍 Conectando ao banco...")
conn = psycopg2.connect(db_url)

query_veiculos = """
SELECT DISTINCT v.id, v.placa
FROM veiculos v
INNER JOIN execucao_servico es ON v.id = es.veiculo_id
WHERE es.status = 'finalizado' AND es.quilometragem IS NOT NULL
GROUP BY v.id, v.placa
HAVING COUNT(*) >= 3
ORDER BY v.id
LIMIT 200
"""

print("📊 Carregando veículos...\n")
df_veiculos = pd.read_sql(query_veiculos, conn)
total_veiculos = len(df_veiculos)
print(f"Total de veículos: {total_veiculos}\n")

todos_registros = []

def processar_veiculo(conn, veiculo_id, placa):
    """Processa um veículo e retorna lista de registros"""
    
    query = """
    SELECT fim_execucao, quilometragem
    FROM execucao_servico
    WHERE veiculo_id = %s AND status = 'finalizado'
    ORDER BY fim_execucao ASC
    """
    
    df = pd.read_sql(query, conn, params=(veiculo_id,))
    
    if df.empty or len(df) < 3:
        return []
    
    # Calcular diferenças para detectar outliers
    diffs = []
    for i in range(1, len(df)):
        diff = df.iloc[i]['quilometragem'] - df.iloc[i-1]['quilometragem']
        if diff > 0:
            diffs.append(diff)
    
    mediana_local = median(diffs) if diffs else 0
    limite_outlier = mediana_local * 3
    
    registros = []
    
    for i in range(len(df)):
        km_atual = df.iloc[i]['quilometragem']
        data_atual = df.iloc[i]['fim_execucao'].date()
        
        # Informações anterior
        km_anterior = None
        data_anterior = None
        dias_anterior = None
        km_dia_anterior = None
        tipo_problema = "OK"
        
        if i > 0:
            km_anterior = df.iloc[i-1]['quilometragem']
            data_anterior = df.iloc[i-1]['fim_execucao'].date()
            dias_anterior = (data_atual - data_anterior).days
            # CORRIGIR: Apenas calcular se dias > 0 (evita NaN/Inf)
            if dias_anterior > 0:
                km_dia_anterior = round((km_atual - km_anterior) / dias_anterior, 2)
            else:
                km_dia_anterior = None
        
        # Informações próximo
        km_proximo = None
        data_proximo = None
        dias_proximo = None
        km_dia_proximo = None
        
        if i < len(df) - 1:
            km_proximo = df.iloc[i+1]['quilometragem']
            data_proximo = df.iloc[i+1]['fim_execucao'].date()
            dias_proximo = (data_proximo - data_atual).days
            # CORRIGIR: Apenas calcular se dias > 0 (evita NaN/Inf)
            if dias_proximo > 0:
                km_dia_proximo = round((km_proximo - km_atual) / dias_proximo, 2)
            else:
                km_dia_proximo = None
        
        # Detectar problemas
        if km_atual == 0:
            tipo_problema = "ZERADO"
        elif i > 0 and km_atual < km_anterior:
            tipo_problema = "DESCRESCENTE"
        elif i > 0 and (km_atual - km_anterior) > limite_outlier:
            tipo_problema = "OUTLIER"
        
        registros.append({
            'veiculo_id': veiculo_id,
            'placa': placa,
            'visita_indice': i + 1,
            'data_visita': data_atual.strftime('%Y-%m-%d'),
            'km_registrado': int(km_atual),
            'problema_tipo': tipo_problema,
            'km_anterior': int(km_anterior) if km_anterior else None,
            'data_anterior': data_anterior.strftime('%Y-%m-%d') if data_anterior else None,
            'dias_anterior': dias_anterior,
            'km_dia_anterior': km_dia_anterior,  # Agora será number corretamente
            'km_proximo': int(km_proximo) if km_proximo else None,
            'data_proximo': data_proximo.strftime('%Y-%m-%d') if data_proximo else None,
            'dias_proximo': dias_proximo,
            'km_dia_proximo': km_dia_proximo  # Agora será number corretamente
        })
    
    return registros


print("🔎 Processando veículos...\n")
print("=" * 140)

contador = 0
for idx, veiculo in df_veiculos.iterrows():
    veiculo_id = int(veiculo['id'])
    placa = veiculo['placa']
    
    registros = processar_veiculo(conn, veiculo_id, placa)
    
    if not registros:
        continue
    
    # Verificar se tem algum problema
    tem_problema = any(r['problema_tipo'] != "OK" for r in registros)
    
    if tem_problema:
        contador += 1
        print(f"\n[VEÍCULO {contador}] {placa}")
        print("=" * 140)
        
        for reg in registros:
            status = "✓" if reg['problema_tipo'] == "OK" else "❌"
            print(f"  Visita {reg['visita_indice']}: {reg['data_visita']} → {reg['km_registrado']:,} km {status}", end="")
            
            if reg['problema_tipo'] != "OK":
                print(f" [{reg['problema_tipo']}]")
                if reg['km_anterior'] is not None:
                    print(f"    ├─ Anterior: {reg['data_anterior']} → {reg['km_anterior']:,} km ({reg['dias_anterior']} dias)")
                if reg['km_proximo'] is not None:
                    print(f"    ├─ Próximo: {reg['data_proximo']} → {reg['km_proximo']:,} km ({reg['dias_proximo']} dias)")
                if reg['km_dia_anterior'] is not None:
                    print(f"    ├─ km/dia (com anterior): {reg['km_dia_anterior']} km/dia")
                if reg['km_dia_proximo'] is not None:
                    print(f"    ├─ km/dia (com próximo): {reg['km_dia_proximo']} km/dia")
                print()
            else:
                print()
    
    todos_registros.extend(registros)
    
    if (idx + 1) % 50 == 0:
        print(f"... Processados {idx + 1} veículos...")

conn.close()

print("\n" + "=" * 140)

# Salvar CSV
df_registros = pd.DataFrame(todos_registros)

print(f"\n📊 RESUMO FINAL:")
print(f"  • Veículos analisados: {total_veiculos}")
print(f"  • Veículos com problemas: {contador}")
print(f"  • Total de registros extraídos: {len(df_registros)}")
print(f"  • Registros com problemas: {len(df_registros[df_registros['problema_tipo'] != 'OK'])}")

print(f"\n📌 DISTRIBUIÇÃO DE PROBLEMAS:")
problemas = df_registros[df_registros['problema_tipo'] != 'OK']['problema_tipo'].value_counts()
for tipo, count in problemas.items():
    pct = (count / len(df_registros)) * 100
    print(f"  • {tipo}: {count} ({pct:.2f}%)")

print(f"\n💾 Salvando CSV...")
arquivo = "relatorio_problemas_bruto_200casos_FIXO.csv"
df_registros.to_csv(arquivo, index=False, encoding='utf-8')
print(f"✅ {arquivo}")

print(f"\n📋 AMOSTRA (primeiros 30 registros com problema):")
problematicos = df_registros[df_registros['problema_tipo'] != 'OK']
print(problematicos[['placa', 'visita_indice', 'data_visita', 'km_registrado', 'problema_tipo', 'km_anterior', 'dias_anterior', 'km_dia_anterior']].head(30).to_string(index=False))

print(f"\n✅ Processo concluído!")
