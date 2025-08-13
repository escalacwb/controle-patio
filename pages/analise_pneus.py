# pages/analise_pneus.py
import base64, json
from typing import Optional
import streamlit as st
from openai import OpenAI
import utils  # usa sua consultar_placa_comercial()

def _file_to_dataurl(file) -> Optional[str]:
    if not file: return None
    data = file.read()
    if not data: return None
    name = (getattr(file, "name", "") or "").lower()
    mime = "image/jpeg"
    if name.endswith(".png"): mime = "image/png"
    elif name.endswith(".webp"): mime = "image/webp"
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def _montar_prompt(placa, nome, telefone, email, placa_info, eixos):
    instructions = f"""
Você é especialista em pneus de veículos pesados. Avalie as fotos enviadas.
Contexto:
- Placa: {placa}
- Motorista: {nome} (tel: {telefone}, email: {email})
- Dados da placa/API: {json.dumps(placa_info or {}, ensure_ascii=False)}

Para cada eixo, identifique: desalinhamento, desbalanceamento, dente de serra, cunha, conicidade,
desgaste lateral (interno/externo) e pressão incorreta.

Responda APENAS em JSON:
{{
  "placa": "...",
  "resumo_geral": "...",
  "eixos": [
    {{
      "eixo": "...",
      "achados": ["..."],
      "recomenda_alinhamento": true/false,
      "recomenda_balanceamento": true/false,
      "confianca": 0.0-1.0,
      "observacoes": "..."
    }}
  ],
  "recomendacoes_finais": ["..."]
}}
Se as fotos estiverem ruins, diga exatamente o que falta (ângulo, foco, luz, distância).
"""
    content = [{"type":"text","text":"Analise as imagens e siga as instruções."}]
    for e in eixos:
        content.append({"type":"text","text":f"Eixo: {e['label']} — ordem: Esquerda(1,2), Direita(1,2)."})
        for label, file in [("Esquerda 1", e["esq1"]), ("Esquerda 2", e["esq2"]),
                            ("Direita 1", e["dir1"]), ("Direita 2", e["dir2"])]:
            if file:
                data_url = _file_to_dataurl(file)
                if data_url:
                    content.append({"type":"text","text":f"Foto {label} ({e['label']})"})
                    content.append({"type":"input_image","image_url": data_url})
    return instructions, content

def _analisar(placa, nome, telefone, email, placa_info, eixos) -> dict:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        return {"erro":"OPENAI_API_KEY ausente em .streamlit/secrets.toml"}
    client = OpenAI(api_key=api_key)
    instructions, content = _montar_prompt(placa, nome, telefone, email, placa_info, eixos)
    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            instructions=instructions,
            input=[{"role":"user","content":content}],
            response_format={"type":"json_object"}
        )
        out = getattr(resp, "output_text", None)
        return json.loads(out) if out else {"erro":"sem output"}
    except Exception as e:
        return {"erro": f"Falha na API: {e}"}

def app():
    st.title("🛞 Análise de Pneus por Foto")
    st.caption("Envie fotos por eixo (esquerda/direita). O laudo sai automático.")
    if not st.secrets.get("OPENAI_API_KEY"):
        st.warning("Defina OPENAI_API_KEY em .streamlit/secrets.toml (ou nos Secrets do Streamlit Cloud).")

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
            st.session_state.eixos.append({"label":"Dianteiro","esq1":None,"esq2":None,"dir1":None,"dir2":None})
    with colB:
        if st.button("➕ Adicionar Traseiro"):
            n = sum(1 for e in st.session_state.eixos if e["label"].startswith("Traseiro"))
            st.session_state.eixos.append({
                "label": f"Traseiro {n+1}" if n else "Traseiro",
                "esq1":None,"esq2":None,"dir1":None,"dir2":None
            })
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
                    eixo["esq1"] = st.file_uploader(f"Foto Esquerda 1 ({eixo['label']})",
                                                    type=["jpg","jpeg","png","webp"], key=f"esq1_{i}")
                    eixo["esq2"] = st.file_uploader(f"Foto Esquerda 2 ({eixo['label']})",
                                                    type=["jpg","jpeg","png","webp"], key=f"esq2_{i}")
                with c2:
                    st.markdown("**Direita**")
                    eixo["dir1"] = st.file_uploader(f"Foto Direita 1 ({eixo['label']})",
                                                    type=["jpg","jpeg","png","webp"], key=f"dir1_{i}")
                    eixo["dir2"] = st.file_uploader(f"Foto Direita 2 ({eixo['label']})",
                                                    type=["jpg","jpeg","png","webp"], key=f"dir2_{i}")

    st.markdown("---")

    enviar = st.button("🚀 Enviar para análise", disabled=not st.secrets.get("OPENAI_API_KEY") or not st.session_state.eixos)
    if enviar:
        with st.spinner("Analisando imagens..."):
            laudo = _analisar(placa, nome, telefone, email, placa_info, st.session_state.eixos)
        if "erro" in laudo:
            st.error(laudo["erro"])
        else:
            st.success("Laudo recebido.")
            st.json(laudo)
            st.markdown("### Resultado resumido")
            if laudo.get("resumo_geral"): st.write(laudo["resumo_geral"])
            for ex in laudo.get("eixos", []):
                with st.container(border=True):
                    st.markdown(f"**{ex.get('eixo','Eixo')}**")
                    ach = ex.get("achados") or []
                    if ach: st.write("• " + "\n• ".join(ach))
                    st.write(f"**Alinhamento?** {ex.get('recomenda_alinhamento')}")
                    st.write(f"**Balanceamento?** {ex.get('recomenda_balanceamento')}")
                    if ex.get("observacoes"): st.caption(ex["observacoes"])
            if laudo.get("recomendacoes_finais"):
                st.markdown("### Recomendações finais")
                st.write("• " + "\n• ".join(laudo["recomendacoes_finais"]))
