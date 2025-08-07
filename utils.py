import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests
import re # Importa a biblioteca de expressões regulares

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

def consultar_placa_comercial(placa: str):
    """Consulta a API comercial (API Placas) para obter dados do veículo."""
    if not placa:
        return False, "A placa não pode estar em branco."
    token = st.secrets.get("PLACA_API_TOKEN")
    if not token:
        return False, "Token da API de Placas não encontrado nos Secrets."
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
            error_message = response.json().get("message", f"Erro na API (Código: {response.status_code}).")
            return False, error_message
    except requests.exceptions.Timeout:
        return False, "A consulta demorou muito para responder (Timeout)."
    except Exception as e:
        return False, f"Ocorreu um erro inesperado: {str(e)}"

def formatar_telefone(numero: str) -> str:
    """Formata um número de telefone no padrão (XX)XXXXX-XXXX."""
    if not numero:
        return ""
    numeros = re.sub(r'\D', '', numero)
    if len(numeros) == 11:
        return f"({numeros[:2]}){numeros[2:7]}-{numeros[7:]}"
    elif len(numeros) == 10:
        return f"({numeros[:2]}){numeros[2:6]}-{numeros[6:]}"
    else:
        return numero

def formatar_placa(placa: str) -> str:
    """Formata uma placa no padrão antigo (AAA-1234). Placas Mercosul não são alteradas."""
    if not placa:
        return ""
    # --- MUDANÇA: Garantindo que a expressão regular está 100% correta ---
    # O padrão r'[^A-Z0-9]' remove qualquer caractere que NÃO seja uma letra de A a Z ou um número de 0 a 9.
    placa_limpa = re.sub(r'[^A-Z0-9]', '', placa.upper())
    if len(placa_limpa) == 7 and placa_limpa[4].isdigit():
        return f"{placa_limpa[:3]}-{placa_limpa[3:]}"
    else:
        return placa_limpa