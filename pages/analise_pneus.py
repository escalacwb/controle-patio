# pages/analise_pneus.py
import os
import io
import json
import base64
from typing import Optional, List, Tuple

import streamlit as st
from PIL import Image, ImageOps
from openai import OpenAI
import utils  # manter: usa consultar_placa_comercial()

# ----------------------------
# Configurações
# ----------------------------
WHATSAPP_NUMERO = "5567984173800"  # telefone da empresa (somente dígitos, com DDI)
MAX_OBS = 150                      # limite de caracteres para observação
MAX_SIDE = 1024                    # lado máximo de imagem para economizar tokens
JPEG_QUALITY = 85                  # compressão JPEG

# ----------------------------
# Utilidades de imagem
# ----------------------------
def _open_and_prepare(file) -> Optional[Image.Image]:
    """Abre imagem do upload, corrige orientação EXIF, converte para RGB, redimensiona."""
    if not file:
        return None
    try:
        img = Image.open(file)
    except Exception:
        return None
    try:
        img = ImageOps.exif_transpose(img)  # corrige rotação
    except Exception:
        pass
    if img.mode != "RGB":
        img = img.convert("RGB")
    # Redimensiona mantendo proporção (maior lado = MAX_SIDE)
    w, h = img.size
    if max(w, h) > MAX_SIDE:
        if w >= h:
            nh = int(h * (MAX_SIDE / w))
            img = img.resize((MAX_SIDE, nh), Image.LANCZOS)
        else:
            nw = int(w * (MAX_SIDE / h))
            img = img.resize((nw, MAX_SIDE), Image.LANCZOS)
    return img

def _grid_2x2(left_top: Image.Image, left_bottom: Image.Image,
              right_top: Image.Image, right_bottom: Image.Image) -> Image.Image:
    """Monta uma colagem 2x2: esquerda (cima/baixo), direita (cima/baixo)."""
    # Normaliza larguras por coluna e alturas por linha
    lt, lb, rt, rb = left_top, left_bottom, right_top, right_bottom
    # Ajusta largura das colunas pela menor largura de cada coluna para alinhamento visual
    left_w = min(lt.width if lt else MAX_SIDE, lb.width if lb else MAX_SIDE)
    right_w = min(rt.width if rt else MAX_SIDE, rb.width if rb else MAX_SIDE)

    def _fit_w(img, target_w):
        if not img:
            return Image.new("RGB", (target_w, target_w), "white")
        if img.width == target_w:
            return img
        nh = int(img.height * (target_w / img.width))
        return img.resize((target_w, nh), Image.LANCZOS)

    lt = _fit_w(lt, left_w) if lt else Image.new("RGB", (left_w, left_w), "white")
    lb = _fit_w(lb, left_w) if lb else Image.new("RGB", (left_w, left_w), "white")
    rt = _fit_w(rt, right_w) if rt else Image.new("RGB", (right_w, right_w), "white")
    rb = _fit_w(rb, right_w) if rb else Image.new("RGB", (right_w, right_w), "white")

    # Alturas por linha
    top_h = max(lt.height, rt.height)
    bot_h = max(lb.height, rb.height)

    # Se alguma imagem for menor, "ancora" no topo e preenche com branco embaixo
    def _pad_h(img, target_h):
        if img.height == target_h:
            return img
        canvas = Image.new("RGB", (img.width, target_h), "white")
        canvas.paste(img, (0, 0))
        return canvas

    lt = _pad_h(lt, top_h)
    rt = _pad_h(rt, top_h)
    lb = _pad_h(lb, bot_h)
    rb = _pad_h(rb, bot_h)

    total_w = left_w + right_w
    total_h = top_h + bot_h
    out = Image.new("RGB", (total_w, total_h), "white")
    out.paste(lt, (0, 0))
    out.paste(rt, (left_w, 0))
    out.paste(lb, (0, top_h))
    out.paste(rb, (left_w, top_h))
    return out

def _stack_vertical(top_img: Image.Image, bottom_img: Image.Image) -> Image.Image:
    """Empilha duas imagens verticalmente centralizando pela largura."""
    w = max(top_img.width, bottom_img.width)
    def _center_w(img, target_w):
        if img.width == target_w:
            return img
        canvas = Image.new("RGB", (target_w, img.height), "white")
        x = (target_w - img.width) // 2
        canvas.paste(img, (x, 0))
        return canvas
    top = _center_w(top_img, w)
    bottom = _center_w(bottom_img, w)
    out = Image.new("RGB", (w, top.height + bottom.height), "white")
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height))
    return out

def _img_to_dataurl(img: Image.Image) -> str:
    """Converte PIL Image -> data URL JPEG."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"

# ----------------------------
# Prompt / OpenAI
# ----------------------------
def _build_multimodal_message(data_url: str, meta: dict, obs: str) -> list:
    """
    Monta o conteúdo multimodal a ser enviado.
    Envia UMA imagem (colagem com todos os eixos) + texto com instruções claras.
    """
    aviso = (
        "Você é o AVP — Analisador Virtual de Pneus, um sistema AUTOMÁTICO de visão computacional. "
        "⚠️ Laudo auxiliar, sujeito a erros. Não usar como única base de decisão. "
        "Recomenda-se inspeção presencial por profissional qualificado."
    )

    # Instruções sobre layout:
    layout = (
        "A imagem enviada contém DUAS colagens empilhadas:\n"
        "1) TOPO = EIXO DIANTEIRO (2x2):\n"
        "   - Coluna ESQUERDA = LADO MOTORISTA (cima: foto de TRÁS→FRENTE; baixo: foto de FRENTE→TRÁS)\n"
        "   - Coluna DIREITA  = LADO OPOSTO (cima: TRÁS→FRENTE; baixo: FRENTE→TRÁS)\n"
        "2) BASE = EIXO TRASEIRO (2x2):\n"
        "   - Coluna ESQUERDA = LADO MOTORISTA (cima: FRENTE do conjunto geminado; baixo: TRÁS do conjunto geminado)\n"
        "   - Coluna DIREITA  = LADO OPOSTO (cima: FRENTE; baixo: TRÁS)\n"
    )

    formato = (
        "Responda SOMENTE em JSON válido:\n"
        "{\n"
        '  "placa": "...",\n'
        '  "resumo_geral": "...",\n'
        '  "eixos": [\n'
        '    {\n'
        '      "eixo": "Dianteiro",\n'
        '      "achados": ["..."],\n'
        '      "recomenda_alinhamento": true/false,\n'
        '      "recomenda_balanceamento": true/false,\n'
        '      "confianca": 0.0-1.0,\n'
        '      "observacoes": "..." \n'
        '    },\n'
        '    {\n'
        '      "eixo": "Traseiro",\n'
        '      "achados": ["..."],\n'
        '      "recomenda_alinhamento": true/false,\n'
        '      "recomenda_balanceamento": true/false,\n'
        '      "confianca": 0.0-1.0,\n'
        '      "observacoes": "..." \n'
        '    }\n'
        '  ],\n'
        '  "recomendacoes_finais": ["..."],\n'
        '  "aviso": "Laudo automático do AVP: utilize como apoio, sujeito a erros."\n'
        "}\n"
    )

    header = (
        f"{aviso}\n\n"
        f"Contexto:\n"
        f"- Placa: {meta.get('placa')}\n"
        f"- Motorista/gestor: {meta.get('nome')} (tel: {meta.get('telefone')}, email: {meta.get('email')})\n"
        f"- Empresa: {meta.get('empresa')}\n"
        f"- Dados da placa/API: {json.dumps(meta.get('placa_info') or {}, ensure_ascii=False)}\n"
        f"- Observação do motorista: {obs}\n\n"
        f"{layout}\n"
        "Tarefa: verificar desalinhamento, desbalanceamento, dente de serra, cunha, conicidade, desgaste lateral (interno/externo) e pressão incorreta.\n\n"
        f"{formato}"
    )

    return [
        {"type": "text", "text": header},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

def _call_openai_single_image(data_url: str, meta: dict, obs: str, model_name: str) -> dict:
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente em Secrets/variável de ambiente."}

    client = OpenAI(api_key=api_key)
    content = _build_multimodal_message(data_url, meta, obs)

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
            # fallback: tenta achar primeiro bloco JSON
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

# ----------------------------
# UI principal (app)
# ----------------------------
def app():
    st.title("🛞 Análise de Pneus por Foto — AVP")
    st.caption("Laudo automático de apoio — sujeito a erros. Recomenda-se inspeção presencial.")

    # Modelo
    col_m1, col_m2 = st.columns([1, 3])
    with col_m1:
        modo_detalhado = st.toggle("Análise detalhada (gpt-4.0)", value=False)
    modelo = "gpt-4o" if modo_detalhado else "gpt-4o-mini"

    # Form de identificação
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

    # Observação curta
    observacao = st.text_area("Observação do motorista (máx. 150 caracteres)", max_chars=MAX_OBS, placeholder="Ex.: puxa para a direita, vibra acima de 80 km/h…")

    st.markdown("### 📸 Eixo Dianteiro (4 fotos)")
    st.caption("LADO MOTORISTA: (1) TRÁS→FRENTE, (2) FRENTE→TRÁS — LADO OPOSTO: (1) TRÁS→FRENTE, (2) FRENTE→TRÁS")
    cdm, cdo = st.columns(2)
    with cdm:
        d_m_1 = st.file_uploader("Motorista — Foto 1 (trás→frente)", type=["jpg","jpeg","png"], key="dm1")
        d_m_2 = st.file_uploader("Motorista — Foto 2 (frente→trás)", type=["jpg","jpeg","png"], key="dm2")
    with cdo:
        d_o_1 = st.file_uploader("Oposto — Foto 1 (trás→frente)", type=["jpg","jpeg","png"], key="do1")
        d_o_2 = st.file_uploader("Oposto — Foto 2 (frente→trás)", type=["jpg","jpeg","png"], key="do2")

    st.markdown("### 📸 Eixo Traseiro (4 fotos — conjunto geminado)")
    st.caption("LADO MOTORISTA: (1) FRENTE, (2) TRÁS — LADO OPOSTO: (1) FRENTE, (2) TRÁS")
    ctm, cto = st.columns(2)
    with ctm:
        t_m_1 = st.file_uploader("Motorista — Frente (conjunto)", type=["jpg","jpeg","png"], key="tm1")
        t_m_2 = st.file_uploader("Motorista — Trás (conjunto)", type=["jpg","jpeg","png"], key="tm2")
    with cto:
        t_o_1 = st.file_uploader("Oposto — Frente (conjunto)", type=["jpg","jpeg","png"], key="to1")
        t_o_2 = st.file_uploader("Oposto — Trás (conjunto)", type=["jpg","jpeg","png"], key="to2")

    st.markdown("---")
    pronto = st.button("🚀 Enviar para análise")

    if pronto:
        # Checagem de chave
        if not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
            st.error("Defina OPENAI_API_KEY em Secrets/variável de ambiente.")
            st.stop()

        # Verifica fotos
        faltando = [x for x in [d_m_1, d_m_2, d_o_1, d_o_2, t_m_1, t_m_2, t_o_1, t_o_2] if x is None]
        if faltando:
            st.error("Envie todas as 8 fotos (4 dianteiro + 4 traseiro).")
            st.stop()

        # Pré-processa
        with st.spinner("Preparando imagens…"):
            dm1 = _open_and_prepare(d_m_1)
            dm2 = _open_and_prepare(d_m_2)
            do1 = _open_and_prepare(d_o_1)
            do2 = _open_and_prepare(d_o_2)

            tm1 = _open_and_prepare(t_m_1)
            tm2 = _open_and_prepare(t_m_2)
            to1 = _open_and_prepare(t_o_1)
            to2 = _open_and_prepare(t_o_2)

            # Colagem 2x2 do eixo dianteiro:
            # Coluna esquerda = Motorista (cima: trás→frente / baixo: frente→trás)
            # Coluna direita  = Oposto    (cima: trás→frente / baixo: frente→trás)
            colagem_dianteiro = _grid_2x2(
                left_top=dm1, left_bottom=dm2,
                right_top=do1, right_bottom=do2
            )

            # Colagem 2x2 do eixo traseiro:
            # Coluna esquerda = Motorista (cima: frente / baixo: trás)
            # Coluna direita  = Oposto    (cima: frente / baixo: trás)
            colagem_traseiro = _grid_2x2(
                left_top=tm1, left_bottom=tm2,
                right_top=to1, right_bottom=to2
            )

            # Colagem final (dianteiro em cima, traseiro embaixo)
            colagem_final = _stack_vertical(colagem_dianteiro, colagem_traseiro)

            st.image(colagem_dianteiro, caption="Pré-visualização — Eixo Dianteiro (2x2)", use_column_width=True)
            st.image(colagem_traseiro, caption="Pré-visualização — Eixo Traseiro (2x2)", use_column_width=True)

        # Monta data URL
        data_url = _img_to_dataurl(colagem_final)

        # Meta
        meta = {
            "placa": placa,
            "nome": nome,
            "empresa": empresa,
            "telefone": telefone,
            "email": email,
            "placa_info": placa_info
        }

        # Chama OpenAI
        with st.spinner("Analisando com IA…"):
            laudo = _call_openai_single_image(data_url, meta, observacao or "", modelo)

        if "erro" in laudo:
            st.error(laudo["erro"])
            if laudo.get("raw"):
                with st.expander("Resposta bruta do modelo"):
                    st.code(laudo["raw"])
            st.stop()

        # Exibição do laudo
        st.success("Laudo recebido.")
        st.json(laudo)

        # Resumo amigável
        st.markdown("### 🧾 Resumo")
        if laudo.get("resumo_geral"):
            st.write(laudo["resumo_geral"])
        for ex in laudo.get("eixos", []):
            with st.container(border=True):
                st.markdown(f"**{ex.get('eixo','Eixo')}**")
                ach = ex.get("achados") or []
                if ach:
                    st.write("• " + "\n• ".join(ach))
                st.write(f"**Alinhamento?** {ex.get('recomenda_alinhamento')}")
                st.write(f"**Balanceamento?** {ex.get('recomenda_balanceamento')}")
                if ex.get("observacoes"):
                    st.caption(ex["observacoes"])
        if laudo.get("recomendacoes_finais"):
            st.markdown("### 🔧 Recomendações finais")
            st.write("• " + "\n• ".join(laudo["recomendacoes_finais"]))

        # Link do WhatsApp (mensagem do cliente para a empresa)
        # Monta um resumo curto para WhatsApp (limita tamanho)
        resumo_wpp = laudo.get("resumo_geral") or ""
        resumo_wpp = (resumo_wpp[:600] + "…") if len(resumo_wpp) > 600 else resumo_wpp
        msg = (
            "Olá, fiz o teste de análise dos pneus e recebi o seguinte resultado:\n\n"
            f"{resumo_wpp}\n\n"
            f"Caminhão/Placa: {placa}\n"
            f"Empresa: {empresa}\n"
            f"Motorista/Gestor: {nome}\n"
            f"Telefone: {telefone}\n"
            f"E-mail: {email}\n"
            f"Observação: {observacao or '-'}\n\n"
            "Gostaria de conversar sobre a manutenção do veículo."
        )
        from urllib.parse import quote
        link_wpp = f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(msg)}"
        st.markdown(f"[📲 Enviar resultado via WhatsApp]({link_wpp})", unsafe_allow_html=True)
