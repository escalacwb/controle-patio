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
            # Garante que as colunas tenham um tamanho mínimo para melhor visualização
            num_cols = len(df_boxes)
            cols = st.columns(num_cols)
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
        if box_id in st.session_state.box_states:
            del st.session_state.box_states[box_id]
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

        # ⬅️ Botão ÚNICO DO BOX: retirar bloco inteiro (voltar tudo para pendente)
        c_unassign, _ = st.columns([0.5, 0.5])
        if c_unassign.button("↩️ Retirar do Box (voltar para pendente)", key=f"unassign_block_{box_id}", use_container_width=True):
            desalocar_bloco_do_box(conn, box_id, int(execucao_id))
            st.session_state.box_states = {}
            st.rerun()

    st.subheader("Serviços em Execução")
    for unique_id, servico in list(box_state.get('servicos', {}).items()):
        if servico.get('status') != 'removido':
            # Apenas nome e quantidade (sem botões por serviço)
            c1, c2 = st.columns([0.75, 0.25])
            c1.write(servico['tipo'])
            nova_qtd = c2.number_input("Qtd", value=servico['qtd_executada'], min_value=0,
                                      key=f"qtd_{unique_id}", label_visibility="collapsed")
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
    novo_servico_tipo = c_add1.selectbox("Selecione o serviço", [""] + servicos_disponiveis,
                                         key=f"new_srv_tipo_{box_id}", label_visibility="collapsed")
    novo_servico_qtd = c_add2.number_input("Qtd", min_value=1, value=1, key=f"new_srv_qtd_{box_id}",
                                            label_visibility="collapsed")
    if c_add3.button("➕", key=f"add_{box_id}", help="Adicionar à lista"):
        if novo_servico_tipo:
            adicionar_servico_extra(conn, box_id, int(execucao_id), novo_servico_tipo, novo_servico_qtd, catalogo_servicos)
            st.session_state.box_states = {} # Força resync
            st.rerun()

    obs_final_value = st.text_area("Observações Finais da Execução", key=f"obs_final_{box_id}",
                                     value=box_state.get('obs_final', ''))
    if obs_final_value != box_state.get('obs_final', ''):
        st.session_state.box_states[box_id]['obs_final'] = obs_final_value
        st.rerun()

    st.markdown("---")
    # ✅ Apenas um botão: Finalizar Box
    if st.button("✅ Finalizar Box", key=f"finish_{box_id}", type="primary", use_container_width=True):
        finalizar_execucao(conn, box_id, int(execucao_id))

def sync_box_state_from_db(conn, box_id, veiculo_id):
    query = """
        (SELECT 'borracharia' as area, id, tipo, quantidade, observacao_execucao as observacao
           FROM servicos_solicitados_borracharia
          WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'alinhamento' as area, id, tipo, quantidade, observacao_execucao as observacao
           FROM servicos_solicitados_alinhamento
          WHERE veiculo_id = %s AND box_id = %s AND status = 'em_andamento') UNION ALL
        (SELECT 'manutencao' as area, id, tipo, quantidade, observacao_execucao as observacao
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
            'status': 'ativo'
        } for _, row in df_servicos.iterrows()
    }
    obs_geral = df_servicos['observacao'].dropna().unique()
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
            cursor.execute("SELECT veiculo_id, quilometragem FROM execucao_servico WHERE id = %s", (execucao_id,))
            result = cursor.fetchone()
            veiculo_id, quilometragem = result['veiculo_id'], result['quilometragem']
            
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

# === Botão ÚNICO: retirar bloco inteiro do box (voltar tudo para pendente)
def desalocar_bloco_do_box(conn, box_id, execucao_id):
    """
    Retira a execução do box devolvendo TODOS os serviços para 'pendente' e
    removendo a linha de execucao_servico (evita colisão com constraints).
    """
    try:
        with conn.cursor() as cursor:
            # 1) Serviços -> pendente (limpa vínculos)
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

            # 2) Remove a execução (não deixa pendente para não violar constraints)
            cursor.execute("DELETE FROM execucao_servico WHERE id = %s", (execucao_id,))

            # 3) Libera o box
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))

            conn.commit()

        st.info(f"Execução retirada do Box {box_id}. Serviços voltaram para a fila (pendente).")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao retirar bloco do box: {e}")

def _salvar_alteracoes_finais(conn, box_id, execucao_id, status_final, obs_final):
    """
    Atualiza todas as linhas de serviço desse box com a quantidade executada e status_final,
    gravando a observação final da execução. Retorna True/False.
    """
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
    """
    Sempre FINALIZA a execução, mesmo com quantidades = 0.
    Envia notificações para os grupos de Telegram definidos.
    """
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # 1) Finaliza todos os serviços (inclusive qty 0) com a observação final
            if not _salvar_alteracoes_finais(conn, box_id, execucao_id, 'finalizado', obs_final):
                conn.rollback()
                return

            # 2) Marca a execução como 'finalizado'
            usuario_finalizacao_id = st.session_state.get('user_id')
            cursor.execute(
                "UPDATE execucao_servico "
                "   SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s "
                " WHERE id = %s "
                " RETURNING veiculo_id",
                (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id)
            )
            veiculo_id = cursor.fetchone()['veiculo_id']

            # 3) Libera o box
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()

            st.success(f"Box {box_id} finalizado com sucesso!")

            # 4) Atualizações adicionais e envio de notificações
            with st.spinner("Atualizando média e enviando notificações..."):
                recalcular_media_veiculo(conn, veiculo_id)

                # --- INÍCIO: LÓGICA DE NOTIFICAÇÃO DO TELEGRAM ---
                try:
                    # Busca dados do veículo para a mensagem
                    cursor.execute("SELECT placa, empresa FROM veiculos WHERE id = %s", (veiculo_id,))
                    veiculo_info = cursor.fetchone()
                    placa = veiculo_info['placa'] if veiculo_info else 'N/A'
                    empresa = veiculo_info['empresa'] if veiculo_info else 'N/A'

                    # Mensagem 1 (Detalhada, para grupo de operação)
                    servicos_realizados = box_state.get('servicos', {}).values()
                    servicos_filtrados = [s for s in servicos_realizados if s.get('qtd_executada', 0) > 0]
                    
                    if servicos_filtrados:
                        lista_servicos_str = ""
                        for servico in servicos_filtrados:
                            lista_servicos_str += f"- {servico['tipo']}: {servico['qtd_executada']} unid.\n"

                        mensagem_operacao = (
                            f"✅ *Serviço Finalizado no Box {box_id}*\n\n"
                            f"🚚 *Veículo:* `{placa}` ({empresa})\n\n"
                            f"*Serviços Executados:*\n{lista_servicos_str}"
                        )
                        if obs_final:
                            mensagem_operacao += f"\n*Observações:*\n_{obs_final}_"
                    
                        # Mensagem 2 (Simples, para grupo de liberação)
                        mensagem_liberacao = f"➡️ Veículo *{placa}* ({empresa}) finalizado e liberado do Box {box_id}."
                        
                        # Use st.secrets para buscar os IDs dos grupos
                        # Você deve configurar estes segredos no seu ambiente Streamlit
                        # Ex: [telegram]
                        # chat_id_operacao = "-10012345678"
                        # chat_id_liberacao = "-10087654321"
                        id_grupo_operacao = st.secrets["telegram"]["chat_id_operacao"]
                        id_grupo_liberacao = st.secrets["telegram"]["chat_id_liberacao"]

                        enviar_notificacao_telegram(mensagem_operacao, id_grupo_operacao)
                        enviar_notificacao_telegram(mensagem_liberacao, id_grupo_liberacao)
                        
                        st.toast("Notificações enviadas!", icon="📢")

                except Exception as e:
                    st.warning(f"O serviço foi finalizado, mas houve um erro ao enviar a notificação do Telegram: {e}")
                # --- FIM: LÓGICA DE NOTIFICAÇÃO DO TELEGRAM ---

            st.session_state.box_states = {}
            st.rerun()

    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")