# /pages/revisao_proativa.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from datetime import datetime
import pytz
from urllib.parse import quote_plus
import re
from utils import formatar_telefone

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📞 Revisão Proativa de Clientes")
    st.markdown("Identifique, contate e atualize os dados de veículos que precisam de uma nova revisão.")

    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 0
    # O estado 'rp_dismissed_vehicles' foi removido, pois a nova lógica usa o banco de dados.
    if 'rp_editing_vehicle_id' not in st.session_state:
        st.session_state.rp_editing_vehicle_id = None
    if 'rp_editing_client_id' not in st.session_state:
        st.session_state.rp_editing_client_id = None

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    # --- SEÇÃO DE FORMULÁRIOS DE EDIÇÃO (APARECEM NO TOPO QUANDO ATIVOS) ---
    if st.session_state.rp_editing_vehicle_id:
        veiculo_id = st.session_state.rp_editing_vehicle_id
        df_v = pd.read_sql("SELECT * FROM veiculos WHERE id = %s", conn, params=(int(veiculo_id),))
        if not df_v.empty:
            v_edit = df_v.iloc[0]
            with st.expander(f"✏️ Editando Veículo: {v_edit['placa']}", expanded=True):
                with st.form("form_edit_vehicle_rp"):
                    ve_col1, ve_col2 = st.columns(2)
                    novo_modelo = ve_col1.text_input("Modelo", value=v_edit['modelo'] or '')
                    novo_ano = ve_col2.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(v_edit['ano_modelo'] or datetime.now().year), step=1)
                    ve_col3, ve_col4 = st.columns(2)
                    novo_motorista = ve_col3.text_input("Nome do Motorista", value=v_edit['nome_motorista'] or '')
                    novo_contato_motorista = ve_col4.text_input("Contato do Motorista", value=v_edit['contato_motorista'] or '')
                    
                    submit_v, cancel_v = st.columns(2)
                    if submit_v.form_submit_button("✅ Salvar Veículo", type="primary", use_container_width=True):
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE veiculos SET modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s",
                                               (novo_modelo, novo_ano, novo_motorista, formatar_telefone(novo_contato_motorista), int(v_edit['id'])))
                                conn.commit()
                                st.success(f"Veículo {v_edit['placa']} atualizado!")
                                st.session_state.rp_editing_vehicle_id = None
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar veículo: {e}")
                    if cancel_v.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.session_state.rp_editing_vehicle_id = None
                        st.rerun()

    if st.session_state.rp_editing_client_id:
        cliente_id = st.session_state.rp_editing_client_id
        df_c = pd.read_sql("SELECT * FROM clientes WHERE id = %s", conn, params=(int(cliente_id),))
        if not df_c.empty:
            c_edit = df_c.iloc[0]
            with st.expander(f"✏️ Editando Empresa: {c_edit['nome_empresa']}", expanded=True):
                with st.form("form_edit_client_rp"):
                    ce_col1, ce_col2 = st.columns(2)
                    novo_resp = ce_col1.text_input("Nome do Responsável", value=c_edit['nome_responsavel'] or '')
                    novo_contato_resp = ce_col2.text_input("Contato do Responsável", value=c_edit['contato_responsavel'] or '')
                    
                    submit_c, cancel_c = st.columns(2)
                    if submit_c.form_submit_button("✅ Salvar Empresa", type="primary", use_container_width=True):
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute("UPDATE clientes SET nome_responsavel = %s, contato_responsavel = %s WHERE id = %s",
                                               (novo_resp, formatar_telefone(novo_contato_resp), int(c_edit['id'])))
                                conn.commit()
                                st.success(f"Cliente {c_edit['nome_empresa']} atualizado!")
                                st.session_state.rp_editing_client_id = None
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar cliente: {e}")
                    if cancel_c.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.session_state.rp_editing_client_id = None
                        st.rerun()

    st.markdown("---")
    intervalo_revisao_km = st.number_input("Avisar a cada (KM)", min_value=1000, max_value=100000, value=10000, step=1000,
                                       help="O sistema irá alertar sobre veículos que rodaram aproximadamente esta quilometragem desde a última visita.")
    st.markdown("---")

    try:
        with st.spinner("Buscando veículos e fazendo previsões..."):
            query = """
                WITH ranked_visits AS (
                    SELECT veiculo_id, id as execucao_id, fim_execucao, quilometragem,
                           ROW_NUMBER() OVER(PARTITION BY veiculo_id ORDER BY fim_execucao DESC) as rn
                    FROM execucao_servico WHERE status = 'finalizado' AND quilometragem IS NOT NULL
                ),
                ultima_visita AS (
                    SELECT veiculo_id, execucao_id, fim_execucao as data_ultima_visita, quilometragem as km_ultima_visita
                    FROM ranked_visits WHERE rn = 1
                ),
                servicos_ultima_visita AS (
                    SELECT uv.veiculo_id, STRING_AGG(s.tipo, '; ') as servicos_anteriores
                    FROM ultima_visita uv
                    LEFT JOIN (
                        SELECT execucao_id, tipo FROM servicos_solicitados_borracharia UNION ALL
                        SELECT execucao_id, tipo FROM servicos_solicitados_alinhamento UNION ALL
                        SELECT execucao_id, tipo FROM servicos_solicitados_manutencao
                    ) s ON uv.execucao_id = s.execucao_id GROUP BY uv.veiculo_id
                )
                SELECT
                    v.id as veiculo_id, v.placa, v.empresa, v.modelo, v.ano_modelo,
                    v.nome_motorista, v.contato_motorista, v.media_km_diaria,
                    v.cliente_id, c.nome_responsavel, c.contato_responsavel,
                    uv.data_ultima_visita, uv.km_ultima_visita, suv.servicos_anteriores
                FROM veiculos v
                JOIN ultima_visita uv ON v.id = uv.veiculo_id
                LEFT JOIN servicos_ultima_visita suv ON v.id = suv.veiculo_id
                LEFT JOIN clientes c ON v.cliente_id = c.id
                WHERE v.media_km_diaria IS NOT NULL AND v.media_km_diaria > 0
                AND v.data_revisao_proativa IS NULL;
            """
            df = pd.read_sql(query, conn)

        if df.empty:
            st.info("Não há veículos com média de KM calculada para exibir.")
            st.stop()

        df['dias_desde_ultima_visita'] = (pd.Timestamp.now(tz=MS_TZ) - pd.to_datetime(df['data_ultima_visita'], utc=True).dt.tz_convert(MS_TZ)).dt.days
        df['km_atual_estimada'] = df['km_ultima_visita'] + (df['dias_desde_ultima_visita'] * df['media_km_diaria'])
        
        veiculos_para_contatar = df[df['km_atual_estimada'] >= (df['km_ultima_visita'] + intervalo_revisao_km)].copy()
        veiculos_para_contatar.sort_values(by='km_atual_estimada', ascending=False, inplace=True)
        
        st.subheader(f"Veículos Sugeridos para Contato ({len(veiculos_para_contatar)}):")

        if veiculos_para_contatar.empty:
            st.success("🎉 Nenhum veículo atendeu aos critérios para o contato proativo no momento.")
        else:
            page_size = 20
            start_index = st.session_state.page_number * page_size
            end_index = start_index + page_size
            total_pages = (len(veiculos_para_contatar) + page_size - 1) // page_size
            veiculos_pagina_atual = veiculos_para_contatar.iloc[start_index:end_index]

            for _, veiculo in veiculos_pagina_atual.iterrows():
                with st.container(border=True):
                    col1, col2 = st.columns([0.7, 0.3])
                    with col1:
                        st.markdown(f"**Veículo:** `{veiculo['placa']}` - {veiculo['modelo']} ({veiculo['empresa']})")
                        st.info(f"**Motorista:** {veiculo['nome_motorista'] or 'N/A'} | **Contato:** {veiculo['contato_motorista'] or 'N/A'}")
                        st.warning(f"**Gestor Frota:** {veiculo['nome_responsavel'] or 'N/A'} | **Contato:** {veiculo['contato_responsavel'] or 'N/A'}")
                        st.markdown(f"**Últimos Serviços:** *{veiculo['servicos_anteriores'] or 'Nenhum serviço registrado na última visita.'}*")
                    with col2:
                        st.metric("KM Estimada Atual", f"{int(veiculo['km_atual_estimada']):,}".replace(',', '.'))
                    
                    st.caption(f"Última visita em {veiculo['data_ultima_visita'].strftime('%d/%m/%Y')} com {int(veiculo['km_ultima_visita']):,} km. Média de {int(veiculo['media_km_diaria'])} km/dia.".replace(',', '.'))
                    
                    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
                    
                    def get_whatsapp_link(nome, numero, veiculo_info):
                        if not numero or not isinstance(numero, str): return None
                        num_limpo = "55" + re.sub(r'\D', '', numero)
                        if len(num_limpo) < 12: return None
                        msg = f"Olá, {nome}! Tudo bem? Vimos que seu caminhão {veiculo_info['modelo']} (placa {veiculo_info['placa']}) está próximo da quilometragem de revisão ({int(veiculo_info['km_atual_estimada']):,} km). Gostaria de agendar um horário?".replace(',', '.')
                        return f"https://wa.me/{num_limpo}?text={quote_plus(msg)}"

                    link_motorista = get_whatsapp_link(veiculo['nome_motorista'], veiculo['contato_motorista'], veiculo)
                    link_gestor = get_whatsapp_link(veiculo['nome_responsavel'], veiculo['contato_responsavel'], veiculo)

                    b_col1.link_button("📲 Falar com Motorista", url=link_motorista or "", use_container_width=True, disabled=not link_motorista)
                    b_col2.link_button("📲 Falar com Gestor", url=link_gestor or "", use_container_width=True, disabled=not link_gestor)
                    
                    if b_col3.button("✏️ Alt. Veículo", key=f"edit_v_{veiculo['veiculo_id']}", use_container_width=True):
                        st.session_state.rp_editing_vehicle_id = veiculo['veiculo_id']
                        st.session_state.rp_editing_client_id = None
                        st.rerun()
                    if b_col4.button("✏️ Alt. Empresa", key=f"edit_c_{veiculo['veiculo_id']}", use_container_width=True, disabled=pd.isna(veiculo['cliente_id'])):
                        st.session_state.rp_editing_client_id = veiculo['cliente_id']
                        st.session_state.rp_editing_vehicle_id = None
                        st.rerun()
                    if b_col5.button("✅ Contato Feito", key=f"dismiss_{veiculo['veiculo_id']}", use_container_width=True):
                        try:
                            with conn.cursor() as cursor:
                                cursor.execute(
                                    "UPDATE veiculos SET data_revisao_proativa = %s WHERE id = %s",
                                    (datetime.now(MS_TZ).date(), int(veiculo['veiculo_id']))
                                )
                            conn.commit()
                            st.toast(f"Veículo {veiculo['placa']} marcado como contatado.", icon="👍")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao marcar veículo: {e}")

            st.markdown("---")
            col_prev, col_info, col_next = st.columns([1, 2, 1])
            if col_prev.button("⬅️ Anterior", use_container_width=True, disabled=(st.session_state.page_number == 0)):
                st.session_state.page_number -= 1
                st.rerun()
            
            col_info.markdown(f"<div style='text-align: center; font-size: 1.2rem;'>Página {st.session_state.page_number + 1} de {total_pages}</div>", unsafe_allow_html=True)
            
            if col_next.button("Próxima ➡️", use_container_width=True, disabled=(st.session_state.page_number >= total_pages - 1)):
                st.session_state.page_number += 1
                st.rerun()

    except Exception as e:
        st.error(f"Ocorreu um erro ao processar os dados: {e}")
        st.exception(e)
    finally:
        release_connection(conn)