import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from streamlit_autorefresh import st_autorefresh

def app():
    # --- CONFIGURAÇÕES DA PÁGINA ---
    st.set_page_config(layout="wide") # Garante que a página use toda a largura da tela
    
    # Atualiza a página a cada 30 segundos (30000 milissegundos)
    st_autorefresh(interval=30000, key="datarefresh")

    # CSS para aumentar o tamanho das fontes e estilizar os cartões
    st.markdown("""
        <style>
        /* Aumenta o tamanho do título principal */
        h1 {
            font-size: 3rem !important;
        }
        /* Estilo para os títulos das seções (EM ATENDIMENTO / FILA) */
        .section-header {
            font-size: 2.5rem !important;
            font-weight: bold;
            color: #22a7f0; /* Azul primário do tema */
            text-align: center;
            margin-bottom: 20px;
        }
        /* Estilo para os cartões dos boxes e da fila */
        .card {
            background-color: #292929;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #444;
        }
        .card-title {
            font-size: 1.8rem;
            font-weight: bold;
        }
        .card-content {
            font-size: 1.5rem;
        }
        .placa-text {
            font-size: 2.2rem;
            font-weight: bold;
            color: #FFFFFF;
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
        }
        </style>
    """, unsafe_allow_html=True)

    st.title("Painel Operacional do Pátio")
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return

    try:
        # --- SEÇÃO 1: VEÍCULOS EM ATENDIMENTO NOS BOXES ---
        st.markdown('<p class="section-header">EM ATENDIMENTO</p>', unsafe_allow_html=True)
        
        query_boxes = """
            SELECT 
                b.id as box_id,
                v.placa,
                v.empresa,
                f.nome as funcionario
            FROM boxes b
            JOIN execucao_servico es ON b.id = es.box_id
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN funcionarios f ON es.funcionario_id = f.id
            WHERE es.status = 'em_andamento'
            ORDER BY b.id;
        """
        df_boxes = pd.read_sql(query_boxes, conn)

        if not df_boxes.empty:
            # Cria colunas para cada box em atendimento
            cols = st.columns(len(df_boxes))
            for i, row in df_boxes.iterrows():
                with cols[i]:
                    with st.container():
                        st.markdown(f'<div class="card"><p class="card-title">BOX {row["box_id"]}</p><p class="placa-text">{row["placa"]}</p><p class="card-content">Empresa: {row["empresa"]}<br>Mecânico: {row["funcionario"]}</p></div>', unsafe_allow_html=True)
        else:
            st.info("Nenhum veículo em atendimento nos boxes no momento.")

        st.markdown("---")

        # --- SEÇÃO 2: FILA DE ESPERA (SERVIÇOS PENDENTES) ---
        st.markdown('<p class="section-header">FILA DE ESPERA</p>', unsafe_allow_html=True)
        
        query_fila = """
            SELECT 
                v.placa,
                v.empresa,
                STRING_AGG(s.tipo, ', ') as servicos -- Agrupa todos os serviços pendentes do veículo
            FROM (
                SELECT veiculo_id, tipo, data_solicitacao FROM servicos_solicitados_borracharia WHERE status = 'pendente'
                UNION ALL
                SELECT veiculo_id, tipo, data_solicitacao FROM servicos_solicitados_alinhamento WHERE status = 'pendente'
                UNION ALL
                SELECT veiculo_id, tipo, data_solicitacao FROM servicos_solicitados_manutencao WHERE status = 'pendente'
            ) s
            JOIN veiculos v ON s.veiculo_id = v.id
            GROUP BY v.placa, v.empresa, s.veiculo_id
            ORDER BY MIN(s.data_solicitacao) ASC; -- Ordena pela data do primeiro serviço solicitado
        """
        df_fila = pd.read_sql(query_fila, conn)

        if not df_fila.empty:
            # Cria 3 colunas para exibir a fila de forma organizada
            col1, col2, col3 = st.columns(3)
            cols_fila = [col1, col2, col3]
            
            for i, row in df_fila.iterrows():
                with cols_fila[i % 3]: # Distribui os veículos entre as 3 colunas
                    with st.container():
                        st.markdown(f'<div class="card"><p class="placa-text">{row["placa"]}</p><p class="card-content">Empresa: {row["empresa"]}<br>Serviços: {row["servicos"]}</p></div>', unsafe_allow_html=True)
        else:
            st.info("Fila de espera vazia.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
    finally:
        release_connection(conn)