# /pages/visao_boxes.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, enviar_notificacao_telegram, recalcular_media_veiculo
import psycopg2.extras
from pages.ui_components import render_mobile_navbar
render_mobile_navbar(active_page="boxes")

MS_TZ = pytz.timezone('America/Campo_Grande')

# A inicialização centralizada no main.py é a principal, esta é uma segurança.
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
                st.session_state.box_states[box_id]['servicos'][unique_id]['status'] = 'removido'
                st.rerun()

    st.subheader("Adicionar Serviço Extra")
    todos_servicos = catalogo_servicos.get("borracharia", []) + catalogo_servicos.get("alinhamento", []) + catalogo_servicos.get("manutencao", [])
    servicos_disponiveis = sorted(list(set(todos_servicos)))
    c_add1, c_add2, c_add3 = st.columns([0.7, 0.15, 0.15])
    novo_servico_tipo = c_add1.selectbox("Selecione o serviço", [""] + servicos_disponiveis, key=f"new_srv_tipo_{box_id}", label_visibility="collapsed")
    novo_servico_qtd = c_add2.number_input("Qtd", min_value=1, value=1, key=f"new_srv_qtd_{box_id}", label_visibility="collapsed")
    if c_add3.button("➕", key=f"add_{box_id}", help="Adicionar à lista"):
        if novo_servico_tipo:
            area_servico = ''
            if novo_servico_tipo in catalogo_servicos.get("borracharia", []): area_servico = 'borracharia'
            elif novo_servico_tipo in catalogo_servicos.get("alinhamento", []): area_servico = 'alinhamento'
            elif novo_servico_tipo in catalogo_servicos.get("manutencao", []): area_servico = 'manutencao'
            if area_servico:
                new_service_id = f"novo_{datetime.now().timestamp()}"
                st.session_state.box_states[box_id]['servicos'][new_service_id] = { 'db_id': None, 'tipo': novo_servico_tipo, 'quantidade': novo_servico_qtd, 'qtd_executada': novo_servico_qtd, 'area': area_servico, 'status': 'ativo_novo' }
                st.rerun()
            else: st.error("Não foi possível identificar a área do serviço.")

    obs_final_value = st.text_area("Observações", key=f"obs_final_{box_id}", value=box_state.get('obs_final', ''))
    if obs_final_value != box_state.get('obs_final', ''):
        st.session_state.box_states[box_id]['obs_final'] = obs_final_value
        # Não precisa de rerun aqui, o valor será pego pelos botões de ação

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    if col1.button("💾 Salvar Progresso", key=f"save_{box_id}", use_container_width=True):
        salvar_alteracoes_box(conn, box_id, int(execucao_id))

    if col2.button("✅ Finalizar Box", key=f"finish_{box_id}", type="primary", use_container_width=True):
        finalizar_execucao(conn, box_id, int(execucao_id))

    if col3.button("🔙 Remover do Box", key=f"remove_{box_id}", use_container_width=True):
        remover_do_box(conn, box_id, int(execucao_id))

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

def _persistir_mudancas(cursor, box_state, execucao_id, status_servico):
    obs_final = box_state.get('obs_final', '')
    
    cursor.execute("SELECT veiculo_id, quilometragem FROM execucao_servico WHERE id = %s", (execucao_id,))
    result = cursor.fetchone()
    veiculo_id, quilometragem = result['veiculo_id'], result['quilometragem']

    for unique_id, servico in list(box_state['servicos'].items()):
        if servico.get('status') == 'ativo_novo':
            tabela = f"servicos_solicitados_{servico['area']}"
            query = f"INSERT INTO {tabela} (veiculo_id, tipo, quantidade, status, box_id, execucao_id, data_solicitacao, data_atualizacao, observacao_execucao, quilometragem) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"
            cursor.execute(query, (veiculo_id, servico['tipo'], servico['qtd_executada'], status_servico, int(unique_id.split('_')[-1]), execucao_id, datetime.now(MS_TZ), datetime.now(MS_TZ), obs_final, quilometragem))
            servico['db_id'] = cursor.fetchone()[0]
            servico['status'] = 'ativo'
        elif servico.get('status') in ['ativo', 'removido']:
            db_status = 'cancelado' if servico.get('status') == 'removido' else status_servico
            tabela = f"servicos_solicitados_{servico['area']}"
            query = f"UPDATE {tabela} SET status = %s, quantidade = %s, data_atualizacao = %s, observacao_execucao = %s WHERE id = %s"
            cursor.execute(query, (db_status, servico['qtd_executada'], datetime.now(MS_TZ), obs_final, servico['db_id']))

def salvar_alteracoes_box(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    if not box_state: return
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            _persistir_mudancas(cursor, box_state, execucao_id, status_servico='em_andamento')
        conn.commit()
        st.toast(f"Alterações no Box {box_id} salvas com sucesso!", icon="💾")
        # Força resincronização para atualizar os IDs dos novos serviços no estado
        veiculo_id = pd.read_sql("SELECT veiculo_id FROM execucao_servico WHERE id = %s", conn, params=(execucao_id,)).iloc[0]['veiculo_id']
        sync_box_state_from_db(conn, box_id, veiculo_id)
        st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao salvar alterações: {e}")

def remover_do_box(conn, box_id, execucao_id):
    try:
        with conn.cursor() as cursor:
            tabelas = ["servicos_solicitados_borracharia", "servicos_solicitados_alinhamento", "servicos_solicitados_manutencao"]
            for tabela in tabelas:
                cursor.execute(f"UPDATE {tabela} SET status = 'pendente', box_id = NULL, funcionario_id = NULL, execucao_id = NULL WHERE execucao_id = %s", (execucao_id,))
            
            cursor.execute("UPDATE execucao_servico SET status = 'cancelado', fim_execucao = %s WHERE id = %s", (datetime.now(MS_TZ), execucao_id))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()

            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
            st.success(f"Veículo removido do Box {box_id}. Os serviços estão aguardando nova alocação.")
            st.rerun()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao remover do box: {e}")

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    if not box_state: return
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # Persiste todas as mudanças com o status final
            _persistir_mudancas(cursor, box_state, execucao_id, status_servico='finalizado')
            
            # Finaliza a execução principal
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s WHERE id = %s RETURNING veiculo_id", (datetime.now(MS_TZ), execucao_id))
            veiculo_id = cursor.fetchone()['veiculo_id']
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            
            st.success(f"Box {box_id} finalizado com sucesso!")
            
            with st.spinner("Atualizando média e enviando notificações..."):
                recalcular_media_veiculo(conn, veiculo_id)
                
                # --- LÓGICA DE NOTIFICAÇÃO COMPLETA ---
                # (Esta parte foi recuperada da sua versão funcional)
                chat_id_operacional = st.secrets.get("TELEGRAM_CHAT_ID")
                chat_id_faturamento = st.secrets.get("TELEGRAM_FATURAMENTO_CHAT_ID")

                cursor.execute("SELECT v.placa, v.empresa, f.nome as funcionario_nome, es.nome_motorista, es.quilometragem FROM execucao_servico es JOIN veiculos v ON es.veiculo_id = v.id LEFT JOIN funcionarios f ON es.funcionario_id = f.id WHERE es.id = %s", (execucao_id,))
                info_execucao = cursor.fetchone()
                
                servicos_realizados_etapa = [f"- {s['tipo']} (Qtd: {s['qtd_executada']})" for s in box_state.get('servicos', {}).values() if s.get('status') != 'removido']
                servicos_etapa_str = "\n".join(servicos_realizados_etapa)
                obs_final = box_state.get('obs_final', '')
                
                mensagem_op = (f"▶️ *Etapa Concluída!*\n\n*Serviços realizados no Box {box_id}:*\n{servicos_etapa_str}\n\n*Veículo:* `{info_execucao['placa']}`\n*Mecânico:* {info_execucao['funcionario_nome']}\n*Finalizado por:* {st.session_state.get('user_name')}")
                if obs_final: mensagem_op += f"\n\n*Observação:* _{obs_final}_"

                query_pendentes = "SELECT COUNT(*) FROM (SELECT 1 FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' UNION ALL SELECT 1 FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' UNION ALL SELECT 1 FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente') as pending_services;"
                cursor.execute(query_pendentes, (veiculo_id, veiculo_id, veiculo_id))
                servicos_pendentes_restantes = cursor.fetchone()[0]

                if servicos_pendentes_restantes == 0:
                    mensagem_op += "\n\n✅ *TODOS OS SERVIÇOS CONCLUÍDOS. Encaminhar para faturamento.*"
                    if chat_id_faturamento:
                        query_resumo_total = "SELECT serv.tipo, serv.quantidade, f.nome as funcionario_nome FROM execucao_servico es LEFT JOIN (SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_borracharia UNION ALL SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_alinhamento UNION ALL SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_manutencao) serv ON es.id = serv.execucao_id LEFT JOIN funcionarios f ON serv.funcionario_id = f.id WHERE es.veiculo_id = %s AND es.quilometragem = %s AND es.status = 'finalizado' AND serv.tipo IS NOT NULL"
                        df_resumo = pd.read_sql(query_resumo_total, conn, params=(veiculo_id, info_execucao['quilometragem']))
                        lista_servicos_str = "\n".join([f"- {row['tipo']} (Qtd: {row['quantidade']}) - *Mecânico: {row['funcionario_nome']}*" for _, row in df_resumo.iterrows()])
                        
                        mensagem_fat = (f"✅ *VEÍCULO LIBERADO PARA FATURAMENTO!*\n\n*Placa:* `{info_execucao['placa']}`\n*Empresa:* {info_execucao['empresa']}\n*Motorista:* {info_execucao['nome_motorista'] or 'N/A'}\n*KM:* {info_execucao['quilometragem']}\n*Finalizado por:* {st.session_state.get('user_name')}\n\n*Resumo de Todos os Serviços:*\n{lista_servicos_str}\n\n✅ *AÇÃO:* Alterar venda e deixar pronto para assinar ou pagar!")
                        enviar_notificacao_telegram(mensagem_fat, chat_id_faturamento)

                if chat_id_operacional:
                    enviar_notificacao_telegram(mensagem_op, chat_id_operacional)

            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")
        st.exception(e)