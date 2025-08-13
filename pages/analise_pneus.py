import base64
import io
from PIL import Image
from openai import OpenAI

client = OpenAI(api_key="SUA_CHAVE_OPENAI")

def redimensionar(img, largura_max=1024):
    largura, altura = img.size
    if largura > largura_max:
        proporcao = largura_max / largura
        nova_altura = int(altura * proporcao)
        img = img.resize((largura_max, nova_altura), Image.LANCZOS)
    return img

def juntar_fotos(fotos_lado_motorista, fotos_lado_passageiro):
    # Une fotos lado motorista (esq) e lado passageiro (dir) lado a lado
    altura_total = sum(f.size[1] for f in fotos_lado_motorista)
    largura_total = fotos_lado_motorista[0].size[0] + fotos_lado_passageiro[0].size[0]
    resultado = Image.new("RGB", (largura_total, altura_total))
    
    y_offset = 0
    for idx in range(len(fotos_lado_motorista)):
        resultado.paste(fotos_lado_motorista[idx], (0, y_offset))
        resultado.paste(fotos_lado_passageiro[idx], (fotos_lado_motorista[idx].size[0], y_offset))
        y_offset += fotos_lado_motorista[idx].size[1]
    return resultado

def preparar_imagem_eixo(fotos_motorista, fotos_passageiro):
    # Redimensiona
    fotos_motorista = [redimensionar(Image.open(f)) for f in fotos_motorista]
    fotos_passageiro = [redimensionar(Image.open(f)) for f in fotos_passageiro]
    return juntar_fotos(fotos_motorista, fotos_passageiro)

def imagem_para_base64(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

def analise_pneus(
    eixo_dianteiro_motorista, eixo_dianteiro_passageiro,
    eixo_traseiro_motorista, eixo_traseiro_passageiro,
    observacao="", modelo="gpt-4o-mini"
):
    """
    Fotos por eixo:
      - eixo dianteiro: [foto_frente, foto_tras] por lado
      - eixo traseiro: [foto_frente, foto_tras] por lado
    """

    # Limita observação
    observacao = observacao[:150]

    # Monta imagens agrupadas
    img_dianteiro = preparar_imagem_eixo(eixo_dianteiro_motorista, eixo_dianteiro_passageiro)
    img_traseiro = preparar_imagem_eixo(eixo_traseiro_motorista, eixo_traseiro_passageiro)

    # Converte para base64
    img_dianteiro_b64 = imagem_para_base64(img_dianteiro)
    img_traseiro_b64 = imagem_para_base64(img_traseiro)

    prompt = f"""
Você é um especialista em análise de desgaste e manutenção preventiva de pneus de caminhão.
Analise as imagens dos eixos dianteiro e traseiro e considere a observação do motorista.
Indique se há problemas, quais são, e sugira ações de manutenção.
Não fale sobre agendamento, apenas recomende ações.

Observação do motorista: "{observacao}"
    """

    response = client.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": "Você é um mecânico experiente e especializado em pneus de caminhão."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_dianteiro_b64}"}},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_traseiro_b64}"}},
            ]}
        ],
        max_tokens=800
    )

    resultado = response.choices[0].message.content

    # Link WhatsApp para envio ao cliente
    numero_empresa = "5567984173800"
    mensagem_whatsapp = f"Olá, realizei o teste de análise de pneus. Seguem os resultados:\n\n{resultado}\n\nGostaria de conversar sobre a manutenção do caminhão."
    link_whatsapp = f"https://wa.me/{numero_empresa}?text={mensagem_whatsapp.replace(' ', '%20')}"

    return {
        "analise": resultado,
        "link_whatsapp": link_whatsapp
    }
