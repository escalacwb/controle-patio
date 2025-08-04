import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests

def hash_password(password):
    """Gera o hash de uma senha para armazenamento seguro."""
    return hashlib.sha256(password.encode()).hexdigest()

def enviar_notificacao_telegram(mensagem):
    """
    Envia uma mensagem para o Telegram e retorna um status.
    Retorna: (True, "Mensagem de sucesso") ou (False, "Mensagem de erro")
    """
    try:
        token = st.secrets.get("TELEGRAM_TOKEN")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID")

        if not token or not chat_id:
            return False, "Credenciais do Telegram (TOKEN ou CHAT_ID) não encontradas nos Secrets."

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "Markdown"
        }
        
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
    """Busca os detalhes dos serviços para uma execução específica, usando o execucao_id."""
    query = """
        SELECT s.area, s.tipo, s.quantidade, s.status, f.nome as funcionario_nome
        FROM (
            SELECT execucao_id, 'Borracharia' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_borracharia
            UNION ALL
            SELECT execucao_id, 'Alinhamento' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_alinhamento
            UNION ALL
            SELECT execucao_id, 'Manutenção Mecânica' as area, tipo, quantidade, status, funcionario_id FROM servicos_solicitados_manutencao
        ) s
        LEFT JOIN funcionarios f ON s.funcionario_id = f.id
        WHERE s.execucao_id = %s
        ORDER BY s.area, s.tipo;
    """
    return pd.read_sql(query, conn, params=(execucao_id,))