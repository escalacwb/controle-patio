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
# Utilitários de imagem
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

    # Pillow novo: usar textbbox; se falhar, fallback aproximado
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

# -------- Helpers para exportação PDF (renderizando texto em imagem) --------
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
        lines.append("")  # quebra de parágrafo
    if lines and lines[-1] == "":
        lines.pop()
    return lines

def _render_report_image(laudo: dict, meta: dict, obs: str, collage: Image.Image) -> Image.Image:
    """Gera um 'poster' do relatório (texto + colagem) como uma imagem longa."""
    W = 1240
    P = 40   # padding
    title_font = _get_font(28)
    h2_font = _get_font(22)
    body_font = _get_font(17)

    # Primeiro, calculamos a altura necessária
    dummy = Image.new("RGB", (W, 10), "white")
    draw = ImageDraw.Draw(dummy)
    height = P

    # Título
    height += 40
    # Meta
    meta_lines = _wrap_text(
        draw,
        f"Placa: {meta.get('placa') or '-'}  |  Empresa: {meta.get('empresa') or '-'}  |  Motorista/Gestor: {meta.get('nome') or '-'}  |  Tel: {meta.get('telefone') or '-'}  |  E-mail: {meta.get('email') or '-'}",
        body_font, W - 2*P
    )
    height += (len(meta_lines) * 22) + 10

    # Resumo
    if laudo.get("resumo_geral"):
        res_lines = _wrap_text(draw, laudo.get("resumo_geral",""), body_font, W - 2*P)
        height += 30 + len(res_lines) * 22 + 10

    # Qualidade
    q = laudo.get("qualidade_imagens") or {}
    if q:
        q_text = f"Qualidade das imagens: score {q.get('score','-')} | Problemas: {', '.join(q.get('problemas') or []) or '-'} | Faltantes: {', '.join(q.get('faltantes') or []) or '-'}"
        q_lines = _wrap_text(draw, q_text, body_font, W - 2*P)
        height += 30 + len(q_lines)*22

    # Eixos (diagnóstico global)
    for eixo in laudo.get("eixos", []):
        rel = eixo.get("diagnostico_global") or eixo.get("relatorio") or ""
        rel_lines = _wrap_text(draw, f"{eixo.get('titulo', eixo.get('tipo','Eixo'))}: {rel}", body_font, W - 2*P)
        height += 30 + len(rel_lines)*22

    # Recomendações
    if laudo.get("recomendacoes_finais"):
        rec_text = "Recomendações finais: " + " • ".join(laudo.get("recomendacoes_finais"))
        rec_lines = _wrap_text(draw, rec_text, body_font, W - 2*P)
        height += 30 + len(rec_lines)*22

    # Observação motorista
    if obs:
        obs_lines = _wrap_text(draw, f"Observação do motorista: {obs}", body_font, W - 2*P)
        height += 30 + len(obs_lines)*22

    # Colagem
    col_w = W - 2*P
    scale = min(1.0, col_w / collage.width)
    col_h = int(collage.height * scale)
    height += 30 + col_h + P

    # Criar canvas final
    out = Image.new("RGB", (W, height), "white")
    d = ImageDraw.Draw(out)

    y = P
    d.text((P, y), "Laudo de Análise de Pneus — AVP", font=title_font, fill=(0,0,0))
    y += 40

    for line in meta_lines:
        d.text((P, y), line, font=body_font, fill=(0,0,0))
        y += 22
    y += 10

    if laudo.get("resumo_geral"):
        d.text((P, y), "Resumo", font=h2_font, fill=(0,0,0)); y += 30
        for line in res_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22
        y += 10

    if q:
        d.text((P, y), "Qualidade das imagens", font=h2_font, fill=(0,0,0)); y += 30
        for line in q_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    for eixo in laudo.get("eixos", []):
        y += 30
        d.text((P, y), eixo.get("titulo", eixo.get("tipo","Eixo")), font=h2_font, fill=(0,0,0)); y += 30
        rel = eixo.get("diagnostico_global") or eixo.get("relatorio") or ""
        for line in _wrap_text(d, rel, body_font, W - 2*P):
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    if laudo.get("recomendacoes_finais"):
        y += 30
        d.text((P, y), "Recomendações finais", font=h2_font, fill=(0,0,0)); y += 30
        for line in rec_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    if obs:
        y += 30
        d.text((P, y), "Observação do motorista", font=h2_font, fill=(0,0,0)); y += 30
        for line in obs_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    # Colagem (redimensionada)
    y += 30
    if scale < 1.0:
        col_resized = collage.resize((col_w, col_h), Image.LANCZOS)
    else:
        col_resized = collage.copy()
    out.paste(col_resized, (P, y))
    return out

def _build_pdf_bytes(report_img: Image.Image) -> bytes:
    """Converte a imagem do relatório para PDF (1 página)."""
    buf = io.BytesIO()
    report_img.save(buf, format="PDF", resolution=150.0)
    return buf.getvalue()

# =========================
# OpenAI / Prompt (ANÁLISE GLOBAL POR EIXO)
# =========================
def _build_multimodal_message(data_url: str, meta: dict, obs: str, axis_titles: List[str]) -> list:
    aviso = (
        "Você é o AVP — Analisador Virtual de Pneus, um sistema AUTOMÁTICO de visão computacional. "
        "⚠️ Este laudo é auxiliar e pode conter erros. Não usar como única base de decisão. "
        "Recomenda-se inspeção presencial por profissional qualificado."
    )

    # Orientação de fotografia com novo padrão: Frente (câmera paralela à banda) + 45°
    orientacao_foto = (
        "Orientações para leitura e qualidade: As fotos vêm de motoristas via celular. "
        "Para cada lado do eixo, enviar **duas fotos**: (1) **de frente** para o pneu, com a câmera **paralela à banda**; "
        "(2) em **~45°** para evidenciar a profundidade dos sulcos. Distância ~0,8–1,2 m. "
        "Enquadrar banda + dois ombros e um pouco do flanco. Evitar sombras duras/contraluz; manter foco nítido. "
        "Se o pneu estiver fora do caminhão, a foto em 45° pode ser levemente de cima."
    )

    layout = (
        "Você receberá UMA imagem com uma SEQUÊNCIA de colagens 2×2 empilhadas verticalmente. "
        "Cada colagem possui um rótulo no canto superior (ex.: 'Eixo Dianteiro 1', 'Eixo Traseiro 2'). "
        "Em TODAS as colagens: coluna ESQUERDA = lado MOTORISTA; coluna DIREITA = lado OPOSTO. "
        "Padrão por colagem 2×2:\n"
        "• **Linha de CIMA** = fotos **de frente** (câmera paralela à banda) — Motorista (esq), Oposto (dir);\n"
        "• **Linha de BAIXO** = fotos **em ~45°** — Motorista (esq), Oposto (dir).\n"
        "Para eixos traseiros **germinados**, considere a foto 'de frente' e 'em 45°' do **conjunto** do lado Motorista e do lado Oposto. "
        f"Ordem de cima para baixo: {', '.join(axis_titles)}."
    )

    # >>> Análise GLOBAL por eixo (texto corrido), com pressão por pneu quando possível
    escopo = (
        "Atue como especialista em pneus de caminhões pesados. Entregue um diagnóstico **global por eixo** "
        "(texto fluido, sem bullets), descrevendo padrão de desgaste observado (ombros, centro, cunha, conicidade, "
        "serrilhamento/dente de serra, cupping, recap solta, trincas superficiais) e as **causas prováveis no conjunto** "
        "(ex.: convergência fechada/aberta, cambagem positiva/negativa, caster avançado/recuado, pressão inadequada, "
        "sobrecarga, componentes de suspensão/rolamento). "
        "Se possível, informe **pressão por pneu** (baixa/alta/ok) para Motorista e Oposto. "
        "Quando as fotos limitarem a avaliação, aponte exatamente o que faltou (ângulo/foco/luz/distância)."
    )

    formato = (
        "Responda SOMENTE em JSON válido no formato:\n"
        "{\n"
        '  "placa": "string",\n'
        '  "qualidade_imagens": {"score": 0.0-1.0, "problemas": ["..."], "faltantes": ["..."]},\n'
        '  "eixos": [\n'
        '    {\n'
        '      "titulo": "Eixo Dianteiro 1",\n'
        '      "tipo": "Dianteiro|Traseiro",\n'
        '      "diagnostico_global": "texto corrido e profissional integrando desgaste observado e causas prováveis no conjunto",\n'
        '      "pressao_pneus": {"motorista":"baixa|alta|ok|indef","oposto":"baixa|alta|ok|indef"},\n'
        '      "achados_chave": ["opcional: até 5 pontos resumidos de evidências"],\n'
        '      "severidade_eixo": 0-5,\n'
        '      "prioridade_manutencao": "baixa|média|alta"\n'
        '    }\n'
        '  ],\n'
        '  "recomendacoes_finais": ["ações curtas e priorizadas"],\n'
        '  "resumo_geral": "explicação em 2–4 frases para leigo",\n'
        '  "whatsapp_resumo": "2–3 linhas diretas para WhatsApp"\n'
        "}\n"
    )

    header = (
        f"{aviso}\n\n"
        "Contexto do veículo:\n"
        f"- Placa: {meta.get('placa')}\n"
        f"- Motorista/gestor: {meta.get('nome')} (tel: {meta.get('telefone')}, email: {meta.get('email')})\n"
        f"- Empresa: {meta.get('empresa')}\n"
        f"- Observação do motorista: {obs}\n"
        f"- Dados da placa/API: {json.dumps(meta.get('placa_info') or {}, ensure_ascii=False)}\n\n"
        f"{orientacao_foto}\n\n{layout}\n\n{escopo}\n\n{formato}"
    )

    return [
        {"type": "text", "text": header},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]


def _call_openai_single_image(data_url: str, meta: dict, obs: str, model_name: str, axis_titles: List[str]) -> dict:
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente em Secrets/variável de ambiente."}

    client = OpenAI(api_key=api_key)
    content = _build_multimodal_message(data_url, meta, obs, axis_titles)

    try:
        resp = client.chat.completions.create(
            model=model_name,  # "gpt-4o-mini" (padrão) ou "gpt-4o"
            messages=[
                {"role": "system", "content": "Você é um mecânico especialista em pneus de caminhões."},
                {"role": "user", "content": content},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content or ""
        try:
            return json.loads(text)
        except Exception:
            import re
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            return {"erro": "Modelo não retornou JSON válido", "raw": text}
    except Exception as e:
        return {"erro": f"Falha na API: {e}"}

# =========================
# UI
# =========================
def app():
    st.title("🛞 Análise de Pneus por Foto — AVP")
    st.caption("Laudo automático de apoio (sujeito a erros). Recomenda-se inspeção presencial.")

    # Toggle do modelo
    col_m1, _ = st.columns([1, 3])
    with col_m1:
        modo_detalhado = st.toggle("Análise detalhada (gpt-4.0)", value=False)
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

    placa_info = None
    if buscar and placa:
        ok, data = utils.consultar_placa_comercial(placa)
        if ok:
            placa_info = data
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
        "Observação do motorista (máx. 150 caracteres)",
        max_chars=MAX_OBS,
        placeholder="Ex.: puxa para a direita, vibra acima de 80 km/h…"
    )

    # ------- Controle dinâmico de eixos -------
    if "axes" not in st.session_state:
        st.session_state.axes: List[Dict] = []  # cada item: {"tipo": "Dianteiro|Traseiro", "files": {}}

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

    if not st.session_state.axes:
        st.info("Adicione pelo menos um eixo (Dianteiro/Traseiro).")
        return

    # Uploaders por eixo — NOVO PADRÃO
    for idx, eixo in enumerate(st.session_state.axes, start=1):
        with st.container(border=True):
            st.subheader(f"Eixo {idx} — {eixo['tipo']}")
            # 4 fotos por eixo: Motorista (Frente, 45°) | Oposto (Frente, 45°)
            if eixo["tipo"] == "Dianteiro":
                st.caption("MOTORISTA: (1) FRENTE, (2) 45° — OPOSTO: (1) FRENTE, (2) 45°")
                cm, co = st.columns(2)
                with cm:
                    eixo["files"]["lt"] = st.file_uploader(
                        f"Motorista — Foto 1 (FRENTE) — Dianteiro {idx}",
                        type=["jpg","jpeg","png"], key=f"d_dm1_{idx}"
                    )
                    eixo["files"]["lb"] = st.file_uploader(
                        f"Motorista — Foto 2 (45°) — Dianteiro {idx}",
                        type=["jpg","jpeg","png"], key=f"d_dm2_{idx}"
                    )
                with co:
                    eixo["files"]["rt"] = st.file_uploader(
                        f"Oposto — Foto 1 (FRENTE) — Dianteiro {idx}",
                        type=["jpg","jpeg","png"], key=f"d_do1_{idx}"
                    )
                    eixo["files"]["rb"] = st.file_uploader(
                        f"Oposto — Foto 2 (45°) — Dianteiro {idx}",
                        type=["jpg","jpeg","png"], key=f"d_do2_{idx}"
                    )
            else:
                st.caption("MOTORISTA: (1) FRENTE (conjunto), (2) 45° (conjunto) — OPOSTO: (1) FRENTE (conjunto), (2) 45° (conjunto)")
                cm, co = st.columns(2)
                with cm:
                    eixo["files"]["lt"] = st.file_uploader(
                        f"Motorista — Frente (conjunto germinado) — Traseiro {idx}",
                        type=["jpg","jpeg","png"], key=f"t_tm1_{idx}"
                    )
                    eixo["files"]["lb"] = st.file_uploader(
                        f"Motorista — 45° (conjunto germinado) — Traseiro {idx}",
                        type=["jpg","jpeg","png"], key=f"t_tm2_{idx}"
                    )
                with co:
                    eixo["files"]["rt"] = st.file_uploader(
                        f"Oposto — Frente (conjunto germinado) — Traseiro {idx}",
                        type=["jpg","jpeg","png"], key=f"t_to1_{idx}"
                    )
                    eixo["files"]["rb"] = st.file_uploader(
                        f"Oposto — 45° (conjunto germinado) — Traseiro {idx}",
                        type=["jpg","jpeg","png"], key=f"t_to2_{idx}"
                    )

    st.markdown("---")
    pronto = st.button("🚀 Enviar para análise")
    if not pronto:
        return

    if not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        st.error("Defina OPENAI_API_KEY em Secrets/variável de ambiente.")
        return

    # Verificação de fotos por eixo
    for i, eixo in enumerate(st.session_state.axes, start=1):
        files = eixo["files"]
        if not all(files.get(k) for k in ("lt","lb","rt","rb")):
            st.error(f"Envie as 4 fotos do eixo {i} — {eixo['tipo']}.")
            return

    with st.spinner("Preparando imagens…"):
        collages, titles = [], []
        for i, eixo in enumerate(st.session_state.axes, start=1):
            # abre e redimensiona
            lt = _open_and_prepare(eixo["files"]["lt"])
            lb = _open_and_prepare(eixo["files"]["lb"])
            rt = _open_and_prepare(eixo["files"]["rt"])
            rb = _open_and_prepare(eixo["files"]["rb"])

            if eixo["tipo"] == "Dianteiro":
                labels = dict(
                    title=f"Eixo Dianteiro {i}",
                    left_top="Motorista — Frente",
                    left_bottom="Motorista — 45°",
                    right_top="Oposto — Frente",
                    right_bottom="Oposto — 45°",
                )
            else:
                labels = dict(
                    title=f"Eixo Traseiro {i}",
                    left_top="Motorista — Frente (conjunto)",
                    left_bottom="Motorista — 45° (conjunto)",
                    right_top="Oposto — Frente (conjunto)",
                    right_bottom="Oposto — 45° (conjunto)",
                )
            col = _grid_2x2_labeled(lt, lb, rt, rb, labels)
            collages.append(col)
            titles.append(labels["title"])

        # Pré-visualização individual: apenas se DEBUG = True
        if DEBUG:
            for c, t in zip(collages, titles):
                st.image(c, caption=f"Pré-visualização — {t}", use_column_width=True)

        # Empilha tudo numa imagem única
        colagem_final = _stack_vertical_center(collages, titles)
        # Guardamos para exportação posterior
        st.session_state["ultima_colagem"] = colagem_final

    data_url = _img_to_dataurl(colagem_final)
    meta = {
        "placa": placa, "nome": nome, "empresa": empresa,
        "telefone": telefone, "email": email, "placa_info": placa_info
    }
    obs = (observacao or "")[:MAX_OBS]

    with st.spinner("Analisando com IA…"):
        laudo = _call_openai_single_image(data_url, meta, obs, modelo, titles)

    if "erro" in laudo:
        st.error(laudo["erro"])
        # Resposta bruta só em debug
        if DEBUG and laudo.get("raw"):
            with st.expander("Resposta bruta do modelo"):
                st.code(laudo["raw"])
        return

    # ---- Apresentação do laudo ----
    st.success("Laudo recebido.")

    st.markdown("## 🧾 Resumo")
    if laudo.get("resumo_geral"):
        st.write(laudo["resumo_geral"])

    q = laudo.get("qualidade_imagens") or {}
    if q:
        score = q.get("score")
        probs = ", ".join(q.get("problemas") or [])
        falt = ", ".join(q.get("faltantes") or [])
        st.caption(
            f"Qualidade estimada: {score if score is not None else '-'} | "
            f"Problemas: {probs or '-'} | Faltantes: {falt or '-'}"
        )

    # Render: novo formato (diagnóstico global por eixo), com fallback
    for eixo in laudo.get("eixos", []):
        with st.container(border=True):
            titulo = eixo.get("titulo", eixo.get("tipo", "Eixo"))
            st.markdown(f"### {titulo}")

            diag = eixo.get("diagnostico_global") or eixo.get("relatorio")
            if isinstance(diag, str) and diag.strip():
                st.write(diag.strip())
            else:
                st.write("Diagnóstico do eixo não informado pelo modelo.")

            # Pressão por pneu (opcional, conciso)
            press = eixo.get("pressao_pneus") or {}
            if press:
                st.caption(
                    f"Pressão estimada — Motorista: {press.get('motorista','-')} | Oposto: {press.get('oposto','-')}"
                )

            # Achados chave e severidade/prioridade (se vierem)
            ach = eixo.get("achados_chave") or []
            sev = eixo.get("severidade_eixo")
            pri = eixo.get("prioridade_manutencao")
            linha = []
            if sev is not None:
                linha.append(f"Severidade do eixo: {sev}/5")
            if pri:
                linha.append(f"Prioridade: {pri}")
            if linha:
                st.caption(" | ".join(linha))
            if ach:
                st.caption("Achados-chave: " + "; ".join(ach))

    if laudo.get("recomendacoes_finais"):
        st.markdown("## 🔧 Recomendações finais")
        st.write("• " + "\n• ".join(laudo["recomendacoes_finais"]))

    # ---- Exportar PDF ----
    st.markdown("---")
    col_exp1, col_exp2 = st.columns([1, 3])
    with col_exp1:
        if st.button("📄 Exportar PDF"):
            try:
                collage = st.session_state.get("ultima_colagem")
                if collage is None:
                    st.error("Não foi possível localizar a colagem final para exportação.")
                else:
                    report_img = _render_report_image(laudo, meta, obs, collage)
                    pdf_bytes = _build_pdf_bytes(report_img)
                    st.download_button(
                        "⬇️ Baixar PDF do Laudo",
                        data=pdf_bytes,
                        file_name=f"laudo_{meta.get('placa') or 'veiculo'}.pdf",
                        mime="application/pdf",
                    )
            except Exception as e:
                st.error(f"Falha ao gerar PDF: {e}")

    # ---- WhatsApp (mensagem do cliente para a empresa) ----
    from urllib.parse import quote
    resumo_wpp = laudo.get("whatsapp_resumo") or (laudo.get("resumo_geral") or "")
    resumo_wpp = (resumo_wpp[:700] + "…") if len(resumo_wpp) > 700 else resumo_wpp
    msg = (
        "Olá! Fiz o teste de análise de pneus e gostaria de conversar sobre a manutenção do veículo.\n\n"
        f"{resumo_wpp}\n\n"
        f"Caminhão/Placa: {meta.get('placa')}\n"
        f"Empresa: {meta.get('empresa')}\n"
        f"Motorista/Gestor: {meta.get('nome')}\n"
        f"Telefone: {meta.get('telefone')}\n"
        f"E-mail: {meta.get('email')}\n"
        f"Observação: {obs or '-'}"
    )
    link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(msg)}"
    with col_exp2:
        st.markdown(f"[📲 Enviar resultado via WhatsApp]({link_wpp})")
