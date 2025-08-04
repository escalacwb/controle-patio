import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from utils import get_catalogo_servicos

MS_TZ = pytz.timezone('America/Campo_Grande')

if 'box_states' not in st.session_state:
    st.session_state.box_states = {}

# (As funções visao_boxes, get_estado_atual_boxes e render_box não mudam)
# A única mudança é na função finalizar_execucao
def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
            # --- ALTERAÇÃO: Captura o ID do usuário logado ---
            usuario_finalizacao_id = st.session_state.get('user_id')

            for servico in box_state.get('servicos', {}).values():
                if servico['status'] == 'ativo_novo':
                    tabela = f"servicos_solicitados_{servico['area']}"
                    query = f"INSERT INTO {tabela} (veiculo_id, tipo, quantidade, status, box_id, execucao_id, data_solicitacao, data_atualizacao, observacao_execucao) SELECT veiculo_id, %s, %s, 'finalizado', box_id, id, %s, %s, %s FROM execucao_servico WHERE id = %s"
                    cursor.execute(query, (servico['tipo'], servico['qtd_executada'], datetime.now(MS_TZ), datetime.now(MS_TZ), obs_final, execucao_id))
                else:
                    status_final = 'cancelado' if servico['status'] == 'removido' else 'finalizado'
                    tabela = f"servicos_solicitados_{servico['area']}"
                    query = f"UPDATE {tabela} SET status = %s, quantidade = %s, data_atualizacao = %s, observacao_execucao = %s WHERE id = %s"
                    cursor.execute(query, (status_final, servico['qtd_executada'], datetime.now(MS_TZ), obs_final, servico['db_id']))
            
            # --- ALTERAÇÃO: Adiciona o ID do usuário na atualização ---
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s", (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id))
            
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")
            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")

# (O resto do arquivo visao_boxes.py continua aqui)
# Para garantir, o código completo está abaixo:
def visao_boxes_completo(): # Nome da função alterado para não conflitar
    if 'box_states' not in st.session_state: st.session_state.box_states = {}
    st.title("🔧 Visão Geral dos Boxes")
    st.markdown("Monitore, atualize e finalize os serviços em cada box.")
    catalogo_servicos = get_catalogo_servicos()
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return
    try:
        df_boxes = get_estado_atual_boxes(conn)
        if df_boxes.empty:
            st.warning("Nenhum box cadastrado no sistema.")
            return
        if 'id' in df_boxes.columns and not df_boxes.empty:
            cols = st.columns(len(df_boxes))
            for index, box_data in df_boxes.iterrows():
                with cols[index]:
                    render_box(conn, box_data, catalogo_servicos)
    except Exception as e:
        st.error(f"❌ Erro Crítico ao carregar a visão dos boxes: {e}")
        st.exception(e)
    finally:
        release_connection(conn)

# (get_estado_atual_boxes e render_box e sync_box_state_from_db aqui sem alterações)
# (Copie as versões dessas funções do seu arquivo que você me mandou)