import streamlit as st
import pandas as pd
from pages.ui_components import render_mobile_navbar
render_mobile_navbar(active_page="filas")
from database import get_connection, release_connection
from streamlit_autorefresh import st_autorefresh


def app():
    # --- CONFIGURAÇÕES DA PÁGINA ---
    st.set_page_config(layout="wide")
    
    # Atualiza a página a cada 30 segundos
    st_autorefresh(interval=30000, key="datarefresh")

    # --- CSS APRIMORADO PARA O PAINEL DE TV ---
    st.markdown("""
        <style>
        /* Remove o padding padrão do Streamlit para aproveitar mais a tela */
        .main .block-container {
            padding: 1rem 2rem;
        }
        /* Aumenta o tamanho do título principal */
        h1 {
            font-size: 2.8rem !important;
            text-align: center;
        }
        /* Estilo para os títulos das seções (EM ATENDIMENTO / FILA) */
        .section-header {
            font-size: 2.2rem !important;
            font-weight: bold;
            color: #22a7f0;
            text-align: center;
            margin-bottom: 20px;
        }
        /* Estilo para os cartões dos boxes e da fila */
        .card {
            background-color: #292929;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            border: 1px solid #444;
            height: 100%;
        }
        .card-title {
            font-size: 1.7rem;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .card-content {
            font-size: 1.1rem;
        }
        .placa-text {
            font-size: 2.0rem;
            font-weight: bold;
            color: #FFFFFF;
            background-color: #1a1a1a;
            padding: 10px;
            border-radius: 5px;
            text-align: center;
            margin-bottom: 10px;
        }
        /* NOVO: Estilo para o número de ordem na fila */
        .queue-number {
            font-size: 2.5rem;
            font-weight: bold;
            color: #22a7f0;
            float: left;
            margin-right: 15px;
            line-height: 1;
        }
        /* NOVO: Estilo para a lista de serviços dentro do cartão */
        .service-list {
            font-size: 1.0rem;
            font-style: italic;
            color: #ccc;
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
        
        # MUDANÇA: Query agora busca a lista de serviços para cada box
        query_boxes = """
            WITH servicos_em_andamento AS (
                SELECT 
                    execucao_id, 
                    STRING_AGG(tipo || ' (Qtd: ' || quantidade || ')', '<br>') as lista_servicos
                FROM (
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_borracharia WHERE status = 'em_andamento'
                    UNION ALL
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_alinhamento WHERE status = 'em_andamento'
                    UNION ALL
                    SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_manutencao WHERE status = 'em_andamento'
                ) s
                GROUP BY execucao_id
            )
            SELECT 
                b.id as box_id,
                v.placa,
                v.empresa,
                f.nome as funcionario,
                sa.lista_servicos
            FROM boxes b
            JOIN execucao_servico es ON b.id = es.box_id
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN funcionarios f ON es.funcionario_id = f.id
            LEFT JOIN servicos_em_andamento sa ON es.id = sa.execucao_id
            WHERE es.status = 'em_andamento' AND b.id > 0
            ORDER BY b.id;
        """
        df_boxes = pd.read_sql(query_boxes, conn)

        if not df_boxes.empty:
            cols = st.columns(len(df_boxes))
            for i, row in df_boxes.iterrows():
                with cols[i]:
                    # MUDANÇA: Exibe a lista de serviços no cartão
                    st.markdown(f'''
                        <div class="card">
                            <p class="card-title">BOX {row["box_id"]}</p>
                            <p class="placa-text">{row["placa"]}</p>
                            <p class="card-content">
                                <b>Empresa:</b> {row["empresa"]}<br>
                                <b>Mecânico:</b> {row["funcionario"]}
                            </p>
                            <hr>
                            <p class="service-list">{row["lista_servicos"] or "N/A"}</p>
                        </div>
                    ''', unsafe_allow_html=True)
        else:
            st.info("Nenhum veículo em atendimento nos boxes no momento.")

        st.markdown("---")

        # --- SEÇÃO 2: FILA DE ESPERA (SERVIÇOS PENDENTES) ---
        st.markdown('<p class="section-header">FILA DE ESPERA</p>', unsafe_allow_html=True)
        
        # MUDANÇA: Query agora busca os serviços com suas quantidades
        query_fila = """
            SELECT 
                v.placa,
                v.empresa,
                STRING_AGG(s.tipo || ' (Qtd: ' || s.quantidade || ')', '<br>') as servicos
            FROM (
                SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_borracharia WHERE status = 'pendente'
                UNION ALL
                SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_alinhamento WHERE status = 'pendente'
                UNION ALL
                SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_manutencao WHERE status = 'pendente'
            ) s
            JOIN veiculos v ON s.veiculo_id = v.id
            GROUP BY v.placa, v.empresa, s.veiculo_id
            ORDER BY MIN(s.data_solicitacao) ASC;
        """
        df_fila = pd.read_sql(query_fila, conn)

        if not df_fila.empty:
            col1, col2, col3 = st.columns(3)
            cols_fila = [col1, col2, col3]
            
            for i, row in df_fila.iterrows():
                with cols_fila[i % 3]:
                    # MUDANÇA: Adiciona o número de ordem e a lista detalhada de serviços
                    st.markdown(f'''
                        <div class="card">
                            <p class="card-title">
                                <span class="queue-number">{i + 1}º</span>
                                <span>NA FILA</span>
                            </p>
                            <p class="placa-text">{row["placa"]}</p>
                            <p class="card-content"><b>Empresa:</b> {row["empresa"]}</p>
                            <hr>
                            <p class="service-list">{row["servicos"] or "N/A"}</p>
                        </div>
                    ''', unsafe_allow_html=True)
        else:
            st.info("Fila de espera vazia.")

    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
    finally:
        release_connection(conn)