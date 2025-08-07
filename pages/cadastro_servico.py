import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, consultar_placa_sinesp

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")
    
    # Inicializações do estado da sessão
    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []

    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = { "placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0 }
    state = st.session_state.cadastro_servico_state
    
    st.markdown("---")

    st.header("1️⃣ Identificação do Veículo")

    # --- Layout com campo de placa e botão de busca SINESP ---
    col_placa, col_botao = st.columns([0.7, 0.3])
    with col_placa:
        placa_input = st.text_input(
            "Digite a placa do veículo", 
            value=state["placa_input"], 
            key="placa_input_cadastro_servico", 
            label_visibility="collapsed"
        ).upper()
    
    with col_botao:
        if st.button("🔎 Buscar Placa SINESP", use_container_width=True, help="Consulta dados públicos do veículo. Use para cadastrar veículos novos mais rápido."):
            if placa_input:
                with st.spinner("Consultando SINESP, por favor aguarde..."):
                    sucesso, resultado = consultar_placa_sinesp(placa_input)
                    if sucesso:
                        st.session_state.modelo_encontrado_sinesp = resultado.get('modelo', '')
                        st.toast(f"Modelo encontrado: {st.session_state.modelo_encontrado_sinesp}", icon="✅")
                    else:
                        st.session_state.modelo_encontrado_sinesp = ''
                        st.error(resultado)
            else:
                st.warning("Digite uma placa para consultar.")
    
    # Lógica principal de busca no banco de dados local
    if placa_input != state["placa_input"]:
        state["placa_input"] = placa_input
        state["veiculo_id"], state["veiculo_info"] = None, None
        st.session_state.servicos_para_adicionar = []
        if 'show_edit_form' in st.session_state:
            del st.session_state['show_edit_form']
        if 'modelo_encontrado_sinesp' in st.session_state:
             del st.session_state['modelo_encontrado_sinesp']
        st.rerun()

    if state["placa_input"] and state["veiculo_id"] is None:
        conn = get_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    query = "SELECT id, empresa, modelo, nome_motorista, contato_motorista FROM veiculos WHERE placa = %s"
                    cursor.execute(query, (state["placa_input"],))
                    resultado = cursor.fetchone()
                    if resultado:
                        state["veiculo_id"], state["veiculo_info"] = resultado["id"], resultado
                    else:
                        st.warning("Veículo não encontrado em seu banco. Cadastre-o abaixo.")
            except Exception as e:
                st.error(f"Erro ao buscar veículo: {e}")
            finally:
                release_connection(conn)

    # Bloco para exibir/editar um veículo que já existe no seu banco
    if state["veiculo_id"]:
        col1, col2 = st.columns([0.7, 0.3])
        with col1:
            st.success(
                f"Veículo: **{state['veiculo_info']['modelo']}** | "
                f"Empresa: **{state['veiculo_info']['empresa']}**\n\n"
                f"Motorista: **{state['veiculo_info']['nome_motorista'] or 'Não informado'}** | "
                f"Contato: **{state['veiculo_info']['contato_motorista'] or 'Não informado'}**"
            )
        with col2:
            if st.button("🔄 Alterar Dados", use_container_width=True):
                st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                st.rerun()

        if st.session_state.get('show_edit_form', False):
            with st.form("form_edit_veiculo"):
                st.info("Altere os dados do veículo e salve.")
                nova_empresa = st.text_input("Empresa", value=state['veiculo_info']['empresa'])
                novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                novo_contato = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                submitted = st.form_submit_button("✅ Salvar Alterações")
                if submitted:
                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor() as cursor:
                                query = "UPDATE veiculos SET empresa = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s"
                                cursor.execute(query, (nova_empresa, novo_motorista, novo_contato, state['veiculo_id']))
                                conn.commit()
                            
                            state['veiculo_info']['empresa'] = nova_empresa
                            state['veiculo_info']['nome_motorista'] = novo_motorista
                            state['veiculo_info']['contato_motorista'] = novo_contato
                            
                            st.session_state.show_edit_form = False
                            st.success("Dados do veículo atualizados com sucesso!")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao atualizar os dados: {e}")
                        finally:
                            release_connection(conn)
    
    # Bloco para cadastrar um novo veículo
    elif state["placa_input"]:
        with st.expander("Cadastrar Novo Veículo", expanded=True):
            with st.form("form_novo_veiculo_rapido"):
                empresa = st.text_input("Empresa *")
                
                # Preenche o campo 'modelo' com o valor da consulta SINESP, se existir
                modelo_default = st.session_state.get('modelo_encontrado_sinesp', '')
                modelo = st.text_input("Modelo do Veículo *", value=modelo_default)
                
                nome_motorista = st.text_input("Nome do Motorista")
                contato_motorista = st.text_input("Contato do Motorista")

                if st.form_submit_button("Cadastrar e Continuar"):
                    if not all([empresa, modelo]):
                        st.warning("Empresa e Modelo são obrigatórios.")
                    else:
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query = """
                                        INSERT INTO veiculos (placa, empresa, modelo, nome_motorista, contato_motorista, data_entrada) 
                                        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
                                    """
                                    cursor.execute(query, (state["placa_input"], empresa, modelo, nome_motorista, contato_motorista, datetime.now(MS_TZ)))
                                    new_id = cursor.fetchone()[0]
                                    conn.commit()
                                    
                                    # Atualiza o state com os dados completos para continuar o fluxo
                                    state["veiculo_id"] = new_id
                                    state["veiculo_info"] = {
                                        "id": new_id, "modelo": modelo, "empresa": empresa,
                                        "nome_motorista": nome_motorista, "contato_motorista": contato_motorista
                                    }
                                    st.success("🚚 Veículo cadastrado com sucesso!")
                                    st.rerun()
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao cadastrar veículo: {e}")
                            finally:
                                release_connection(conn)

    # Bloco para seleção de serviços (só aparece se um veículo estiver selecionado)
    if state["veiculo_id"]:
        st.markdown("---")
        st.header("2️⃣ Seleção de Serviços")
        km_value = state.get("quilometragem") if state.get("quilometragem") else None
        state["quilometragem"] = st.number_input("Quilometragem (Obrigatório)", min_value=1, step=1, value=km_value, key="km_servico", placeholder="Digite a KM...")
        
        servicos_do_banco = get_catalogo_servicos()
        
        def area_de_servico(nome_area, chave_area):
            st.subheader(nome_area)
            servicos_disponiveis = servicos_do_banco.get(chave_area, [])
            
            col1, col2, col3 = st.columns([0.7, 0.15, 0.15])
            with col1:
                servico_selecionado = st.selectbox(f"Selecione o serviço de {nome_area}", options=[""] + servicos_disponiveis, key=f"select_{chave_area}", label_visibility="collapsed")
            with col2:
                quantidade = st.number_input("Qtd", min_value=1, value=1, step=1, key=f"qtd_{chave_area}", label_visibility="collapsed")
            with col3:
                if st.button("➕ Adicionar", key=f"add_{chave_area}", use_container_width=True):
                    if servico_selecionado:
                        novo_servico = {"area": nome_area, "tipo": servico_selecionado, "qtd": quantidade}
                        st.session_state.servicos_para_adicionar.append(novo_servico)
                        st.rerun()
                    else:
                        st.warning("Por favor, selecione um serviço para adicionar.")

        area_de_servico("Borracharia", "borracharia")
        area_de_servico("Alinhamento", "alinhamento")
        area_de_servico("Mecânica", "manutencao")

        st.markdown("---")

        if st.session_state.servicos_para_adicionar:
            st.subheader("Serviços na Lista para Cadastro:")
            for i, servico in enumerate(st.session_state.servicos_para_adicionar):
                col_serv, col_qtd, col_del = st.columns([0.7, 0.15, 0.15])
                col_serv.write(f"**{servico['area']}**: {servico['tipo']}")
                col_qtd.write(f"Qtd: {servico['qtd']}")
                if col_del.button("❌ Remover", key=f"del_{i}", use_container_width=True):
                    st.session_state.servicos_para_adicionar.pop(i)
                    st.rerun()
        
        observacao_geral = st.text_area("Observações gerais para todos os serviços")
        
        st.markdown("---")
        if st.button("Registrar todos os serviços da lista", type="primary"):
            servicos_a_cadastrar = st.session_state.servicos_para_adicionar
            if not servicos_a_cadastrar:
                st.warning("⚠️ Nenhum serviço foi adicionado à lista.")
            elif not state["quilometragem"] or state["quilometragem"] <= 0:
                st.error("❌ A quilometragem é obrigatória e deve ser maior que zero.")
            else:
                conn = get_connection()
                if not conn: return
                sucesso = True
                try:
                    with conn.cursor() as cursor:
                        table_map = {"Borracharia": "servicos_solicitados_borracharia", "Alinhamento": "servicos_solicitados_alinhamento", "Mecânica": "servicos_solicitados_manutencao"}
                        for s in servicos_a_cadastrar:
                            table_name = table_map.get(s['area'])
                            query = f"INSERT INTO {table_name} (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)"
                            cursor.execute(query, (state["veiculo_id"], s['tipo'], s['qtd'], observacao_geral, state["quilometragem"], datetime.now(MS_TZ), datetime.now(MS_TZ)))
                        conn.commit()
                except Exception as e:
                    conn.rollback()
                    st.error(f"❌ Erro ao salvar serviços: {e}")
                    sucesso = False
                finally:
                    release_connection(conn)
                if sucesso:
                    st.success("✅ Serviços cadastrados com sucesso!")
                    st.session_state.servicos_para_adicionar = []
                    st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
                    st.balloons()
                    st.rerun()

    # Botão de limpar a tela
    if st.button("Limpar tela e iniciar novo cadastro"):
        st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
        st.session_state.servicos_para_adicionar = []
        if 'modelo_encontrado_sinesp' in st.session_state:
             del st.session_state['modelo_encontrado_sinesp']
        st.rerun()