Com certeza! Integrar a nova lógica de análise e o formato de laudo aprimorado no seu código existente é o próximo passo.

Abaixo, apresento o código do arquivo analise_pneus.py modificado. As alterações foram concentradas nas seguintes áreas para não afetar o funcionamento geral do sistema:

_build_multimodal_message: Esta função foi completamente atualizada para usar os novos prompts (tanto o de sistema quanto o de usuário) que detalham o perfil do especialista e a estrutura de dados exigida.

_render_laudo_ui: Atualizada para renderizar na tela do Streamlit o novo formato do laudo, com a estrutura de Resumo Executivo, Diagnóstico Global, Análise por Eixo/Pneu e Recomendações categorizadas.

_render_report_image: Similarmente, foi modificada para gerar a imagem do PDF seguindo o novo template profissional, extraindo os dados da nova estrutura JSON.

Lógica de Fallback: A lógica que agrega os resultados, caso a análise por eixo seja necessária, foi ajustada para montar a nova estrutura de dados de forma coesa.

As demais funções, como o processamento de imagens, upload de arquivos e a estrutura principal do app, foram mantidas intactas para garantir a estabilidade.

Código analise_pneus.py Atualizado
Copie e cole este conteúdo para substituir o seu arquivo analise_pneus.py existente.

Python

# pages/analise_pneus.py
import os
import io
import json
import base64
from typing import Optional, List, Dict

import streamlit as st
from PIL import Image, ImageOps, ImageDraw, ImageFont
from openai import OpenAI
import utils  # usa consultar_placa_comercial()

# =========================
# Config
# =========================
WHATSAPP_NUMERO = "5567984173800"   # telefone da empresa (somente dígitos com DDI)
MAX_OBS = 150
MAX_SIDE = 1024                     # maior lado ao redimensionar (economia de tokens)
JPEG_QUALITY = 85                   # compressão

# Modo debug: mostra colagens e resposta bruta. Em produção, deixe False.
DEBUG = bool(st.secrets.get("DEBUG_ANALISE_PNEUS", False))

# =========================
# Utilitários de imagem (Sem alterações)
# =========================
def _open_and_prepare(file) -> Optional[Image.Image]:
    """Abre imagem, corrige EXIF, converte RGB e redimensiona para MAX_SIDE."""
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
    """Desenha um selo com texto no canvas. Compatível com Pillow moderno (textbbox)."""
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
        try:
            tw, th = font.getsize(text) if font else (len(text) * 6, 12)
        except Exception:
            tw, th = (len(text) * 6, 12)

    rect = [xy[0], xy[1], xy[0] + tw + pad * 2, xy[1] + th + pad * 2]
    draw.rectangle(rect, fill=bg)
    draw.text((xy[0] + pad, xy[1] + pad), text, fill=fg, font=font)


def _grid_2x2_labeled(
    lt: Image.Image, lb: Image.Image, rt: Image.Image, rb: Image.Image,
    labels: Dict[str, str]
) -> Image.Image:
    """
    Monta colagem 2x2 (esq cima/baixo, dir cima/baixo) e aplica rótulos.
    labels: {"title","left_top","left_bottom","right_top","right_bottom"}
    """
    left_w = min(lt.width if lt else MAX_SIDE, lb.width if lb else MAX_SIDE)
    right_w = min(rt.width if rt else MAX_SIDE, rb.width if rb else MAX_SIDE)

    lt = _fit_to_width(lt, left_w) if lt else Image.new("RGB", (left_w, left_w), "white")
    lb = _fit_to_width(lb, left_w) if lb else Image.new("RGB", (left_w, left_w), "white")
    rt = _fit_to_width(rt, right_w) if rt else Image.new("RGB", (right_w, right_w), "white")
    rb = _fit_to_width(rb, right_w) if rb else Image.new("RGB", (right_w, right_w), "white")

    top_h = max(lt.height, rt.height)
    bot_h = max(lb.height, rb.height)
    lt, rt = _pad_to_height(lt, top_h), _pad_to_height(rt, top_h)
    lb, rb = _pad_to_height(lb, bot_h), _pad_to_height(rb, bot_h)

    total_w = left_w + right_w
    total_h = top_h + bot_h
    out = Image.new("RGB", (total_w, total_h), "white")
    out.paste(lt, (0, 0))
    out.paste(rt, (left_w, 0))
    out.paste(lb, (0, top_h))
    out.paste(rb, (left_w, top_h))

    if labels.get("title"):
        _draw_label(out, labels["title"], xy=(8, 8))
    _draw_label(out, labels.get("left_top", ""), xy=(8, 8))
    _draw_label(out, labels.get("right_top", ""), xy=(left_w + 8, 8))
    _draw_label(out, labels.get("left_bottom", ""), xy=(8, top_h + 8))
    _draw_label(out, labels.get("right_bottom", ""), xy=(left_w + 8, top_h + 8))
    return out


def _stack_vertical_center(collages: List[Image.Image], titles: List[str]) -> Image.Image:
    """Empilha N colagens verticalmente, centralizando. Titula cada seção."""
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
# Utilitários de PDF e Relatório (Funções Atualizadas)
# =========================
def _get_font(size=16):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    lines = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            bbox = draw.textbbox((0,0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines

def _render_report_image(laudo: dict, meta: dict, collage: Image.Image) -> Image.Image:
    """Gera uma imagem longa do relatório para conversão em PDF, usando a nova estrutura de laudo."""
    W = 1240
    P = 40   # padding
    H_PAD = 15 # Espaçamento vertical
    
    title_font = _get_font(28)
    h2_font = _get_font(24)
    h3_font = _get_font(20)
    body_font = _get_font(17)
    bold_body_font = _get_font(17) # Simulação, ideal seria carregar fonte bold
    
    # Canvas inicial para cálculo de altura
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (W, 10), "white"))
    
    def get_text_height(text, font, max_w):
        return len(_wrap_text(dummy_draw, text, font, max_w)) * (font.size + 5)

    height = P

    # 1. Cabeçalho
    height += get_text_height("Laudo Técnico de Análise Visual de Pneus", title_font, W - 2*P) + H_PAD
    meta_text = f"Placa: {meta.get('placa') or '-'} | Empresa: {meta.get('empresa') or '-'} | Motorista: {meta.get('nome') or '-'}"
    height += get_text_height(meta_text, body_font, W - 2*P) + H_PAD * 2

    # 2. Resumo Executivo
    height += get_text_height("2. RESUMO EXECUTIVO", h2_font, W - 2*P) + H_PAD
    height += get_text_height(laudo.get('resumo_executivo', 'N/A'), body_font, W - 2*P) + H_PAD * 2

    # 3. Diagnóstico Global
    height += get_text_height("3. DIAGNÓSTICO GLOBAL DO VEÍCULO", h2_font, W - 2*P) + H_PAD
    dg = laudo.get('diagnostico_global_veiculo', {})
    for title, key in [("Problemas Sistêmicos:", 'problemas_sistemicos'), 
                       ("Problemas Isolados:", 'problemas_isolados'), 
                       ("Componentes para Inspeção Prioritária:", 'componentes_mecanicos_suspeitos')]:
        items = dg.get(key, [])
        if items:
            height += get_text_height(title, h3_font, W-2*P)
            for item in items:
                height += get_text_height(f"• {item}", body_font, W - 2*P)
            height += H_PAD
    height += H_PAD

    # 4. Análise por Eixo
    height += get_text_height("4. ANÁLISE DETALHADA POR EIXO", h2_font, W - 2*P) + H_PAD
    for eixo in laudo.get('analise_eixos', []):
        height += get_text_height(eixo.get('titulo_eixo', 'Eixo Desconhecido'), h2_font, W-2*P) + H_PAD
        height += get_text_height(f"Diagnóstico do Eixo: {eixo.get('diagnostico_geral_eixo', 'N/A')}", body_font, W - 2*P) + H_PAD
        
        for pneu in eixo.get('analise_pneus', []):
            height += get_text_height(f"Lado: {pneu.get('posicao', '-')}", h3_font, W-2*P)
            height += get_text_height(f"  Estado Geral: {pneu.get('estado_geral', '-')}", body_font, W-2*P)
            height += get_text_height("  Defeitos Observados:", body_font, W-2*P)
            for d in pneu.get('defeitos_observados',[]):
                height += get_text_height(f"    • {d.get('defeito')} (Gravidade: {d.get('gravidade')})", body_font, W-2*P)
            height += get_text_height("  Causas Prováveis:", body_font, W-2*P)
            for c in pneu.get('causas_provaveis',[]):
                height += get_text_height(f"    • Para '{c.get('defeito')}': {c.get('causa')}", body_font, W-2*P)
            height += get_text_height(f"  Ação Recomendada: {pneu.get('acao_recomendada_especifica', '-')}", body_font, W-2*P) + H_PAD
        height += H_PAD

    # 5. Recomendações Finais
    height += get_text_height("5. RECOMENDAÇÕES FINAIS", h2_font, W - 2*P) + H_PAD
    rf = laudo.get('recomendacoes_finais', {})
    for title, key in [("Ações Corretivas Imediatas:", 'corretivas_imediatas'),
                       ("Manutenções Preventivas:", 'preventivas'),
                       ("Orientações Operacionais:", 'operacionais')]:
        items = rf.get(key, [])
        if items:
            height += get_text_height(title, h3_font, W-2*P)
            for item in items:
                height += get_text_height(f"• {item}", body_font, W-2*P)
            height += H_PAD
    height += H_PAD

    # Colagem
    scale = (W - 2*P) / collage.width
    height += int(collage.height * scale) + P

    # Desenhar no canvas final
    out = Image.new("RGB", (W, int(height)), "white")
    draw = ImageDraw.Draw(out)
    y = P

    def draw_wrapped_text(text, font, y_pos):
        lines = _wrap_text(draw, text, font, W - 2*P)
        for line in lines:
            draw.text((P, y_pos), line, font=font, fill=(0,0,0))
            y_pos += font.size + 5
        return y_pos

    y = draw_wrapped_text("Laudo Técnico de Análise Visual de Pneus", title_font, y)
    y = draw_wrapped_text(meta_text, body_font, y)
    y += H_PAD * 2

    y = draw_wrapped_text("2. RESUMO EXECUTIVO", h2_font, y) + H_PAD
    y = draw_wrapped_text(laudo.get('resumo_executivo', 'N/A'), body_font, y) + H_PAD * 2
    
    y = draw_wrapped_text("3. DIAGNÓSTICO GLOBAL DO VEÍCULO", h2_font, y) + H_PAD
    for title, key in [("Problemas Sistêmicos:", 'problemas_sistemicos'), ("Problemas Isolados:", 'problemas_isolados'), ("Componentes para Inspeção Prioritária:", 'componentes_mecanicos_suspeitos')]:
        items = dg.get(key, [])
        if items:
            y = draw_wrapped_text(title, h3_font, y)
            for item in items: y = draw_wrapped_text(f"• {item}", body_font, y)
            y += H_PAD

    y = draw_wrapped_text("4. ANÁLISE DETALHADA POR EIXO", h2_font, y) + H_PAD
    for eixo in laudo.get('analise_eixos', []):
        y = draw_wrapped_text(eixo.get('titulo_eixo', 'Eixo Desconhecido'), h2_font, y) + H_PAD
        y = draw_wrapped_text(f"Diagnóstico do Eixo: {eixo.get('diagnostico_geral_eixo', 'N/A')}", body_font, y) + H_PAD
        for pneu in eixo.get('analise_pneus', []):
            y = draw_wrapped_text(f"Lado: {pneu.get('posicao', '-')}", h3_font, y)
            y = draw_wrapped_text(f"  Estado Geral: {pneu.get('estado_geral', '-')}", body_font, y)
            y = draw_wrapped_text("  Defeitos Observados:", body_font, y)
            for d in pneu.get('defeitos_observados',[]): y = draw_wrapped_text(f"    • {d.get('defeito')} (Gravidade: {d.get('gravidade')})", body_font, y)
            y = draw_wrapped_text("  Causas Prováveis:", body_font, y)
            for c in pneu.get('causas_provaveis',[]): y = draw_wrapped_text(f"    • Para '{c.get('defeito')}': {c.get('causa')}", body_font, y)
            y = draw_wrapped_text(f"  Ação Recomendada: {pneu.get('acao_recomendada_especifica', '-')}", body_font, y) + H_PAD
        y += H_PAD

    y = draw_wrapped_text("5. RECOMENDAÇÕES FINAIS", h2_font, y) + H_PAD
    for title, key in [("Ações Corretivas Imediatas:", 'corretivas_imediatas'), ("Manutenções Preventivas:", 'preventivas'), ("Orientações Operacionais:", 'operacionais')]:
        items = rf.get(key, [])
        if items:
            y = draw_wrapped_text(title, h3_font, y)
            for item in items: y = draw_wrapped_text(f"• {item}", body_font, y)
            y += H_PAD

    # Colagem
    col_resized = collage.resize((int(collage.width * scale), int(collage.height * scale)), Image.LANCZOS)
    out.paste(col_resized, (P, y))
    
    return out


def _build_pdf_bytes(report_img: Image.Image) -> bytes:
    """Converte a imagem do relatório para PDF (1 página)."""
    buf = io.BytesIO()
    report_img.save(buf, format="PDF", resolution=150.0)
    return buf.getvalue()


# =========================
# OpenAI / Prompt helpers (Funções Atualizadas)
# =========================
def _build_multimodal_message(data_url: str, meta: dict, obs: str, axis_titles: List[str]) -> list:
    """Constrói o prompt de usuário detalhado para a API da OpenAI."""
    # O prompt de sistema é enviado separadamente na chamada da API
    prompt_usuario = f"""
### CONTEXTO DO VEÍCULO E ANÁLISE

**Dados do Veículo:**
- **Placa:** {meta.get('placa', 'N/A')}
- **Empresa:** {meta.get('empresa', 'N/A')}
- **Motorista/Gestor:** {meta.get('nome', 'N/A')}
- **Telefone:** {meta.get('telefone', 'N/A')}
- **E-mail:** {meta.get('email', 'N/A')}
- **Informações da Placa (API):** {json.dumps(meta.get('placa_info', {}), ensure_ascii=False)}

**Observação do Motorista:**
> {obs}

---

### ORGANIZAÇÃO DAS FOTOS

**IMPORTANTE:** A imagem fornecida é uma montagem vertical de várias colagens 2x2.
- **Ordem dos Eixos:** Cada colagem 2x2 representa um eixo, e elas estão empilhadas na seguinte ordem, de cima para baixo: **{", ".join(axis_titles)}**.
- **Estrutura da Colagem 2x2 (para cada eixo):**
  - **Canto Superior Esquerdo:** Pneu do lado do **Motorista**, foto **de Frente** (paralela à banda).
  - **Canto Inferior Esquerdo:** Pneu do lado do **Motorista**, foto **em 45 graus**.
  - **Canto Superior Direito:** Pneu do lado **Oposto** (passageiro), foto **de Frente**.
  - **Canto Inferior Direito:** Pneu do lado **Oposto** (passageiro), foto **em 45 graus**.
- **Pneus Germinados (Traseiros):** As fotos mostram o conjunto (interno e externo) de cada lado. Sua análise deve considerar a dupla de pneus.

---

### BASE DE CONHECIMENTO (HEURÍSTICAS)

- **Desgaste e Geometria:**
  - **Ombros internos gastos (Divergência):** Rodas apontando para fora.
  - **Ombros externos gastos (Convergência):** Rodas apontando para dentro.
  - **Desgaste em um lado do pneu (Cambagem):** Inclinação da roda.
  - **Serrilhamento/Dente de serra:** Geralmente desalinhamento (cáster), folgas ou amortecedores.
- **Pressão:**
  - **Centro liso/gasto:** Pressão excessiva.
  - **Ombros gastos com centro preservado:** Pressão baixa.
  - **Diferença de desgaste entre pneus germinados:** Calibragem desigual entre eles.
- **Falhas e Suspensão:**
  - **Escalonamento/Escamação:** Arraste, pressão baixa, problemas de suspensão (molas, amortecedores).
  - **Flat spots (áreas planas):** Travamento de freios.
  - **Ondulações:** Desbalanceamento ou falha estrutural interna.

---

### TAREFAS DE ANÁLISE

Com base nas imagens e no contexto, execute as seguintes tarefas e estruture sua resposta **exclusivamente** no formato JSON especificado abaixo.

1.  **Resumo Executivo:** Forneça um parágrafo inicial com as conclusões mais críticas e o estado geral do veículo.
2.  **Análise por Eixo e Pneu:** Para cada eixo (colagem 2x2), realize uma análise detalhada.
    - **Diagnóstico do Eixo:** Um resumo do comportamento do eixo como um todo.
    - **Análise Individual dos Pneus (Motorista e Oposto):** Para cada lado, detalhe:
        - **Estado Geral:** Novo, semi-novo, fim de vida, recapado, etc.
        - **Defeitos Observados:** Liste *cada* defeito visível (ex: "Desgaste no ombro externo", "Serrilhamento leve").
        - **Causas Prováveis:** Para *cada* defeito listado, explique a causa técnica mais provável, vinculando-a a problemas de geometria, suspensão, pressão ou operação.
        - **Ação Recomendada Específica:** Ação para aquele pneu/lado específico.
3.  **Diagnóstico Global do Veículo:** Após a análise individual, cruze os dados.
    - **Problemas Sistêmicos:** Identifique padrões que se repetem entre os eixos (ex: todos os dianteiros com convergência).
    - **Problemas Isolados:** Defeitos que ocorrem em apenas um pneu.
    - **Componentes Mecânicos Suspeitos:** Liste os componentes que precisam de inspeção prioritária (ex: "Amortecedores dianteiros", "Buchas da barra estabilizadora").
4.  **Recomendações Finais (Categorizadas):** Crie uma lista de ações claras, divididas em três categorias:
    - **Ações Corretivas Imediatas:** O que precisa ser feito com urgência para garantir a segurança.
    - **Manutenções Preventivas:** O que fazer para evitar que os problemas retornem.
    - **Orientações Operacionais:** Dicas para o motorista/gestor (calibragem, condução).

---

### FORMATO DE SAÍDA OBRIGATÓRIO (JSON)

Responda **APENAS** com um objeto JSON válido, sem nenhum texto ou explicação adicional fora dele. A estrutura deve seguir este modelo:
```json
{{
  "resumo_executivo": "...",
  "diagnostico_global_veiculo": {{
    "problemas_sistemicos": ["..."],
    "problemas_isolados": ["..."],
    "componentes_mecanicos_suspeitos": ["..."]
  }},
  "analise_eixos": [
    {{
      "titulo_eixo": "Eixo Dianteiro 1",
      "diagnostico_geral_eixo": "O eixo apresenta sinais claros de desalinhamento por convergência...",
      "analise_pneus": [
        {{
          "posicao": "Motorista",
          "estado_geral": "Semi-novo, recapado.",
          "defeitos_observados": [
            {{"defeito": "Desgaste acentuado no ombro externo", "gravidade": "Severa"}},
            {{"defeito": "Leves fissuras na banda de rodagem", "gravidade": "Baixa"}}
          ],
          "causas_provaveis": [
            {{"defeito": "Desgaste acentuado no ombro externo", "causa": "Indica excesso de convergência (toe-in), fazendo com que a parte externa do pneu arraste mais. Pode também ser agravado por folgas em pivôs de direção."}},
            {{"defeito": "Leves fissuras na banda de rodagem", "causa": "Sinal de envelhecimento do composto de borracha ou exposição prolongada a altas temperaturas."}}
          ],
          "acao_recomendada_especifica": "Verificar alinhamento e geometria. Monitorar fissuras."
        }},
        {{
          "posicao": "Oposto",
          "estado_geral": "Semi-novo, original.",
          "defeitos_observados": [
            {{"defeito": "Desgaste acentuado no ombro externo", "gravidade": "Severa"}}
          ],
          "causas_provaveis": [
            {{"defeito": "Desgaste acentuado no ombro externo", "causa": "Confirma o problema sistêmico de convergência no eixo. O desgaste similar em ambos os lados reforça o diagnóstico de desalinhamento."}}
          ],
          "acao_recomendada_especifica": "Verificar alinhamento e geometria."
        }}
      ]
    }}
  ],
  "recomendacoes_finais": {{
    "corretivas_imediatas": [
      "Realizar alinhamento e balanceamento do eixo dianteiro com urgência.",
      "Inspecionar pivôs e terminais de direção em busca de folgas."
    ],
    "preventivas": [
      "Implementar rodízio de pneus a cada 20.000 km.",
      "Verificar o alinhamento a cada 6 meses ou após impactos severos."
    ],
    "operacionais": [
      "Realizar calibragem semanal com pneus frios, conforme especificação da carga."
    ]
  }},
  "whatsapp_resumo": "Detectamos um problema de desalinhamento no eixo dianteiro que está causando desgaste severo nos pneus. Ações corretivas são necessárias."
}}
"""
return [
{"type": "text", "text": prompt_usuario},
{"type": "image_url", "image_url": {"url": data_url}},
]

=========================
OpenAI callers (Sem alterações)
=========================
def _call_openai_single_image(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
return {"erro": "OPENAI_API_KEY ausente em Secrets/variável de ambiente."}

client = OpenAI(api_key=api_key)
# NOVO: O prompt de sistema é definido aqui
prompt_sistema = """
Você é um especialista brasileiro em análise visual de pneus de caminhões, carretas e ônibus, com foco exclusivo na avaliação a partir de fotografias. Sua experiência combina conhecimento técnico aprofundado de mecânica pesada, geometria veicular (convergência, divergência, cambagem, cáster), suspensão, inflagem e padrões de desgaste.
Sua missão é realizar um diagnóstico preciso, vinculando cada defeito visual à sua causa mecânica ou operacional mais provável. Você deve ter uma visão sistêmica, entendendo como um problema em um pneu pode indicar uma falha no conjunto.
Use linguagem técnica, mas acessível. Seja objetivo e baseie-se estritamente nas evidências visuais. Se uma foto não permitir certeza, aponte a limitação e apresente a hipótese com um nível de confiança. Responda sempre em português do Brasil.
"""
content = _build_multimodal_message(data_url, meta, obs, axis_titles)

try:
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": content},
        ],
        temperature=0,
        response_format={"type": "json_object"}, # Exige saída em JSON
    )
    text = resp.choices[0].message.content or ""
    try:
        return json.loads(text)
    except Exception as e:
        return {"erro": f"Modelo não retornou JSON válido mesmo com a exigência. Erro: {e}", "raw": text}
except Exception as e:
    return {"erro": f"Falha na API: {e}"}
def _call_openai_single_axis(collage: Image.Image, meta: dict, obs: str, model_name: str, axis_title: str) -> dict:
"""Fallback: analisa UMA colagem (um eixo) - ADAPTADO."""
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key: return {"erro": "OPENAI_API_KEY não configurada."}

client = OpenAI(api_key=api_key)
data_url = _img_to_dataurl(collage)

# Prompt de fallback simplificado mas pedindo a nova estrutura
prompt_usuario = f"""
Análise de UM EIXO: {axis_title}.
Contexto: Placa {meta.get('placa')}, Obs: {obs}
Retorne JSON **APENAS** com a análise deste eixo, seguindo a estrutura completa do laudo (resumo_executivo, diagnostico_global_veiculo, analise_eixos, recomendacoes_finais, whatsapp_resumo).
O array 'analise_eixos' deve conter apenas um item: a análise para '{axis_title}'.
"""

content = [
    {"type": "text", "text": prompt_usuario},
    {"type": "image_url", "image_url": {"url": data_url}}
]

try:
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "Você é um especialista em pneus. Responda em JSON."},
            {"role": "user", "content": content},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content or ""
    return json.loads(text)
except Exception as e:
    return {"erro": f"Falha na API (fallback): {e}", "raw": locals().get("text", "")}
=========================
UI helpers (Função Atualizada)
=========================
def _render_laudo_ui(laudo: dict):
st.success("Laudo recebido com sucesso!")

# 2. Resumo Executivo
st.markdown("## 🧾 2. Resumo Executivo")
st.write(laudo.get('resumo_executivo', "Nenhum resumo executivo fornecido."))
st.markdown("---")

# 3. Diagnóstico Global
st.markdown("## 🔬 3. Diagnóstico Global do Veículo")
dg = laudo.get('diagnostico_global_veiculo', {})
st.markdown("### Problemas Sistêmicos")
st.write("• " + "\n• ".join(dg.get('problemas_sistemicos', ["Nenhum identificado."])))
st.markdown("### Problemas Isolados")
st.write("• " + "\n• ".join(dg.get('problemas_isolados', ["Nenhum identificado."])))
st.markdown("### Componentes para Inspeção Prioritária")
st.write("• " + "\n• ".join(dg.get('componentes_mecanicos_suspeitos', ["Nenhum identificado."])))
st.markdown("---")

# 4. Análise por Eixo
st.markdown("## ⚙️ 4. Análise Detalhada por Eixo")
for eixo in laudo.get('analise_eixos', []):
    with st.container(border=True):
        st.markdown(f"### {eixo.get('titulo_eixo', 'Eixo Desconhecido')}")
        st.caption(f"**Diagnóstico do Eixo:** {eixo.get('diagnostico_geral_eixo', 'N/A')}")

        for pneu in eixo.get('analise_pneus', []):
            st.markdown(f"#### Lado: {pneu.get('posicao', 'N/A')}")
            st.write(f"**Estado Geral:** {pneu.get('estado_geral', 'N/A')}")
            
            st.write("**Defeitos Observados:**")
            for d in pneu.get('defeitos_observados', []):
                st.write(f"- {d.get('defeito')} (Gravidade: {d.get('gravidade')})")

            st.write("**Causas Prováveis:**")
            for c in pneu.get('causas_provaveis', []):
                st.write(f"- **Para '{c.get('defeito')}':** {c.get('causa')}")

            st.write(f"**Ação Recomendada:** {pneu.get('acao_recomendada_especifica', 'N/A')}")
st.markdown("---")

# 5. Recomendações Finais
st.markdown("## ✅ 5. Recomendações Finais")
rf = laudo.get('recomendacoes_finais', {})
st.markdown("### 🚨 Ações Corretivas Imediatas")
st.write("• " + "\n• ".join(rf.get('corretivas_imediatas', ["Nenhuma."])))
st.markdown("### 🛠️ Manutenções Preventivas")
st.write("• " + "\n• ".join(rf.get('preventivas', ["Nenhuma."])))
st.markdown("### 👨‍🏫 Orientações Operacionais")
st.write("• " + "\n• ".join(rf.get('operacionais', ["Nenhuma."])))
=========================
UI (Função Principal)
=========================
def app():
st.title("🛞 Análise de Pneus por Foto — AVP")
st.caption("Laudo automático de apoio (sujeito a erros). Recomenda-se inspeção presencial.")

col_m1, _ = st.columns([1, 3])
with col_m1:
    modo_detalhado = st.toggle("Análise detalhada (gpt-4o)", value=False)
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

if 'placa_info' not in st.session_state:
    st.session_state.placa_info = None

if buscar and placa:
    ok, data = utils.consultar_placa_comercial(placa)
    if ok:
        st.session_state.placa_info = data
        st.success(f"Dados da placa: {json.dumps(st.session_state.placa_info, ensure_ascii=False)}")
    else:
        st.warning(data)
        st.session_state.placa_info = {"erro": data}

st.markdown("---")

with st.expander("📸 Como fotografar para melhor leitura (dica rápida)"):
    st.write(
        "- Para **cada lado**, tire **duas fotos** do pneu:\n"
        "  1) **De frente**: câmera **paralela à banda**;\n"
        "  2) **Em ~45°**: para evidenciar profundidade dos sulcos.\n"
        "- **Traseiro (germinado)**: faça a dupla de fotos do **conjunto**."
    )

observacao = st.text_area("Observação do motorista", max_chars=MAX_OBS, placeholder="Ex.: puxa para a direita…")

if "axes" not in st.session_state:
    st.session_state.axes: List[Dict] = []

cA, cB, cC = st.columns(3)
if cA.button("➕ Adicionar Dianteiro"): st.session_state.axes.append({"tipo": "Dianteiro", "files": {}})
if cB.button("➕ Adicionar Traseiro"): st.session_state.axes.append({"tipo": "Traseiro", "files": {}})
if st.session_state.axes and cC.button("🗑️ Remover último eixo"): st.session_state.axes.pop()

if not st.session_state.axes and "laudo" not in st.session_state:
    st.info("Adicione pelo menos um eixo para começar.")
    return

if st.session_state.axes:
    for idx, eixo in enumerate(st.session_state.axes, start=1):
        with st.container(border=True):
            st.subheader(f"Eixo {idx} — {eixo['tipo']}")
            cm, co = st.columns(2)
            with cm:
                eixo["files"]["lt"] = st.file_uploader(f"Motorista — Frente — Eixo {idx}", type=["jpg","jpeg","png"], key=f"f_m_{idx}")
                eixo["files"]["lb"] = st.file_uploader(f"Motorista — 45° — Eixo {idx}", type=["jpg","jpeg","png"], key=f"a_m_{idx}")
            with co:
                eixo["files"]["rt"] = st.file_uploader(f"Oposto — Frente — Eixo {idx}", type=["jpg","jpeg","png"], key=f"f_o_{idx}")
                eixo["files"]["rb"] = st.file_uploader(f"Oposto — 45° — Eixo {idx}", type=["jpg","jpeg","png"], key=f"a_o_{idx}")

st.markdown("---")
if st.button("🚀 Enviar para análise", disabled=not st.session_state.axes):
    if not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        st.error("Defina OPENAI_API_KEY em Secrets/variável de ambiente.")
        st.stop()

    for i, eixo in enumerate(st.session_state.axes, start=1):
        if not all(eixo["files"].get(k) for k in ("lt","lb","rt","rb")):
            st.error(f"Envie as 4 fotos do eixo {i} — {eixo['tipo']}.")
            st.stop()

    with st.spinner("Preparando imagens…"):
        collages, titles = [], []
        for i, eixo in enumerate(st.session_state.axes, start=1):
            lt, lb = _open_and_prepare(eixo["files"]["lt"]), _open_and_prepare(eixo["files"]["lb"])
            rt, rb = _open_and_prepare(eixo["files"]["rt"]), _open_and_prepare(eixo["files"]["rb"])
            labels = {
                "title": f"Eixo {i} - {eixo['tipo']}",
                "left_top": "Motorista - Frente", "left_bottom": "Motorista - 45°",
                "right_top": "Oposto - Frente", "right_bottom": "Oposto - 45°"
            }
            collages.append(_grid_2x2_labeled(lt, lb, rt, rb, labels))
            titles.append(labels["title"])
        
        colagem_final = _stack_vertical_center(collages, titles)
        st.session_state["ultima_colagem"] = colagem_final
        st.session_state["collages"] = collages
        st.session_state["titles"] = titles

    data_url = _img_to_dataurl(colagem_final)
    meta = {
        "placa": placa, "nome": nome, "empresa": empresa,
        "telefone": telefone, "email": email, "placa_info": st.session_state.placa_info
    }
    obs = (observacao or "")[:MAX_OBS]

    with st.spinner("Analisando com IA... Isso pode levar um minuto."):
        laudo = _call_openai_single_image(data_url, meta, obs, modelo, titles)

    expected_n = len(titles)
    got_n = len(laudo.get("analise_eixos", [])) if isinstance(laudo, dict) else 0

    if "erro" in laudo or got_n != expected_n:
        st.warning("Análise principal falhou ou incompleta. Tentando fallback por eixo...")
        agreg = { "analise_eixos": [], "recomendacoes_finais": {"corretivas_imediatas": [], "preventivas": [], "operacionais": []} }
        
        with st.spinner("Analisando eixo por eixo..."):
            for cimg, atitle in zip(st.session_state["collages"], st.session_state["titles"]):
                sub = _call_openai_single_axis(cimg, meta, obs, modelo, atitle)
                if isinstance(sub, dict) and "erro" not in sub:
                    if sub.get("analise_eixos"): agreg["analise_eixos"].extend(sub["analise_eixos"])
                    # Agregar outras chaves
                    for key in ["resumo_executivo", "whatsapp_resumo"]:
                        if not agreg.get(key) and sub.get(key): agreg[key] = sub.get(key)
                    if sub.get("diagnostico_global_veiculo"):
                       if 'diagnostico_global_veiculo' not in agreg: agreg['diagnostico_global_veiculo'] = {"problemas_sistemicos": [], "problemas_isolados": [], "componentes_mecanicos_suspeitos": []}
                       for k_dg in agreg['diagnostico_global_veiculo']:
                           agreg['diagnostico_global_veiculo'][k_dg].extend(sub['diagnostico_global_veiculo'].get(k_dg,[]))
                    if sub.get("recomendacoes_finais"):
                        for k_rf in agreg['recomendacoes_finais']:
                            agreg['recomendacoes_finais'][k_rf].extend(sub['recomendacoes_finais'].get(k_rf,[]))
        laudo = agreg

    if "erro" in laudo or not laudo.get("analise_eixos"):
        st.error(f"A análise falhou. Detalhes: {laudo.get('erro', 'Resposta vazia.')}")
        if DEBUG and laudo.get("raw"):
            st.code(laudo["raw"])
        st.stop()

    st.session_state["laudo"] = laudo
    st.session_state["meta"] = meta
    st.session_state["obs"] = obs
    
    try:
        report_img = _render_report_image(laudo, meta, st.session_state["ultima_colagem"])
        st.session_state["pdf_bytes"] = _build_pdf_bytes(report_img)
    except Exception as e:
        st.warning(f"Não foi possível pré-gerar o PDF: {e}")

if "laudo" in st.session_state:
    _render_laudo_ui(st.session_state["laudo"])

    st.markdown("---")
    col_exp1, col_exp2 = st.columns([1, 3])
    if "ultima_colagem" in st.session_state:
        if col_exp1.button("🔄 Regerar PDF") or "pdf_bytes" not in st.session_state:
            try:
                report_img = _render_report_image(st.session_state["laudo"], st.session_state["meta"], st.session_state["ultima_colagem"])
                st.session_state["pdf_bytes"] = _build_pdf_bytes(report_img)
            except Exception as e: st.error(f"Falha ao gerar PDF: {e}")
        
        if "pdf_bytes" in st.session_state:
            col_exp1.download_button("⬇️ Baixar PDF", data=st.session_state["pdf_bytes"], file_name=f"laudo_{st.session_state.get('meta',{}).get('placa')}.pdf", mime="application/pdf")

    from urllib.parse import quote
    resumo_wpp = st.session_state["laudo"].get("whatsapp_resumo", "")
    msg = f"Olá! Segue resumo da análise de pneus para o veículo {st.session_state.get('meta',{}).get('placa')}:\n\n{resumo_wpp}"
    link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(msg)}"
    col_exp2.markdown(f"[📲 Enviar resumo via WhatsApp]({link_wpp})")
if name == "main":
app()