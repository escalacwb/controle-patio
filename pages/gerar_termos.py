# /pages/gerar_termos.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import locale
import psycopg2.extras

# --- CONFIGURAÇÃO DE DATA E HORA EM PORTUGUÊS ---
try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Não foi possível configurar a localidade para pt_BR. A data pode não ser exibida corretamente.")

def gerar_texto_termo(dados_veiculo, selecoes):
    """Gera o texto completo do termo de responsabilidade com base nas seleções."""
    
    # --- DADOS DO VEÍCULO ---
    # Adicionamos uma verificação para garantir que dados_veiculo não é None
    if not dados_veiculo:
        return "Erro: Dados do veículo não encontrados.", "", ""

    nome_motorista = dados_veiculo.get('nome_motorista', '').upper() if dados_veiculo.get('nome_motorista') else ''
    placa = dados_veiculo.get('placa', '').upper()
    cliente = dados_veiculo.get('empresa', '').upper()
    
    marca_modelo_str = dados_veiculo.get('modelo', '')
    partes_modelo = marca_modelo_str.split(' ', 1)
    marca = partes_modelo[0].upper() if len(partes_modelo) > 0 else ''
    modelo = partes_modelo[1].upper() if len(partes_modelo) > 1 else ''
    
    agora = datetime.now()
    data_extenso = agora.strftime(f"Dourados - MS, %d de %B de %Y (%A)")

    avarias_padrao = [
        "FOLGA EM BUCHA JUMELO", "FOLGA EM BUCHA TIRANTE", "FOLGA EM TERMINAL",
        "PINO DE CENTRO QUEBRADO", "FOLGA EM MANGA DE EIXO", "FOLGA EM ROLAMENTO",
        "MOLA QUEBRADA"
    ]
    
    avarias_selecionadas = [avaria for avaria in avarias_padrao if selecoes.get(avaria)]
    
    # --- MONTAGEM DO TEXTO (preparado para HTML) ---
    texto_base = (
        f"Eu, {nome_motorista}, responsável pelo veículo {marca} {modelo} de placa {placa}, "
        f"pertencente à empresa {cliente}, DECLARO, para os devidos fins, que autorizo a execução do serviço de alinhamento "
        "na unidade acima identificada, ciente de que o serviço será realizado pela empresa Capital Service LTDA, "
        "mesmo diante das condições abaixo descritas:"
    )

    partes_texto = [texto_base]
    
    if avarias_selecionadas:
        texto_avarias = "- O veículo apresenta as seguintes avarias:<br>" + "<br>".join([f"&nbsp;&nbsp;&nbsp;&nbsp;{item}" for item in avarias_selecionadas])
        partes_texto.append(texto_avarias)
        partes_texto.append(
            "Estou plenamente ciente de que as folgas identificadas nos componentes da suspensão e direção podem comprometer "
            "a precisão e a eficácia do alinhamento, resultando em resultado insatisfatório ou fora dos padrões recomendados."
        )
        partes_texto.append(
            "Declaro também estar ciente de que a circulação do veículo com tais folgas representa risco potencial à segurança, "
            "podendo gerar perda de estabilidade, desgaste prematuro dos pneus e danos adicionais ao sistema de suspensão e direção."
        )

    if selecoes.get("CARRETA CARREGADA"):
        partes_texto.append(
            "Além disso, o caminhão encontra-se carregado, condição que pode interferir na medição precisa dos ângulos de alinhamento "
            "devido à alteração temporária na geometria da suspensão e direção. Estou ciente de que, por esse motivo, o resultado "
            "do alinhamento pode não refletir a condição ideal de uso com o veículo descarregado, e que poderá haver necessidade "
            "de novo ajuste após a remoção da carga."
        )

    if selecoes.get("CAMBAGEM"):
        partes_texto.append(
            "Além disso, foi constatado que a cambagem do veículo encontra-se fora dos parâmetros recomendados pelo fabricante. "
            "Essa condição pode afetar a dirigibilidade, o desgaste dos pneus e o desempenho geral da suspensão. Estou ciente "
            "de que, para a correção adequada, pode ser necessário realizar intervenções estruturais ou substituição de componentes, "
            "e que, sem esses ajustes, o alinhamento poderá não apresentar os resultados esperados."
        )
        
    texto_final = (
        "Assumo total responsabilidade pelas consequências decorrentes da realização do alinhamento nestas condições, "
        "bem como pela utilização do veículo após a execução do serviço.<br><br>"
        "Declaro, ainda, que compreendo e aceito que, <b>devido às condições apresentadas, este serviço será realizado sem garantia</b>, "
        "uma vez que <b>não é possível garantir a precisão técnica exigida pelo fabricante</b>."
    )
    partes_texto.append(texto_final)
    
    return "<br><br>".join(partes_texto), nome_motorista.strip(), data_extenso

def app():
    st.set_page_config(layout="centered")
    st.title("📄 Gerador de Termo de Responsabilidade")
    st.markdown("Selecione as condições observadas para gerar o termo para impressão.")

    try:
        execucao_id = int(st.query_params.get("execucao_id"))
    except (ValueError, TypeError):
        st.error("ID do serviço não encontrado. Por favor, acesse esta página através do botão 'Gerar Termo' na tela de Serviços Concluídos.")
        st.stop()

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    dados_veiculo = None # Inicializa como None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            query = """
                SELECT v.placa, v.modelo, v.empresa, es.nome_motorista
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                WHERE es.id = %s
            """
            cursor.execute(query, (execucao_id,))
            resultado = cursor.fetchone()
            if resultado:
                dados_veiculo = dict(resultado)
                st.success(f"Gerando termo para o veículo: {dados_veiculo['placa']} - {dados_veiculo['modelo']}")
            else:
                st.error("Serviço não encontrado no sistema.")
                st.stop()
    finally:
        release_connection(conn)
    
    if not dados_veiculo:
        st.error("Não foi possível carregar os dados do veículo.")
        st.stop()

    st.markdown("---")
    st.subheader("Selecione as Condições e Avarias")
    
    selecoes = {}
    col1, col2 = st.columns(2)
    with col1:
        selecoes["FOLGA EM BUCHA JUMELO"] = st.checkbox("Folga em Bucha Jumelo")
        selecoes["FOLGA EM BUCHA TIRANTE"] = st.checkbox("Folga em Bucha Tirante")
        selecoes["FOLGA EM TERMINAL"] = st.checkbox("Folga em Terminal")
        selecoes["PINO DE CENTRO QUEBRADO"] = st.checkbox("Pino de Centro Quebrado")
        selecoes["FOLGA EM MANGA DE EIXO"] = st.checkbox("Folga em Manga de Eixo")
    with col2:
        selecoes["FOLGA EM ROLAMENTO"] = st.checkbox("Folga em Rolamento")
        selecoes["MOLA QUEBRADA"] = st.checkbox("Mola Quebrada")
        st.markdown("---")
        selecoes["CARRETA CARREGADA"] = st.checkbox("Carreta Carregada")
        selecoes["CAMBAGEM"] = st.checkbox("Cambagem")
        
    st.markdown("---")
    
    texto_completo, nome_assinatura, data_extenso = gerar_texto_termo(dados_veiculo, selecoes)
    
    st.subheader("Pré-visualização e Impressão")
    
    html_para_impressao = f"""
    <style>
        .print-button {{
            display: block; width: 100%; padding: 0.75rem; border-radius: 0.5rem;
            background-color: #FF4B4B; color: white; font-weight: 600;
            text-align: center; cursor: pointer; text-decoration: none;
            margin-top: 1.5em; border: none;
        }}
        .print-button:hover {{ opacity: 0.8; }}
        #view-area {{
            border: 1px solid #555; padding: 2rem; border-radius: 5px;
            background-color: #fff; color: #000;
        }}
        
        /* --- INÍCIO DAS REGRAS DE IMPRESSÃO CORRIGIDAS --- */
        @media print {{
            @page {{
                size: A4 portrait;
                margin: 1.5cm;
            }}

            body > #root > div:not(.stApp), .stApp > header, .stSidebar, .print-button-container {{
                display: none !important;
                visibility: hidden !important;
            }}

            .main {{
                visibility: visible !important;
            }}

            .main * {{
                visibility: hidden;
            }}

            #printable-area, #printable-area * {{
                visibility: visible;
            }}

            #printable-area {{
                position: fixed;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                border: none !important;
                padding: 0 !important;
                color: #000 !important;
                background-color: #fff !important;
                display: flex;
                flex-direction: column;
            }}
            
            .termo-body {{
                flex-grow: 1;
                text-align: justify;
                font-family: sans-serif;
                font-size: 11pt;
                line-height: 1.5;
            }}
            .termo-header, .termo-footer {{
                flex-grow: 0;
                flex-shrink: 0;
                text-align: center;
                font-family: sans-serif;
            }}
        }}
        /* --- FIM DAS REGRAS DE IMPRESSÃO CORRIGIDAS --- */
    </style>

    <div id="view-area">
        <h3 style="text-align: center; font-family: sans-serif;">TERMO DE RESPONSABILIDADE</h3>
        <p style="font-family: sans-serif; text-align: justify; font-size: 11pt; line-height: 1.5;">{texto_completo}</p>
        <br><br>
        <p style="text-align: center; font-family: sans-serif;">{data_extenso}</p>
        <br><br><br>
        <p style="text-align: center; font-family: sans-serif;">___________________________________<br><b>{nome_assinatura}</b></p>
    </div>

    <div class="print-button-container">
        <button class="print-button" onclick="window.print()">
            🖨️ Imprimir Termo
        </button>
    </div>
    
    <div id="printable-area" style="display: none;">
        <div class="termo-header">
            <h3 style="text-align: center; font-family: sans-serif;">TERMO DE RESPONSABILIDADE</h3>
        </div>
        <div class="termo-body">
            <p>{texto_completo}</p>
        </div>
        <div class="termo-footer">
            <p style="text-align: center; font-family: sans-serif;">{data_extenso}</p>
            <p style="text-align: center; font-family: sans-serif;">&nbsp;</p> 
            <p style="text-align: center; font-family: sans-serif;">___________________________________<br><b>{nome_assinatura}</b></p>
        </div>
    </div>
    """

    st.components.v1.html(html_para_impressao, height=600, scrolling=True)

if __name__ == "__main__":
    app()