# pages/analise_pneus.py
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
WHATSAPP_NUMERO = "5567984173800"   # telefone da empresa (somente dígitos com DDI)
MAX_OBS = 250                       # Aumentado para mais detalhes, conforme solicitado
MAX_SIDE = 1024                     # maior lado ao redimensionar (economia de tokens)
JPEG_QUALITY = 85                   # compressão

# Modo debug: mostra colagens e resposta bruta. Em produção, deixe False.
DEBUG = bool(st.secrets.get("DEBUG_ANALISE_PNEUS", False))

# =========================
# Utilitários de imagem (Sua versão original, intacta)
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
        # rótulo de faixa
        _draw_label(out, titles[idx], xy=(10, y + 10))
        y += c.height
    return out


def _img_to_dataurl(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

# =========================
# Utilitários de PDF (ATUALIZADO PARA LAUDO COMPLETO)
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
    if not isinstance(text, str):
        text = str(text)
    for paragraph in text.split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), test, font=font)
                w_check = bbox[2] - bbox[0]
            else:
                w_check, _ = draw.textsize(test, font=font)
            if (w_check) <= max_w:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
    return lines

def _render_report_image(laudo: dict, meta: dict, obs: str, collage: Image.Image) -> Image.Image:
    """ATUALIZADO: Gera um 'poster' completo do relatório para o PDF."""
    W, P, H_PAD = 1240, 40, 15
    title_font = _get_font(32)
    h2_font = _get_font(26)
    h3_font = _get_font(22)
    body_font = _get_font(18)
    caption_font = _get_font(16)
    
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (W, 10), "white"))
    
    def get_text_height(text, font, indent=0):
        if not text: return 0
        return len(_wrap_text(dummy_draw, text, font, W - 2*P - indent)) * (font.size + 4) + 5

    # --- Calcular Altura Total ---
    height = P
    meta_text = f"Placa: {meta.get('placa','-')} | Empresa: {meta.get('empresa','-')} | Motorista: {meta.get('nome','-')}"
    height += get_text_height(f"Laudo Técnico de Análise Visual de Pneus", title_font) + H_PAD
    height += get_text_height(meta_text, body_font) + H_PAD * 2

    is_new_laudo = "resumo_executivo" in laudo

    if is_new_laudo:
        height += get_text_height("1. Resumo Executivo", h2_font) + H_PAD
        height += get_text_height(laudo.get('resumo_executivo', 'N/A'), body_font) + H_PAD * 2
        height += get_text_height("2. Diagnóstico Global do Veículo", h2_font) + H_PAD
        dg = laudo.get('diagnostico_global_veiculo', {})
        height += get_text_height("Problemas Sistêmicos:", h3_font)
        height += get_text_height("\n".join(f"• {i}" for i in dg.get('problemas_sistemicos',[])), body_font, indent=20) + H_PAD
        height += get_text_height("Componentes para Inspeção Prioritária:", h3_font)
        height += get_text_height("\n".join(f"• {i}" for i in dg.get('componentes_mecanicos_suspeitos',[])), body_font, indent=20) + H_PAD * 2
        height += get_text_height("3. Análise Detalhada por Eixo", h2_font) + H_PAD
        for eixo in laudo.get('analise_detalhada_eixos', []):
            height += get_text_height(eixo.get('titulo_eixo', 'Eixo'), h3_font) + H_PAD
            for pneu in eixo.get('analise_pneus', []):
                height += get_text_height(f"Lado: {pneu.get('posicao')}", body_font, indent=20)
                for defeito in pneu.get('defeitos', []):
                    height += get_text_height(f"• Defeito: {defeito.get('nome_defeito')} ({defeito.get('urgencia')})", body_font, indent=40)
                    exp = defeito.get('explicacao', {})
                    height += get_text_height(f"  Risco: {exp.get('risco_nao_corrigir')}", caption_font, indent=40) + H_PAD
        height += H_PAD
        height += get_text_height("4. Plano de Ação", h2_font) + H_PAD
        plano = laudo.get('plano_de_acao', {})
        height += get_text_height("Ações Críticas:", h3_font)
        height += get_text_height("\n".join(f"• {i}" for i in plano.get('critico_risco_imediato',[])), body_font, indent=20) + H_PAD
    else: # Laudo antigo (fallback)
        height += get_text_height(laudo.get("resumo_geral",""), body_font) + H_PAD
        for eixo in laudo.get("eixos", []):
            height += get_text_height(eixo.get("titulo", "Eixo"), h2_font) + H_PAD
            height += get_text_height(eixo.get("diagnostico_global", ""), body_font) + H_PAD

    scale = (W - 2*P) / collage.width if collage.width > 0 else 1
    height += int(collage.height * scale) + P

    # --- Desenhar no Canvas Final ---
    out = Image.new("RGB", (W, int(height)), "white")
    draw = ImageDraw.Draw(out)
    y = P

    def draw_wrapped_text(text, font, y_pos, indent=0, color=(0,0,0)):
        if not text: return y_pos
        lines = _wrap_text(draw, text, font, W - 2*P - indent)
        for line in lines:
            draw.text((P + indent, y_pos), line, font=font, fill=color)
            y_pos += font.size + 4
        return y_pos + 5

    y = draw_wrapped_text("Laudo Técnico de Análise Visual de Pneus", title_font, y) + H_PAD
    y = draw_wrapped_text(meta_text, body_font, y) + H_PAD * 2
    
    if is_new_laudo:
        y = draw_wrapped_text("1. Resumo Executivo", h2_font, y) + H_PAD
        y = draw_wrapped_text(laudo.get('resumo_executivo', 'N/A'), body_font, y) + H_PAD * 2
        y = draw_wrapped_text("2. Diagnóstico Global do Veículo", h2_font, y) + H_PAD
        dg = laudo.get('diagnostico_global_veiculo', {})
        y = draw_wrapped_text("Problemas Sistêmicos:", h3_font, y)
        y = draw_wrapped_text("\n".join(f"• {i}" for i in dg.get('problemas_sistemicos',[])), body_font, y, indent=20) + H_PAD
        y = draw_wrapped_text("Componentes para Inspeção Prioritária:", h3_font, y)
        y = draw_wrapped_text("\n".join(f"• {i}" for i in dg.get('componentes_mecanicos_suspeitos',[])), body_font, y, indent=20) + H_PAD * 2
        y = draw_wrapped_text("3. Análise Detalhada por Eixo", h2_font, y) + H_PAD
        for eixo in laudo.get('analise_detalhada_eixos', []):
            y = draw_wrapped_text(eixo.get('titulo_eixo', 'Eixo'), h3_font, y)
            for pneu in eixo.get('analise_pneus', []):
                y = draw_wrapped_text(f"Lado: {pneu.get('posicao')}", body_font, y, indent=20)
                for defeito in pneu.get('defeitos', []):
                    y = draw_wrapped_text(f"• Defeito: {defeito.get('nome_defeito')} ({defeito.get('urgencia')})", body_font, y, indent=40)
            y += H_PAD
        y = draw_wrapped_text("4. Plano de Ação", h2_font, y) + H_PAD
        plano = laudo.get('plano_de_acao', {})
        y = draw_wrapped_text("Ações Críticas:", h3_font, y, color=(200,0,0))
        y = draw_wrapped_text("\n".join(f"• {i}" for i in plano.get('critico_risco_imediato',[])), body_font, y, indent=20) + H_PAD
    else:
        y = draw_wrapped_text(laudo.get("resumo_geral",""), body_font, y) + H_PAD
        for eixo in laudo.get("eixos", []):
            y = draw_wrapped_text(eixo.get("titulo", "Eixo"), h2_font, y) + H_PAD
            y = draw_wrapped_text(eixo.get("diagnostico_global", ""), body_font, y) + H_PAD

    col_resized = collage.resize((int(collage.width * scale), int(collage.height * scale)), Image.LANCZOS)
    out.paste(col_resized, (P, y))
    y += col_resized.height + P
    
    return out.crop((0, 0, W, y))


def _build_pdf_bytes(report_img: Image.Image) -> bytes:
    """Converte a imagem do relatório para PDF (1 página)."""
    buf = io.BytesIO()
    report_img.save(buf, format="PDF", resolution=150.0)
    return buf.getvalue()

# =========================
# OpenAI / Prompt helpers (SEÇÃO ATUALIZADA)
# =========================
def _build_multimodal_message(data_url: str, meta: dict, obs: str, axis_titles: List[str]) -> list:
    """ATUALIZADO - Constrói o prompt de usuário com base no novo padrão exigido pelo gestor."""
    prompt_usuario = f"""
### ANÁLISE TÉCNICA DE PNEUS PARA GESTÃO DE FROTA

**1. CONTEXTO DO VEÍCULO**
- **Placa:** {meta.get('placa', 'N/A')}
- **Empresa:** {meta.get('empresa', 'N/A')}
- **Motorista/Gestor:** {meta.get('nome', 'N/A')}
- **Informações Adicionais (API):** {json.dumps(meta.get('placa_info', {}), ensure_ascii=False)}
- **Observação do Motorista:** {obs}

---
**2. ORGANIZAÇÃO DAS FOTOS (MUITO IMPORTANTE)**
A imagem fornecida é uma montagem vertical de colagens 2x2.
- **Ordem dos Eixos:** As colagens estão empilhadas na ordem: **{", ".join(axis_titles)}**.
- **Estrutura da Colagem 2x2 (por eixo):**
  - **Superior Esquerdo:** Motorista, foto de Frente.
  - **Inferior Esquerdo:** Motorista, foto em 45°.
  - **Superior Direito:** Oposto, foto de Frente.
  - **Inferior Direito:** Oposto, foto em 45°.

---
**3. TAREFAS OBRIGATÓRIAS DE ANÁLISE**
Execute uma análise completa e retorne a resposta **EXCLUSIVAMENTE** no formato JSON especificado abaixo.

**A. Resumo Executivo:** Um parágrafo direto para o gestor, destacando os problemas mais críticos e as ações urgentes recomendadas.

**B. Tabela de Visão Geral:** Um sumário rápido de todos os pneus analisados.

**C. Análise Detalhada por Eixo:** Para cada eixo:
  - **Diagnóstico do Eixo:** Análise do conjunto.
  - **Análise por Pneu (Motorista e Oposto):** Para cada pneu:
    - **Defeitos:** Para CADA defeito encontrado:
      - **`nome_defeito`**: Nome técnico (ex: "Desgaste por convergência", "Serrilhamento").
      - **`localizacao_visual`**: **Descreva textualmente onde olhar na foto** (ex: "Ombro externo do pneu", "Blocos centrais da banda de rodagem").
      - **`explicacao` (Pedagógica):**
        - **`significado`**: O que o defeito é.
        - **`impacto_operacional`**: Como afeta o veículo no dia a dia.
        - **`risco_nao_corrigir`**: Consequências de ignorar o problema, incluindo uma **estimativa de perda de vida útil em porcentagem**.
      - **`urgencia`**: Classifique como **"Crítico"**, **"Médio"** ou **"Baixo"**.

**D. Diagnóstico Global do Veículo:** Conecte os pontos. Se múltiplos pneus têm o mesmo problema, explique a causa raiz sistêmica (ex: "O desgaste em ambos os pneus dianteiros sugere...").

**E. Plano de Ação:** Recomendações finais categorizadas por prioridade.

---
**4. FORMATO DE SAÍDA JSON (OBRIGATÓRIO)**
```json
{{
  "resumo_executivo": "...",
  "tabela_visao_geral": [
    {{"posicao": "Eixo 1 - Motorista", "principal_defeito": "...", "urgencia": "Crítico"}}
  ],
  "analise_detalhada_eixos": [
    {{
      "titulo_eixo": "Eixo Dianteiro 1",
      "diagnostico_geral_eixo": "...",
      "analise_pneus": [
        {{
          "posicao": "Motorista",
          "defeitos": [
            {{
              "nome_defeito": "Desgaste irregular no ombro externo",
              "localizacao_visual": "Borda externa da banda de rodagem.",
              "explicacao": {{
                "significado": "Desgaste excessivo na parte de fora do pneu, causado por desalinhamento.",
                "impacto_operacional": "Aumento do consumo de combustível e da temperatura do pneu.",
                "risco_nao_corrigir": "Redução da vida útil em até 30% e perda da recapabilidade."
              }},
              "urgencia": "Crítico"
            }}
          ]
        }}
      ]
    }}
  ],
  "diagnostico_global_veiculo": "O padrão de desgaste repetido nos eixos dianteiros indica um problema crônico...",
  "plano_de_acao": {{
    "critico_risco_imediato": ["..."],
    "medio_agendar_manutencao": ["..."],
    "baixo_observacao_preventiva": ["..."]
  }},
  "whatsapp_resumo": "Laudo do veículo {{meta.get('placa', 'N/A')}}: Identificamos problemas críticos de alinhamento..."
}}
```
"""
    return [
        {"type": "text", "text": prompt_usuario},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]


def _call_openai_single_image(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
    """ATUALIZADO - Chama a API com a nova persona e exigência de JSON."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente."}

    client = OpenAI(api_key=api_key)
    prompt_sistema = "Você é um especialista sênior em manutenção de frotas pesadas, com vasta experiência em diagnóstico visual de pneus, focado em risco operacional e custo. Seja pedagógico, priorize ações, tenha visão sistêmica e quantifique o impacto. Siga rigorosamente o formato JSON."
    content = _build_multimodal_message(data_url, meta, obs, axis_titles)

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or ""
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
        return {"erro": f"Falha na API ou no processamento do JSON: {e}", "raw": raw_text}


def _call_openai_single_axis(collage: Image.Image, meta: dict, obs: str, model_name: str, axis_title: str) -> dict:
    """Fallback da sua versão original, para estabilidade."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente."}
    client = OpenAI(api_key=api_key)
    data_url = _img_to_dataurl(collage)
    
    # Usando o prompt de fallback original da sua versão estável
    formato_fallback = '{"eixos": [ { "titulo": "' + axis_title + '", "tipo": "Dianteiro|Traseiro", "diagnostico_global": "...", "necessita_alinhamento": true, "parametros_suspeitos":[], "pressao_pneus":{}, "balanceamento_sugerido": "...", "achados_chave":[], "severidade_eixo":0, "prioridade_manutencao":"baixa", "rodizio_recomendado":"..." } ]}'
    header = f"Análise de UM eixo: {axis_title}. Retorne JSON no formato: {formato_fallback}"

    content = [
        {"type": "text", "text": header},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    try:
        resp = client.chat.completions.create(
            model=model_name, messages=[{"role": "user", "content": content}], temperature=0, response_format={"type": "json_object"}
        )
        text = resp.choices[0].message.content or ""
        return json.loads(text)
    except Exception as e:
        return {"erro": f"Falha na API (fallback): {e}"}

# =========================
# UI helpers (SEÇÃO ATUALIZADA)
# =========================
def _render_laudo_ui(laudo: dict, meta: dict, obs: str):
    """ATUALIZADO - Renderiza o novo laudo profissional na tela."""
    
    # Compatibilidade: Se o laudo vier no formato antigo (do fallback), mostra o antigo renderizador
    if "resumo_executivo" not in laudo:
        st.warning("Laudo recebido em formato de compatibilidade (fallback). A análise pode ser menos detalhada.")
        _render_laudo_ui_original(laudo, meta, obs) # Chama a função original
        return

    st.success("Laudo Profissional Gerado")
    
    urgency_map = {
        "Crítico": "⛔ Crítico", "Médio": "⚠️ Médio", "Baixo": "ℹ️ Baixo",
    }

    st.markdown("### 1. Resumo Executivo para o Gestor")
    st.write(laudo.get('resumo_executivo', "N/A"))

    st.markdown("### 2. Tabela de Visão Geral")
    if laudo.get('tabela_visao_geral'):
        st.dataframe(laudo['tabela_visao_geral'], use_container_width=True, hide_index=True)

    st.markdown("### 3. Diagnóstico Global do Veículo")
    st.info(laudo.get('diagnostico_global_veiculo', "N/A"))

    st.markdown("### 4. Análise Detalhada por Eixo")
    if 'ultima_colagem' in st.session_state:
        st.image(st.session_state['ultima_colagem'], caption="Imagem completa enviada para análise", use_container_width=True)

    for eixo in laudo.get('analise_detalhada_eixos', []):
        with st.expander(f"**{eixo.get('titulo_eixo', 'Eixo')}** - Clique para expandir", expanded=True):
            st.write(f"**Diagnóstico do Eixo:** {eixo.get('diagnostico_geral_eixo', 'N/A')}")
            for pneu in eixo.get('analise_pneus', []):
                st.markdown(f"--- \n #### Lado: {pneu.get('posicao')}")
                for defeito in pneu.get('defeitos', []):
                    with st.container(border=True):
                        urg = defeito.get('urgencia', 'N/A')
                        st.markdown(f"**Defeito:** {defeito.get('nome_defeito')} [{urgency_map.get(urg, urg)}]")
                        st.caption(f"📍 Onde Olhar: {defeito.get('localizacao_visual', 'N/A')}")
                        exp = defeito.get('explicacao', {})
                        st.markdown(f"""
                        - **O que significa:** {exp.get('significado', 'N/A')}
                        - **Impacto na Operação:** {exp.get('impacto_operacional', 'N/A')}
                        - **Risco se não corrigido:** {exp.get('risco_nao_corrigir', 'N/A')}
                        """)

    st.markdown("### 5. Plano de Ação Recomendado")
    plano = laudo.get('plano_de_acao', {})
    st.error("⛔ Ações Críticas (Risco Imediato)")
    st.write("• " + "\n• ".join(plano.get('critico_risco_imediato', ["Nenhuma."])))
    st.warning("⚠️ Ações de Prioridade Média (Agendar Manutenção)")
    st.write("• " + "\n• ".join(plano.get('medio_agendar_manutencao', ["Nenhuma."])))
    st.info("ℹ️ Ações de Baixa Prioridade (Observação Preventiva)")
    st.write("• " + "\n• ".join(plano.get('baixo_observacao_preventiva', ["Nenhuma."])))


def _render_laudo_ui_original(laudo: dict, meta: dict, obs: str):
    """Sua função de renderização original, para fallback."""
    st.success("Laudo recebido.")
    st.markdown("## 🧾 Resumo")
    if laudo.get("resumo_geral"):
        st.write(laudo["resumo_geral"])
    cfg = laudo.get("configuracao_detectada")
    if isinstance(cfg, str) and cfg.strip():
        st.caption(f"Configuração detectada: {cfg}")
    for eixo in laudo.get("eixos", []):
        with st.container(border=True):
            titulo = eixo.get("titulo", eixo.get("tipo", "Eixo"))
            st.markdown(f"### {titulo}")
            diag = eixo.get("diagnostico_global") or eixo.get("relatorio")
            st.write(diag.strip() if isinstance(diag, str) and diag.strip() else "Diagnóstico do eixo não informado pelo modelo.")
            if eixo.get("necessita_alinhamento") is not None:
                st.caption(f"Necessita alinhamento: {'sim' if eixo.get('necessita_alinhamento') else 'não'}")
            ps = eixo.get("parametros_suspeitos") or []
            if isinstance(ps, list) and ps:
                parts = []
                for p in ps:
                    try:
                        parts.append(f"{p.get('parametro','-')}: {p.get('tendencia','indefinida')} (confiança {p.get('confianca',0):.2f})")
                    except Exception:
                        pass
                if parts:
                    st.caption("Parâmetros suspeitos: " + " | ".join(parts))
            press = eixo.get("pressao_pneus") or {}
            if press:
                st.caption(f"Pressão — Motorista: {press.get('motorista','-')} | Oposto: {press.get('oposto','-')}")
            bal = eixo.get("balanceamento_sugerido")
            if isinstance(bal, str) and bal.strip():
                st.caption(f"Balanceamento: {bal}")
            ach = eixo.get("achados_chave") or []
            if ach:
                st.caption("Achados-chave: " + "; ".join(ach))
            sev = eixo.get("severidade_eixo")
            pri = eixo.get("prioridade_manutencao")
            linha = []
            if sev is not None:
                linha.append(f"Severidade do eixo: {sev}/5")
            if pri:
                linha.append(f"Prioridade: {pri}")
            if linha:
                st.caption(" | ".join(linha))
            rod = eixo.get("rodizio_recomendado")
            if isinstance(rod, str) and rod.strip():
                st.caption(f"Rodízio recomendado: {rod}")
    if laudo.get("recomendacoes_finais"):
        st.markdown("## 🔧 Recomendações finais")
        st.write("• " + "\n• ".join(laudo["recomendacoes_finais"]))

# =========================
# UI (Sua versão original, estável)
# =========================
def app():
    st.title("🛞 Análise de Pneus por Foto — AVP")
    st.caption("Laudo automático de apoio (sujeito a erros). Recomenda-se inspeção presencial.")

    # Toggle do modelo
    col_m1, _ = st.columns([1, 3])
    with col_m1:
        modo_detalhado = st.toggle("Análise detalhada (gpt-4o)", value=False)
    modelo = "gpt-4o" if modo_detalhado else "gpt-4o-mini"

    # Identificação
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
            st.success(f"Dados da placa: {json.dumps(placa_info, ensure_ascii=False)}")
        else:
            st.warning(data)
    
    st.markdown("---")

    # Guia rápido de fotografia — NOVO PADRÃO (Frente + 45°)
    with st.expander("📸 Como fotografar para melhor leitura (dica rápida)"):
        st.write(
            "- Para **cada lado**, tire **duas fotos** do pneu:\n"
            "  1) **De frente**: câmera **paralela à banda** (visão frontal da banda de rodagem);\n"
            "  2) **Em ~45°**: para evidenciar profundidade dos sulcos.\n"
            "- Distância **~1 metro**; enquadre **banda + dois ombros** e um pouco do flanco.\n"
            "- Evite **contraluz** e sombras fortes; garanta foco nítido.\n"
            "- **Traseiro (germinado)**: faça a dupla (**frente** e **45°**) do **conjunto** do lado Motorista e do lado Oposto.\n"
            "- Se o pneu estiver **fora do caminhão**, a foto em 45° pode ser levemente **de cima**."
        )

    observacao = st.text_area(
        "Observação do motorista (máx. 250 caracteres)",
        max_chars=MAX_OBS,
        placeholder="Ex.: puxa para a direita, vibra acima de 80 km/h…"
    )

    # ------- Controle dinâmico de eixos -------
    if "axes" not in st.session_state:
        st.session_state.axes = []

    cA, cB, cC = st.columns(3)
    with cA:
        if st.button("➕ Adicionar Dianteiro"):
            st.session_state.axes.append({"tipo": "Dianteiro", "files": {}})
    with cB:
        if st.button("➕ Adicionar Traseiro"):
            st.session_state.axes.append({"tipo": "Traseiro", "files": {}})
    with cC:
        if st.session_state.axes and st.button("🗑️ Remover último eixo"):
            st.session_state.axes.pop()

    if not st.session_state.axes and "laudo" not in st.session_state:
        st.info("Adicione pelo menos um eixo (Dianteiro/Traseiro).")
        return

    # Uploaders por eixo — NOVO PADRÃO
    if st.session_state.axes:
        for idx, eixo in enumerate(st.session_state.axes, start=1):
            with st.container(border=True):
                st.subheader(f"Eixo {idx} — {eixo['tipo']}")
                cm, co = st.columns(2)
                with cm:
                    eixo["files"]["lt"] = st.file_uploader(f"Motorista — Foto 1 (FRENTE) — Eixo {idx}", type=["jpg","jpeg","png"], key=f"d_dm1_{idx}")
                    eixo["files"]["lb"] = st.file_uploader(f"Motorista — Foto 2 (45°) — Eixo {idx}", type=["jpg","jpeg","png"], key=f"d_dm2_{idx}")
                with co:
                    eixo["files"]["rt"] = st.file_uploader(f"Oposto — Foto 1 (FRENTE) — Eixo {idx}", type=["jpg","jpeg","png"], key=f"d_do1_{idx}")
                    eixo["files"]["rb"] = st.file_uploader(f"Oposto — Foto 2 (45°) — Eixo {idx}", type=["jpg","jpeg","png"], key=f"d_do2_{idx}")
    
    st.markdown("---")
    pronto = st.button("🚀 Enviar para análise")

    # ============= Renderização e Lógica Principal =============
    if "laudo" in st.session_state:
        _render_laudo_ui(st.session_state["laudo"], st.session_state.get("meta", {}), st.session_state.get("obs", ""))
        
        st.markdown("---")
        col_exp1, col_exp2 = st.columns([1, 3])
        with col_exp1:
            if "ultima_colagem" in st.session_state:
                if st.button("🔄 Regerar PDF"):
                    try:
                        report_img = _render_report_image(st.session_state["laudo"], st.session_state.get("meta", {}), st.session_state.get("obs", ""), st.session_state["ultima_colagem"])
                        st.session_state["pdf_bytes"] = _build_pdf_bytes(report_img)
                    except Exception as e:
                        st.error(f"Falha ao gerar PDF: {e}")
                if "pdf_bytes" in st.session_state:
                    st.download_button("⬇️ Baixar PDF do Laudo", st.session_state["pdf_bytes"], f"laudo_{st.session_state.get('meta',{}).get('placa')}.pdf")
        
        with col_exp2:
            from urllib.parse import quote
            resumo_wpp = st.session_state["laudo"].get("whatsapp_resumo") or st.session_state["laudo"].get("resumo_executivo", "") or st.session_state["laudo"].get("resumo_geral", "")
            meta = st.session_state.get("meta", {})
            msg = f"Análise de pneus para o veículo {meta.get('placa', '')}:\n\n{resumo_wpp}"
            link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(msg)}"
            st.markdown(f"[📲 Enviar resultado via WhatsApp]({link_wpp})")

    if pronto:
        for i, eixo in enumerate(st.session_state.axes, start=1):
            if not all(eixo["files"].get(k) for k in ("lt","lb","rt","rb")):
                st.error(f"Envie as 4 fotos do eixo {i}.")
                return

        with st.spinner("Preparando imagens…"):
            collages, titles = [], []
            for i, eixo in enumerate(st.session_state.axes, start=1):
                lt, lb = _open_and_prepare(eixo["files"]["lt"]), _open_and_prepare(eixo["files"]["lb"])
                rt, rb = _open_and_prepare(eixo["files"]["rt"]), _open_and_prepare(eixo["files"]["rb"])
                labels = {"title": f"Eixo {i} - {eixo['tipo']}"}
                collages.append(_grid_2x2_labeled(lt, lb, rt, rb, labels))
                titles.append(labels["title"])
            colagem_final = _stack_vertical_center(collages, titles)
            st.session_state["ultima_colagem"] = colagem_final
            st.session_state["titles"] = titles

        data_url = _img_to_dataurl(colagem_final)
        meta = {"placa": placa, "nome": nome, "empresa": empresa, "telefone": telefone, "email": email, "placa_info": placa_info}
        
        with st.spinner("Analisando com IA (pode levar até 2 minutos)..."):
            laudo = _call_openai_single_image(data_url, meta, observacao, modelo, titles)
        
        if "erro" in laudo or not ("analise_detalhada_eixos" in laudo or "eixos" in laudo):
            st.warning("Análise principal falhou. Tentando fallback por eixo...")
            eixos_ok = []
            laudo_final = {}
            for cimg, atitle in zip(st.session_state["collages"], st.session_state["titles"]):
                sub_laudo = _call_openai_single_axis(cimg, meta, observacao, modelo, atitle)
                if "eixos" in sub_laudo:
                    eixos_ok.extend(sub_laudo["eixos"])
            if eixos_ok:
                laudo_final = {"eixos": eixos_ok, "resumo_geral": "Análise concluída em modo de fallback."}
            else:
                st.error(f"Análise e fallback falharam: {laudo.get('erro', 'Resposta inválida.')}")
                if DEBUG and laudo.get("raw"): st.code(laudo.get("raw"))
                return
            laudo = laudo_final
        
        st.session_state["laudo"] = laudo
        st.session_state["meta"] = meta
        st.session_state["obs"] = observacao

        try:
            report_img = _render_report_image(laudo, meta, observacao, st.session_state["ultima_colagem"])
            st.session_state["pdf_bytes"] = _build_pdf_bytes(report_img)
        except Exception as e:
            st.warning(f"Não foi possível pré-gerar o PDF: {e}")
        st.rerun()

if __name__ == "__main__":
    app()
