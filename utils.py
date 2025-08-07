import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests

def hash_password(password):
    """Gera o hash de uma senha para armazenamento seguro."""
    return hashlib.sha256(password.encode()).hexdigest()

# --- FUNÇÃO DE NOTIFICAÇÃO ATUALIZADA ---
def enviar_notificacao_telegram(mensagem, chat_id_destino):
    """Envia uma mensagem para um chat_id específico do Telegram."""
    try:
        token = st.secrets.get("TELEGRAM_TOKEN")
        
        if not token or not chat_id_destino:
            print("Token ou Chat ID de destino não fornecidos ou não encontrados nos Secrets.")
            return False, "Credenciais do Telegram (Token ou Chat ID de destino) incompletas."

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        params = {
            "chat_id": chat_id_destino,
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

# --- MUDANÇA: ADIÇÃO DA FUNÇÃO DE CONSULTA SINESP ---
def consultar_placa_sinesp(placa: str):
    """
    Consulta a API pública do SINESP Cidadão para obter dados básicos de um veículo.
    AVISO: Esta é uma API não documentada e pode parar de funcionar a qualquer momento.
    """
    if not placa:
        return False, "A placa não pode estar em branco."

    url = "https://cidadao.sinesp.gov.br/sinesp-cidadao/mobile/consultar-placa/v5"
    headers = {"Content-Type": "application/json; charset=UTF-8", "User-Agent": "SinespCidadao / 3.0.0"}
    payload = {"placa": placa}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            if data.get('codigoRetorno') == '0':
                return True, {
                    'modelo': data.get('modelo'), 'cor': data.get('cor'),
                    'ano': data.get('ano'), 'anoModelo': data.get('anoModelo'),
                    'placa': data.get('placa'), 'chassi': data.get('chassi'),
                    'situacao': data.get('situacao'),
                }
            else:
                return False, data.get('mensagemRetorno', 'Erro desconhecido retornado pela API.')
        else:
            return False, f"Erro na comunicação com a API (Código: {response.status_code})."
    except requests.exceptions.Timeout:
        return False, "A consulta demorou muito para responder (Timeout)."
    except requests.exceptions.RequestException as e:
        return False, f"Ocorreu um erro de conexão: {e}"
    except Exception as e:
        return False, f"Ocorreu um erro inesperado: {str(e)}"