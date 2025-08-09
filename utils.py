import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests
import re

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def enviar_notificacao_telegram(mensagem, chat_id_destino):
    try:
        token = st.secrets.get("TELEGRAM_TOKEN")
        if not token or not chat_id_destino:
            return False, "Credenciais do Telegram incompletas."
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {"chat_id": chat_id_destino, "text": mensagem, "parse_mode": "Markdown"}
        response = requests.post(url, json=params)
        if response.status_code == 200:
            return True, "Notificação enviada com sucesso!"
        else:
            return False, f"Erro retornado pelo Telegram (código {response.status_code}): {response.text}"
    except Exception as e:
        return False, f"Ocorreu uma exceção no Python ao tentar enviar: {str(e)}"

try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    if 'streamlit' in st.__name__:
        st.warning("Não foi possível configurar a localidade para pt_BR.")

def get_catalogo_servicos():
    conn = get_connection()
    if not conn: return {"borracharia": [], "alinhamento": [], "manutencao": []}
    try:
        catalogo = {
            "borracharia": pd.read_sql("SELECT nome FROM servicos_borracharia ORDER BY nome", conn)['nome'].tolist(),
            "alinhamento": pd.read_sql("SELECT nome FROM servicos_alinhamento ORDER BY nome", conn)['nome'].tolist(),
            "manutencao": pd.read_sql("SELECT nome FROM servicos_manutencao ORDER BY nome", conn)['nome'].tolist()
        }
    finally:
        release_connection(conn)
    return catalogo

def consultar_placa_comercial(placa: str):
    if not placa: return False, "A placa não pode estar em branco."
    token = st.secrets.get("PLACA_API_TOKEN")
    if not token: return False, "Token da API de Placas não encontrado nos Secrets."
    url = f"https://wdapi2.com.br/consulta/{placa}/{token}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            data = response.json()
            modelo_veiculo = data.get('marcaModelo', data.get('MODELO', 'Não encontrado'))
            if data.get('fipe') and data['fipe'].get('dados'):
                fipe_dados = sorted(data['fipe']['dados'], key=lambda x: x.get('score', 0), reverse=True)
                if fipe_dados:
                    modelo_veiculo = fipe_dados[0].get('texto_modelo', modelo_veiculo)
            return True, {'modelo': modelo_veiculo, 'anoModelo': data.get('anoModelo')}
        else:
            return False, response.json().get("message", f"Erro na API (Código: {response.status_code}).")
    except Exception as e:
        return False, f"Ocorreu um erro inesperado: {str(e)}"

def formatar_telefone(numero: str) -> str:
    if not numero: return ""
    numeros = re.sub(r'\D', '', numero)
    if len(numeros) == 11: return f"({numeros[:2]}){numeros[2:7]}-{numeros[7:]}"
    elif len(numeros) == 10: return f"({numeros[:2]}){numeros[2:6]}-{numeros[6:]}"
    return numero

def formatar_placa(placa: str) -> str:
    if not placa: return ""
    placa_limpa = re.sub(r'[^A-Z0-9]', '', placa.upper())
    if len(placa_limpa) == 7 and placa_limpa[4].isdigit():
        return f"{placa_limpa[:3]}-{placa_limpa[3:]}"
    return placa_limpa

def recalcular_media_veiculo(conn, veiculo_id):
    # (Sua função recalcular_media_veiculo aqui)
    pass

# --- NOVA FUNÇÃO DE BUSCA INTELIGENTE DE CLIENTES ---
def buscar_clientes_por_similaridade(termo_busca):
    """
    Busca clientes no banco com nomes similares ao termo pesquisado.
    """
    if not termo_busca or len(termo_busca) < 3:
        return []
    
    conn = get_connection()
    if not conn:
        return []
    
    # Usa a função similarity() para encontrar nomes parecidos
    query = """
        SELECT id, nome_empresa 
        FROM clientes 
        WHERE similarity(nome_empresa, %s) > 0.2
        ORDER BY similarity(nome_empresa, %s) DESC
        LIMIT 10;
    """
    try:
        df = pd.read_sql(query, conn, params=(termo_busca, termo_busca))
        # Converte o dataframe para uma lista de tuplas para ser mais leve
        return list(df.itertuples(index=False, name=None))
    finally:
        release_connection(conn)