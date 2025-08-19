# /pages/revisao_proativa.py

import streamlit as st
import pandas as pd
from pages.ui_components import render_mobile_navbar
render_mobile_navbar(active_page="revisao")
from database import get_connection, release_connection
from datetime import datetime
import pytz
from urllib.parse import quote_plus
import re
from utils import formatar_telefone, buscar_clientes_por_similaridade, get_cliente_details
import psycopg2.extras


MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📞 Revisão Proativa de Clientes")
    st.markdown("Identifique, contate e atualize os dados de veículos que precisam de uma nova revisão.")

    # NOVO: Botão para recarregar os dados da página
    col1, col2 = st.columns([0.8, 0.2])
    with col2:
        if st.button("🔄 Atualizar Dados", use_container_width=True, help="Recarrega todos os dados do banco de dados para esta página."):
            st.rerun()

    # --- INICIALIZAÇÃO DO ESTADO DA SESSÃO ---
    if 'page_number' not in st.session_state:
        st.session_state.page_number = 0
    if 'rp_editing_vehicle_id' not in st.session_state:
        st.session_state.rp_editing_vehicle_id = None
    if 'rp_editing_company_for_vehicle_id' not in st.session_state:
        st.session_state.rp_editing_company_for_vehicle_id = None

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    # --- PAINEL DE EDIÇÃO DE EMPRESA (LÓGICA EXISTENTE MANTIDA) ---
    if st.session_state.rp_editing_company_for_vehicle_id:
        veiculo_id_para_editar = st.session_state.rp_editing_company_for_vehicle_id
        df_v_edit = pd.read_sql("SELECT placa, empresa, cliente_id FROM veiculos WHERE id = %s", conn, params=(int(veiculo_id_para_editar),))
        
        if not df_v_edit.empty:
            v_edit_data = df_v_edit.iloc[0]
            with st.expander(f"✏️ Alterando Empresa do Veículo: {v_edit_data['placa']}", expanded=True):
                
                if 'rp_busca_empresa_edit' not in st.session_state:
                    st.session_state.rp_busca_empresa_edit = v_edit_data['empresa'] or ""

                busca_empresa_edit = st.text_input("Digite para buscar a nova empresa", value=st.session_state.rp_busca_empresa_edit, key="rp_busca_empresa_input")

                if busca_empresa_edit != st.session_state.rp_busca_empresa_edit:
                    st.session_state.rp_busca_empresa_edit = busca_empresa_edit
                    st.session_state.pop('rp_last_selected_client_id', None)
                    st.session_state.pop('rp_details_responsavel', None)
                    st.rerun()

                cliente_id_final = v_edit_data['cliente_id']
                nome_empresa_final = st.session_state.rp_busca_empresa_edit
                cliente_id_selecionado_edit = None

                if len(st.session_state.rp_busca_empresa_edit) >= 3:
                    resultados_busca = buscar_clientes_por_similaridade(st.session_state.rp_busca_empresa_edit)
                    if resultados_busca:
                        opcoes_cliente_edit = {"": None}
                        for id_c, nome_e, nome_f in resultados_busca:
                            texto_exibicao = f"{nome_e} (Fantasia: {nome_f})" if nome_f and nome_f.strip() and nome_e.lower() != nome_f.lower() else nome_e
                            opcoes_cliente_edit[texto_exibicao] = id_c
                        opcoes_cliente_edit[f"Nenhum destes. Criar nova empresa '{st.session_state.rp_busca_empresa_edit}'"] = "NOVO"
                        
                        cliente_selecionado_str = st.selectbox("Selecione a empresa encontrada ou confirme a criação de uma nova:", options=list(opcoes_cliente_edit.keys()), key="rp_select_edit_empresa")
                        
                        cliente_id_selecionado_edit = opcoes_cliente_edit[cliente_selecionado_str]
                        if cliente_id_selecionado_edit and cliente_id_selecionado_edit != "NOVO":
                            cliente_id_final = cliente_id_selecionado_edit
                            nome_empresa_final = next((item[1] for item in resultados_busca if item[0] == cliente_id_final), st.session_state.rp_busca_empresa_edit)
                        elif cliente_id_selecionado_edit == "NOVO":
                            cliente_id_final = None

                if cliente_id_selecionado_edit != st.session_state.get('rp_last_selected_client_id'):
                    st.session_state.rp_last_selected_client_id = cliente_id_selecionado_edit
                    if isinstance(cliente_id_selecionado_edit, int):
                        st.session_state.rp_details_responsavel = get_cliente_details(cliente_id_selecionado_edit)
                    else:
                        st.session_state.rp_details_responsavel = {}
                    st.session_state.rp_editing_responsavel = False
                    st.rerun()
                
                st.markdown("---")
                st.subheader("Dados do Responsável pela Frota")
                
                details = st.session_state.get('rp_details_responsavel', {})
                nome_resp = details.get('nome_responsavel', "") if details else ""
                contato_resp = details.get('contato_responsavel', "") if details else ""

                if st.session_state.get('rp_editing_responsavel', False):
                    with st.form("form_rp_edit_responsavel"):
                        st.info("Você está editando os dados do responsável para esta empresa.")
                        novo_nome_resp = st.text_input("Nome do Responsável", value=nome_resp)
                        novo_contato_resp = st.text_input("Contato do Responsável", value=contato_resp)
                        if st.form_submit_button("✅ Salvar Responsável"):
                            id_cliente_para_salvar = st.session_state.get('rp_last_selected_client_id')
                            if id_cliente_para_salvar and isinstance(id_cliente_para_salvar, int):
                                try:
                                    with conn.cursor() as cursor:
                                        cursor.execute("UPDATE clientes SET nome_responsavel = %s, contato_responsavel = %s, data_atualizacao_contato = NOW() WHERE id = %s", (novo_nome_resp, formatar_telefone(novo_contato_resp), int(id_cliente_para_salvar)))
                                        conn.commit()
                                        st.success("Responsável atualizado!")
                                        st.session_state.rp_editing_responsavel = False
                                        st.session_state.rp_last_selected_client_id = None
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Erro ao salvar: {e}")
                            else:
                                st.warning("Selecione um cliente existente da lista para poder editar o responsável.")
                else:
                    col_nome, col_contato, col_btn = st.columns([0.4, 0.4, 0.2])
                    col_nome.text_input("Nome do Responsável", value=nome_resp, disabled=True, key="rp_resp_nome")
                    col_contato.text_input("Contato do Responsável", value=contato_resp, disabled=True, key="rp_resp_contato")
                    with col_btn:
                        st.write(""); st.write("")
                        if st.button("✏️ Alterar", use_container_width=True, key="rp_edit_resp_btn"):
                            if isinstance(st.session_state.get('rp_last_selected_client_id'), int):
                                st.session_state.rp_editing_responsavel = True
                                st.rerun()
                            else:
                                st.toast("Selecione um cliente da lista para poder editar.", icon="⚠️")

                st.markdown("---")
                s_col, c_col = st.columns(2)
                if s_col.button("✅ Salvar Vinculação da Empresa", type="primary", use_container_width=True):
                    try:
                        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                            if cliente_id_final is None and nome_empresa_final:
                                cursor.execute("INSERT INTO clientes (nome_empresa) VALUES (%s) RETURNING id", (nome_empresa_final,))
                                cliente_id_final = cursor.fetchone()['id']
                            
                            if cliente_id_final:
                                query_veiculo = "UPDATE veiculos SET empresa = %s, cliente_id = %s WHERE id = %s"
                                cursor.execute(query_veiculo, (nome_empresa_final, cliente_id_final, int(veiculo_id_para_editar)))
                                conn.commit()
                                st.success("Vinculação da empresa atualizada com sucesso!")
                                st.session_state.rp_editing_company_for_vehicle_id = None
                                st.session_state.pop('rp_busca_empresa_edit', None)
                                st.rerun()
                            else:
                                st.error("Nenhum cliente selecionado ou criado para vincular.")
                    except Exception as e:
                        st.error(f"Erro ao salvar vinculação: {e}")

                if c_col.button("❌ Cancelar Alteração de Empresa", use_container_width=True):
                    st.session_state.rp_editing_company_for_vehicle_id = None
                    st.session_state.pop('rp_busca_empresa_edit', None)
                    st.rerun()

    # --- SEÇÃO DE FORMULÁRIO DE EDIÇÃO DE VEÍCULO (LÓGICA EXISTENTE MANTIDA) ---
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
                                cursor.execute("""
                                    UPDATE veiculos 
                                    SET modelo = %s, ano_modelo = %s, nome_motorista = %s, 
                                        contato_motorista = %s, data_atualizacao_contato = NOW()
                                    WHERE id = %s
                                """, (novo_modelo, novo_ano, novo_motorista, formatar_telefone(novo_contato_motorista), int(v_edit['id'])))
                                conn.commit()
                                st.success(f"Veículo {v_edit['placa']} atualizado!")
                                st.session_state.rp_editing_vehicle_id = None
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar veículo: {e}")
                    if cancel_v.form_submit_button("❌ Cancelar", use_container_width=True):
                        st.session_state.rp_editing_vehicle_id = None
                        st.rerun()

    st.markdown("---")
    
    # --- NOVA INTERFACE DE SELEÇÃO DE MODO ---
    st.subheader("1. Selecione o Modo de Busca")
    modo_busca = st.radio(
        "Buscar veículos por:",
        ("Quilometragem", "Tempo desde a Última Visita"),
        horizontal=True,
        label_visibility="collapsed"
    )

    # --- LÓGICA CONDICIONAL PARA EXIBIR OS FILTROS CORRETOS ---
    if modo_busca == "Quilometragem":
        intervalo_revisao_km = st.number_input(
            "Avisar a cada (KM)",
            min_value=1000, max_value=100000, value=10000, step=1000
        )
    else: # Modo "Tempo"
        col1, col2 = st.columns(2)
        intervalo_tempo_valor = col1.number_input(
            "Tempo desde a última visita",
            min_value=1, value=6, step=1
        )
        intervalo_tempo_unidade = col2.selectbox(
            "Unidade de Tempo",
            ("meses", "dias")
        )

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
        df['km_rodados'] = df['km_atual_estimada'] - df['km_ultima_visita']
        
        # --- LÓGICA DE FILTRAGEM ADAPTATIVA ---
        if modo_busca == "Quilometragem":
            st.subheader(f"Veículos Sugeridos para Contato (KM rodados > {intervalo_revisao_km})")
            veiculos_para_contatar = df[df['km_rodados'] >= intervalo_revisao_km].copy()
            veiculos_para_contatar.sort_values(by='km_rodados', ascending=False, inplace=True)
        else: # Modo "Tempo"
            if intervalo_tempo_unidade == "meses":
                dias_limite = intervalo_tempo_valor * 30 
                st.subheader(f"Veículos Sugeridos para Contato ({intervalo_tempo_valor} {intervalo_tempo_unidade} sem visita)")
            else: # dias
                dias_limite = intervalo_tempo_valor
                st.subheader(f"Veículos Sugeridos para Contato ({intervalo_tempo_valor} {intervalo_tempo_unidade} sem visita)")

            veiculos_para_contatar = df[df['dias_desde_ultima_visita'] >= dias_limite].copy()
            veiculos_para_contatar.sort_values(by='dias_desde_ultima_visita', ascending=False, inplace=True)
        
        st.subheader(f"Encontrados: {len(veiculos_para_contatar)} veículos")

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
                        # --- Exibição condicional da métrica principal ---
                        if modo_busca == "Quilometragem":
                             st.metric("KM Rodados Desde a Última Visita", f"{int(veiculo['km_rodados']):,}".replace(',', '.'))
                        else:
                             st.metric("Dias Desde a Última Visita", f"{int(veiculo['dias_desde_ultima_visita'])}")

                    
                    cap_col1, cap_col2 = st.columns([0.7, 0.3])
                    with cap_col1:
                        media_km_diaria = veiculo['media_km_diaria']
                        media_formatada = f"{media_km_diaria:.2f}" if pd.notna(media_km_diaria) else "N/A"
                        st.caption(f"Última visita em {veiculo['data_ultima_visita'].strftime('%d/%m/%Y')} com {int(veiculo['km_ultima_visita']):,} km. Média de {media_formatada} km/dia.".replace(',', '.'))
                    with cap_col2:
                        st.link_button("✏️ Ajustar Média", url=f"ajustar_media_km?veiculo_id={veiculo['veiculo_id']}", use_container_width=True)

                    b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
                    
                    def create_whatsapp_link(numero, msg_text):
                        if not numero or not isinstance(numero, str): return None
                        num_limpo = "55" + re.sub(r'\D', '', numero)
                        if len(num_limpo) < 12: return None
                        return f"https://wa.me/{num_limpo}?text={quote_plus(msg_text)}"
                    
                    # --- GERAÇÃO DE MENSAGEM CONDICIONAL ---
                    if modo_busca == "Quilometragem":
                        km_ultima_visita_str = f"{int(veiculo['km_ultima_visita']):,}".replace(',', '.')
                        km_atual_estimada_str = f"{int(veiculo['km_atual_estimada']):,}".replace(',', '.')
                        km_rodados_str = f"{int(veiculo['km_rodados']):,}".replace(',', '.')
                        
                        msg_motorista = (
                            f"Olá, {veiculo['nome_motorista']}! Tudo bem?\n\n"
                            f"Aqui é da Capital Truck Center. Vimos que seu caminhão {veiculo['modelo']}, placa {veiculo['placa']}, está precisando de uma nova revisão.\n\n"
                            f"A última foi com {km_ultima_visita_str} km e, com base no histórico de rodagem dele, já rodou aproximadamente {km_rodados_str} km desde então, estando agora com cerca de {km_atual_estimada_str} km.\n\n"
                            f"Para garantir a segurança e o bom funcionamento do veículo, é importante fazer uma nova revisão. Responda esta mensagem para organizarmos os próximos passos!"
                        )
                        msg_gestor = (
                            f"Prezado(a) {veiculo['nome_responsavel']}, tudo bem?\n\n"
                            f"Somos da Capital Truck Center e, em nosso acompanhamento proativo da sua frota, identificamos uma necessidade de revisão para o veículo {veiculo['modelo']}, placa {veiculo['placa']}.\n\n"
                            f"A última manutenção foi em {veiculo['data_ultima_visita'].strftime('%d/%m/%Y')} com {km_ultima_visita_str} km. Com base no histórico de rodagem, o veículo rodou aproximadamente {km_rodados_str} km desde então, e nossa projeção indica que está agora com cerca de {km_atual_estimada_str} km.\n\n"
                            f"Para manter a manutenção preventiva em dia, gostaríamos de alinhar os próximos passos."
                        )
                    else: # Modo "Tempo"
                        dias_sem_visita = int(veiculo['dias_desde_ultima_visita'])
                        data_ultima_visita_str = veiculo['data_ultima_visita'].strftime('%d/%m/%Y')
                        
                        if dias_sem_visita > 45:
                            tempo_str = f"mais de {dias_sem_visita // 30} meses"
                        else:
                            tempo_str = f"{dias_sem_visita} dias"

                        msg_motorista = (
                            f"Olá, {veiculo['nome_motorista']}! Tudo bem?\n\n"
                            f"Aqui é da Capital Truck Center. Estamos entrando em contato pois notamos que já faz um tempo desde a última manutenção do seu caminhão {veiculo['modelo']}, placa {veiculo['placa']}.\n\n"
                            f"A última visita dele aqui conosco foi em {data_ultima_visita_str}, ou seja, há {tempo_str}.\n\n"
                            f"Para manter a manutenção preventiva em dia e garantir a segurança, gostaríamos de agendar uma nova revisão. Responda esta mensagem para organizarmos os próximos passos!"
                        )
                        msg_gestor = (
                            f"Prezado(a) {veiculo['nome_responsavel']}, tudo bem?\n\n"
                            f"Somos da Capital Truck Center e, em nosso acompanhamento proativo da sua frota, notamos que o veículo {veiculo['modelo']}, placa {veiculo['placa']}, não passa por uma revisão em nossa oficina há {tempo_str} (desde {data_ultima_visita_str}).\n\n"
                            f"Para manter a manutenção preventiva em dia e garantir a performance e segurança do ativo, gostaríamos de alinhar os próximos passos para uma nova revisão."
                        )

                    link_motorista = create_whatsapp_link(veiculo['contato_motorista'], msg_motorista)
                    link_gestor = create_whatsapp_link(veiculo['contato_responsavel'], msg_gestor)

                    b_col1.link_button("📲 Falar com Motorista", url=link_motorista or "", use_container_width=True, disabled=not link_motorista)
                    b_col2.link_button("📲 Falar com Gestor", url=link_gestor or "", use_container_width=True, disabled=not link_gestor)
                    
                    if b_col3.button("✏️ Alt. Veículo", key=f"edit_v_{veiculo['veiculo_id']}", use_container_width=True):
                        st.session_state.rp_editing_vehicle_id = veiculo['veiculo_id']
                        st.session_state.rp_editing_company_for_vehicle_id = None
                        st.rerun()
                    if b_col4.button("✏️ Alt. Empresa", key=f"edit_c_{veiculo['veiculo_id']}", use_container_width=True, disabled=pd.isna(veiculo['cliente_id'])):
                        st.session_state.rp_editing_company_for_vehicle_id = veiculo['veiculo_id']
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
