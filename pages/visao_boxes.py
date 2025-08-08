import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, enviar_notificacao_telegram, recalcular_media_veiculo

MS_TZ = pytz.timezone('America/Campo_Grande')

# (O resto do arquivo visao_boxes.py permanece o mesmo da sua última versão funcional)
# ...
# A única mudança é na função finalizar_execucao, conforme abaixo:

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
            # Lógica de salvar serviços (UPDATE, INSERT)
            # ...
            cursor.execute("SELECT veiculo_id FROM execucao_servico WHERE id = %s", (execucao_id,))
            veiculo_id = cursor.fetchone()[0]
            
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")

            # --- MUDANÇA: Gatilho para recalcular a média do veículo ---
            st.info("Atualizando média de KM do veículo...")
            recalcular_media_veiculo(conn, veiculo_id)

            # Lógica de notificação
            # ...

            if box_id in st.session_state.box_states: del st.session_state.box_states[box_id]
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")
        st.exception(e)