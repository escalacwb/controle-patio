import streamlit as st

import pandas as pd

from database import get_connection, release_connection

from datetime import datetime

import pytz



MS_TZ = pytz.timezone('America/Campo_Grande')



def alocar_servicos():

    st.title("🚚 Alocação de Serviços por Área")

    st.markdown("Selecione um veículo com serviços pendentes e aloque-o a um box e funcionário.")

    

    rerun_flag = False

    conn = get_connection()

    if not conn:

        st.error("Falha ao conectar ao banco de dados.")

        return



    try:

        query_veiculos_pendentes = """

            WITH status_por_veiculo AS (

                SELECT

                    veiculo_id,

                    COUNT(*) FILTER (WHERE status = 'pendente') AS pendentes,

                    COUNT(*) FILTER (WHERE status = 'em_andamento') AS em_andamento

                FROM (

                    SELECT veiculo_id, status FROM servicos_solicitados_borracharia WHERE status IN ('pendente', 'em_andamento')

                    UNION ALL

                    SELECT veiculo_id, status FROM servicos_solicitados_alinhamento WHERE status IN ('pendente', 'em_andamento')

                    UNION ALL

                    SELECT veiculo_id, status FROM servicos_solicitados_manutencao WHERE status IN ('pendente', 'em_andamento')

                ) AS todos_servicos

                GROUP BY veiculo_id

            )

            SELECT v.id, v.placa, v.empresa

            FROM veiculos v

            JOIN status_por_veiculo sv ON v.id = sv.veiculo_id

            WHERE sv.pendentes > 0 AND sv.em_andamento = 0

            ORDER BY v.placa;

        """

        veiculos_df = pd.read_sql(query_veiculos_pendentes, conn)

        

        # --- MUDANÇA: Adicionado "WHERE id > 0" para filtrar os registros de migração ---

        funcionarios_df = pd.read_sql("SELECT id, nome FROM funcionarios WHERE id > 0 ORDER BY nome", conn)

        boxes_df = pd.read_sql("SELECT id FROM boxes WHERE ocupado = FALSE AND id > 0 ORDER BY id", conn)



        veiculo_options = [f"{row['id']} - {row['placa']} ({row['empresa']})" for _, row in veiculos_df.iterrows()]

        funcionario_options = [f"{row['id']} - {row['nome']}" for _, row in funcionarios_df.iterrows()]

        box_options = [str(row['id']) for _, row in boxes_df.iterrows()]



        if not veiculo_options:

            st.info("🎉 Nenhum veículo aguardando alocação no momento.")

            return



        selected_veiculo_display = st.selectbox("Selecione o Veículo para Alocar", veiculo_options, key="veiculo_select")

        

        if selected_veiculo_display:

            veiculo_id_int = int(selected_veiculo_display.split(" - ")[0])

            query_areas_pendentes = """

                SELECT 'borracharia' AS area FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' UNION

                SELECT 'alinhamento' AS area FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' UNION

                SELECT 'manutencao' AS area FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente';

            """

            areas_df = pd.read_sql(query_areas_pendentes, conn, params=(veiculo_id_int, veiculo_id_int, veiculo_id_int))

            areas_com_servico_pendente = [a.replace('manutencao', 'Manutenção Mecânica').title() for a in areas_df['area'].tolist()]



            if not areas_com_servico_pendente:

                st.warning("Este veículo não parece ter mais serviços pendentes.")

                return



            quilometragem_cadastrada = 0

            try:

                with conn.cursor() as cursor:

                    query_km = """

                        (SELECT quilometragem FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1) UNION

                        (SELECT quilometragem FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1) UNION

                        (SELECT quilometragem FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)

                        LIMIT 1;

                    """

                    cursor.execute(query_km, (veiculo_id_int, veiculo_id_int, veiculo_id_int))

                    resultado_km = cursor.fetchone()

                    if resultado_km and resultado_km[0] is not None:

                        quilometragem_cadastrada = resultado_km[0]

            except Exception as e:

                st.warning(f"Não foi possível buscar a KM do cadastro: {e}")

            

            with st.form("form_alocacao"):

                st.subheader(f"Alocar para: {selected_veiculo_display.split(' (')[0]}")

                area_selecionada_display = st.selectbox("Área do Serviço a ser executado", areas_com_servico_pendente, key="area_select")

                col1, col2 = st.columns(2)

                with col1: box_selecionado = st.selectbox("Box Disponível", box_options, key="box_select")

                with col2: funcionario_selecionado = st.selectbox("Funcionário Responsável", funcionario_options, key="funcionario_select")

                if quilometragem_cadastrada > 0: st.info(f"Quilometragem do cadastro: **{quilometragem_cadastrada} km**")

                else: st.error("ERRO: Não foi encontrada a quilometragem do cadastro.")

                

                if st.form_submit_button("Alocar Serviços e Iniciar Execução"):

                    if not all([box_selecionado, funcionario_selecionado, area_selecionada_display]):

                        st.error("❌ Todos os campos são obrigatórios.")

                    else:

                        try:

                            with conn.cursor() as cursor:

                                funcionario_id_int, box_id_int = int(funcionario_selecionado.split(" - ")[0]), int(box_selecionado)

                                area_selecionada = area_selecionada_display.replace('Manutenção Mecânica', 'manutencao').lower()

                                

                                usuario_alocacao_id = st.session_state.get('user_id')



                                cursor.execute(

                                    "SELECT nome_motorista, contato_motorista FROM veiculos WHERE id = %s",

                                    (veiculo_id_int,)

                                )

                                motorista_info = cursor.fetchone()

                                nome_motorista_atual = motorista_info[0] if motorista_info else None

                                contato_motorista_atual = motorista_info[1] if motorista_info else None



                                insert_exec_query = """

                                    INSERT INTO execucao_servico 

                                    (veiculo_id, box_id, funcionario_id, quilometragem, status, inicio_execucao, usuario_alocacao_id, nome_motorista, contato_motorista) 

                                    VALUES (%s, %s, %s, %s, 'em_andamento', %s, %s, %s, %s) RETURNING id

                                """

                                cursor.execute(insert_exec_query, (

                                    veiculo_id_int, box_id_int, funcionario_id_int, 

                                    quilometragem_cadastrada, datetime.now(MS_TZ), usuario_alocacao_id,

                                    nome_motorista_atual, contato_motorista_atual

                                ))

                                execucao_id = cursor.fetchone()[0]



                                tabela_servico = f"servicos_solicitados_{area_selecionada}"

                                update_solicitado_query = f"UPDATE {tabela_servico} SET box_id = %s, funcionario_id = %s, status = 'em_andamento', data_atualizacao = %s, execucao_id = %s WHERE veiculo_id = %s AND status = 'pendente';"

                                cursor.execute(update_solicitado_query, (box_id_int, funcionario_id_int, datetime.now(MS_TZ), execucao_id, veiculo_id_int))

                                

                                cursor.execute("UPDATE boxes SET ocupado = TRUE WHERE id = %s;", (box_id_int,))

                                conn.commit()

                                st.success(f"✅ Sucesso! Veículo alocado no Box {box_id_int}.")

                                rerun_flag = True

                        except Exception as e:

                            conn.rollback()

                            st.error(f"❌ Erro Crítico ao alocar serviços: {e}")

    except Exception as e:

        st.error(f"❌ Erro ao carregar dados da página: {e}")

        st.exception(e)

    finally:

        release_connection(conn)

    

    if rerun_flag:

        st.rerun()