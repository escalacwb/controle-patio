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
    
    # --- BOTÃO DE SINCRONIZAÇÃO GLOBAL ---
    if st.button("🔄 Sincronizar Todos os Boxes"):
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
            b.id, 
            b.area as box_area, 
            es.id as execucao_id, 
            v.placa, 
            v.empresa, 
            v.nome_motorista, 
            v.contato_motorista,
            v.modelo,                     -- << NOVO: modelo do veículo
            f.nome as funcionario_nome, 
            es.veiculo_id, 
            es.funcionario_id, 
            es.quilometragem
        FROM boxes b
        LEFT JOIN execucao_servico es 
               ON b.id = es.box_id AND es.status = 'em_andamento'
        LEFT JOIN veiculos v 
               ON es.veiculo_id = v.id
        LEFT JOIN funcionarios f 
               ON es.funcionario_id = f.id
        WHERE b.id > 0
        ORDER BY b.id;
    """
    return pd.read_sql(query, conn, index_col='id')



def render_box(conn, box_data, catalogo_servicos):
    box_id = int(box_data.name)
    execucao_id = box_data['execucao_id']

    if pd.isna(execucao_id):
        st.success(f"🧰 BOX {box_id} ✅ Livre")
        if box_id in st.session_state.box_states:
            del st.session_state.box_states[box_id]
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

        # Modelo do veículo (vem de v.modelo no SELECT de get_estado_atual_boxes)
        if 'modelo' in box_data.index and pd.notna(box_data['modelo']) and str(box_data['modelo']).strip():
            st.markdown(f"**Modelo:** {box_data['modelo']}")

        # Observações dos serviços deste box (do CADASTRO do serviço)
        # aceita tanto 'observacao' quanto 'observacao_cadastro' (para compat)
        obs_servicos = []
        for s in st.session_state.box_states.get(box_id, {}).get('servicos', {}).values():
            if s.get('status') == 'removido':
                continue
            cad = s.get('observacao') or s.get('observacao_cadastro')
            if cad and str(cad).strip():
                obs_servicos.append(str(cad).strip())
        if obs_servicos:
            resumo_obs = " | ".join(sorted(set(obs_servicos)))
            st.markdown(f"**Observações (serviços):** {resumo_obs}")

        c_unassign, _ = st.columns([0.5, 0.5])
        if c_unassign.button("↩️ Retirar do Box", key=f"unassign_block_{box_id}", use_container_width=True):
            desalocar_bloco_do_box(conn, box_id, int(execucao_id))
            st.session_state.box_states = {}
            st.rerun()

    st.subheader("Serviços em Execução")
    for unique_id, servico in list(box_state.get('servicos', {}).items()):
        if servico.get('status') != 'removido':
            c1, c2 = st.columns([0.75, 0.25])
            c1.write(servico['tipo'])

            # Observações por serviço
            obs_cad = servico.get('observacao') or servico.get('observacao_cadastro')
            if obs_cad and str(obs_cad).strip():
                c1.caption(f"Obs. cadastro: {obs_cad}")
            obs_exec = servico.get('observacao_execucao')
            if obs_exec and str(obs_exec).strip():
                c1.caption(f"Obs. execução: {obs_exec}")

            nova_qtd = c2.number_input(
                "Qtd",
                value=servico['qtd_executada'],
                min_value=0,
                key=f"qtd_{unique_id}",
                label_visibility="collapsed"
            )
            if nova_qtd != servico['qtd_executada']:
                st.session_state.box_states[box_id]['servicos'][unique_id]['qtd_executada'] = nova_qtd
                st.rerun()

    st.subheader("Adicionar Serviço Extra")
    todos_servicos = (
        catalogo_servicos.get("borracharia", []) +
        catalogo_servicos.get("alinhamento", []) +
        catalogo_servicos.get("manutencao", [])
    )
    servicos_disponiveis = sorted(list(set(todos_servicos)))
    c_add1, c_add2, c_add3 = st.columns([0.7, 0.15, 0.15])
    novo_servico_tipo = c_add1.selectbox(
        "Selecione o serviço",
        [""] + servicos_disponiveis,
        key=f"new_srv_tipo_{box_id}",
        label_visibility="collapsed"
    )
    novo_servico_qtd = c_add2.number_input(
        "Qtd",
        min_value=1,
        value=1,
        key=f"new_srv_qtd_{box_id}",
        label_visibility="collapsed"
    )
    if c_add3.button("➕", key=f"add_{box_id}", help="Adicionar à lista"):
        if novo_servico_tipo:
            adicionar_servico_extra(conn, box_id, int(execucao_id), novo_servico_tipo, novo_servico_qtd, catalogo_servicos)
            st.session_state.box_states = {}
            st.rerun()

    obs_final_value = st.text_area(
        "Observações Finais da Execução",
        key=f"obs_final_{box_id}",
        value=box_state.get('obs_final', '')
    )
    if obs_final_value != box_state.get('obs_final', ''):
        st.session_state.box_states[box_id]['obs_final'] = obs_final_value
        st.rerun()

    st.markdown("---")
    if st.button("✅ Finalizar Box", key=f"finish_{box_id}", type="primary", use_container_width=True):
        finalizar_execucao(conn, box_id, int(execucao_id))


def sync_box_state_from_db(conn, box_id, veiculo_id):
    query = """
        (SELECT 'borracharia'  AS area, id, tipo, quantidade,
                observacao AS observacao_cadastro,               -- << NOVO
                observacao_execucao
           FROM servicos_solicitados_borracharia
          WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
        UNION ALL
        (SELECT 'alinhamento' AS area, id, tipo, quantidade,
                observacao AS observacao_cadastro,               -- << NOVO
                observacao_execucao
           FROM servicos_solicitados_alinhamento
          WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
        UNION ALL
        (SELECT 'manutencao'  AS area, id, tipo, quantidade,
                observacao AS observacao_cadastro,               -- << NOVO
                observacao_execucao
           FROM servicos_solicitados_manutencao
          WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento')
    """
    df_servicos = pd.read_sql(query, conn, params=[veiculo_id, box_id] * 3)

    servicos_dict = {
        f"{row['area']}_{row['id']}": {
            'db_id': row['id'],
            'tipo': row['tipo'],
            'quantidade': row['quantidade'],
            'qtd_executada': row['quantidade'],
            'area': row['area'],
            'status': 'ativo',
            'observacao_cadastro': (
                row['observacao_cadastro'] if pd.notna(row['observacao_cadastro']) else None
            ),                                                   # << NOVO
            'observacao_execucao': (
                row['observacao_execucao'] if pd.notna(row['observacao_execucao']) else None
            ),                                                   # << NOVO (mantido)
        } 
        for _, row in df_servicos.iterrows()
    }

    # mantém seu comportamento atual para obs_final
    obs_geral = df_servicos['observacao_execucao'].dropna().unique() \
        if 'observacao_execucao' in df_servicos.columns else []
    st.session_state.box_states[box_id] = {
        'servicos': servicos_dict,
        'obs_final': (obs_geral[0] if len(obs_geral) > 0 else "")
    }


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
            cursor.execute("SELECT veiculo_id, quilometragem, nome_motorista FROM execucao_servico WHERE id = %s", (execucao_id,))
            result = cursor.fetchone()
            veiculo_id, quilometragem, nome_motorista = result['veiculo_id'], result['quilometragem'], result['nome_motorista']
            
            tabela = f"servicos_solicitados_{area_servico}"
            query = f"""
                INSERT INTO {tabela}
                    (veiculo_id, tipo, quantidade, status, box_id, execucao_id,
                     data_solicitacao, data_atualizacao, quilometragem)
                VALUES
                    (%s, %s, %s, 'em_andamento', %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (veiculo_id, tipo, qtd, box_id, execucao_id,
                                    datetime.now(MS_TZ), datetime.now(MS_TZ), quilometragem))
            conn.commit()
            st.toast(f"Serviço '{tipo}' adicionado ao Box {box_id}.", icon="➕")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao adicionar serviço: {e}")

def desalocar_bloco_do_box(conn, box_id, execucao_id):
    try:
        with conn.cursor() as cursor:
            for tabela in ["servicos_solicitados_borracharia",
                           "servicos_solicitados_alinhamento",
                           "servicos_solicitados_manutencao"]:
                cursor.execute(
                    f"""UPDATE {tabela}
                           SET status = 'pendente',
                               box_id = NULL,
                               funcionario_id = NULL,
                               execucao_id = NULL,
                               data_atualizacao = %s
                         WHERE execucao_id = %s""",
                    (datetime.now(MS_TZ), execucao_id)
                )

            cursor.execute("DELETE FROM execucao_servico WHERE id = %s", (execucao_id,))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
        st.info(f"Execução retirada do Box {box_id}. Serviços voltaram para a fila (pendente).")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao retirar bloco do box: {e}")

def _salvar_alteracoes_finais(conn, box_id, execucao_id, status_final, obs_final):
    try:
        with conn.cursor() as cursor:
            for servico in st.session_state.box_states.get(box_id, {}).get('servicos', {}).values():
                tabela = f"servicos_solicitados_{servico['area']}"
                cursor.execute(
                    f"""UPDATE {tabela}
                           SET quantidade = %s,
                               observacao_execucao = %s,
                               status = %s,
                               data_atualizacao = %s
                         WHERE id = %s""",
                    (servico['qtd_executada'], obs_final, status_final, datetime.now(MS_TZ), servico['db_id'])
                )
        return True
    except Exception as e:
        st.error(f"Erro ao salvar alterações finais: {e}")
        return False

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # PASSO 1: COLETAR DADOS PARA AS NOTIFICAÇÕES ANTES DE QUALQUER ALTERAÇÃO
            usuario_finalizacao_id = st.session_state.get('user_id')
            usuario_finalizacao_nome = st.session_state.get('user_name', 'N/A')

            cursor.execute("""
                SELECT 
                    es.veiculo_id, es.quilometragem, es.nome_motorista,
                    v.placa, v.empresa, f.nome as funcionario_nome
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                LEFT JOIN funcionarios f ON es.funcionario_id = f.id
                WHERE es.id = %s
            """, (execucao_id,))
            info_notificacao = cursor.fetchone()
            veiculo_id = info_notificacao['veiculo_id']
            quilometragem = info_notificacao['quilometragem']

            query_pendentes = "SELECT COUNT(*) FROM (SELECT 1 FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' UNION ALL SELECT 1 FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' UNION ALL SELECT 1 FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente') as pending_services;"
            cursor.execute(query_pendentes, (veiculo_id, veiculo_id, veiculo_id))
            servicos_pendentes_restantes = cursor.fetchone()[0]

            # PASSO 2: SALVAR ALTERAÇÕES NO BANCO DE DADOS
            if not _salvar_alteracoes_finais(conn, box_id, execucao_id, 'finalizado', obs_final):
                conn.rollback()
                return

            cursor.execute(
                "UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s",
                (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id)
            )
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()

            st.success(f"Box {box_id} finalizado com sucesso!")

            # PASSO 3: AÇÕES PÓS-COMMIT (CÁLCULO DE MÉDIA E NOTIFICAÇÕES)
            with st.spinner("Atualizando média e enviando notificações..."):
                recalcular_media_veiculo(conn, veiculo_id)
                
                chat_id_operacional = st.secrets.get("TELEGRAM_CHAT_ID")
                chat_id_faturamento = st.secrets.get("TELEGRAM_FATURAMENTO_CHAT_ID")

                servicos_realizados_etapa = [f"- {s['tipo']} (Qtd: {s['qtd_executada']})" for s in box_state.get('servicos', {}).values() if s.get('status') != 'removido']
                servicos_etapa_str = "\n".join(servicos_realizados_etapa) if servicos_realizados_etapa else "Nenhum serviço executado."
                
                mensagem_op = (
                    f"▶️ *Etapa Concluída!*\n\n"
                    f"*Serviços realizados no Box {box_id}:*\n"
                    f"{servicos_etapa_str}\n\n"
                    f"*Veículo:* `{info_notificacao['placa']}`\n"
                    f"*Mecânico:* {info_notificacao['funcionario_nome']}\n"
                    f"*Finalizado por:* {usuario_finalizacao_nome}"
                )
                
                if obs_final:
                    mensagem_op += f"\n\n*Observação:* _{obs_final}_"

                if servicos_pendentes_restantes == 0:
                    mensagem_op += "\n\n✅ *TODOS OS SERVIÇOS CONCLUÍDOS. Encaminhar para faturamento.*"
                    
                    if chat_id_faturamento:
                        query_resumo_total = """
                            SELECT serv.tipo, serv.quantidade, f.nome as funcionario_nome
                            FROM execucao_servico es
                            LEFT JOIN (
                                SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_borracharia WHERE status = 'finalizado' UNION ALL
                                SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_alinhamento WHERE status = 'finalizado' UNION ALL
                                SELECT execucao_id, tipo, quantidade, funcionario_id FROM servicos_solicitados_manutencao WHERE status = 'finalizado'
                            ) serv ON es.id = serv.execucao_id
                            LEFT JOIN funcionarios f ON es.funcionario_id = f.id
                            WHERE es.veiculo_id = %s AND es.quilometragem = %s
                        """
                        cursor.execute(query_resumo_total, (veiculo_id, quilometragem))
                        resumo_servicos = cursor.fetchall()
                        
                        lista_servicos_str = "\n".join([f"- {s['tipo']} (Qtd: {s['quantidade']}) - *Mecânico: {s.get('funcionario_nome') or 'N/A'}*" for s in resumo_servicos])
                        
                        mensagem_fat = (
                            f"✅ *VEÍCULO LIBERADO PARA FATURAMENTO!*\n\n"
                            f"*Placa:* `{info_notificacao['placa']}`\n"
                            f"*Empresa:* {info_notificacao['empresa']}\n"
                            f"*Motorista:* {info_notificacao['nome_motorista'] or 'N/A'}\n"
                            f"*KM:* {quilometragem}\n"
                            f"*Finalizado por (Sistema):* {usuario_finalizacao_nome}\n\n"
                            f"*Resumo de Todos os Serviços:*\n{lista_servicos_str}\n\n"
                            f"✅ *AÇÃO:* Alterar venda e deixar pronto para assinar ou pagar!"
                        )
                        enviar_notificacao_telegram(mensagem_fat, chat_id_faturamento)

                if chat_id_operacional:
                    enviar_notificacao_telegram(mensagem_op, chat_id_operacional)

            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro Crítico ao finalizar Box {box_id}: {e}")
        st.exception(e)