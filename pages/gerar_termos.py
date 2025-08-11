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
    nome_motorista = dados_veiculo.get('nome_motorista', '').upper()
    placa = dados_veiculo.get('placa', '').upper()
    cliente = dados_veiculo.get('empresa', '').upper()
    
    marca_modelo_str = dados_veiculo.get('modelo', '')
    partes_modelo = marca_modelo_str.split(' ', 1)
    marca = partes_modelo[0].upper() if len(partes_modelo) > 0 else ''
    modelo = partes_modelo[1].upper() if len(partes_modelo) > 1 else ''
    
    # --- DATA ATUAL POR EXTENSO ---
    agora = datetime.now()
    data_extenso = agora.strftime(f"Dourados - MS, %d de %B de %Y (%A)")

    # --- LISTA DE AVARIAS PADRÃO ---
    avarias_padrao = [
        "FOLGA EM BUCHA JUMELO", "FOLGA EM BUCHA TIRANTE", "FOLGA EM TERMINAL",
        "PINO DE CENTRO QUEBRADO", "FOLGA EM MANGA DE EIXO", "FOLGA EM ROLAMENTO",
        "MOLA QUEBRADA"
    ]
    
    avarias_selecionadas = [avaria for avaria in avarias_padrao if selecoes.get(avaria)]
    
    # --- MONTAGEM DO TEXTO ---
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

    dados_veiculo = {}
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
    
    st.subheader("Pré-visualização do Termo")
    
    # Monta o HTML do termo em uma única variável
    termo_html = f"""
    <div id="printable">
        <h3 style="text-align: center; font-family: sans-serif;">TERMO DE RESPONSABILIDADE</h3>
        <p style="font-family: sans-serif; text-align: justify;">{texto_completo}</p>
        <br><br>
        <p style="text-align: center; font-family: sans-serif;">{data_extenso}</p>
        <br><br><br>
        <p style="text-align: center; font-family: sans-serif;">___________________________________<br><b>{nome_assinatura}</b></p>
    </div>
    """
    
    # Exibe o termo na tela
    with st.container(border=True):
        st.markdown(termo_html, unsafe_allow_html=True)

    # --- NOVA LÓGICA DE IMPRESSÃO ---
    print_button_html = """
    <style>
        .print-button {
            display: block;
            width: 100%;
            padding: 0.75rem;
            border: 1px solid transparent;
            border-radius: 0.5rem;
            background-color: #FF4B4B; /* Cor primária do Streamlit */
            color: white;
            font-weight: 600;
            text-align: center;
            cursor: pointer;
            text-decoration: none;
            margin-top: 1em;
        }
        .print-button:hover {
            opacity: 0.8;
        }
        @media print {
            /* Esconde tudo, exceto a área imprimível e seus filhos */
            body * {
                visibility: hidden;
            }
            #printable, #printable * {
                visibility: visible;
            }
            #printable {
                position: absolute;
                left: 0;
                top: 0;
                width: 100%;
            }
        }
    </style>
    <a href="javascript:window.print()" class="print-button">
        🖨️ Imprimir Termo
    </a>
    """
    st.components.v1.html(print_button_html, height=50)

if __name__ == "__main__":
    app()