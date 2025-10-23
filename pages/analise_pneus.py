# pages/analise_pneus.py - VERSÃO FINAL COM TABELA DE PNEUS POR POSIÇÃO + MARCA DE FOGO

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
# Utilitários de imagem (mantidos intactos da versão original)
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
    """Monta colagem 2x3 (2 colunas x 3 linhas) com rótulos."""
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
    
    lt = _fit_to_width(lt, left_w) if lt else Image.new("RGB", (left_w, left_w), "white")
    lm = _fit_to_width(lm, left_w) if lm else Image.new("RGB", (left_w, left_w), "white")
    lb = _fit_to_width(lb, left_w) if lb else Image.new("RGB", (left_w, left_w), "white")
    rt = _fit_to_width(rt, right_w) if rt else Image.new("RGB", (right_w, right_w), "white")
    rm = _fit_to_width(rm, right_w) if rm else Image.new("RGB", (right_w, right_w), "white")
    rb = _fit_to_width(rb, right_w) if rb else Image.new("RGB", (right_w, right_w), "white")
    
    top_h = max(lt.height, rt.height)
    mid_h = max(lm.height, rm.height)
    bot_h = max(lb.height, rb.height)
    
    lt, rt = _pad_to_height(lt, top_h), _pad_to_height(rt, top_h)
    lm, rm = _pad_to_height(lm, mid_h), _pad_to_height(rm, mid_h)
    lb, rb = _pad_to_height(lb, bot_h), _pad_to_height(rb, bot_h)
    
    total_w = left_w + right_w
    total_h = top_h + mid_h + bot_h
    out = Image.new("RGB", (total_w, total_h), "white")
    
    out.paste(lt, (0, 0))
    out.paste(rt, (left_w, 0))
    out.paste(lm, (0, top_h))
    out.paste(rm, (left_w, top_h))
    out.paste(lb, (0, top_h + mid_h))
    out.paste(rb, (left_w, top_h + mid_h))
    
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
# Prompt Avançado COM MARCA DE FOGO E TABELA DE POSIÇÃO
# =========================

def _build_advanced_prompt(meta: dict, obs: str, axis_titles: List[str]) -> str:
    """Constrói prompt extremamente detalhado com solicitação de marca de fogo."""
    
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

**Linha 2 - 45° SULCOS (profundidade):**
- Profundidade dos sulcos (estimativa em mm, escala 0-16mm)
- Picotamento, cortes na banda
- Objetos cravados (pregos, parafusos)
- Textura da borracha, rachaduras nos sulcos

**Linha 3 - LATERAL (flancos e estrutura):**
- Bolhas/ondulações no flanco (CRÍTICO)
- Cortes e perfurações laterais
- Trincas por envelhecimento
- **MARCA/MODELO DO PNEU:** Identifique se visível (ex: Michelin XZE, Pirelli FH01, Bridgestone R297)
- **MARCA DE FOGO:** Número/código gravado a fogo no flanco (ex: "FOT-1234", "B7H-5689"). Se não visível, escreva "não identificado"
- Marcações DOT, TWI, dimensões, data de fabricação
- Região do talão (parte inferior perto do aro)

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
5. **Marca/Modelo:** Se legível na foto lateral (ex: "Michelin X Multiway")
6. **Marca de Fogo:** Código gravado a fogo, se visível (ex: "FOT-1234" ou "não identificado")

### 4.2 Análise Qualitativa Detalhada
Para cada defeito identificado:

1. **Nome Técnico** (use códigos da base se aplicável)
2. **Localização Anatômica Precisa**
3. **Diagnóstico de Causa Raiz**
4. **Impactos Operacionais Quantificados**
5. **Classificação de Urgência**

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
  
  "tabela_pneus_por_posicao": [
    {{
      "eixo": "Eixo 1",
      "posicao": "Motorista",
      "marca_modelo": "Michelin XZE ou não identificado",
      "marca_de_fogo": "FOT-1234 ou não identificado",
      "profundidade_sulco_mm": 5.5,
      "desgaste_percentual": 65,
      "defeitos_resumidos": "Desgaste irregular, corte leve",
      "status_legal": "Conforme",
      "urgencia": "Médio",
      "acao_recomendada": "Alinhamento em 30 dias"
    }},
    {{
      "eixo": "Eixo 1",
      "posicao": "Oposto",
      "marca_modelo": "Pirelli FH01",
      "marca_de_fogo": "não identificado",
      "profundidade_sulco_mm": 4.0,
      "desgaste_percentual": 75,
      "defeitos_resumidos": "Sulco irregular",
      "status_legal": "Atenção",
      "urgencia": "Alto",
      "acao_recomendada": "Recapagem urgente"
    }}
  ],
  
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
      
      "analise_pneus": [
        {{
          "posicao": "Motorista|Oposto",
          "marca_modelo": "Michelin XZE ou não identificado",
          "marca_de_fogo": "FOT-1234 ou não identificado",
          
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
      ]
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

1. **Foto Lateral (Linha 3) é CRUCIAL:** Aqui você detecta 40% dos defeitos críticos E identifica marca/modelo + marca de fogo
2. **Marca de Fogo:** Procure por códigos gravados (geralmente 4-12 caracteres alfanuméricos). Ex: "FOT-1234", "B7H-5689", "MXW-7823"
3. **Marca/Modelo:** Procure por logos e nomes (Michelin, Pirelli, Bridgestone, Goodyear, etc) + linha do produto (XZE, FH01, R297)
4. **Se não visível:** Sempre escreva "não identificado" ao invés de deixar vazio
5. **Tabela de Posição:** OBRIGATÓRIA - Liste TODOS os pneus fotografados com marca/modelo/fogo

**EXECUTE A ANÁLISE AGORA. RETORNE APENAS O JSON.**
"""
    return prompt

# =========================
# Chamada OpenAI (inalterada)
# =========================

def _call_openai_advanced(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
    """Chamada OpenAI com prompt avançado - COM MELHOR TRATAMENTO DE ERROS."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente nos secrets."}
    
    # Verificar se API key parece válida
    if not api_key.startswith("sk-"):
        return {"erro": "API Key inválida. Deve começar com 'sk-'"}
    
    client = OpenAI(api_key=api_key)
    
    system_prompt = """Você é um Engenheiro Mecânico sênior especializado em manutenção de frotas comerciais pesadas com 20+ anos de experiência.

Suas especialidades:
- Diagnóstico visual avançado de pneus
- Análise de geometria de suspensão e direção
- Gestão de custos de manutenção de frotas
- Interpretação de padrões de desgaste e falhas
- Legislação de trânsito brasileira (CONTRAN)
- Identificação de marcas, modelos e marcas de fogo em pneus

IMPORTANTE: As imagens incluem fotos laterais (flancos) dos pneus. Nesta foto lateral (Linha 3), além de detectar defeitos, você DEVE:
1. Identificar a MARCA e MODELO do pneu (ex: Michelin XZE, Pirelli FH01)
2. Identificar a MARCA DE FOGO gravada (código alfanumérico de 4-12 caracteres, ex: FOT-1234)
3. Se não visível, escreva "não identificado"

Retorne APENAS o JSON estruturado. Não adicione texto fora do JSON."""
    
    user_prompt = _build_advanced_prompt(meta, obs, axis_titles)
    
    content = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    
    try:
        # Tentar chamada à API com timeout
        import time
        start_time = time.time()
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.2,
            max_tokens=4096,
            response_format={"type": "json_object"},
            timeout=120  # 2 minutos
        )
        
        elapsed = time.time() - start_time
        if DEBUG:
            st.write(f"✅ API respondeu em {elapsed:.1f} segundos")
        
        # Tentar extrair texto
        text = response.choices[0].message.content
        
        if not text:
            return {"erro": "API retornou resposta vazia"}
        
        # Tentar parsear JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            return {
                "erro": f"Resposta da API não é JSON válido: {str(e)}",
                "resposta_bruta": text[:500]  # Primeiros 500 chars
            }
        
    except Exception as e:
        erro_tipo = type(e).__name__
        erro_msg = str(e)
        
        # Erros específicos
        if "authentication" in erro_msg.lower() or "api_key" in erro_msg.lower():
            return {
                "erro": "❌ ERRO DE AUTENTICAÇÃO",
                "detalhes": "API Key inválida ou expirada. Verifique em https://platform.openai.com/api-keys",
                "erro_tecnico": erro_msg
            }
        
        elif "insufficient_quota" in erro_msg.lower() or "quota" in erro_msg.lower():
            return {
                "erro": "❌ ERRO DE CRÉDITOS",
                "detalhes": "Saldo insuficiente. Adicione créditos em https://platform.openai.com/billing",
                "erro_tecnico": erro_msg
            }
        
        elif "timeout" in erro_msg.lower():
            return {
                "erro": "⏱️ TIMEOUT",
                "detalhes": "Análise demorou mais de 2 minutos. Tente com imagens menores",
                "erro_tecnico": erro_msg
            }
        
        elif "content_policy" in erro_msg.lower():
            return {
                "erro": "🚫 ERRO DE POLÍTICA",
                "detalhes": "Conteúdo violou políticas da OpenAI",
                "erro_tecnico": erro_msg
            }
        
        else:
            return {
                "erro": f"❌ ERRO: {erro_tipo}",
                "detalhes": erro_msg,
                "erro_tecnico": erro_msg
            }

# =========================
# UI Renderização COM TABELA DE POSIÇÃO
# =========================

# =========================
# FUNÇÃO _render_advanced_report COMPLETA E CORRIGIDA
# Substitua toda a função no seu arquivo (da linha ~530 até ~790)
# =========================

def _render_advanced_report(laudo: dict, meta: dict, obs: str):
    """Renderiza relatório avançado com tabela de pneus por posição - VERSÃO CORRIGIDA COM DEFENSIVE PROGRAMMING."""
    
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
    
    # Tabela de pneus por posição - COM VALIDAÇÃO
    st.markdown("### 🔍 Tabela de Pneus por Posição (com Marca de Fogo)")
    tabela_pneus = laudo.get("tabela_pneus_por_posicao")
    if tabela_pneus and isinstance(tabela_pneus, list) and len(tabela_pneus) > 0:
        import pandas as pd
        try:
            df_pneus = pd.DataFrame(tabela_pneus)
            
            df_pneus_display = df_pneus.rename(columns={
                "eixo": "Eixo",
                "posicao": "Posição",
                "marca_modelo": "Marca/Modelo",
                "marca_de_fogo": "Marca de Fogo",
                "profundidade_sulco_mm": "Sulco (mm)",
                "desgaste_percentual": "Desgaste (%)",
                "defeitos_resumidos": "Defeitos",
                "status_legal": "Legal",
                "urgencia": "Urgência",
                "acao_recomendada": "Ação Recomendada"
            })
            
            def highlight_nao_identificado(val):
                if isinstance(val, str) and "não identificado" in val.lower():
                    return 'background-color: #fff3cd'
                return ''
            
            st.dataframe(
                df_pneus_display.style.applymap(highlight_nao_identificado, subset=['Marca de Fogo']),
                use_container_width=True,
                hide_index=True
            )
            
            st.caption("💡 **Dica:** Células amarelas indicam marca de fogo não identificada na foto.")
        except Exception as e:
            st.warning(f"Erro ao renderizar tabela de posição: {e}")
    else:
        st.info("Tabela de posição não disponível neste laudo.")
    
    st.markdown("### 📊 Tabela de Visão Geral - Status dos Pneus")
    tabela_geral = laudo.get("tabela_visao_geral")
    if tabela_geral and isinstance(tabela_geral, list) and len(tabela_geral) > 0:
        st.dataframe(tabela_geral, use_container_width=True, hide_index=True)
    
    # Conformidade legal - COM VALIDAÇÃO
    conformidade = laudo.get("conformidade_legal")
    if conformidade and isinstance(conformidade, dict):
        st.markdown("### ⚖️ Conformidade Legal (CONTRAN 316/2009)")
        status_legal = conformidade.get("status_geral", "N/A")
        
        if status_legal == "Não Conforme":
            st.error(f"⛔ **VEÍCULO NÃO CONFORME** - {conformidade.get('acao_legal_necessaria', '')}")
        elif status_legal == "Atenção":
            st.warning(f"⚠️ **ATENÇÃO** - Pneus próximos ao limite legal")
        else:
            st.success("✅ Veículo conforme legislação")
    
    st.markdown("### 🔍 Análise Detalhada por Eixo")
    
    # Análise por eixo - COM VALIDAÇÃO COMPLETA
    eixos = laudo.get("analise_detalhada_eixos")
    if eixos and isinstance(eixos, list) and len(eixos) > 0:
        for eixo in eixos:
            if not isinstance(eixo, dict):
                continue
                
            with st.expander(f"**{eixo.get('titulo_eixo', 'Eixo')}** - {eixo.get('tipo_eixo', '')}", expanded=False):
                st.write(f"**Diagnóstico do Conjunto:** {eixo.get('diagnostico_conjunto_eixo', 'N/A')}")
                
                # Problemas sistêmicos - CORRIGIDO
                problemas_eixo = eixo.get("problemas_sistemicos_eixo")
                if problemas_eixo and isinstance(problemas_eixo, list) and len(problemas_eixo) > 0:
                    st.markdown("**⚠️ Problemas Sistêmicos Detectados:**")
                    for prob in problemas_eixo:
                        if prob and isinstance(prob, str):
                            st.write(f"- {prob}")
                
                # Análise de pneus - COM VALIDAÇÃO
                pneus = eixo.get("analise_pneus")
                if pneus and isinstance(pneus, list):
                    for pneu in pneus:
                        if not isinstance(pneu, dict):
                            continue
                            
                        st.markdown(f"#### 📍 Pneu: {pneu.get('posicao', 'N/A')}")
                        
                        marca_modelo = pneu.get('marca_modelo', 'não identificado')
                        marca_fogo = pneu.get('marca_de_fogo', 'não identificado')
                        marca_info = f"**Marca/Modelo:** {marca_modelo} | **Marca de Fogo:** {marca_fogo}"
                        st.caption(marca_info)
                        
                        medidas = pneu.get("medidas_quantitativas")
                        if medidas and isinstance(medidas, dict):
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Sulco", f"{medidas.get('profundidade_sulco_estimada_mm', 0)} mm")
                            with col2:
                                st.metric("Desgaste", f"{medidas.get('percentual_desgaste', 0):.1f}%")
                            with col3:
                                st.metric("Vida Restante", f"{medidas.get('vida_util_restante_km_estimado', 0):,} km")
                            with col4:
                                status_legal = medidas.get("status_legal", "N/A")
                                cor = "🟢" if status_legal == "Conforme" else "🟡" if "Próximo" in str(status_legal) else "🔴"
                                st.metric("Legal", f"{cor} {status_legal}")
                        
                        defeitos = pneu.get("defeitos")
                        if defeitos and isinstance(defeitos, list):
                            for defeito in defeitos:
                                if not isinstance(defeito, dict):
                                    continue
                                    
                                with st.container(border=True):
                                    urgencia = defeito.get("urgencia", "N/A")
                                    emoji = "🔴" if urgencia == "Crítico" else "🟠" if urgencia == "Alto" else "🟡" if urgencia == "Médio" else "🟢"
                                    
                                    st.markdown(f"**{emoji} {defeito.get('nome_defeito', 'Defeito')}** [{urgencia}]")
                                    st.caption(f"📍 Onde olhar: {defeito.get('localizacao_detalhada', 'N/A')}")
                                    
                                    causa = defeito.get("diagnostico_causa_raiz")
                                    if causa and isinstance(causa, dict):
                                        st.markdown(f"**🔎 Causa Raiz:** {causa.get('causa_primaria', 'N/A')}")
                                        param_suspeito = causa.get("parametro_suspeito")
                                        if param_suspeito:
                                            st.caption(f"↳ Parâmetro: {param_suspeito}")
                                    
                                    impactos = defeito.get("impactos_quantificados")
                                    if impactos and isinstance(impactos, dict):
                                        st.markdown("**💰 Impactos:**")
                                        st.write(f"- Perda de vida útil: {impactos.get('perda_vida_util_percentual', 0)}% (~{impactos.get('perda_vida_util_km', 'N/A')})")
                                        st.write(f"- Aumento consumo: {impactos.get('aumento_consumo_combustivel_percentual', 0)}%")
                                        st.write(f"- Custo perda recapabilidade: {impactos.get('custo_perda_recapabilidade', 'N/A')}")
                                    
                                    exp = defeito.get("explicacao_pedagogica")
                                    if exp and isinstance(exp, dict):
                                        with st.expander("ℹ️ Entenda o problema"):
                                            st.markdown(f"""
**O que é:** {exp.get('o_que_e', 'N/A')}

**Por que acontece:** {exp.get('por_que_acontece', 'N/A')}

**Como afeta a operação:** {exp.get('como_afeta_operacao', 'N/A')}

**Consequências de ignorar:** {exp.get('consequencias_ignorar', 'N/A')}

**Analogia:** {exp.get('analogia_simples', 'N/A')}
""")
                
                # Recomendações do eixo - CORRIGIDO
                recomendacoes = eixo.get("recomendacoes_eixo")
                if recomendacoes and isinstance(recomendacoes, list) and len(recomendacoes) > 0:
                    st.markdown("**🔧 Recomendações para Este Eixo:**")
                    for rec in recomendacoes:
                        if rec and isinstance(rec, str):
                            st.write(f"- {rec}")
                
                # Custo do eixo - CORRIGIDO
                custo = eixo.get("custo_estimado_eixo")
                if custo and isinstance(custo, dict):
                    custo_min = custo.get("min", 0)
                    custo_max = custo.get("max", 0)
                    if custo_min > 0 or custo_max > 0:
                        st.caption(f"💵 Custo estimado: R$ {custo_min} - {custo_max}")
    
    st.markdown("### 🚛 Diagnóstico Global do Veículo")
    diagnostico_global = laudo.get("diagnostico_global_veiculo", {})
    
    # Problemas sistêmicos globais - CORRIGIDO
    problemas = diagnostico_global.get("problemas_sistemicos_identificados")
    if problemas and isinstance(problemas, list) and len(problemas) > 0:
        st.error("**⚠️ Problemas Sistêmicos Identificados:**")
        for prob in problemas:
            if prob and isinstance(prob, str):
                st.write(f"• {prob}")
    
    # Componentes mecânicos - CORRIGIDO
    componentes = diagnostico_global.get("componentes_mecanicos_suspeitos")
    if componentes and isinstance(componentes, list) and len(componentes) > 0:
        st.warning("**🔧 Componentes Mecânicos Suspeitos:**")
        for comp in componentes:
            if comp and isinstance(comp, dict):
                componente = comp.get('componente', 'N/A')
                motivo = comp.get('motivo', 'N/A')
                acao = comp.get('acao', 'N/A')
                st.write(f"• **{componente}:** {motivo} → {acao}")
    
    st.markdown("### 📋 Plano de Ação Priorizado")
    plano = laudo.get("plano_de_acao_priorizado", {})
    
    # Crítico - CORRIGIDO
    acoes_criticas = plano.get("critico_risco_imediato")
    if acoes_criticas and isinstance(acoes_criticas, list) and len(acoes_criticas) > 0:
        st.error("**🔴 CRÍTICO - Risco Imediato**")
        for acao in acoes_criticas:
            if acao and isinstance(acao, str):
                st.write(f"• {acao}")
    
    # Alto - CORRIGIDO
    acoes_alto = plano.get("alto_agendar_7_dias")
    if acoes_alto and isinstance(acoes_alto, list) and len(acoes_alto) > 0:
        st.warning("**🟠 ALTO - Agendar em 7 Dias**")
        for acao in acoes_alto:
            if acao and isinstance(acao, str):
                st.write(f"• {acao}")
    
    # Médio - CORRIGIDO
    acoes_medio = plano.get("medio_agendar_30_dias")
    if acoes_medio and isinstance(acoes_medio, list) and len(acoes_medio) > 0:
        st.info("**🟡 MÉDIO - Agendar em 30 Dias**")
        for acao in acoes_medio:
            if acao and isinstance(acao, str):
                st.write(f"• {acao}")
    
    # Baixo - CORRIGIDO
    acoes_baixo = plano.get("baixo_monitoramento_preventivo")
    if acoes_baixo and isinstance(acoes_baixo, list) and len(acoes_baixo) > 0:
        st.success("**🟢 BAIXO - Monitoramento Preventivo**")
        for acao in acoes_baixo:
            if acao and isinstance(acao, str):
                st.write(f"• {acao}")
    
    # Análise de custo-benefício - COM VALIDAÇÃO
    custo_beneficio = laudo.get("analise_custo_beneficio")
    if custo_beneficio and isinstance(custo_beneficio, dict):
        st.markdown("### 💰 Análise de Custo-Benefício")
        
        col1, col2 = st.columns(2)
        with col1:
            investimento = custo_beneficio.get("investimento_total_estimado")
            if investimento and isinstance(investimento, dict):
                minimo = investimento.get('minimo', 0)
                maximo = investimento.get('maximo', 0)
                st.metric("Investimento Necessário", f"R$ {minimo:,.0f} - {maximo:,.0f}")
        
        with col2:
            roi = custo_beneficio.get("roi_estimado")
            if roi:
                st.metric("ROI Estimado", roi)
        
        # Economia potencial - CORRIGIDO
        economia = custo_beneficio.get("economia_potencial")
        if economia and isinstance(economia, dict) and len(economia) > 0:
            st.write("**Economia Potencial ao Agir Agora:**")
            for key, value in economia.items():
                if value:
                    label = key.replace('_', ' ').title()
                    st.write(f"- {label}: {value}")
        
        risco = custo_beneficio.get("risco_nao_agir")
        if risco and isinstance(risco, str):
            st.error(f"**⚠️ Risco de Não Agir:** {risco}")
    
    # Próxima inspeção - COM VALIDAÇÃO
    proxima = laudo.get("proxima_inspecao_recomendada")
    if proxima and isinstance(proxima, dict):
        prazo = proxima.get('prazo_dias', 'N/A')
        motivo = proxima.get('motivo', 'N/A')
        if prazo != 'N/A' or motivo != 'N/A':
            st.markdown("### 📅 Próxima Inspeção Recomendada")
            st.info(f"**Prazo:** {prazo} dias | **Motivo:** {motivo}")


# =========================
# UI Principal (inalterada)
# =========================

def app():
    st.title("🛞 Análise Avançada de Pneus com IA — Protocolo de 3 Fotos")
    st.caption("✅ Agora com análise dos flancos laterais + identificação de marca de fogo!")
    
    st.info("🆕 **NOVO:** Sistema identifica MARCA/MODELO e MARCA DE FOGO gravada nos pneus!")
    
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
            st.success(f"✅ Dados recuperados")
        else:
            st.warning(data)
    
    st.markdown("---")
    
    with st.expander("📸 Protocolo de Fotografia (3 fotos por pneu)", expanded=True):
        st.markdown("""
**Para cada lado do pneu:**

1. **Foto FRONTAL da banda** ⭐
2. **Foto em 45° dos sulcos** ⭐
3. **Foto LATERAL do flanco** 🆕 
   - **IMPORTANTE:** Tire foto próxima o suficiente para ler marcações do pneu
   - Deve ser possível ver marca/modelo (ex: Michelin) e marca de fogo gravada

💡 **Dica:** Se você consegue ler o logo E ver números gravados, a foto está perfeita!
""")
    
    observacao = st.text_area(
        "Observações do motorista/gestor",
        max_chars=MAX_OBS,
        placeholder="Ex.: Vibração, consumo aumentado, último alinhamento..."
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
                    st.markdown("**🔵 Lado MOTORISTA**")
                    eixo["files"]["lt"] = st.file_uploader(
                        f"1️⃣ Frontal — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"lt_{idx}"
                    )
                    eixo["files"]["lm"] = st.file_uploader(
                        f"2️⃣ 45° — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"lm_{idx}"
                    )
                    eixo["files"]["lb"] = st.file_uploader(
                        f"3️⃣ Lateral 🆕 — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"lb_{idx}",
                        help="Foto próxima do flanco para ler marcações"
                    )
                
                with co:
                    st.markdown("**🔴 Lado OPOSTO**")
                    eixo["files"]["rt"] = st.file_uploader(
                        f"1️⃣ Frontal — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"rt_{idx}"
                    )
                    eixo["files"]["rm"] = st.file_uploader(
                        f"2️⃣ 45° — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"rm_{idx}"
                    )
                    eixo["files"]["rb"] = st.file_uploader(
                        f"3️⃣ Lateral 🆕 — Eixo {idx}", 
                        type=["jpg","jpeg","png"], 
                        key=f"rb_{idx}",
                        help="Foto próxima do flanco para ler marcações"
                    )
    
    st.markdown("---")
    pronto = st.button("🚀 Enviar para Análise", type="primary")
    
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
                for key in ["laudo", "meta", "obs", "ultima_colagem"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        
        with col2:
            st.button("📄 Baixar PDF", disabled=True, help="Em desenvolvimento")
        
        with col3:
            from urllib.parse import quote
            resumo_wpp = st.session_state["laudo"].get("whatsapp_resumo", "")
            link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(resumo_wpp)}"
            st.markdown(f"[📲 WhatsApp]({link_wpp})")
    
    if pronto:
        for i, eixo in enumerate(st.session_state.axes, start=1):
            required = ["lt", "lm", "lb", "rt", "rm", "rb"]
            if not all(eixo["files"].get(k) for k in required):
                st.error(f"❌ Envie todas as 6 fotos do Eixo {i}")
                return
        
        with st.spinner("🔄 Preparando imagens..."):
            collages, titles = [], []
            for i, eixo in enumerate(st.session_state.axes, start=1):
                lt = _open_and_prepare(eixo["files"]["lt"])
                lm = _open_and_prepare(eixo["files"]["lm"])
                lb = _open_and_prepare(eixo["files"]["lb"])
                rt = _open_and_prepare(eixo["files"]["rt"])
                rm = _open_and_prepare(eixo["files"]["rm"])
                rb = _open_and_prepare(eixo["files"]["rb"])
                
                labels = {
                    "title": f"Eixo {i} - {eixo['tipo']}",
                    "left_top": "Motorista - Frontal",
                    "left_middle": "Motorista - 45°",
                    "left_bottom": "Motorista - Lateral",
                    "right_top": "Oposto - Frontal",
                    "right_middle": "Oposto - 45°",
                    "right_bottom": "Oposto - Lateral"
                }
                
                collages.append(_grid_2x3_labeled(lt, lm, lb, rt, rm, rb, labels))
                titles.append(labels["title"])
            
            colagem_final = _stack_vertical_center(collages, titles)
            st.session_state["ultima_colagem"] = colagem_final
            st.session_state["titles"] = titles
            
            if DEBUG:
                st.image(colagem_final, caption="Enviada à IA")
            
            data_url = _img_to_dataurl(colagem_final)
        
        meta = {
            "placa": placa,
            "nome": nome,
            "empresa": empresa,
            "telefone": telefone,
            "email": email,
            "placa_info": placa_info
        }
        
        with st.spinner("🤖 Analisando... (até 2 min)"):
            laudo = _call_openai_advanced(data_url, meta, observacao, modelo, titles)
        
        if "erro" in laudo:
            st.error(f"### {laudo.get('erro', 'Erro desconhecido')}")
        
            detalhes = laudo.get('detalhes')
           
            if detalhes:
                st.warning(f"**Detalhes:** {detalhes}")
    
            erro_tecnico = laudo.get('erro_tecnico')
            if erro_tecnico and DEBUG:
                with st.expander("🔧 Erro Técnico (Debug)"):
                    st.code(erro_tecnico)
    
            resposta_bruta = laudo.get('resposta_bruta')
            if resposta_bruta and DEBUG:
                with st.expander("📄 Resposta Bruta da API"):
                    st.code(resposta_bruta)
    
    # Sugestões de solução
        st.markdown("### 💡 O que fazer:")
        if "autenticação" in laudo.get('erro', '').lower():
            st.info("""
1. Verifique se a API Key está correta em `.streamlit/secrets.toml`
2. Acesse https://platform.openai.com/api-keys e gere nova chave se necessário
3. Certifique-se que a chave começa com `sk-`
        """)
        elif "créditos" in laudo.get('erro', '').lower():
            st.info("""
1. Adicione créditos em https://platform.openai.com/billing
2. Verifique se seu cartão de crédito está ativo
3. Aguarde alguns minutos após adicionar créditos
        """)
        elif "timeout" in laudo.get('erro', '').lower():
            st.info("""
1. Tente com menos eixos (analise 1-2 eixos por vez)
2. Reduza resolução das fotos (MAX_SIDE = 1024 em vez de 1536)
3. Use gpt-4o-mini em vez de gpt-4o
        """)
        else:
            st.info("""
1. Verifique sua conexão de internet
2. Tente novamente em alguns minutos
3. Se persistir, entre em contato com suporte
        """)
    
        return
        
        st.session_state["laudo"] = laudo
        st.session_state["meta"] = meta
        st.session_state["obs"] = observacao
        st.success("✅ Análise concluída com identificação de marcas!")
        st.rerun()

