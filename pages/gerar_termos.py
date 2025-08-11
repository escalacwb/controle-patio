# /pages/gerar_termos.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import locale
import psycopg2.extras

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    st.warning("Não foi possível configurar a localidade para pt_BR.")

def gerar_texto_termo(dados_veiculo, selecoes):
    # ... (Esta função permanece exatamente a mesma)
    pass

def app():
    st.set_page_config(layout="centered")
    st.title("📄 Gerador de Termo de Responsabilidade")
    st.markdown("Selecione as condições observadas para gerar o termo para impressão.")

    # --- MUDANÇA: BUSCA DADOS PELO ID DA URL ---
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
    
    release_connection(conn)
    
    # --- O RESTO DA PÁGINA PERMANECE O MESMO ---
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
    
    with st.container(border=True):
        st.markdown(f'<div id="printable">{texto_completo.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
        st.markdown(f"<br><br>_{data_extenso}_")
        st.markdown(f"<br><br>___________________________________<br>**{nome_assinatura}**", unsafe_allow_html=True)

    if st.button("🖨️ Imprimir Termo", type="primary", use_container_width=True):
        # ... (código JavaScript de impressão - sem alteração)
        pass

if __name__ == "__main__":
    app()