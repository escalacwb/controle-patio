#!/usr/bin/env python3
"""
SCRIPT: simular_correcoes_digitos_v3.py
=======================================
FASE 2C: SIMULAÇÃO - Gera CSV com todos os valores antes/depois
- NÃO altera o banco de dados
- Gera relatórios completos para revisão
- Mostra score de cada correção
- Permite análise antes de aplicar
"""

import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from itertools import combinations
from statistics import median
import numpy as np
from datetime import datetime

load_dotenv()

db_url = os.getenv("DB_URL")
if not db_url:
    print("❌ DB_URL não encontrada em .env")
    exit(1)

print("🔍 Conectando ao banco...")
conn = psycopg2.connect(db_url)

print("\n" + "="*140)
print("🧪 SIMULAÇÃO: CORREÇÃO INTELIGENTE - SEM ALTERAR O BANCO")
print("="*140 + "\n")

# Carregar dados
query_todos = """
SELECT 
    v.id as veiculo_id,
    v.placa,
    es.id as exec_id,
    es.fim_execucao,
    es.quilometragem,
    ROW_NUMBER() OVER (PARTITION BY v.id ORDER BY es.fim_execucao) as visita_indice
FROM veiculos v
INNER JOIN execucao_servico es ON v.id = es.veiculo_id
WHERE es.status = 'finalizado' AND es.quilometragem IS NOT NULL
ORDER BY v.id, es.fim_execucao
"""

print("📊 Carregando dados...")
df_todos = pd.read_sql(query_todos, conn)
print(f"✓ Total de registros carregados: {len(df_todos)}\n")

def calcular_km_dia_media(veiculo_id, df_todos):
    """Calcula MEDIANA km/dia do veículo"""
    df_veiculo = df_todos[df_todos['veiculo_id'] == veiculo_id].copy()
    df_veiculo = df_veiculo[df_veiculo['quilometragem'] > 0].sort_values('fim_execucao').reset_index(drop=True)
    
    if len(df_veiculo) < 2:
        return None
    
    km_diffs = []
    for i in range(1, len(df_veiculo)):
        km_diff = df_veiculo.iloc[i]['quilometragem'] - df_veiculo.iloc[i-1]['quilometragem']
        days_diff = (df_veiculo.iloc[i]['fim_execucao'].date() - df_veiculo.iloc[i-1]['fim_execucao'].date()).days
        
        if days_diff > 0 and km_diff > 0:
            km_dia = km_diff / days_diff
            if 0 < km_dia < 1000:
                km_diffs.append(km_dia)
    
    if km_diffs:
        return median(km_diffs)
    return None

def encontrar_descrescentes(df_veiculo):
    """Encontra índices de registros descrescentes"""
    descrescentes = []
    for i in range(1, len(df_veiculo)):
        if df_veiculo.iloc[i]['quilometragem'] < df_veiculo.iloc[i-1]['quilometragem']:
            descrescentes.append(i)
    return descrescentes

def avaliar_grupo(km_values, dias_intervals, grupo_indices, histórico_km_dia=None):
    """
    Calcula score de qualidade de uma correção (0-100)
    Quanto MAIOR o score, melhor a correção
    """
    km_teste = list(km_values)
    
    # Aplicar +1M aos índices do grupo
    for idx in grupo_indices:
        km_teste[idx] += 1_000_000
    
    # 1. Validar sequência (deve ser sempre crescente)
    for i in range(1, len(km_teste)):
        if km_teste[i] < km_teste[i-1]:
            return 0
    
    # 2. Calcular km/dia após correção
    diffs = []
    for i in range(1, len(km_teste)):
        diff_km = km_teste[i] - km_teste[i-1]
        dias = dias_intervals[i-1] if i-1 < len(dias_intervals) else 1
        if dias > 0:
            km_dia = diff_km / dias
            if 0 < km_dia < 1500:
                diffs.append(km_dia)
    
    if not diffs:
        return 0
    
    diffs = np.array(diffs)
    
    # 3. Calcular coeficiente de variação (uniformidade)
    media = np.mean(diffs)
    desvio = np.std(diffs)
    cv = desvio / media if media > 0 else 1.0
    
    # 4. Score baseado em CV (quanto MENOR CV, melhor)
    if cv < 0.15:
        score = 100
    elif cv < 0.25:
        score = 95
    elif cv < 0.40:
        score = 80
    elif cv < 0.60:
        score = 65
    else:
        score = 20
    
    # 5. Ajustar score com histórico se disponível
    if histórico_km_dia and histórico_km_dia > 0:
        desvio_historico = abs(media - histórico_km_dia) / histórico_km_dia
        
        if desvio_historico < 0.2:
            score = min(100, score + 10)
        elif desvio_historico > 0.8:
            score = max(0, score - 20)
    
    return int(score)

def encontrar_melhor_grupo(km_values, dias_intervals, histórico_km_dia=None, min_score=70):
    """
    Testa TODOS os subconjuntos e encontra o melhor grupo para +1M
    Retorna (indices_grupo, score, km_corrigido)
    """
    melhor_score = -1
    melhor_grupo = None
    km_melhor = list(km_values)
    
    # Testar TODOS os subconjuntos possíveis
    for r in range(1, len(km_values)):
        for grupo_indices in combinations(range(len(km_values)), r):
            score = avaliar_grupo(km_values, dias_intervals, grupo_indices, histórico_km_dia)
            
            if score > melhor_score:
                melhor_score = score
                melhor_grupo = grupo_indices
                
                # Atualizar km_melhor
                km_melhor = list(km_values)
                for idx in melhor_grupo:
                    km_melhor[idx] += 1_000_000
    
    # Retornar se passou do threshold
    if melhor_score >= min_score:
        return melhor_grupo, melhor_score, km_melhor
    else:
        return None, melhor_score, km_values

print("🔎 Analisando todos os veículos com descrescentes (SIMULAÇÃO)...\n")
print("="*140)

correcoes_propostas = []
nao_corrigidos = []
contador_propostas = 0
contador_nao = 0

for veiculo_id in df_todos['veiculo_id'].unique():
    df_veiculo = df_todos[df_todos['veiculo_id'] == veiculo_id].sort_values('fim_execucao').reset_index(drop=True)
    placa = df_veiculo.iloc[0]['placa']
    
    if len(df_veiculo) < 2:
        continue
    
    # Detectar descrescentes
    indices_desc = encontrar_descrescentes(df_veiculo)
    if not indices_desc:
        continue
    
    # Se temos descrescentes, testar
    km_values = df_veiculo['quilometragem'].tolist()
    dias_intervals = []
    for i in range(1, len(df_veiculo)):
        dias = (df_veiculo.iloc[i]['fim_execucao'].date() - df_veiculo.iloc[i-1]['fim_execucao'].date()).days
        dias_intervals.append(max(dias, 1))
    
    # Obter histórico do veículo
    histórico = calcular_km_dia_media(veiculo_id, df_todos)
    
    # Encontrar melhor grupo
    melhor_grupo, score, km_corrigido = encontrar_melhor_grupo(
        km_values, dias_intervals, histórico, min_score=70
    )
    
    if melhor_grupo is None:
        # Não foi possível corrigir com confiança
        for idx in indices_desc:
            nao_corrigidos.append({
                'placa': placa,
                'veiculo_id': veiculo_id,
                'visita': int(df_veiculo.iloc[idx]['visita_indice']),
                'exec_id': int(df_veiculo.iloc[idx]['exec_id']),
                'data': df_veiculo.iloc[idx]['fim_execucao'].date().strftime('%Y-%m-%d'),
                'km_atual': int(km_values[idx]),
                'motivo': f'Score insuficiente: {score}/100',
                'score': score
            })
        contador_nao += len(indices_desc)
        print(f"⚠️  {placa} | Score {score}/100 (min 70) - REJEITADO")
    else:
        # Propor correções
        for idx in melhor_grupo:
            km_novo = int(km_corrigido[idx])
            km_antes = int(km_values[idx])
            exec_id = int(df_veiculo.iloc[idx]['exec_id'])
            
            correcoes_propostas.append({
                'placa': placa,
                'veiculo_id': veiculo_id,
                'visita': int(df_veiculo.iloc[idx]['visita_indice']),
                'exec_id': exec_id,
                'data': df_veiculo.iloc[idx]['fim_execucao'].date().strftime('%Y-%m-%d'),
                'km_antes': km_antes,
                'km_depois': km_novo,
                'diferenca': km_novo - km_antes,
                'score': score,
                'grupo_tamanho': len(melhor_grupo),
                'histórico_km_dia': int(histórico) if histórico else 0
            })
            
            print(f"✅ {placa} V{int(df_veiculo.iloc[idx]['visita_indice'])} | "
                  f"{km_antes:,} → {km_novo:,} km [SCORE:{score}%]")
        
        contador_propostas += len(melhor_grupo)

print("\n" + "="*140)
print("\n📊 RESUMO DA SIMULAÇÃO:")
print(f"  • ✅ Correções PROPOSTAS: {contador_propostas}")
print(f"  • ⚠️  REJEITADAS (score baixo): {contador_nao}")
print(f"  • Total analisado: {contador_propostas + contador_nao}")

print(f"\n💾 Gerando relatórios (SEM ALTERAR O BANCO)...\n")

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# 1. Relatório de PROPOSTAS (Correções recomendadas)
if correcoes_propostas:
    df_propostas = pd.DataFrame(correcoes_propostas)
    arquivo_propostas = f"SIMULACAO_PROPOSTAS_{timestamp}.csv"
    df_propostas.to_csv(arquivo_propostas, index=False, encoding='utf-8')
    print(f"✅ {arquivo_propostas}")
    print(f"   {len(df_propostas)} registros propostos para correção")
    
    # Estatísticas
    print(f"\n   📈 ESTATÍSTICAS DAS PROPOSTAS:")
    print(f"      • Score Mínimo: {df_propostas['score'].min()}%")
    print(f"      • Score Máximo: {df_propostas['score'].max()}%")
    print(f"      • Score Médio: {df_propostas['score'].mean():.1f}%")
    print(f"      • KM Total a corrigir: {df_propostas['diferenca'].sum():,} km")
    print(f"      • Veículos afetados: {df_propostas['placa'].nunique()}")

# 2. Relatório de REJEIÇÕES (Não conseguiu corrigir)
if nao_corrigidos:
    df_rejeicoes = pd.DataFrame(nao_corrigidos)
    arquivo_rejeicoes = f"SIMULACAO_REJEICOES_{timestamp}.csv"
    df_rejeicoes.to_csv(arquivo_rejeicoes, index=False, encoding='utf-8')
    print(f"\n✅ {arquivo_rejeicoes}")
    print(f"   {len(df_rejeicoes)} registros rejeitados")
    
    # Análise de rejeições
    print(f"\n   ⚠️  ANÁLISE DAS REJEIÇÕES:")
    print(f"      • Score Mínimo: {df_rejeicoes['score'].min()}%")
    print(f"      • Score Máximo: {df_rejeicoes['score'].max()}%")
    print(f"      • Score Médio: {df_rejeicoes['score'].mean():.1f}%")

# 3. Relatório CONSOLIDADO com histórico completo
print(f"\n📋 Gerando relatório consolidado com histórico...")
relatorio_consolidado = []

for veiculo_id in df_todos['veiculo_id'].unique():
    df_veiculo = df_todos[df_todos['veiculo_id'] == veiculo_id].sort_values('fim_execucao').reset_index(drop=True)
    placa = df_veiculo.iloc[0]['placa']
    
    # Carregar correções propostas para este veículo
    correcoes_veiculo = {int(r['exec_id']): r for r in correcoes_propostas if r['veiculo_id'] == veiculo_id}
    
    for idx, row in df_veiculo.iterrows():
        exec_id = int(row['exec_id'])
        
        if exec_id in correcoes_veiculo:
            correção = correcoes_veiculo[exec_id]
            status = "PROPOSTO_CORRIGIR"
            km_novo = correção['km_depois']
            score = correção['score']
        else:
            status = "SEM_ALTERAÇÃO"
            km_novo = None
            score = None
        
        relatorio_consolidado.append({
            'placa': placa,
            'veiculo_id': veiculo_id,
            'visita': int(row['visita_indice']),
            'exec_id': exec_id,
            'data': row['fim_execucao'].date().strftime('%Y-%m-%d'),
            'km_atual': int(row['quilometragem']),
            'km_proposto': km_novo,
            'status': status,
            'score': score
        })

df_consolidado = pd.DataFrame(relatorio_consolidado)
arquivo_consolidado = f"SIMULACAO_CONSOLIDADO_{timestamp}.csv"
df_consolidado.to_csv(arquivo_consolidado, index=False, encoding='utf-8')
print(f"✅ {arquivo_consolidado}")
print(f"   Histórico completo com status de cada registro")

# 4. Relatório por VEÍCULO (resumido)
print(f"\n📊 Gerando resumo por veículo...")
resumo_veiculo = []

for placa in df_consolidado['placa'].unique():
    df_placa = df_consolidado[df_consolidado['placa'] == placa]
    propostas = len(df_placa[df_placa['status'] == 'PROPOSTO_CORRIGIR'])
    
    if propostas > 0:
        resumo_veiculo.append({
            'placa': placa,
            'total_registros': len(df_placa),
            'propostas_corrigir': propostas,
            'score_medio': int(df_placa[df_placa['score'].notna()]['score'].mean()) if len(df_placa[df_placa['score'].notna()]) > 0 else None,
            'km_total_antes': int(df_placa['km_atual'].sum()),
            'km_total_depois': int(df_placa.apply(lambda r: r['km_proposto'] if r['km_proposto'] else r['km_atual'], axis=1).sum())
        })

if resumo_veiculo:
    df_resumo = pd.DataFrame(resumo_veiculo)
    arquivo_resumo = f"SIMULACAO_RESUMO_VEICULOS_{timestamp}.csv"
    df_resumo.to_csv(arquivo_resumo, index=False, encoding='utf-8')
    print(f"✅ {arquivo_resumo}")
    print(f"   Resumo de {len(df_resumo)} veículos com propostas")

conn.close()

print(f"\n" + "="*140)
print(f"✅ SIMULAÇÃO CONCLUÍDA - SEM ALTERAÇÕES AO BANCO!")
print(f"="*140)
print(f"\n📂 ARQUIVOS GERADOS:")
if correcoes_propostas:
    print(f"   1. {arquivo_propostas} - Correções recomendadas (APLIQUE ESTE)")
if nao_corrigidos:
    print(f"   2. {arquivo_rejeicoes} - Casos rejeitados")
print(f"   3. {arquivo_consolidado} - Histórico completo")
if resumo_veiculo:
    print(f"   4. {arquivo_resumo} - Resumo por veículo")

print(f"\n🔍 PRÓXIMAS AÇÕES:")
print(f"   1. Revise os CSVs com os valores antigos e novos")
print(f"   2. Valide as correções propostas")
print(f"   3. Se estiver OK, execute: python aplicar_correcoes_simulacao.py")
print(f"   4. Este script aplicará as mudanças ao banco de dados")
