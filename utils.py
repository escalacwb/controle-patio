import streamlit as st
import pandas as pd
from database import get_connection, release_connection
import locale

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