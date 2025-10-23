# pages/analise_pneus.py - VERSÃO FINAL COM PROTOCOLO DE 3 FOTOS

import os
import io
import json
import base64
from typing import Optional, List, Dict
from datetime import datetime
import streamlit as st
from PIL import Image, ImageOps, ImageDraw, ImageFont
from openai import OpenAI
import utils  # usa consultar_placa_comercial()

# =========================
# Config
# =========================
WHATSAPP_NUMERO = "5567984173800"
MAX_OBS = 500
MAX_SIDE = 1536
JPEG_QUALITY = 90
DEBUG = bool(st.secrets.get("DEBUG_ANALISE_PNEUS", False))

# Carregar base de conhecimento de defeitos
DEFEITOS_DB = None
try:
    with open('defeitos_database.json', 'r', encoding='utf-8') as f:
        DEFEITOS_DB = json.load(f)
except Exception as e:
    st.warning(f"Base de defeitos não carregada: {e}")
    DEFEITOS_DB = {"defeitos_catalogados": [], "limites_legais": {}, "custos_servicos": {}}

# =========================
# Utilitários de imagem
# =========================

def _open_and_prepare(file) -> Optional[Image.Image]:
    """Abre imagem, corrige EXIF, converte RGB e redimensiona."""
    if not file:
        return None
    try:
        img = Image.open(file)
    except Exception:
        return None
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > MAX_SIDE:
        if w >= h:
            nh = int(h * (MAX_SIDE / w))
            img = img.resize((MAX_SIDE, nh), Image.LANCZOS)
        else:
            nw = int(w * (MAX_SIDE / h))
            img = img.resize((nw, MAX_SIDE), Image.LANCZOS)
    return img

def _fit_to_width(img: Image.Image, target_w: int) -> Image.Image:
    if img.width == target_w:
        return img
    nh = int(img.height * (target_w / img.width))
    return img.resize((target_w, nh), Image.LANCZOS)

def _pad_to_height(img: Image.Image, target_h: int) -> Image.Image:
    if img.height == target_h:
        return img
    canvas = Image.new("RGB", (img.width, target_h), "white")
    canvas.paste(img, (0, 0))
    return canvas

def _draw_label(canvas: Image.Image, text: str, xy=(8, 8), bg=(34, 167, 240), fg=(255, 255, 255)):
    """Desenha um selo com texto no canvas."""
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    pad = 8
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = (len(text) * 6, 12)
    rect = [xy[0], xy[1], xy[0] + tw + pad * 2, xy[1] + th + pad * 2]
    draw.rectangle(rect, fill=bg)
    draw.text((xy[0] + pad, xy[1] + pad), text, fill=fg, font=font)

def _grid_2x3_labeled(
    lt: Image.Image, lm: Image.Image, lb: Image.Image,
    rt: Image.Image, rm: Image.Image, rb: Image.Image,
    labels: Dict[str, str]
) -> Image.Image:
    """
    Monta colagem 2x3 (2 colunas x 3 linhas) com rótulos.
    
    Layout:
    ┌─────────────────┬─────────────────┐
    │ MOTORISTA       │ OPOSTO          │
    │ Foto FRONTAL    │ Foto FRONTAL    │
    │ (lt)            │ (rt)            │
    ├─────────────────┼─────────────────┤
    │ MOTORISTA       │ OPOSTO          │
    │ Foto 45° SULCOS │ Foto 45° SULCOS │
    │ (lm)            │ (rm)            │
    ├─────────────────┼─────────────────┤
    │ MOTORISTA       │ OPOSTO          │
    │ Foto LATERAL    │ Foto LATERAL    │
    │ (lb)            │ (rb)            │
    └─────────────────┴─────────────────┘
    """
    # Garantir que todas imagens existam
    left_w = min(
        lt.width if lt else MAX_SIDE,
        lm.width if lm else MAX_SIDE, 
        lb.width if lb else MAX_SIDE
    )
    right_w = min(
        rt.width if rt else MAX_SIDE,
        rm.width if rm else MAX_SIDE,
        rb.width if rb else MAX_SIDE
    )
    
    # Criar placeholders brancos se alguma imagem faltar
    lt = _fit_to_width(lt, left_w) if lt else Image.new("RGB", (left_w, left_w), "white")
    lm = _fit_to_width(lm, left_w) if lm else Image.new("RGB", (left_w, left_w), "white")
    lb = _fit_to_width(lb, left_w) if lb else Image.new("RGB", (left_w, left_w), "white")
    rt = _fit_to_width(rt, right_w) if rt else Image.new("RGB", (right_w, right_w), "white")
    rm = _fit_to_width(rm, right_w) if rm else Image.new("RGB", (right_w, right_w), "white")
    rb = _fit_to_width(rb, right_w) if rb else Image.new("RGB", (right_w, right_w), "white")
    
    # Uniformizar alturas por linha
    top_h = max(lt.height, rt.height)
    mid_h = max(lm.height, rm.height)
    bot_h = max(lb.height, rb.height)
    
    lt, rt = _pad_to_height(lt, top_h), _pad_to_height(rt, top_h)
    lm, rm = _pad_to_height(lm, mid_h), _pad_to_height(rm, mid_h)
    lb, rb = _pad_to_height(lb, bot_h), _pad_to_height(rb, bot_h)
    
    # Montar canvas final
    total_w = left_w + right_w
    total_h = top_h + mid_h + bot_h
    out = Image.new("RGB", (total_w, total_h), "white")
    
    # Colar imagens
    out.paste(lt, (0, 0))
    out.paste(rt, (left_w, 0))
    out.paste(lm, (0, top_h))
    out.paste(rm, (left_w, top_h))
    out.paste(lb, (0, top_h + mid_h))
    out.paste(rb, (left_w, top_h + mid_h))
    
    # Adicionar labels
    if labels.get("title"):
        _draw_label(out, labels["title"], xy=(8, 8))
    _draw_label(out, labels.get("left_top", ""), xy=(8, 8))
    _draw_label(out, labels.get("right_top", ""), xy=(left_w + 8, 8))
    _draw_label(out, labels.get("left_middle", ""), xy=(8, top_h + 8))
    _draw_label(out, labels.get("right_middle", ""), xy=(left_w + 8, top_h + 8))
    _draw_label(out, labels.get("left_bottom", ""), xy=(8, top_h + mid_h + 8))
    _draw_label(out, labels.get("right_bottom", ""), xy=(left_w + 8, top_h + mid_h + 8))
    
    return out

def _stack_vertical_center(collages: List[Image.Image], titles: List[str]) -> Image.Image:
    """Empilha N colagens verticalmente."""
    if not collages:
        return Image.new("RGB", (800, 600), "white")
    w = max(c.width for c in collages)
    
    def _center_w(img, target_w):
        if img.width == target_w:
            return img
        canvas = Image.new("RGB", (target_w, img.height), "white")
        x = (target_w - img.width) // 2
        canvas.paste(img, (x, 0))
        return canvas
    
    centered = [_center_w(c, w) for c in collages]
    total_h = sum(c.height for c in centered)
    out = Image.new("RGB", (w, total_h), "white")
    y = 0
    for idx, c in enumerate(centered):
        out.paste(c, (0, y))
        _draw_label(out, titles[idx], xy=(10, y + 10))
        y += c.height
    return out

def _img_to_dataurl(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

# =========================
# Prompt Avançado com Protocolo de 3 Fotos
# =========================

def _build_advanced_prompt(meta: dict, obs: str, axis_titles: List[str]) -> str:
    """Constrói prompt extremamente detalhado para análise profissional."""
    
    limites = DEFEITOS_DB.get("limites_legais", {})
    defeitos_conhecidos = DEFEITOS_DB.get("defeitos_catalogados", [])
    custos = DEFEITOS_DB.get("custos_servicos", {})
    
    lista_defeitos = "\n".join([
        f"  - Código {d['codigo']}: {d['nome']} (Severidade: {d['severidade']}, Categoria: {d['categoria']})"
        for d in defeitos_conhecidos[:15]
    ])
    
    prompt = f"""
# SISTEMA AVANÇADO DE ANÁLISE TÉCNICA DE PNEUS PARA FROTAS COMERCIAIS

## 1. CONTEXTO DO VEÍCULO E OPERAÇÃO

### 1.1 Identificação
- **Placa do Veículo:** {meta.get('placa', 'N/A')}
- **Empresa/Frota:** {meta.get('empresa', 'N/A')}
- **Motorista/Gestor:** {meta.get('nome', 'N/A')}
- **Contato:** {meta.get('telefone', 'N/A')} | {meta.get('email', 'N/A')}
- **Data da Inspeção:** {datetime.now().strftime('%d/%m/%Y %H:%M')}

### 1.2 Dados do Veículo (API Externa)
```json
{json.dumps(meta.get('placa_info', {}), ensure_ascii=False, indent=2)}
```

### 1.3 Observações do Motorista/Gestor
"{obs if obs else 'Nenhuma observação fornecida'}"

---

## 2. ESTRUTURA DAS IMAGENS - PROTOCOLO DE 3 FOTOS

**CRÍTICO:** A imagem é uma montagem vertical de colagens 2x3 (2 colunas × 3 linhas).

### 2.1 Ordem dos Eixos (de cima para baixo)
{', '.join(axis_titles)}

### 2.2 Layout de Cada Colagem 2x3
```
┌─────────────────┬─────────────────┐
│ MOTORISTA       │ OPOSTO          │
│ Foto FRONTAL    │ Foto FRONTAL    │
│ (Linha 1)       │ (Linha 1)       │
├─────────────────┼─────────────────┤
│ MOTORISTA       │ OPOSTO          │
│ Foto 45° SULCOS │ Foto 45° SULCOS │
│ (Linha 2)       │ (Linha 2)       │
├─────────────────┼─────────────────┤
│ MOTORISTA       │ OPOSTO          │
│ Foto LATERAL    │ Foto LATERAL    │
│ (Linha 3)       │ (Linha 3)       │
└─────────────────┴─────────────────┘
```

### 2.3 O Que Analisar em Cada Ângulo

**Linha 1 - FRONTAL (banda de rodagem):**
- Padrão de desgaste na largura da banda
- Uniformidade entre centro e ombros
- Alinhamento visual da banda
- Desgaste centralizado (código 13) ou nos ombros (código 22)
- Desgaste irregular assimétrico (código 09)

**Linha 2 - 45° SULCOS (profundidade):**
- Profundidade dos sulcos (estimativa em mm, escala 0-16mm)
- Picotamento, cortes na banda (código 04)
- Objetos cravados (pregos, parafusos - código 31)
- Textura da borracha, rachaduras nos sulcos
- Arrancamento de blocos (código 14)

**Linha 3 - LATERAL (flancos e estrutura):**
- **NOVO ÂNGULO CRÍTICO** para detectar defeitos invisíveis nas outras fotos:
  * Bolhas/ondulações no flanco (códigos 50, 55) - CRÍTICO
  * Cortes e perfurações laterais (código 57) - ALTO
  * Trincas por envelhecimento (código 59) - MÉDIO
  * Descolamentos (código 51, 52)
  * Marcações: DOT, TWI, dimensões, data de fabricação
  * Região do talão (parte inferior perto do aro)

---

## 3. BASE DE CONHECIMENTO TÉCNICO

### 3.1 Legislação Brasileira (CONTRAN 316/2009)
- **Profundidade Mínima Legal:** {limites.get('profundidade_sulco_minima_mm', 1.6)} mm
- **Profundidade Recomendada Substituição:** {limites.get('profundidade_recomendada_substituicao_mm', 3.0)} mm
- **Profundidade Pneu Novo:** ~{limites.get('profundidade_pneu_novo_mm', 16.0)} mm
- **Multa por Infração:** R$ {limites.get('multa_valor_aproximado', 195.23)} + retenção do veículo

### 3.2 Principais Defeitos Catalogados
{lista_defeitos}

### 3.3 Custos Médios de Serviços (Brasil, 2025)
{json.dumps(custos, ensure_ascii=False, indent=2)}

---

## 4. METODOLOGIA DE ANÁLISE EXIGIDA

### 4.1 Análise Quantitativa Obrigatória
Para cada pneu, ESTIME:

1. **Profundidade de Sulco:** Visual estimate em mm (0-16mm scale)
2. **Percentual de Desgaste:** (16mm - sulco_atual) / 16mm × 100%
3. **Vida Útil Restante:** Baseado em profundidade e padrão
4. **Status Legal:** "Conforme" / "Próximo ao Limite" / "ILEGAL (< 1.6mm)"

### 4.2 Análise Qualitativa Detalhada
Para cada defeito identificado:

1. **Nome Técnico** (use códigos da base se aplicável)
2. **Localização Anatômica Precisa:**
   - Linha 1 (Frontal): Centro da banda, ombro esquerdo/direito
   - Linha 2 (45°): Sulcos, profundidade, objetos
   - **Linha 3 (Lateral): Flanco externo, região do talão, marcações**

3. **Diagnóstico de Causa Raiz:**
   - Causa mecânica provável
   - Parâmetro suspeito específico
   - Evidências visuais

4. **Impactos Operacionais Quantificados:**
   - Perda de vida útil (% e km)
   - Aumento de consumo (%)
   - Custo de perda de recapabilidade (R$)
   - Probabilidade e prazo de falha

5. **Classificação de Urgência:**
   - **CRÍTICO:** Risco imediato (bolhas, talão danificado, cintas expostas)
   - **ALTO:** Evolução rápida (cortes profundos, desgaste severo)
   - **MÉDIO:** Requer correção (desgaste moderado, desalinhamento)
   - **BAIXO:** Monitorar (desgaste normal)

### 4.3 Diagnóstico Sistêmico
- Conecte padrões entre eixos
- Identifique componentes mecânicos suspeitos
- Sugira inspeções complementares

---

## 5. FORMATO DE SAÍDA JSON OBRIGATÓRIO

Retorne EXCLUSIVAMENTE JSON seguindo esta estrutura:

```json
{{
  "metadata_inspecao": {{
    "data_hora": "{datetime.now().isoformat()}",
    "placa": "{meta.get('placa', 'N/A')}",
    "empresa": "{meta.get('empresa', 'N/A')}",
    "protocolo_fotos": "3 fotos por pneu (Frontal + 45° + Lateral)"
  }},
  
  "resumo_executivo": {{
    "score_geral_saude": 0-100,
    "status_geral": "Crítico|Atenção|Aceitável|Bom",
    "pneus_criticos_count": 0,
    "pneus_atencao_count": 0,
    "custo_total_estimado_min": 0,
    "custo_total_estimado_max": 0,
    "mensagem_executiva": "Parágrafo direto sobre problemas e ações urgentes"
  }},
  
  "tabela_visao_geral": [
    {{
      "posicao": "Eixo X - Lado Y",
      "profundidade_sulco_mm": 0.0,
      "desgaste_percentual": 0,
      "principal_defeito": "Nome do defeito",
      "urgencia": "Crítico|Alto|Médio|Baixo",
      "status_legal": "Conforme|Próximo|Ilegal",
      "acao_recomendada": "Ação específica"
    }}
  ],
  
  "analise_detalhada_eixos": [
    {{
      "eixo_numero": 1,
      "titulo_eixo": "Nome do eixo",
      "tipo_eixo": "Direcional|Tração|Livre",
      "diagnostico_conjunto_eixo": "Análise do par",
      
      "problemas_sistemicos_eixo": [
        "Problema sistêmico 1",
        "Problema sistêmico 2"
      ],
      
      "analise_pneus": [
        {{
          "posicao": "Motorista|Oposto",
          "medidas_quantitativas": {{
            "profundidade_sulco_estimada_mm": 0.0,
            "profundidade_minima_detectada_mm": 0.0,
            "percentual_desgaste": 0,
            "vida_util_restante_km_estimado": 0,
            "status_legal": "Conforme|Próximo|Ilegal"
          }},
          
          "defeitos": [
            {{
              "codigo_defeito": "XX",
              "nome_defeito": "Nome técnico",
              "localizacao_detalhada": "Linha X da colagem, região específica",
              "severidade": "Crítica|Alta|Média|Baixa",
              "extensao": "% ou descrição",
              "estagio": "Inicial|Moderado|Avançado",
              
              "diagnostico_causa_raiz": {{
                "causa_primaria": "Causa principal",
                "parametro_suspeito": "Parâmetro técnico",
                "causas_secundarias": [],
                "evidencias": "Evidências visuais"
              }},
              
              "impactos_quantificados": {{
                "perda_vida_util_percentual": 0,
                "perda_vida_util_km": "Estimativa",
                "aumento_consumo_combustivel_percentual": 0,
                "custo_perda_recapabilidade": "R$ X-Y",
                "risco_falha_probabilidade": "Baixo|Médio|Alto",
                "tempo_estimado_ate_falha": "X dias"
              }},
              
              "explicacao_pedagogica": {{
                "o_que_e": "Descrição simples",
                "por_que_acontece": "Causa acessível",
                "como_afeta_operacao": "Impacto operacional",
                "consequencias_ignorar": "Riscos",
                "analogia_simples": "Comparação do dia a dia"
              }},
              
              "urgencia": "Crítico|Alto|Médio|Baixo",
              "tempo_para_acao": "X dias"
            }}
          ]
        }}
      ],
      
      "recomendacoes_eixo": [],
      "custo_estimado_eixo": {{"min": 0, "max": 0}}
    }}
  ],
  
  "diagnostico_global_veiculo": {{
    "problemas_sistemicos_identificados": [],
    "componentes_mecanicos_suspeitos": [],
    "inspecoes_complementares_prioritarias": [],
    "hipoteses_operacionais": []
  }},
  
  "plano_de_acao_priorizado": {{
    "critico_risco_imediato": [],
    "alto_agendar_7_dias": [],
    "medio_agendar_30_dias": [],
    "baixo_monitoramento_preventivo": []
  }},
  
  "analise_custo_beneficio": {{
    "investimento_total_estimado": {{"minimo": 0, "maximo": 0}},
    "economia_potencial": {{}},
    "roi_estimado": "",
    "risco_nao_agir": ""
  }},
  
  "conformidade_legal": {{
    "status_geral": "Conforme|Não Conforme|Atenção",
    "pneus_abaixo_limite_legal": [],
    "pneus_proximos_limite": [],
    "risco_multa": "Baixo|Médio|Alto",
    "acao_legal_necessaria": ""
  }},
  
  "whatsapp_resumo": "Laudo resumido para WhatsApp",
  "proxima_inspecao_recomendada": {{"prazo_dias": 30, "motivo": ""}},
  "observacoes_tecnico": "Análise baseada em imagens 2D. Inspeção presencial confirmatória recomendada."
}}
```

---

## 6. DIRETRIZES FINAIS CRÍTICAS

1. **Foto Lateral (Linha 3) é CRUCIAL:** Aqui você detecta 40% dos defeitos críticos que não aparecem nas outras fotos
2. **Seja Quantitativo:** Números > adjetivos
3. **Priorize por Risco:** Crítico = segurança. Alto = $ e tempo
4. **Conecte Sintomas a Causas:** Correlacione observações do motorista com achados visuais
5. **Use a Base de Conhecimento:** Referencie códigos quando aplicável

**EXECUTE A ANÁLISE AGORA. RETORNE APENAS O JSON.**
"""
    return prompt

# =========================
# Chamada OpenAI
# =========================

def _call_openai_advanced(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
    """Chamada OpenAI com prompt avançado."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente."}
    
    client = OpenAI(api_key=api_key)
    
    system_prompt = """Você é um Engenheiro Mecânico sênior especializado em manutenção de frotas comerciais pesadas com 20+ anos de experiência.

Suas especialidades:
- Diagnóstico visual avançado de pneus
- Análise de geometria de suspensão e direção
- Gestão de custos de manutenção de frotas
- Interpretação de padrões de desgaste e falhas
- Legislação de trânsito brasileira (CONTRAN)

IMPORTANTE: As imagens agora incluem fotos laterais (flancos) dos pneus. Esta é a área onde 40% dos defeitos críticos ocorrem (bolhas, cortes, trincas). Analise minuciosamente a Linha 3 (lateral) de cada colagem para detectar estes problemas invisíveis nas fotos frontais.

Retorne APENAS o JSON estruturado. Não adicione texto fora do JSON."""
    
    user_prompt = _build_advanced_prompt(meta, obs, axis_titles)
    
    content = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        
        text = response.choices[0].message.content or ""
        return json.loads(text)
        
    except Exception as e:
        raw_text = locals().get("text", str(e))
        try:
            start = raw_text.find('{')
            end = raw_text.rfind('}') + 1
            if start != -1 and end > start:
                return json.loads(raw_text[start:end])
        except Exception:
            pass
        return {"erro": f"Falha na API: {e}", "raw": raw_text}

# =========================
# UI Renderização
# =========================

def _render_advanced_report(laudo: dict, meta: dict, obs: str):
    """Renderiza relatório avançado na interface."""
    
    resumo = laudo.get("resumo_executivo", {})
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        score = resumo.get("score_geral_saude", 0)
        st.metric("Score de Saúde", f"{score}/100", 
                 delta="🟢 Bom" if score >= 70 else "🟡 Atenção" if score >= 40 else "🔴 Crítico")
    
    with col2:
        st.metric("Pneus Críticos", resumo.get("pneus_criticos_count", 0))
    
    with col3:
        custo_min = resumo.get("custo_total_estimado_min", 0)
        custo_max = resumo.get("custo_total_estimado_max", 0)
        st.metric("Custo Estimado", f"R$ {custo_min:.0f} - {custo_max:.0f}")
    
    with col4:
        status = resumo.get("status_geral", "N/A")
        st.metric("Status Geral", status)
    
    st.markdown("### 📋 Resumo Executivo")
    st.info(resumo.get("mensagem_executiva", "N/A"))
    
    st.markdown("### 📊 Tabela de Visão Geral - Todos os Pneus")
    if laudo.get("tabela_visao_geral"):
        st.dataframe(laudo["tabela_visao_geral"], use_container_width=True, hide_index=True)
    
    conformidade = laudo.get("conformidade_legal", {})
    if conformidade:
        st.markdown("### ⚖️ Conformidade Legal (CONTRAN 316/2009)")
        status_legal = conformidade.get("status_geral", "N/A")
        
        if status_legal == "Não Conforme":
            st.error(f"⛔ **VEÍCULO NÃO CONFORME** - {conformidade.get('acao_legal_necessaria', '')}")
        elif status_legal == "Atenção":
            st.warning(f"⚠️ **ATENÇÃO** - Pneus próximos ao limite legal")
        else:
            st.success("✅ Veículo conforme legislação")
    
    st.markdown("### 🔍 Análise Detalhada por Eixo")
    
    for eixo in laudo.get("analise_detalhada_eixos", []):
        with st.expander(f"**{eixo.get('titulo_eixo', 'Eixo')}** - {eixo.get('tipo_eixo', '')}", expanded=False):
            st.write(f"**Diagnóstico do Conjunto:** {eixo.get('diagnostico_conjunto_eixo', 'N/A')}")
            
            if eixo.get("problemas_sistemicos_eixo"):
                st.markdown("**⚠️ Problemas Sistêmicos Detectados:**")
                for prob in eixo.get("problemas_sistemicos_eixo", []):
                    st.write(f"- {prob}")
            
            for pneu in eixo.get("analise_pneus", []):
                st.markdown(f"#### 📍 Pneu: {pneu.get('posicao', 'N/A')}")
                
                medidas = pneu.get("medidas_quantitativas", {})
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Sulco", f"{medidas.get('profundidade_sulco_estimada_mm', 0)} mm")
                with col2:
                    st.metric("Desgaste", f"{medidas.get('percentual_desgaste', 0):.1f}%")
                with col3:
                    st.metric("Vida Restante", f"{medidas.get('vida_util_restante_km_estimado', 0):,} km")
                with col4:
                    status_legal = medidas.get("status_legal", "N/A")
                    cor = "🟢" if status_legal == "Conforme" else "🟡" if "Próximo" in status_legal else "🔴"
                    st.metric("Legal", f"{cor} {status_legal}")
                
                for defeito in pneu.get("defeitos", []):
                    with st.container(border=True):
                        urgencia = defeito.get("urgencia", "N/A")
                        emoji = "🔴" if urgencia == "Crítico" else "🟠" if urgencia == "Alto" else "🟡" if urgencia == "Médio" else "🟢"
                        
                        st.markdown(f"**{emoji} {defeito.get('nome_defeito', 'Defeito')}** [{urgencia}]")
                        st.caption(f"📍 Onde olhar: {defeito.get('localizacao_detalhada', 'N/A')}")
                        
                        causa = defeito.get("diagnostico_causa_raiz", {})
                        st.markdown(f"**🔎 Causa Raiz:** {causa.get('causa_primaria', 'N/A')}")
                        if causa.get("parametro_suspeito"):
                            st.caption(f"↳ Parâmetro: {causa.get('parametro_suspeito')}")
                        
                        impactos = defeito.get("impactos_quantificados", {})
                        st.markdown("**💰 Impactos:**")
                        st.write(f"- Perda de vida útil: {impactos.get('perda_vida_util_percentual', 0)}% (~{impactos.get('perda_vida_util_km', 'N/A')})")
                        st.write(f"- Aumento consumo: {impactos.get('aumento_consumo_combustivel_percentual', 0)}%")
                        st.write(f"- Custo perda recapabilidade: {impactos.get('custo_perda_recapabilidade', 'N/A')}")
                        
                        with st.expander("ℹ️ Entenda o problema"):
                            exp = defeito.get("explicacao_pedagogica", {})
                            st.markdown(f"""
**O que é:** {exp.get('o_que_e', 'N/A')}

**Por que acontece:** {exp.get('por_que_acontece', 'N/A')}

**Como afeta a operação:** {exp.get('como_afeta_operacao', 'N/A')}

**Consequências de ignorar:** {exp.get('consequencias_ignorar', 'N/A')}

**Analogia:** {exp.get('analogia_simples', 'N/A')}
""")
            
            if eixo.get("recomendacoes_eixo"):
                st.markdown("**🔧 Recomendações para Este Eixo:**")
                for rec in eixo.get("recomendacoes_eixo", []):
                    st.write(f"- {rec}")
            
            custo = eixo.get("custo_estimado_eixo", {})
            if custo:
                st.caption(f"💵 Custo estimado: R$ {custo.get('min', 0)} - {custo.get('max', 0)}")
    
    st.markdown("### 🚛 Diagnóstico Global do Veículo")
    diagnostico_global = laudo.get("diagnostico_global_veiculo", {})
    
    if diagnostico_global.get("problemas_sistemicos_identificados"):
        st.error("**⚠️ Problemas Sistêmicos Identificados:**")
        for prob in diagnostico_global.get("problemas_sistemicos_identificados", []):
            st.write(f"• {prob}")
    
    if diagnostico_global.get("componentes_mecanicos_suspeitos"):
        st.warning("**🔧 Componentes Mecânicos Suspeitos:**")
        for comp in diagnostico_global.get("componentes_mecanicos_suspeitos", []):
            st.write(f"• **{comp.get('componente')}:** {comp.get('motivo')} → {comp.get('acao')}")
    
    st.markdown("### 📋 Plano de Ação Priorizado")
    plano = laudo.get("plano_de_acao_priorizado", {})
    
    if plano.get("critico_risco_imediato"):
        st.error("**🔴 CRÍTICO - Risco Imediato**")
        for acao in plano.get("critico_risco_imediato", []):
            st.write(f"• {acao}")
    
    if plano.get("alto_agendar_7_dias"):
        st.warning("**🟠 ALTO - Agendar em 7 Dias**")
        for acao in plano.get("alto_agendar_7_dias", []):
            st.write(f"• {acao}")
    
    if plano.get("medio_agendar_30_dias"):
        st.info("**🟡 MÉDIO - Agendar em 30 Dias**")
        for acao in plano.get("medio_agendar_30_dias", []):
            st.write(f"• {acao}")
    
    if plano.get("baixo_monitoramento_preventivo"):
        st.success("**🟢 BAIXO - Monitoramento Preventivo**")
        for acao in plano.get("baixo_monitoramento_preventivo", []):
            st.write(f"• {acao}")
    
    if laudo.get("analise_custo_beneficio"):
        st.markdown("### 💰 Análise de Custo-Benefício")
        custo_beneficio = laudo.get("analise_custo_beneficio", {})
        
        col1, col2 = st.columns(2)
        with col1:
            investimento = custo_beneficio.get("investimento_total_estimado", {})
            st.metric("Investimento Necessário", 
                     f"R$ {investimento.get('minimo', 0):,.0f} - {investimento.get('maximo', 0):,.0f}")
        
        with col2:
            st.metric("ROI Estimado", custo_beneficio.get("roi_estimado", "N/A"))
        
        economia = custo_beneficio.get("economia_potencial", {})
        if economia:
            st.write("**Economia Potencial ao Agir Agora:**")
            for key, value in economia.items():
                st.write(f"- {key.replace('_', ' ').title()}: {value}")
        
        if custo_beneficio.get("risco_nao_agir"):
            st.error(f"**⚠️ Risco de Não Agir:** {custo_beneficio.get('risco_nao_agir')}")
    
    proxima = laudo.get("proxima_inspecao_recomendada", {})
    if proxima:
        st.markdown("### 📅 Próxima Inspeção Recomendada")
        st.info(f"**Prazo:** {proxima.get('prazo_dias', 'N/A')} dias | **Motivo:** {proxima.get('motivo', 'N/A')}")

# =========================
# UI Principal
# =========================

def app():
    st.title("🛞 Análise Avançada de Pneus com IA — Protocolo de 3 Fotos")
    st.caption("✅ Agora com análise dos flancos laterais! Laudo técnico profissional baseado em IA.")
    
    # Destaque do novo protocolo
    st.info("🆕 **NOVO PROTOCOLO:** Agora fotografamos os FLANCOS LATERAIS, detectando 40% mais defeitos críticos (bolhas, cortes, trincas) que eram invisíveis antes!")
    
    col_m1, _ = st.columns([1, 3])
    with col_m1:
        modo_detalhado = st.toggle("Análise completa (gpt-4o)", value=True)
        modelo = "gpt-4o" if modo_detalhado else "gpt-4o-mini"
    
    with st.form("form_ident"):
        c1, c2 = st.columns(2)
        with c1:
            nome = st.text_input("Nome do motorista/gestor")
            empresa = st.text_input("Empresa")
            telefone = st.text_input("Telefone de contato")
        with c2:
            email = st.text_input("E-mail")
            placa = st.text_input("Placa do veículo").upper()
        
        buscar = st.form_submit_button("🔎 Buscar dados da placa")
    
    placa_info = st.session_state.get('placa_info', None)
    
    if buscar and placa:
        ok, data = utils.consultar_placa_comercial(placa)
        placa_info = data if ok else {"erro": data}
        st.session_state.placa_info = placa_info
        if ok:
            st.success(f"✅ Dados recuperados: {json.dumps(placa_info, ensure_ascii=False)}")
        else:
            st.warning(data)
    
    st.markdown("---")
    
    with st.expander("📸 Protocolo de Fotografia ATUALIZADO (3 fotos por pneu)", expanded=True):
        st.markdown("""
**Para cada lado do pneu, capture agora 3 fotos:**

1. **Foto FRONTAL da banda** ⭐
   - Câmera perpendicular, distância ~1m
   - Enquadre toda largura da banda

2. **Foto em 45° dos sulcos** ⭐
   - Ângulo diagonal para capturar profundidade
   - Enquadre sulcos centrais

3. **Foto LATERAL do flanco** 🆕 **NOVO - ESSENCIAL**
   - Paralelo ao flanco externo (lado de fora)
   - Enquadre flanco completo desde ombro até talão
   - **Detecta:** Bolhas, cortes, trincas, marcações DOT/TWI

**Requisitos técnicos:**
- Resolução mínima: 1280x720 (recomendado: 1920x1080)
- Iluminação: Natural difusa ou artificial sem sombras
- Foco: Nítido, sem blur

💡 **DICA:** Se você consegue ler o logo do pneu (ex: Michelin) na foto lateral, a foto está boa!
""")
    
    observacao = st.text_area(
        "Observações do motorista/gestor (até 500 caracteres)",
        max_chars=MAX_OBS,
        placeholder="Ex.: Veículo puxa para direita, vibração acima de 80km/h, consumo aumentou 15%, último alinhamento há 8 meses..."
    )
    
    if "axes" not in st.session_state:
        st.session_state.axes = []
    
    cA, cB, cC = st.columns(3)
    with cA:
        if st.button("➕ Adicionar Eixo Dianteiro"):
            st.session_state.axes.append({"tipo": "Dianteiro", "files": {}})
    with cB:
        if st.button("➕ Adicionar Eixo Traseiro"):
            st.session_state.axes.append({"tipo": "Traseiro", "files": {}})
    with cC:
        if st.session_state.axes and st.button("🗑️ Remover Último Eixo"):
            st.session_state.axes.pop()
    
    if not st.session_state.axes and "laudo" not in st.session_state:
        st.info("👆 Adicione pelo menos um eixo para começar")
        return
    
    if st.session_state.axes:
        for idx, eixo in enumerate(st.session_state.axes, start=1):
            with st.container(border=True):
                st.subheader(f"Eixo {idx} — {eixo['tipo']}")
                cm, co = st.columns(2)
                
                with cm:
                    st.markdown("**🔵 Lado MOTORISTA (Esquerdo)**")
                    eixo["files"]["lt"] = st.file_uploader(
                        f"1️⃣ Foto FRONTAL — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"lt_{idx}",
                        help="Banda de rodagem de frente"
                    )
                    eixo["files"]["lm"] = st.file_uploader(
                        f"2️⃣ Foto 45° SULCOS — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"lm_{idx}",
                        help="Ângulo diagonal mostrando profundidade"
                    )
                    eixo["files"]["lb"] = st.file_uploader(
                        f"3️⃣ Foto LATERAL — Eixo {idx} 🆕", 
                        type=["jpg","jpeg","png"], 
                        key=f"lb_{idx}",
                        help="Flanco de lado (detecta bolhas, cortes)"
                    )
                
                with co:
                    st.markdown("**🔴 Lado OPOSTO (Direito)**")
                    eixo["files"]["rt"] = st.file_uploader(
                        f"1️⃣ Foto FRONTAL — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"rt_{idx}",
                        help="Banda de rodagem de frente"
                    )
                    eixo["files"]["rm"] = st.file_uploader(
                        f"2️⃣ Foto 45° SULCOS — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"rm_{idx}",
                        help="Ângulo diagonal mostrando profundidade"
                    )
                    eixo["files"]["rb"] = st.file_uploader(
                        f"3️⃣ Foto LATERAL — Eixo {idx} 🆕", 
                        type=["jpg","jpeg","png"], 
                        key=f"rb_{idx}",
                        help="Flanco de lado (detecta bolhas, cortes)"
                    )
    
    st.markdown("---")
    pronto = st.button("🚀 Enviar para Análise Avançada (3 Fotos)", type="primary")
    
    if "laudo" in st.session_state:
        _render_advanced_report(
            st.session_state["laudo"], 
            st.session_state.get("meta", {}), 
            st.session_state.get("obs", "")
        )
        
        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Nova Análise"):
                for key in ["laudo", "meta", "obs", "ultima_colagem", "pdf_bytes"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        
        with col2:
            st.button("📄 Baixar PDF", disabled=True, help="Em desenvolvimento")
        
        with col3:
            from urllib.parse import quote
            resumo_wpp = st.session_state["laudo"].get("whatsapp_resumo", "")
            link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(resumo_wpp)}"
            st.markdown(f"[📲 Enviar via WhatsApp]({link_wpp})")
    
    if pronto:
        # Validar que TODAS as 6 fotos de cada eixo foram enviadas
        for i, eixo in enumerate(st.session_state.axes, start=1):
            required = ["lt", "lm", "lb", "rt", "rm", "rb"]
            if not all(eixo["files"].get(k) for k in required):
                st.error(f"❌ Envie todas as 6 fotos do Eixo {i} (3 por lado: Frontal + 45° + Lateral)")
                return
        
        with st.spinner("🔄 Preparando imagens com protocolo de 3 fotos..."):
            collages, titles = [], []
            for i, eixo in enumerate(st.session_state.axes, start=1):
                # Abrir todas as 6 fotos
                lt = _open_and_prepare(eixo["files"]["lt"])
                lm = _open_and_prepare(eixo["files"]["lm"])
                lb = _open_and_prepare(eixo["files"]["lb"])
                rt = _open_and_prepare(eixo["files"]["rt"])
                rm = _open_and_prepare(eixo["files"]["rm"])
                rb = _open_and_prepare(eixo["files"]["rb"])
                
                labels = {
                    "title": f"Eixo {i} - {eixo['tipo']}",
                    "left_top": "Motorista - Frontal",
                    "left_middle": "Motorista - 45° Sulcos",
                    "left_bottom": "Motorista - Lateral 🆕",
                    "right_top": "Oposto - Frontal",
                    "right_middle": "Oposto - 45° Sulcos",
                    "right_bottom": "Oposto - Lateral 🆕"
                }
                
                collages.append(_grid_2x3_labeled(lt, lm, lb, rt, rm, rb, labels))
                titles.append(labels["title"])
            
            colagem_final = _stack_vertical_center(collages, titles)
            st.session_state["ultima_colagem"] = colagem_final
            st.session_state["titles"] = titles
            
            if DEBUG:
                st.image(colagem_final, caption="Colagem enviada à IA", use_column_width=True)
            
            data_url = _img_to_dataurl(colagem_final)
        
        meta = {
            "placa": placa,
            "nome": nome,
            "empresa": empresa,
            "telefone": telefone,
            "email": email,
            "placa_info": placa_info
        }
        
        with st.spinner("🤖 Analisando com IA avançada... (pode levar até 2 minutos)"):
            laudo = _call_openai_advanced(data_url, meta, observacao, modelo, titles)
        
        if "erro" in laudo:
            st.error(f"❌ Erro na análise: {laudo.get('erro')}")
            if DEBUG and laudo.get("raw"):
                st.code(laudo.get("raw"))
            return
        
        st.session_state["laudo"] = laudo
        st.session_state["meta"] = meta
        st.session_state["obs"] = observacao
        st.success("✅ Análise concluída! Agora com cobertura completa dos flancos laterais.")
        st.rerun()


if __name__ == "__main__":
    app()
