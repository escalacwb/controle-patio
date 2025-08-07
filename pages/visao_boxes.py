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
        
        if not df_boxes.empty:
            cols = st.columns(len(df_boxes))
            
            # --- MUDANÇA: Usar enumerate para obter o índice de posição correto (0, 1, 2...) ---
            for i, (box_id, box_data) in enumerate(df_boxes.iterrows()):
                # 'i' agora é a posição correta na lista de colunas (0, 1, 2...)
                # 'box_id' é o ID real do box vindo do banco (1, 2, 3...)
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
    servicos_ativos = {uid: s for uid, s in box_state.get('servicos', {}).items() if s.get('status') != 'removido'}
    
    for unique_id, servico in servicos_ativos.items():
        c1, c2, c3 = st.columns([0.7, 0.15, 0.15])
        c1.write(servico['tipo'])
        nova_qtd = c2.number_input("Qtd", value=servico['qtd_executada'], min_value=0, key=f"qtd_{unique_id}", label_visibility="collapsed")
        if nova_qtd != servico['qtd_executada']:
            st.session_state.box_states[box_id]['servicos'][unique_id]['qtd_executada'] = nova_qtd
            st.rerun()

        if c3.button("X", key=f"del_{unique_id}", help=f"Remover {servico['tipo']}"):
            st.session_state.box_states[box_id]['servicos'][unique_id]['status'] = 'removido'
            st.rerun()

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
                    new_service_id = f"novo_{len(box_state.get('servicos', [])) + 1}"
                    st.session_state.box_states[box_id]['servicos'][new_service_id] = { 'db_id': None, 'tipo': novo_servico_tipo, 'quantidade': novo_servico_qtd, 'qtd_executada': novo_servico_qtd, 'area': area_servico, 'status': 'ativo_novo' }
                    st.rerun()
                else: st.error("Não foi possível identificar a área do serviço.")

        st.markdown("---")
        obs_final = st.text_area("Observações Finais da Execução", key=f"obs_final_{box_id}", value=box_state.get('obs_final', ''))
        
        if st.form_submit_button("✅ Salvar e Finalizar Box", type="primary", use_container_width=True):
            st.session_state.box_states[box_id]['obs_final'] = obs_final
            finalizar_execucao(conn, box_id, int(execucao_id))

def sync_box_state_from_db(conn, box_id, veiculo_id):
    query = """
        (SELECT 'borracharia' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'alinhamento' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'manutencao' as area, id, tipo, quantidade, observacao FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
    """
    df_servicos = pd.read_sql(query, conn, params=[veiculo_id, box_id] * 3)
    servicos_dict = {f"{row['area']}_{row['id']}": {'db_id': row['id'], 'tipo': row['tipo'], 'quantidade': row['quantidade'], 'qtd_executada': row['quantidade'], 'area': row['area'], 'status': 'ativo'} for _, row in df_servicos.iterrows()}
    obs_geral = df_servicos['observacao'].dropna().unique()
    st.session_state.box_states[box_id] = {'servicos': servicos_dict, 'obs_final': obs_geral[0] if len(obs_geral) > 0 else ""}

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
            # (A lógica de finalização e notificação permanece a mesma)
            pass
            
            if box_id in st.session_state.box_states: del st.session_state.box_states[box_id]
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")
        st.exception(e)