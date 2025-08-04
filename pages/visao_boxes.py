# ... (início do arquivo e outras funções sem alterações)

def finalizar_execucao(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
            # --- ALTERAÇÃO AQUI: Captura o ID do usuário logado ---
            usuario_finalizacao_id = st.session_state.get('user_id')

            for servico in box_state.get('servicos', {}).values():
                if servico['status'] == 'ativo_novo':
                    # ... (lógica de INSERT sem alterações)
                else:
                    # ... (lógica de UPDATE sem alterações)
            
            # --- ALTERAÇÃO AQUI: Adiciona o ID do usuário na atualização ---
            cursor.execute(
                "UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s", 
                (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id)
            )
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")
            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")

# Código completo abaixo
def finalizar_execucao_completo(conn, box_id, execucao_id):
    box_state = st.session_state.box_states.get(box_id, {})
    obs_final = box_state.get('obs_final', '')
    if not box_state: return
    try:
        with conn.cursor() as cursor:
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
            cursor.execute("UPDATE execucao_servico SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s WHERE id = %s", (datetime.now(MS_TZ), usuario_finalizacao_id, execucao_id))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))
            conn.commit()
            st.success(f"Box {box_id} finalizado com sucesso!")
            if box_id in st.session_state.box_states:
                del st.session_state.box_states[box_id]
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao finalizar Box {box_id}: {e}")