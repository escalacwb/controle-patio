import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, enviar_notificacao_telegram

MS_TZ = pytz.timezone('America/Campo_Grande')

if 'box_states' not in st.session_state:
    st.session_state.box_states = {}

def visao_boxes():
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

def get_estado_atual_boxes(conn):
    query = """
        SELECT b.id, b.area as box_area, es.id as execucao_id, v.placa, v.empresa,
               f.nome as funcionario_nome, es.veiculo_id, es.funcionario_id, es.quilometragem
        FROM boxes b
        LEFT JOIN execucao_servico es ON b.id = es.box_id AND es.status = 'em_andamento'
        LEFT JOIN veiculos v ON es.veiculo_id = v.id
        LEFT JOIN funcionarios f ON es.funcionario_id = f.id
        ORDER BY b.id;
    """
    return pd.read_sql(query, conn, columns=['id'])

def render_box(conn, box_data, catalogo_servicos):
    box_id = int(box_data['id'])
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
        if pd.notna(box_data['quilometragem']):
            st.markdown(f"**KM de Entrada:** {int(box_data['quilometragem']):,} km".replace(',', '.'))
    st.subheader("Serviços em Execução")
    servicos_ativos = {uid: s for uid, s in box_state.get('servicos', {}).items() if s.get('status') != 'removido'}
    for unique_id, servico in servicos_ativos.items():
        c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
        c1.write(servico['tipo'])
        nova_qtd = c2.number_input("Qtd", value=servico['qtd_executada'], min_value=0, key=f"qtd_{unique_id}", label_visibility="collapsed")
        st.session_state.box_states[box_id]['servicos'][unique_id]['qtd_executada'] = nova_qtd
        if c3.button("X", key=f"del_{unique_id}", help=f"Remover {servico['tipo']}"):
            st.session_state.box_states[box_id]['servicos'][unique_id]['status'] = 'removido'
            st.rerun()
    for unique_id_novo, servico_novo in box_state.get('servicos_novos', {}).items():
        st.success(f"Adicionado: {servico_novo['tipo']} (Qtd: {servico_novo['quantidade']})")
    with st.form(f"form_add_and_finish_{box_id}"):
        st.subheader("Adicionar Serviço Extra")
        todos_servicos = catalogo_servicos.get("borracharia", []) + catalogo_servicos.get("alinhamento", []) + catalogo_servicos.get("manutencao", [])
        servicos_disponiveis = sorted(list(set(todos_servicos)))
        c_add1, c_add2, c_add3 = st.columns([0.7, 0.15, 0.15])
        novo_servico_tipo = c_add1.selectbox("Selecione o serviço", [""] + servicos_disponiveis, key=f"new_srv_tipo_{box_id}", label_visibility="collapsed")
        novo_servico_qtd = c_add2.number_input("Qtd", min_value=1, value=1, key=f"new_srv_qtd_{box_id}", label_visibility="collapsed")
        if c_add3.form_submit_button("➕", help=f"Adicionar à lista"):
            if novo_servico_tipo:
                area_servico = ''
                if novo_servico_tipo in catalogo_servicos.get("borracharia", []): area_servico = 'borracharia'
                elif novo_servico_tipo in catalogo_servicos.get("alinhamento", []): area_servico = 'alinhamento'
                elif novo_servico_tipo in catalogo_servicos.get("manutencao", []): area_servico = 'manutencao'
                if area_servico:
                    new_service_id = f"novo_{len(box_state.get('servicos', []))}"
                    st.session_state.box_states[box_id]['servicos'][new_service_id] = { 'db_id': None, 'tipo': novo_servico_tipo, 'quantidade': novo_servico_qtd, 'qtd_executada': novo_servico_qtd, 'area': area_servico, 'status': 'ativo_novo' }
                    st.rerun()
                else: st.error("Não foi possível identificar a área do serviço.")
        st.markdown("---")
        obs_final = st.text_area("Observações Finais da Execução", key=f"obs_final_{box_id}", value=box_state.get('obs_final', ''))
        st.session_state.box_states[box_id]['obs_final'] = obs_final
        
        # --- LINHA CORRIGIDA ---
        if st.form_submit_button("✅ Salvar e Finalizar Box", type="primary", use_container_width=True):
            finalizar_execucao(conn, box_id, int(execucao_id))
            st.rerun()

def sync_box_state_from_db(conn, box_id, veiculo_id):
    query = """
        (SELECT 'borracharia' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'alinhamento' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'manutencao' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
    """
    df_servicos = pd.read_sql(query, conn, params=[veiculo_id, box_id] * 3)
    servicos_dict = {f"{row['area']}_{row['id']}": {'db_id': row['id'], 'tipo': row['tipo'], 'quantidade': row['quantidade'], 'qtd_executada': row['quantidade'], 'area': row['area'], 'status': 'ativo'} for _, row in df_servicos.iterrows()}
    st.session_state.box_states[box_id] = {'servicos': servicos_dict, 'obs_final': '','observacao_geral': df_servicos['observacao'].iloc[0] if not df_servicos.empty and pd.notna(df_servicos['observacao'].iloc[0]) else ""}

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
            usuario_finalizacao_id = st.session_state.get('user_id')
            usuario_finalizacao_nome = st.session_state.get('user_name')
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
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s", (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")
            
            query_placa = "SELECT v.placa FROM veiculos v JOIN execucao_servico es ON v.id = es.veiculo_id WHERE es.id = %s"
            df_placa = pd.read_sql(query_placa, conn, params=(execucao_id,))
            placa_veiculo = df_placa.iloc[0]['placa'] if not df_placa.empty else "N/A"
            mensagem = (f"✅ *Serviço Finalizado!*\n\n*Veículo:* {placa_veiculo}\n*Box:* {box_id}\n*Finalizado por:* {usuario_finalizacao_nome}\n")
            if obs_final:
                mensagem += f"*Observação:* {obs_final}"
            enviar_notificacao_telegram(mensagem)
            
            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")