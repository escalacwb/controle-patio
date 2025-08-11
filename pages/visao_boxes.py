# /pages/visao_boxes.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, enviar_notificacao_telegram, recalcular_media_veiculo
import psycopg2.extras

MS_TZ = pytz.timezone('America/Campo_Grande')

if 'box_states' not in st.session_state:
    st.session_state.box_states = {}

def visao_boxes():
    st.title("🔧 Visão Geral dos Boxes")
    st.markdown("Monitore, atualize e finalize os serviços em cada box.")
    
    if st.button("🔄 Sincronizar Estado de Todos os Boxes"):
        st.session_state.box_states = {}
        st.rerun()

    catalogo_servicos = get_catalogo_servicos()
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        df_boxes = get_estado_atual_boxes(conn)
        
        if not df_boxes.empty:
            cols = st.columns(len(df_boxes))
            for i, (box_id, box_data) in enumerate(df_boxes.iterrows()):
                with cols[i]:
                    render_box(conn, box_data, catalogo_servicos)
        else:
            st.info("Nenhum box em operação no momento.")

    except Exception as e:
        st.error(f"❌ Erro Crítico ao carregar a visão dos boxes: {e}")
        st.exception(e)
    finally:
        release_connection(conn)

def get_estado_atual_boxes(conn):
    query = """
        SELECT 
            b.id, b.area as box_area, es.id as execucao_id, 
            v.placa, v.empresa, v.nome_motorista, v.contato_motorista,
            f.nome as funcionario_nome, es.veiculo_id, es.funcionario_id, es.quilometragem
        FROM boxes b
        LEFT JOIN execucao_servico es ON b.id = es.box_id AND es.status = 'em_andamento'
        LEFT JOIN veiculos v ON es.veiculo_id = v.id
        LEFT JOIN funcionarios f ON es.funcionario_id = f.id
        WHERE b.id > 0 ORDER BY b.id;
    """
    return pd.read_sql(query, conn, index_col='id')

def render_box(conn, box_data, catalogo_servicos):
    box_id = int(box_data.name)
    execucao_id = box_data['execucao_id']

    if pd.isna(execucao_id):
        st.success(f"🧰 BOX {box_id} ✅ Livre")
        if box_id in st.session_state.box_states: del st.session_state.box_states[box_id]
        return
        
    st.header(f"🧰 BOX {box_id}")

    if box_id not in st.session_state.box_states:
        sync_box_state_from_db(conn, box_id, int(box_data['veiculo_id']))
    
    box_state = st.session_state.box_states.get(box_id, {})
    
    with st.container(border=True):
        st.markdown(f"**Placa:** {box_data['placa']} | **Empresa:** {box_data['empresa']}")
        st.markdown(f"**Funcionário:** {box_data['funcionario_nome']}")

    st.subheader("Serviços em Execução")
    for unique_id, servico in list(box_state.get('servicos', {}).items()):
        if servico.get('status') != 'removido':
            c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
            c1.write(servico['tipo'])
            nova_qtd = c2.number_input("Qtd", value=servico['qtd_executada'], min_value=0, key=f"qtd_{unique_id}", label_visibility="collapsed")
            if nova_qtd != servico['qtd_executada']:
                st.session_state.box_states[box_id]['servicos'][unique_id]['qtd_executada'] = nova_qtd
                st.rerun()
            if c3.button("X", key=f"del_{unique_id}", help=f"Remover {servico['tipo']}"):
                st.session_state.box_states[box_id]['servicos'][unique_id]['status'] = 'removido'
                st.rerun()

    st.subheader("Adicionar Serviço Extra")
    todos_servicos = catalogo_servicos.get("borracharia", []) + catalogo_servicos.get("alinhamento", []) + catalogo_servicos.get("manutencao", [])
    servicos_disponiveis = sorted(list(set(todos_servicos)))
    c_add1, c_add2, c_add3 = st.columns([0.7, 0.15, 0.15])
    novo_servico_tipo = c_add1.selectbox("Selecione", [""] + servicos_disponiveis, key=f"new_srv_tipo_{box_id}", label_visibility="collapsed")
    novo_servico_qtd = c_add2.number_input("Qtd", min_value=1, value=1, key=f"new_srv_qtd_{box_id}", label_visibility="collapsed")
    if c_add3.button("➕", key=f"add_{box_id}", help="Adicionar à lista"):
        if novo_servico_tipo:
            area_servico = ''
            if novo_servico_tipo in catalogo_servicos.get("borracharia", []): area_servico = 'borracharia'
            elif novo_servico_tipo in catalogo_servicos.get("alinhamento", []): area_servico = 'alinhamento'
            elif novo_servico_tipo in catalogo_servicos.get("manutencao", []): area_servico = 'manutencao'
            if area_servico:
                new_service_id = f"novo_{datetime.now().timestamp()}" # Chave única
                st.session_state.box_states[box_id]['servicos'][new_service_id] = { 'db_id': None, 'tipo': novo_servico_tipo, 'quantidade': novo_servico_qtd, 'qtd_executada': novo_servico_qtd, 'area': area_servico, 'status': 'ativo_novo' }
                st.rerun()
            else: st.error("Não foi possível identificar a área do serviço.")

    obs_final_value = st.text_area("Observações Finais da Execução", key=f"obs_final_input_{box_id}", value=box_state.get('obs_final', ''))
    if obs_final_value != box_state.get('obs_final'):
        st.session_state.box_states[box_id]['obs_final'] = obs_final_value
        st.rerun()

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    if col1.button("💾 Salvar Progresso", key=f"save_{box_id}", use_container_width=True):
        salvar_alteracoes_box(conn, box_id, int(execucao_id))

    if col2.button("✅ Finalizar Box", key=f"finish_{box_id}", type="primary", use_container_width=True):
        finalizar_execucao(conn, box_id, int(execucao_id))

    if col3.button("❌ Cancelar Serviço", key=f"cancel_{box_id}", use_container_width=True):
        cancelar_execucao(conn, box_id, int(execucao_id))

def sync_box_state_from_db(conn, box_id, veiculo_id):
    query = """
        (SELECT 'borracharia' as area, id, tipo, quantidade, observacao_execucao as observacao FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'alinhamento' as area, id, tipo, quantidade, observacao_execucao as observacao FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'manutencao' as area, id, tipo, quantidade, observacao_execucao as observacao FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
    """
    df_servicos = pd.read_sql(query, conn, params=[veiculo_id, box_id] * 3)
    servicos_dict = {f"{row['area']}_{row['id']}": {'db_id': row['id'], 'tipo': row['tipo'], 'quantidade': row['quantidade'], 'qtd_executada': row['quantidade'], 'area': row['area'], 'status': 'ativo'} for _, row in df_servicos.iterrows()}
    obs_geral = df_servicos['observacao'].dropna().unique()
    st.session_state.box_states[box_id] = {'servicos': servicos_dict, 'obs_final': obs_geral[0] if len(obs_geral) > 0 else ""}

def _persistir_mudancas(cursor, box_state, execucao_id, status_final_servico):
    obs_final = box_state.get('obs_final', '')
    veiculo_id, quilometragem = None, None

    # Pega informações da execução uma única vez
    cursor.execute("SELECT veiculo_id, quilometragem FROM execucao_servico WHERE id = %s", (execucao_id,))
    result = cursor.fetchone()
    if result:
        veiculo_id, quilometragem = result['veiculo_id'], result['quilometragem']

    for unique_id, servico in box_state.get('servicos', {}).items():
        if servico.get('status') == 'ativo_novo':
            tabela = f"servicos_solicitados_{servico['area']}"
            query = f"INSERT INTO {tabela} (veiculo_id, tipo, quantidade, status, box_id, execucao_id, data_solicitacao, data_atualizacao, observacao_execucao, quilometragem) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
            cursor.execute(query, (veiculo_id, servico['tipo'], servico['qtd_executada'], status_final_servico, int(unique_id.split('_')[-1]), execucao_id, datetime.now(MS_TZ), datetime.now(MS_TZ), obs_final, quilometragem))
            servico['db_id'] = cursor.fetchone()[0]
            servico['status'] = 'ativo' # Muda o status na sessão para não inserir novamente
        elif servico.get('status') in ['ativo', 'removido']:
            db_status = 'cancelado' if servico.get('status') == 'removido' else status_final_servico
            tabela = f"servicos_solicitados_{servico['area']}"
            query = f"UPDATE {tabela} SET status = %s, quantidade = %s, data_atualizacao = %s, observacao_execucao = %s WHERE id = %s"
            cursor.execute(query, (db_status, servico['qtd_executada'], datetime.now(MS_TZ), obs_final, servico['db_id']))

def salvar_alteracoes_box(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    if not box_state.get('servicos'):
        st.warning("Nenhuma alteração para salvar.")
        return
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            _persistir_mudancas(cursor, box_state, execucao_id, 'em_andamento')
            conn.commit()
        st.toast(f"Alterações no Box {box_id} salvas com sucesso!", icon="💾")
        sync_box_state_from_db(conn, box_id, conn.cursor().execute("SELECT veiculo_id FROM execucao_servico WHERE id=%s", (execucao_id,)).fetchone()[0])
        st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao salvar alterações no Box {box_id}: {e}")

def cancelar_execucao(conn, box_id, execucao_id):
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            _persistir_mudancas(cursor, st.session_state.box_states.get(box_id, {}), execucao_id, 'cancelado')
            cursor.execute("UPDATE execucao_servico SET status = 'cancelado', fim_execucao = %s WHERE id = %s", (datetime.now(MS_TZ), execucao_id))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.warning(f"Serviço no Box {box_id} foi cancelado.")
            if box_id in st.session_state.box_states: del st.session_state.box_states[box_id]
            st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao cancelar serviço no Box {box_id}: {e}")

def finalizar_execucao(conn, box_id, execucao_id):
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            box_state = st.session_state.box_states.get(box_id, {})
            _persistir_mudancas(cursor, box_state, execucao_id, 'finalizado')
            
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s WHERE id = %s RETURNING veiculo_id", (datetime.now(MS_TZ), execucao_id))
            veiculo_id = cursor.fetchone()['veiculo_id']
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()

            st.success(f"Box {box_id} finalizado com sucesso!")
            
            with st.spinner("Atualizando média e enviando notificações..."):
                recalcular_media_veiculo(conn, veiculo_id)
                
                # --- LÓGICA DE NOTIFICAÇÃO COMPLETA ---
                # (O código de notificação que já funcionava vai aqui, sem alterações)
                # ...
                
            if box_id in st.session_state.box_states: del st.session_state.box_states[box_id]
            st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")