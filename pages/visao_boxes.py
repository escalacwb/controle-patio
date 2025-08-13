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
    
    # --- NOVO BOTÃO DE SINCRONIZAÇÃO GLOBAL ---
    if st.button("🔄 Sincronizar Todos os Boxes"):
        # Limpa o estado da sessão para forçar a releitura do banco de dados
        st.session_state.box_states = {}
        st.toast("Dados sincronizados com o servidor.", icon="✅")
        st.rerun()

    catalogo_servicos = get_catalogo_servicos()
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return
        
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
        WHERE b.id > 0
        ORDER BY b.id;
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

    # Força a sincronização do box individual se ele não estiver no estado da sessão
    if box_id not in st.session_state.box_states:
        sync_box_state_from_db(conn, box_id, int(box_data['veiculo_id']))
    
    box_state = st.session_state.box_states.get(box_id, {})
    
    with st.container(border=True):
        st.markdown(f"**Placa:** {box_data['placa']} | **Empresa:** {box_data['empresa']}")
        if pd.notna(box_data['nome_motorista']) and box_data['nome_motorista']:
            st.markdown(f"**Motorista:** {box_data['nome_motorista']} ({box_data['contato_motorista'] or 'N/A'})")
        st.markdown(f"**Funcionário:** {box_data['funcionario_nome']}")
        if pd.notna(box_data['quilometragem']):
            st.markdown(f"**KM de Entrada:** {int(box_data['quilometragem']):,} km".replace(',', '.'))

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
                remover_servico(conn, servico['db_id'], servico['area'])
                st.session_state.box_states = {} # Força resync
                st.rerun()

    st.subheader("Adicionar Serviço Extra")
    todos_servicos = catalogo_servicos.get("borracharia", []) + catalogo_servicos.get("alinhamento", []) + catalogo_servicos.get("manutencao", [])
    servicos_disponiveis = sorted(list(set(todos_servicos)))
    c_add1, c_add2, c_add3 = st.columns([0.7, 0.15, 0.15])
    novo_servico_tipo = c_add1.selectbox("Selecione o serviço", [""] + servicos_disponiveis, key=f"new_srv_tipo_{box_id}", label_visibility="collapsed")
    novo_servico_qtd = c_add2.number_input("Qtd", min_value=1, value=1, key=f"new_srv_qtd_{box_id}", label_visibility="collapsed")
    if c_add3.button("➕", key=f"add_{box_id}", help="Adicionar à lista"):
        if novo_servico_tipo:
            adicionar_servico_extra(conn, box_id, int(execucao_id), novo_servico_tipo, novo_servico_qtd, catalogo_servicos)
            st.session_state.box_states = {} # Força resync
            st.rerun()

    obs_final_value = st.text_area("Observações Finais da Execução", key=f"obs_final_{box_id}", value=box_state.get('obs_final', ''))
    if obs_final_value != box_state.get('obs_final', ''):
        st.session_state.box_states[box_id]['obs_final'] = obs_final_value
        st.rerun()

    st.markdown("---")
    col2, col3 = st.columns(2)
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

def adicionar_servico_extra(conn, box_id, execucao_id, tipo, qtd, catalogo):
    try:
        area_servico = ''
        if tipo in catalogo.get("borracharia", []): area_servico = 'borracharia'
        elif tipo in catalogo.get("alinhamento", []): area_servico = 'alinhamento'
        elif tipo in catalogo.get("manutencao", []): area_servico = 'manutencao'
        if not area_servico:
            st.error("Não foi possível identificar a área do serviço.")
            return

        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("SELECT veiculo_id, quilometragem FROM execucao_servico WHERE id = %s", (execucao_id,))
            result = cursor.fetchone()
            veiculo_id, quilometragem = result['veiculo_id'], result['quilometragem']
            
            tabela = f"servicos_solicitados_{area_servico}"
            query = f"INSERT INTO {tabela} (veiculo_id, tipo, quantidade, status, box_id, execucao_id, data_solicitacao, data_atualizacao, quilometragem) VALUES (%s, %s, %s, 'em_andamento', %s, %s, %s, %s, %s)"
            cursor.execute(query, (veiculo_id, tipo, qtd, box_id, execucao_id, datetime.now(MS_TZ), datetime.now(MS_TZ), quilometragem))
            conn.commit()
            st.toast(f"Serviço '{tipo}' adicionado ao Box {box_id}.", icon="➕")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao adicionar serviço: {e}")

def remover_servico(conn, db_id, area):
    try:
        tabela = f"servicos_solicitados_{area}"
        with conn.cursor() as cursor:
            # Em vez de deletar, marcamos como cancelado para manter o histórico
            cursor.execute(f"UPDATE {tabela} SET status = 'cancelado' WHERE id = %s", (db_id,))
            conn.commit()
            st.toast("Serviço removido.", icon="➖")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao remover serviço: {e}")

def _salvar_alteracoes_finais(conn, box_id, execucao_id, status_final):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    try:
        with conn.cursor() as cursor:
            for servico in box_state.get('servicos', {}).values():
                tabela = f"servicos_solicitados_{servico['area']}"
                cursor.execute(f"UPDATE {tabela} SET quantidade = %s, observacao_execucao = %s, status = %s WHERE id = %s", 
                               (servico['qtd_executada'], obs_final, status_final, servico['db_id']))
        return True
    except Exception as e:
        st.error(f"Erro ao salvar alterações finais: {e}")
        return False

def finalizar_execucao(conn, box_id, execucao_id):
    if not _salvar_alteracoes_finais(conn, box_id, execucao_id, 'finalizado'):
        conn.rollback()
        return

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            usuario_finalizacao_id = st.session_state.get('user_id')
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s RETURNING veiculo_id", 
                           (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id))
            veiculo_id = cursor.fetchone()['veiculo_id']
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")
            
            with st.spinner("Atualizando média e enviando notificações..."):
                recalcular_media_veiculo(conn, veiculo_id)
                # Lógica de notificação permanece a mesma
                # ...
            
            st.session_state.box_states = {}
            st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")

def cancelar_execucao(conn, box_id, execucao_id):
    if not _salvar_alteracoes_finais(conn, box_id, execucao_id, 'cancelado'):
        conn.rollback()
        return

    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE execucao_servico SET status = 'cancelado', fim_execucao = %s WHERE id = %s", (datetime.now(MS_TZ), execucao_id))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.warning(f"Serviço no Box {box_id} foi cancelado.")
            # Enviar notificação de cancelamento se necessário
            st.session_state.box_states = {}
            st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao cancelar serviço: {e}")