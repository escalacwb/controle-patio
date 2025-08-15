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
WHATSAPP_NUMERO = "5567984173800"
MAX_OBS = 250
MAX_SIDE = 1024
JPEG_QUALITY = 85
DEBUG = bool(st.secrets.get("DEBUG_ANALISE_PNEUS", False))

# =========================
# Utilitários de imagem (Versão Funcional)
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
    if not all([lt, lb, rt, rb]): return Image.new("RGB", (100,100), "white")
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
# Utilitários de PDF e Relatório (Versão Funcional)
# =========================
def _get_font(size=16):
    try: return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try: return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception: return ImageFont.load_default()

def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    lines = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0,0), test, font=font)
                w_check = bbox[2] - bbox[0]
            else:
                w_check, _ = draw.textsize(test, font=font)

            if w_check <= max_w:
                cur = test
            else:
                if cur: lines.append(cur)
                cur = w
        if cur: lines.append(cur)
    return lines

def _render_report_image(laudo: dict, meta: dict, obs: str, collage: Image.Image) -> Image.Image:
    W, P, H_PAD = 1240, 40, 15
    title_font, h2_font, h3_font, body_font = _get_font(32), _get_font(26), _get_font(22), _get_font(18)
    
    # Função para calcular a altura necessária para um bloco de texto
    def get_section_height(texts, font, indent=0):
        h = 0
        for text in texts:
            if not text or not isinstance(text, str): continue
            lines = _wrap_text(dummy_draw, text, font, W - 2*P - indent)
            h += len(lines) * (font.size + 5)
        return h

    dummy_draw = ImageDraw.Draw(Image.new("RGB", (W, 10), "white"))
    height = P

    # Cabeçalho
    height += get_section_height([f"Laudo Técnico de Análise Visual de Pneus - Placa: {meta.get('placa', 'N/A')}"], title_font) + H_PAD
    height += get_section_height([f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}"], body_font) + H_PAD * 2

    # Resumo Executivo
    height += get_section_height(["1. Resumo Executivo"], h2_font) + H_PAD
    height += get_section_height([laudo.get('resumo_executivo', 'N/A')], body_font) + H_PAD * 2
    
    # Diagnóstico Global
    dg = laudo.get('diagnostico_global_veiculo', {})
    height += get_section_height(["2. Diagnóstico Global do Veículo"], h2_font) + H_PAD
    height += get_section_height(["Problemas Sistêmicos:"], h3_font)
    height += get_section_height(dg.get('problemas_sistemicos',[]), body_font, indent=20) + H_PAD
    
    # Plano de Ação
    plano = laudo.get('plano_de_acao', {})
    height += get_section_height(["3. Plano de Ação"], h2_font) + H_PAD
    height += get_section_height(["Ações Críticas:"], h3_font)
    height += get_section_height(plano.get('critico_risco_imediato',[]), body_font, indent=20) + H_PAD
    
    # Colagem
    scale = (W - 2*P) / collage.width if collage.width > 0 else 0
    height += int(collage.height * scale) + P

    # Desenho
    out = Image.new("RGB", (W, int(height)), "white")
    draw = ImageDraw.Draw(out)
    y = P

    def draw_wrapped_text(text, font, y_pos, indent=0, color=(0,0,0)):
        if not text or not isinstance(text, str): return y_pos
        lines = _wrap_text(draw, text, font, W - 2*P - indent)
        for line in lines:
            draw.text((P + indent, y_pos), line, font=font, fill=color)
            y_pos += font.size + 5
        return y_pos

    y = draw_wrapped_text(f"Laudo Técnico - Placa: {meta.get('placa', 'N/A')}", title_font, y) + H_PAD
    y = draw_wrapped_text(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", body_font, y) + H_PAD * 2
    
    y = draw_wrapped_text("1. Resumo Executivo", h2_font, y) + H_PAD
    y = draw_wrapped_text(laudo.get('resumo_executivo', 'N/A'), body_font, y) + H_PAD * 2
    
    y = draw_wrapped_text("2. Diagnóstico Global", h2_font, y) + H_PAD
    y = draw_wrapped_text("Problemas Sistêmicos:", h3_font, y)
    y = draw_wrapped_text("\n".join([f"• {item}" for item in dg.get('problemas_sistemicos',[])]), body_font, y, indent=20) + H_PAD
    
    y = draw_wrapped_text("3. Plano de Ação", h2_font, y) + H_PAD
    y = draw_wrapped_text("Ações Críticas:", h3_font, y, color=(200,0,0))
    y = draw_wrapped_text("\n".join([f"• {item}" for item in plano.get('critico_risco_imediato',[])]), body_font, y, indent=20) + H_PAD
    
    if collage.width > 0:
        col_resized = collage.resize((int(collage.width * scale), int(collage.height * scale)), Image.LANCZOS)
        out.paste(col_resized, (P, y))
        y += col_resized.height + P
    
    return out.crop((0, 0, W, y))

def _build_pdf_bytes(report_img: Image.Image) -> bytes:
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
"""
return [
{"type": "text", "text": prompt_usuario},
{"type": "image_url", "image_url": {"url": data_url}},
]

def _call_openai_single_image(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
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
"""Fallback da versão original, para estabilidade."""
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
return {"erro": "OPENAI_API_KEY ausente."}
client = OpenAI(api_key=api_key)
data_url = _img_to_dataurl(collage)

# Usando o prompt de fallback original e mais simples
formato_fallback = '{"eixos": [ { "titulo": "' + axis_title + '", "diagnostico_global": "...", "necessita_alinhamento": true, "parametros_suspeitos":[] } ]}'
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
=========================
UI helpers (ATUALIZADO PARA NOVO LAUDO)
=========================
def _render_laudo_ui(laudo: dict, meta: dict, obs: str):
st.success("Laudo Profissional Gerado")

urgency_map = {
    "Crítico": "⛔ Crítico",
    "Médio": "⚠️ Médio",
    "Baixo": "ℹ️ Baixo",
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
    st.image(st.session_state['ultima_colagem'], caption="Imagem completa enviada para análise", use_column_width=True)

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
=========================
UI (Versão Funcional)
=========================
def app():
st.title("🛞 Análise de Pneus por Foto — AVP")
st.caption("Laudo automático de apoio (sujeito a erros). Recomenda-se inspeção presencial.")

col_m1, _ = st.columns([1, 3])
with col_m1:
    modo_detalhado = st.toggle("Análise Premium (gpt-4o)", value=True)
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
    if ok: st.success("Dados da placa carregados.")
    else: st.warning(data)

st.markdown("---")
with st.expander("📸 Como fotografar para melhor leitura (dica rápida)"):
    st.write("- Para **cada lado**, tire **duas fotos** do pneu: de **frente** e em **~45°**.")

observacao = st.text_area(
    "Observação do motorista", max_chars=250, placeholder="Ex.: puxa para a direita, vibra acima de 80 km/h…"
)

if "axes" not in st.session_state:
    st.session_state.axes = []

cA, cB, cC = st.columns(3)
if cA.button("➕ Adicionar Dianteiro"): st.session_state.axes.append({"tipo": "Dianteiro", "files": {}})
if cB.button("➕ Adicionar Traseiro"): st.session_state.axes.append({"tipo": "Traseiro", "files": {}})
if st.session_state.axes and cC.button("🗑️ Remover último eixo"): st.session_state.axes.pop()

if not st.session_state.axes and "laudo" not in st.session_state:
    st.info("Adicione pelo menos um eixo para iniciar a análise.")
    return

for idx, eixo in enumerate(st.session_state.axes, start=1):
    with st.container(border=True):
        st.subheader(f"Eixo {idx} — {eixo['tipo']}")
        cm, co = st.columns(2)
        eixo["files"]["lt"] = cm.file_uploader(f"Motorista — Frente — Eixo {idx}", key=f"d_dm1_{idx}")
        eixo["files"]["lb"] = cm.file_uploader(f"Motorista — 45° — Eixo {idx}", key=f"d_dm2_{idx}")
        eixo["files"]["rt"] = co.file_uploader(f"Oposto — Frente — Eixo {idx}", key=f"d_do1_{idx}")
        eixo["files"]["rb"] = co.file_uploader(f"Oposto — 45° — Eixo {idx}", key=f"d_do2_{idx}")
        
st.markdown("---")
pronto = st.button("🚀 Enviar para análise")

if pronto:
    if not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        st.error("OPENAI_API_KEY não configurada.")
        return

    for i, eixo in enumerate(st.session_state.axes):
        if not all(eixo["files"].get(k) for k in ("lt","lb","rt","rb")):
            st.error(f"Envie as 4 fotos do eixo {i+1}.")
            return

    with st.spinner("Preparando imagens…"):
        collages, titles = [], []
        for i, eixo in enumerate(st.session_state.axes, start=1):
            lt, lb = _open_and_prepare(eixo["files"]["lt"]), _open_and_prepare(eixo["files"]["lb"])
            rt, rb = _open_and_prepare(eixo["files"]["rt"]), _open_and_prepare(eixo["files"]["rb"])
            labels = {"title": f"Eixo {i} - {eixo['tipo']}", "left_top": "Motorista-Frente", "left_bottom": "Motorista-45°", "right_top": "Oposto-Frente", "right_bottom": "Oposto-45°"}
            collages.append(_grid_2x2_labeled(lt, lb, rt, rb, labels))
            titles.append(labels["title"])
        
        colagem_final = _stack_vertical_center(collages, titles)
        st.session_state["ultima_colagem"] = colagem_final
    
    data_url = _img_to_dataurl(colagem_final)
    meta = {"placa": placa, "nome": nome, "empresa": empresa, "telefone": telefone, "email": email, "placa_info": placa_info}
    
    with st.spinner("Analisando com IA (pode levar até 2 minutos)..."):
        laudo = _call_openai_single_image(data_url, meta, observacao, modelo, titles)

    if "erro" in laudo or not laudo.get("analise_detalhada_eixos"):
         st.error(f"A análise falhou. Detalhes: {laudo.get('erro', 'Resposta inválida da IA.')}")
         if DEBUG and laudo.get("raw"): st.code(laudo.get("raw"))
         return

    st.session_state["laudo"] = laudo
    st.session_state["meta"] = meta
    st.session_state["obs"] = observacao

    try:
        report_img = _render_report_image(laudo, meta, observacao, st.session_state["ultima_colagem"])
        st.session_state["pdf_bytes"] = _build_pdf_bytes(report_img)
    except Exception as e:
        st.warning(f"Não foi possível pré-gerar o PDF: {e}")
    st.rerun()

if "laudo" in st.session_state:
    _render_laudo_ui(st.session_state["laudo"], st.session_state["meta"], st.session_state["obs"])

    from urllib.parse import quote
    resumo_wpp = st.session_state["laudo"].get("whatsapp_resumo", "")
    msg = f"Olá! Segue resumo da análise de pneus para o veículo {st.session_state.get('meta',{}).get('placa','')}:\n\n{resumo_wpp}"
    link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(msg)}"
    st.sidebar.markdown(f"--- \n [📲 Enviar resumo via WhatsApp]({link_wpp})")
    
    if "pdf_bytes" in st.session_state:
        st.sidebar.download_button("⬇️ Baixar Laudo PDF", st.session_state["pdf_bytes"], f"laudo_{st.session_state.get('meta',{}).get('placa')}.pdf")
if name == "main":
app()