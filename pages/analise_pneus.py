# pages/analise_pneus.py
import os
import re
import json
import base64
from typing import Optional

import streamlit as st
from openai import OpenAI
import utils  # usa sua consultar_placa_comercial()


def _file_to_dataurl(file) -> Optional[str]:
    """Lê o arquivo enviado no Streamlit e retorna um data URL (base64)."""
    if not file:
        return None
    data = file.read()
    if not data:
        return None
    # permite re-leitura em caso de debug/erros
    try:
        file.seek(0)
    except Exception:
        pass

    name = (getattr(file, "name", "") or "").lower()
    mime = "image/jpeg"
    if name.endswith(".png"):
        mime = "image/png"
    elif name.endswith(".webp"):
        mime = "image/webp"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _montar_prompt_chat(placa, nome, telefone, email, placa_info, eixos):
    """
    Monta mensagens para chat.completions (multimodal).
    Inclui um aviso explícito de que a análise é automática e sujeita a erros.
    """
    system = f"""
Você é o **AVP** — Analisador Virtual de Pneus: um sistema AUTOMÁTICO de visão computacional
que gera hipóteses sobre desgaste/irregularidades de pneus a partir de fotos.
⚠️ IMPORTANTE: este laudo é auxiliar e pode conter erros. Não use como única base para decisões.
Recomenda-se inspeção técnica presencial por profissional qualificado.

Contexto do veículo:
- Placa: {placa}
- Motorista: {nome} (tel: {telefone}, email: {email})
- Dados da placa/API: {json.dumps(placa_info or {}, ensure_ascii=False)}

Tarefa:
Analise cuidadosamente cada conjunto de imagens por eixo. Investigue:
- desalinhamento, desbalanceamento, dente de serra, cunha, conicidade,
  desgaste lateral (interno/externo) e pressão incorreta.

Formato de RESPOSTA (somente JSON **válido**):
{{
  "placa": "string",
  "resumo_geral": "string curta e objetiva",
  "eixos": [
    {{
      "eixo": "ex.: Dianteiro, Traseiro 1, Traseiro 2",
      "achados": ["lista de achados objetivos"],
      "recomenda_alinhamento": true/false,
      "recomenda_balanceamento": true/false,
      "confianca": 0.0-1.0,
      "observacoes": "dicas sobre qualidade das fotos e observações adicionais"
    }}
  ],
  "recomendacoes_finais": [
    "lista de recomendações práticas de manutenção/segurança"
  ],
  "aviso": "Laudo automático do AVP: utilize como apoio, sujeito a erros."
}}

Se as fotos estiverem ruins, seja específico sobre o que falta (ângulo, foco, luz, distância).
Use linguagem simples e objetiva nos textos.
""".strip()

    # Conteúdo do usuário em formato multimodal
    user_parts = [{"type": "text", "text": "Analise as imagens e siga as instruções acima. Gere apenas JSON."}]
    for e in eixos:
        user_parts.append(
            {"type": "text", "text": f"Eixo: {e['label']} — ordem: Esquerda(1,2), Direita(1,2)."}
        )
        for label, file in [
            ("Esquerda 1", e["esq1"]),
            ("Esquerda 2", e["esq2"]),
            ("Direita 1", e["dir1"]),
            ("Direita 2", e["dir2"]),
        ]:
            if file:
                data_url = _file_to_dataurl(file)
                if data_url:
                    user_parts.append({"type": "text", "text": f"Foto {label} ({e['label']})"})
                    user_parts.append({"type": "image_url", "image_url": {"url": data_url}})

    return system, user_parts


def _analisar(placa, nome, telefone, email, placa_info, eixos) -> dict:
    """Chama o modelo via chat.completions e retorna um dicionário JSON."""
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"erro": "OPENAI_API_KEY ausente em Secrets/variável de ambiente."}

    client = OpenAI(api_key=api_key)
    system, user_parts = _montar_prompt_chat(placa, nome, telefone, email, placa_info, eixos)

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_parts},
            ],
            temperature=0,  # ajuda a manter JSON estável
        )
        text = resp.choices[0].message.content or ""

        # 1) tenta decodificar diretamente
        try:
            return json.loads(text)
        except Exception:
            # 2) tenta extrair o primeiro bloco { ... }
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            return {"erro": "Modelo não retornou JSON válido", "raw": text}
    except Exception as e:
        return {"erro": f"Falha na API: {e}"}


def app():
    st.title("🛞 Análise de Pneus por Foto")
    st.caption("Envie fotos por eixo (esquerda/direita). O laudo sai automático — uso auxiliar, sujeito a erros.")
    if not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")):
        st.warning("Defina OPENAI_API_KEY nos *Secrets* do Streamlit Cloud ou como variável de ambiente local.")

    # --- Identificação / Placa ---
    with st.form("form_ident"):
        c1, c2 = st.columns(2)
        with c1:
            nome = st.text_input("Nome do motorista")
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

    # --- Eixos dinâmicos ---
    if "eixos" not in st.session_state:
        st.session_state.eixos = []  # {"label","esq1","esq2","dir1","dir2"}

    colA, colB, colC = st.columns(3)
    with colA:
        if st.button("➕ Adicionar Dianteiro"):
            st.session_state.eixos.append(
                {"label": "Dianteiro", "esq1": None, "esq2": None, "dir1": None, "dir2": None}
            )
    with colB:
        if st.button("➕ Adicionar Traseiro"):
            n = sum(1 for e in st.session_state.eixos if e["label"].startswith("Traseiro"))
            st.session_state.eixos.append(
                {
                    "label": f"Traseiro {n+1}" if n else "Traseiro",
                    "esq1": None,
                    "esq2": None,
                    "dir1": None,
                    "dir2": None,
                }
            )
    with colC:
        if st.session_state.eixos and st.button("🗑️ Remover último eixo"):
            st.session_state.eixos.pop()

    if not st.session_state.eixos:
        st.info("Adicione pelo menos um eixo.")
    else:
        for i, eixo in enumerate(st.session_state.eixos):
            with st.container(border=True):
                st.subheader(f"Eixo {i+1}: {eixo['label']}")
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Esquerda**")
                    eixo["esq1"] = st.file_uploader(
                        f"Foto Esquerda 1 ({eixo['label']})", type=["jpg", "jpeg", "png", "webp"], key=f"esq1_{i}"
                    )
                    eixo["esq2"] = st.file_uploader(
                        f"Foto Esquerda 2 ({eixo['label']})", type=["jpg", "jpeg", "png", "webp"], key=f"esq2_{i}"
                    )
                with c2:
                    st.markdown("**Direita**")
                    eixo["dir1"] = st.file_uploader(
                        f"Foto Direita 1 ({eixo['label']})", type=["jpg", "jpeg", "png", "webp"], key=f"dir1_{i}"
                    )
                    eixo["dir2"] = st.file_uploader(
                        f"Foto Direita 2 ({eixo['label']})", type=["jpg", "jpeg", "png", "webp"], key=f"dir2_{i}"
                    )

    st.markdown("---")

    enviar = st.button(
        "🚀 Enviar para análise",
        disabled=not (st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")) or not st.session_state.eixos,
    )
    if enviar:
        with st.spinner("Analisando imagens..."):
            laudo = _analisar(placa, nome, telefone, email, placa_info, st.session_state.eixos)

        if "erro" in laudo:
            st.error(laudo["erro"])
        else:
            st.success("Laudo recebido.")
            st.json(laudo)
            st.markdown("### Resultado resumido")
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
                st.markdown("### Recomendações finais")
                st.write("• " + "\n• ".join(laudo["recomendacoes_finais"]))
