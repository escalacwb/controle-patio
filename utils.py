import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale
import hashlib
import requests
import re
import psycopg2.extras

def hash_password(password):
    """Gera o hash de uma senha para armazenamento seguro."""
    return hashlib.sha256(password.encode()).hexdigest()

def enviar_notificacao_telegram(mensagem, chat_id_destino):
    """Envia uma mensagem para um chat_id específico do Telegram."""
    try:
        token = st.secrets.get("TELEGRAM_TOKEN")
        if not token or not chat_id_destino:
            print("Token ou Chat ID de destino não fornecidos ou não encontrados nos Secrets.")
            return False, "Credenciais do Telegram (Token ou Chat ID de destino) incompletas."
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
    query = """
        SELECT fim_execucao, quilometragem
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado' AND quilometragem IS NOT NULL AND quilometragem > 0
        ORDER BY fim_execucao;
    """
    df_veiculo = pd.read_sql(query, conn, params=(veiculo_id,))
    df_veiculo = df_veiculo.drop_duplicates(subset=['quilometragem'], keep='last')
    
    last_valid_km = -1
    valid_indices = []
    for index, row in df_veiculo.iterrows():
        if row['quilometragem'] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row['quilometragem']
    
    valid_group = df_veiculo.loc[valid_indices]
    media_km_diaria = None
    if len(valid_group) >= 2:
        primeira_visita = valid_group.iloc[0]
        ultima_visita = valid_group.iloc[-1]
        delta_km = int(ultima_visita['quilometragem']) - int(primeira_visita['quilometragem'])
        delta_dias = (ultima_visita['fim_execucao'] - primeira_visita['fim_execucao']).days
        if delta_dias > 0:
            media_km_diaria = float(delta_km / delta_dias)
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE veiculos SET media_km_diaria = %s WHERE id = %s", (media_km_diaria, veiculo_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"Erro ao atualizar a média para o veículo {veiculo_id}: {e}")
        return False

def buscar_clientes_por_similaridade(termo_busca):
    if not termo_busca or len(termo_busca) < 3: return []
    conn = get_connection()
    if not conn: return []
    query = """
        SELECT id, nome_empresa, nome_fantasia 
        FROM clientes 
        WHERE similarity(nome_empresa, %(termo)s) > 0.2 OR similarity(nome_fantasia, %(termo)s) > 0.2
        ORDER BY GREATEST(similarity(nome_empresa, %(termo)s), similarity(nome_fantasia, %(termo)s)) DESC, nome_empresa
        LIMIT 10;
    """
    try:
        df = pd.read_sql(query, conn, params={'termo': termo_busca})
        return list(df.itertuples(index=False, name=None))
    finally:
        release_connection(conn)

# --- NOVA FUNÇÃO PARA BUSCAR DETALHES DE UM CLIENTE ---
def get_cliente_details(cliente_id):
    """Busca os detalhes de um cliente específico pelo ID."""
    if not cliente_id:
        return None
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT nome_responsavel, contato_responsavel FROM clientes WHERE id = %s", (cliente_id,))
            return cursor.fetchone()
    finally:
        release_connection(conn)
        
def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)