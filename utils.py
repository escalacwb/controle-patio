import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests

def hash_password(password):
    """Gera o hash de uma senha para armazenamento seguro."""
    return hashlib.sha256(password.encode()).hexdigest()

def enviar_notificacao_telegram(mensagem, chat_id_destino):
    """Envia uma mensagem para um chat_id específico do Telegram."""
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
    st.warning("Não foi possível configurar a localidade para pt_BR.")

@st.cache_data(ttl=3600)
def get_catalogo_servicos():
    catalogo = {"borracharia": [], "alinhamento": [], "manutencao": []}
    conn = get_connection()
    if not conn: return catalogo
    try:
        catalogo["borracharia"] = pd.read_sql("SELECT nome FROM servicos_borracharia ORDER BY nome", conn)['nome'].tolist()
        catalogo["alinhamento"] = pd.read_sql("SELECT nome FROM servicos_alinhamento ORDER BY nome", conn)['nome'].tolist()
        catalogo["manutencao"] = pd.read_sql("SELECT nome FROM servicos_manutencao ORDER BY nome", conn)['nome'].tolist()
    finally:
        release_connection(conn)
    return catalogo

def get_service_details_for_execution(conn, execucao_id):
    # ... (esta função permanece a mesma)
    pass # Removido para brevidade, mantenha o código original aqui

# --- MUDANÇA: NOVA FUNÇÃO PARA A API COMERCIAL ---
def consultar_placa_comercial(placa: str):
    """
    Consulta a API comercial (API Placas) para obter dados do veículo.
    """
    if not placa:
        return False, "A placa não pode estar em branco."

    # Puxa o token dos Secrets do Streamlit de forma segura
    token = st.secrets.get("PLACA_API_TOKEN")
    if not token:
        return False, "Token da API de Placas não encontrado nos Secrets."

    # Monta a URL conforme a documentação
    url = f"https://wdapi2.com.br/consulta/{placa}/{token}"

    try:
        response = requests.get(url, timeout=15)

        if response.status_code == 200:
            data = response.json()
            
            # Lógica para pegar o melhor nome de modelo disponível
            modelo_veiculo = data.get('marcaModelo', data.get('MODELO', 'Não encontrado'))
            if data.get('fipe') and data['fipe'].get('dados'):
                # Se houver dados da FIPE, tenta pegar o modelo mais completo
                fipe_dados = sorted(data['fipe']['dados'], key=lambda x: x.get('score', 0), reverse=True)
                if fipe_dados:
                    modelo_veiculo = fipe_dados[0].get('texto_modelo', modelo_veiculo)
            
            return True, {
                'modelo': modelo_veiculo,
                'cor': data.get('cor'),
                'ano': data.get('ano'),
                'anoModelo': data.get('anoModelo'),
                'placa': data.get('placa'),
                'municipio': data.get('municipio'),
                'uf': data.get('uf'),
                'situacao': data.get('situacao'),
            }
        else:
            # Usa a mensagem de erro da própria API
            error_message = response.json().get("message", f"Erro na API (Código: {response.status_code}).")
            return False, error_message

    except requests.exceptions.Timeout:
        return False, "A consulta demorou muito para responder (Timeout)."
    except Exception as e:
        return False, f"Ocorreu um erro inesperado: {str(e)}"