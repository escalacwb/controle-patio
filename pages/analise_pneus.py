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
    """Gera um 'poster' do relatório (texto + colagem) como uma imagem longa, incluindo campos extras."""
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

    # Configuração detectada (se houver)
    cfg = laudo.get("configuracao_detectada")
    cfg_lines = []
    if isinstance(cfg, str) and cfg.strip():
        cfg_lines = _wrap_text(draw, f"Configuração detectada: {cfg}", body_font, W - 2*P)
        height += len(cfg_lines)*22 + 10

    # Resumo
    res_lines = []
    if laudo.get("resumo_geral"):
        res_lines = _wrap_text(draw, laudo.get("resumo_geral",""), body_font, W - 2*P)
        height += 30 + len(res_lines) * 22 + 10

    # Qualidade
    q = laudo.get("qualidade_imagens") or {}
    q_lines = []
    if q:
        q_text = f"Qualidade das imagens: score {q.get('score','-')} | Problemas: {', '.join(q.get('problemas') or []) or '-'} | Faltantes: {', '.join(q.get('faltantes') or []) or '-'}"
        q_lines = _wrap_text(draw, q_text, body_font, W - 2*P)
        height += 30 + len(q_lines)*22

    # Eixos (diagnóstico global + extras)
    eixos = laudo.get("eixos", [])
    eixos_blocks = []
    for eixo in eixos:
        bloco = []
        titulo = eixo.get("titulo", eixo.get("tipo","Eixo"))
        diag = eixo.get("diagnostico_global") or eixo.get("relatorio") or ""
        bloco.append(("H2", titulo))
        bloco.append(("TXT", diag))

        if eixo.get("necessita_alinhamento") is not None:
            bloco.append(("TXT", f"Necessita alinhamento: {'sim' if eixo.get('necessita_alinhamento') else 'não'}"))

        ps = eixo.get("parametros_suspeitos") or []
        if isinstance(ps, list) and ps:
            parts = []
            for p in ps:
                try:
                    parts.append(f"{p.get('parametro','-')}: {p.get('tendencia','indefinida')} (confiança {p.get('confianca',0):.2f})")
                except Exception:
                    pass
            if parts:
                bloco.append(("TXT", "Parâmetros suspeitos: " + " | ".join(parts)))

        press = eixo.get("pressao_pneus") or {}
        if press:
            bloco.append(("TXT", f"Pressão — Motorista: {press.get('motorista','-')} | Oposto: {press.get('oposto','-')}"))

        bal = eixo.get("balanceamento_sugerido")
        if isinstance(bal, str) and bal.strip():
            bloco.append(("TXT", f"Balanceamento: {bal}"))

        ach = eixo.get("achados_chave") or []
        if ach:
            bloco.append(("TXT", "Achados-chave: " + "; ".join(ach)))

        sev = eixo.get("severidade_eixo")
        pri = eixo.get("prioridade_manutencao")
        sp = []
        if sev is not None:
            sp.append(f"Severidade do eixo: {sev}/5")
        if pri:
            sp.append(f"Prioridade: {pri}")
        if sp:
            bloco.append(("TXT", " | ".join(sp)))

        rod = eixo.get("rodizio_recomendado")
        if isinstance(rod, str) and rod.strip():
            bloco.append(("TXT", f"Rodízio recomendado: {rod}"))

        eixos_blocks.append(bloco)

    for bloco in eixos_blocks:
        height += 30
        for kind, text in bloco:
            if kind == "H2":
                height += 30
            lines = _wrap_text(draw, text, body_font, W - 2*P)
            height += len(lines)*22

    # Recomendações
    rec_lines = []
    if laudo.get("recomendacoes_finais"):
        rec_text = "Recomendações finais: " + " • ".join(laudo.get("recomendacoes_finais"))
        rec_lines = _wrap_text(draw, rec_text, body_font, W - 2*P)
        height += 30 + len(rec_lines)*22

    # Observação motorista
    obs_lines = []
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

    for line in cfg_lines:
        d.text((P, y), line, font=body_font, fill=(0,0,0))
        y += 22

    if res_lines:
        d.text((P, y), "Resumo", font=h2_font, fill=(0,0,0)); y += 30
        for line in res_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22
        y += 10

    if q_lines:
        d.text((P, y), "Qualidade das imagens", font=h2_font, fill=(0,0,0)); y += 30
        for line in q_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    for bloco in eixos_blocks:
        y += 30
        for kind, text in bloco:
            if kind == "H2":
                d.text((P, y), text, font=h2_font, fill=(0,0,0)); y += 30
            else:
                for line in _wrap_text(d, text, body_font, W - 2*P):
                    d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    if rec_lines:
        y += 30
        d.text((P, y), "Recomendações finais", font=h2_font, fill=(0,0,0)); y += 30
        for line in rec_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    if obs_lines:
        y += 30
        d.text((P, y), "Observação do motorista", font=h2_font, fill=(0,0,0)); y += 30
        for line in obs_lines:
            d.text((P, y), line, font=body_font, fill=(0,0,0)); y += 22

    # Colagem (redimensionada)
    y += 30
    col_resized = collage.resize((col_w, col_h), Image.LANCZOS) if scale < 1.0 else collage.copy()
    out.paste(col_resized, (P, y))
    return out

def _build_pdf_bytes(report_img: Image.Image) -> bytes:
    """Converte a imagem do relatório para PDF (1 página)."""
    buf = io.BytesIO()
    report_img.save(buf, format="PDF", resolution=150.0)
    return buf.getvalue()

# =========================
# OpenAI / Prompt helpers
# =========================
def _build_multimodal_message(data_url: str, meta: dict, obs: str, axis_titles: List[str]) -> list:
    """
    Prompt para imagem única contendo TODAS as colagens.
    Exige N itens em 'eixos' = len(axis_titles) e plano de rodízio detalhado.
    """
    especialista = (
        "Você é um especialista brasileiro em pneus de caminhões (borracharia/alinhamento) com prática em "
        "diagnóstico por desgaste, geometria (convergência, cambagem, cáster), pressão, balanceamento e rodízio "
        "em 4x2 (toco), 6x2 (trucado), 6x4 (traçado), 8x2/8x4 (quarto eixo/bitruck/duplo direcional), "
        "carretas (bi/tritem, rodotrem) e eixos de apoio (pusher/tag). "
        "Escreva em PT-BR claro para leigos e objetivo. Se a imagem não permitir certeza, diga o que faltou e dê hipótese com confiabilidade 0–1. "
        "Nunca invente medidas; baseie-se apenas no que as fotos mostram."
    )

    aviso = (
        "Laudo auxiliar por imagem — AVP. ⚠️ Pode conter erros. Não usar como única base de decisão; "
        "recomenda-se inspeção presencial."
    )

    orientacao_foto = (
        "As fotos chegam em colagens 2×2 por eixo: CIMA = Frente (câmera paralela à banda); BAIXO = ~45°. "
        "Coluna ESQ = Motorista; DIR = Oposto. De cima para baixo, a ordem dos eixos é: "
        + ", ".join(axis_titles) + ". Em traseiros germinados, a dupla (Frente e 45°) mostra o conjunto por lado. "
        "Boas práticas: 0,8–1,2 m; enquadrar banda + dois ombros; evitar contraluz/sombra; foco nítido."
    )

    heuristicas = (
        "Direcional: ombros internos ⇒ divergência; ombros externos ⇒ convergência; um lado do mesmo pneu ⇒ cambagem; "
        "serrilhamento ⇒ rodízio/pressão/cáster; vibração/ondas ⇒ desbalanceamento. "
        "Tração: escamação ⇒ pressão baixa + arraste; centro liso ⇒ pressão alta; diferença entre germinados ⇒ pressões desiguais/rolamento/suspensão/alinhamento. "
        "Apoio/carretas: desgaste irregular ⇒ altura/baixar eixo, carga desigual ou geometria fora; último eixo arrastando ⇒ quebra de esquadro. "
        "Pressão visual: centro>ombros=alta; ombros>centro=baixa; germinados diferentes=pressões desiguais."
    )

    rodizio = (
        "Plano de rodízio (OBRIGATÓRIO e DETALHADO):\n"
        "- Forneça um mapa de posições do MELHOR ao PIOR pneu (ex.: Melhor → Dianteiro Esq; 2º → Dianteiro Dir; ...),\n"
        "- Informe quando **virar o pneu na roda**, quando **trocar de lado (direita↔esquerda)** e quando **fazer ambos**;\n"
        "- Considere o **caimento da via no Brasil** (pista mais alta no centro e caída para a direita) ao sugerir as posições finais;\n"
        "- Adapte para 4x2, 6x2, 6x4, 8x2/8x4 e carretas conforme o caso."
    )

    tarefas = (
        "Tarefas: detectar configuração do conjunto; para CADA colagem 2×2 (um eixo), escrever diagnóstico GLOBAL integrando os 4 quadrantes "
        "(desgaste/causas prováveis), dizer se precisa alinhar e listar parâmetros suspeitos com confiança 0–1; "
        "estimar pressão por lado com justificativa; indicar balanceamento quando aplicável; sugerir rodízio DETALHADO; listar limitações; "
        "definir severidade_eixo (0–5) e prioridade (baixa/média/alta)."
    )

    formato = (
        "Responda SOMENTE em JSON válido. O array 'eixos' deve conter EXATAMENTE "
        f"{len(axis_titles)} itens, um para cada colagem, na mesma ordem: {', '.join(axis_titles)}.\n"
        "{\n"
        f'  "placa": "{meta.get("placa")}",\n'
        '  "configuracao_detectada": "ex.: 6x4 (traçado) | 8x2 (bitruck) | carreta 3 eixos | indefinida",\n'
        '  "qualidade_imagens": {"score": 0.0, "problemas": [], "faltantes": []},\n'
        '  "eixos": [\n'
        '    {\n'
        '      "titulo": "Eixo ...",\n'
        '      "tipo": "Dianteiro|Traseiro",\n'
        '      "diagnostico_global": "texto corrido integrando os quatro quadrantes",\n'
        '      "necessita_alinhamento": true,\n'
        '      "parametros_suspeitos": [\n'
        '        {"parametro": "convergência", "tendencia": "aberta|fechada|indefinida", "confianca": 0.0},\n'
        '        {"parametro": "cambagem", "tendencia": "positiva|negativa|indefinida", "confianca": 0.0},\n'
        '        {"parametro": "cáster", "tendencia": "avançado|recuado|indefinido", "confianca": 0.0}\n'
        '      ],\n'
        '      "pressao_pneus": {\n'
        '        "motorista": "provável baixa|alta|ok|indefinida (justificativa curta)",\n'
        '        "oposto": "provável baixa|alta|ok|indefinida (justificativa curta)"\n'
        '      },\n'
        '      "balanceamento_sugerido": "sim|não|indefinido (com justificativa)",\n'
        '      "achados_chave": [],\n'
        '      "severidade_eixo": 0,\n'
        '      "prioridade_manutencao": "baixa|média|alta",\n'
        '      "rodizio_recomendado": "plano detalhado com mapa de posições, virar na roda/trocar de lado e observação do caimento da via"\n'
        '    }\n'
        '  ],\n'
        '  "recomendacoes_finais": [],\n'
        '  "resumo_geral": "",\n'
        '  "whatsapp_resumo": "até 450 caracteres"\n'
        "}\n"
    )

    header = (
        f"{especialista}\n\n{aviso}\n\n"
        "Contexto do veículo (se fornecido):\n"
        f"- Nome: {meta.get('nome')} | Empresa: {meta.get('empresa')} | Tel: {meta.get('telefone')} | E-mail: {meta.get('email')} | Placa: {meta.get('placa')}\n"
        f"- Dados da placa/API: {json.dumps(meta.get('placa_info') or {}, ensure_ascii=False)}\n"
        f"- Observação do motorista: {obs}\n\n"
        f"{orientacao_foto}\n\n{heuristicas}\n\n{rodizio}\n\n{tarefas}\n\n{formato}"
    )

    return [
        {"type": "text", "text": header},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

def _build_single_axis_message(data_url: str, meta: dict, obs: str, axis_title: str) -> list:
    """
    Prompt alternativo para fallback: imagem contendo APENAS UMA colagem (um eixo).
    Pede para retornar exatamente 1 item no array 'eixos' correspondente a esse título.
    """
    header = (
        "Imagem com UMA colagem 2×2 referente a UM eixo do veículo.\n"
        f"Título do eixo: {axis_title}.\n"
        "CIMA = Frente (câmera paralela à banda); BAIXO = ~45°; ESQ = Motorista; DIR = Oposto. "
        "Entregue JSON com EXATAMENTE 1 item em 'eixos' (esse eixo), incluindo diagnóstico global, "
        "necessidade de alinhamento com parâmetros suspeitos (e confiança 0–1), pressão por lado com justificativa, "
        "balanceamento quando aplicável e RODÍZIO DETALHADO (mapa de posições melhor→pior, quando virar na roda, trocar de lado ou ambos, "
        "considerando caimento da via no Brasil)."
        "\nFormato de resposta (JSON válido):\n"
        "{\n"
        f'  "placa": "{meta.get("placa")}",\n'
        '  "configuracao_detectada": "ou indefinida",\n'
        '  "qualidade_imagens": {"score": 0.0, "problemas": [], "faltantes": []},\n'
        '  "eixos": [ { "titulo": "' + axis_title + '", "tipo": "Dianteiro|Traseiro", '
        '"diagnostico_global": "", "necessita_alinhamento": true, '
        '"parametros_suspeitos":[{"parametro":"convergência","tendencia":"aberta|fechada|indefinida","confianca":0.0}, '
        '{"parametro":"cambagem","tendencia":"positiva|negativa|indefinida","confianca":0.0}, '
        '{"parametro":"cáster","tendencia":"avançado|recuado|indefinido","confianca":0.0}], '
        '"pressao_pneus":{"motorista":"...","oposto":"..."}, '
        '"balanceamento_sugerido":"...", "achados_chave":[], "severidade_eixo":0, '
        '"prioridade_manutencao":"baixa|média|alta", '
        '"rodizio_recomendado":"plano detalhado para este eixo" } ],\n'
        '  "recomendacoes_finais": [], "resumo_geral": "", "whatsapp_resumo": ""\n'
        "}\n"
    )
    return [
        {"type": "text", "text": header},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

# =========================
# OpenAI callers
# =========================
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
                {
                    "role": "system",
                    "content": (
                        "Você é um especialista brasileiro em pneus de caminhões com prática em diagnóstico por desgaste, "
                        "geometria (convergência, cambagem, cáster), pressão, balanceamento e rodízio. "
                        "Escreva em PT-BR claro para leigos; não invente medidas; se faltar evidência, diga o que faltou e dê hipótese com confiança 0–1."
                    )
                },
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

def _call_openai_single_axis(collage: Image.Image, meta: dict, obs: str, model_name: str, axis_title: str) -> dict:
    """Fallback: analisa UMA colagem (um eixo) e retorna JSON com 1 item em 'eixos'."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente em Secrets/variável de ambiente."}
    client = OpenAI(api_key=api_key)

    # Data URL a partir da colagem unitária
    buf = io.BytesIO()
    collage.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64}"

    content = _build_single_axis_message(data_url, meta, obs, axis_title)
    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um especialista brasileiro em pneus de caminhões com prática em diagnóstico por desgaste, "
                        "geometria (convergência, cambagem, cáster), pressão, balanceamento e rodízio. "
                        "Escreva em PT-BR claro para leigos; não invente medidas; se faltar evidência, diga o que faltou e dê hipótese com confiança 0–1."
                    )
                },
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
            return {"erro": "Modelo (fallback) não retornou JSON válido", "raw": text}
    except Exception as e:
        return {"erro": f"Falha na API (fallback): {e}"}

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
        # Guardamos para exportação posterior e fallback
        st.session_state["ultima_colagem"] = colagem_final
        st.session_state["collages"] = collages
        st.session_state["titles"] = titles

    data_url = _img_to_dataurl(colagem_final)
    meta = {
        "placa": placa, "nome": nome, "empresa": empresa,
        "telefone": telefone, "email": email, "placa_info": placa_info
    }
    obs = (observacao or "")[:MAX_OBS]

    with st.spinner("Analisando com IA…"):
        laudo = _call_openai_single_image(data_url, meta, obs, modelo, titles)

    # ===== Fallback robusto por eixo (se vier menos eixos do que o esperado) =====
    expected_n = len(titles)
    got_n = len(laudo.get("eixos", [])) if isinstance(laudo, dict) else 0

    if "erro" in laudo or got_n != expected_n:
        if "erro" in laudo and DEBUG:
            st.warning("Tentando fallback por eixo devido a erro no JSON único.")
        elif got_n != expected_n and DEBUG:
            st.warning(f"JSON veio com {got_n} eixos; esperado {expected_n}. Ativando fallback por eixo.")

        # Agrega resultados por colagem
        agreg = {
            "placa": meta.get("placa"),
            "configuracao_detectada": laudo.get("configuracao_detectada") if isinstance(laudo, dict) else None,
            "qualidade_imagens": laudo.get("qualidade_imagens") if isinstance(laudo, dict) else {"score": None,"problemas":[],"faltantes":[]},
            "eixos": [],
            "recomendacoes_finais": [],
            "resumo_geral": "",
            "whatsapp_resumo": ""
        }

        eixos_ok = []
        for cimg, atitle in zip(st.session_state["collages"], st.session_state["titles"]):
            sub = _call_openai_single_axis(cimg, meta, obs, modelo, atitle)
            if isinstance(sub, dict) and isinstance(sub.get("eixos"), list) and sub["eixos"]:
                eixos_ok.extend(sub["eixos"])
                # Tenta pegar config/qualidade mais informativas
                if not agreg.get("configuracao_detectada") and sub.get("configuracao_detectada"):
                    agreg["configuracao_detectada"] = sub.get("configuracao_detectada")
                if sub.get("qualidade_imagens"):
                    q = agreg.get("qualidade_imagens") or {}
                    q2 = sub.get("qualidade_imagens") or {}
                    # Estratégia simples de merge textual
                    probs = list(set((q.get("problemas") or []) + (q2.get("problemas") or [])))
                    falt = list(set((q.get("faltantes") or []) + (q2.get("faltantes") or [])))
                    agreg["qualidade_imagens"] = {"score": q.get("score") or q2.get("score"), "problemas": probs, "faltantes": falt}
                # Recomendações finais (concat)
                if sub.get("recomendacoes_finais"):
                    agreg["recomendacoes_finais"].extend([r for r in sub["recomendacoes_finais"] if isinstance(r, str)])

                # Resumos (mantém o primeiro que for preenchido)
                if not agreg.get("resumo_geral") and sub.get("resumo_geral"):
                    agreg["resumo_geral"] = sub.get("resumo_geral")
                if not agreg.get("whatsapp_resumo") and sub.get("whatsapp_resumo"):
                    agreg["whatsapp_resumo"] = sub.get("whatsapp_resumo")

        agreg["eixos"] = eixos_ok
        laudo = agreg

    if "erro" in laudo:
        st.error(laudo["erro"])
        if DEBUG and laudo.get("raw"):
            with st.expander("Resposta bruta do modelo"):
                st.code(laudo["raw"])
        return

    # ---- Apresentação do laudo ----
    st.success("Laudo recebido.")

    st.markdown("## 🧾 Resumo")
    if laudo.get("resumo_geral"):
        st.write(laudo["resumo_geral"])

    # Configuração detectada (se vier)
    cfg = laudo.get("configuracao_detectada")
    if isinstance(cfg, str) and cfg.strip():
        st.caption(f"Configuração detectada: {cfg}")

    q = laudo.get("qualidade_imagens") or {}
    if q:
        score = q.get("score")
        probs = ", ".join(q.get("problemas") or [])
        falt = ", ".join(q.get("faltantes") or [])
        st.caption(
            f"Qualidade estimada: {score if score is not None else '-'} | "
            f"Problemas: {probs or '-'} | Faltantes: {falt or '-'}"
        )

    # Render por eixo, agora com maior chance de vir completo e com rodízio detalhado
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
                # Agora deve vir detalhado (mapa de posições, virar na roda, troca de lado, caimento da via)
                st.caption(f"Rodízio recomendado: {rod}")

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
    # Limite exigido: 450 caracteres
    resumo_wpp = (resumo_wpp[:450] + "…") if len(resumo_wpp) > 450 else resumo_wpp
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
