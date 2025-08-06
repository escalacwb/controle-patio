import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")
    
    # Inicializa o estado da sessão para a lista de serviços
    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []

    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = { "placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0 }
    state = st.session_state.cadastro_servico_state
    
    st.markdown("---")

    st.header("1️⃣ Identificação do Veículo")
    placa_input = st.text_input("Digite a placa do veículo", value=state["placa_input"], key="placa_input_cadastro_servico").upper()
    if placa_input != state["placa_input"]:
        state["placa_input"], state["veiculo_id"], state["veiculo_info"] = placa_input, None, None
        st.session_state.servicos_para_adicionar = []
        # --- MUDANÇA 1: Limpar o estado do formulário de edição ao trocar de placa ---
        if 'show_edit_form' in st.session_state:
            del st.session_state['show_edit_form']
        st.rerun()

    if state["placa_input"] and state["veiculo_id"] is None:
        conn = get_connection()
        if conn:
            try:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT id, empresa, modelo FROM veiculos WHERE placa = %s", (state["placa_input"],))
                    resultado = cursor.fetchone()
                    if resultado:
                        state["veiculo_id"], state["veiculo_info"] = resultado["id"], resultado
                    else:
                        st.warning("Veículo não encontrado. Cadastre-o abaixo.")
            except Exception as e:
                st.error(f"Erro ao buscar veículo: {e}")
            finally:
                release_connection(conn)

    # --- MUDANÇA 2: LÓGICA DE EXIBIÇÃO E EDIÇÃO DO VEÍCULO ---
    if state["veiculo_id"]:
        col1, col2 = st.columns([0.7, 0.3])
        with col1:
            # Exibe os dados do veículo que estão na memória (session_state)
            st.success(f"Veículo: **{state['veiculo_info']['modelo']}** | Empresa Atual: **{state['veiculo_info']['empresa']}**")
        with col2:
            # Botão para mostrar/esconder o formulário de edição
            if st.button("🔄 Alterar Empresa", use_container_width=True):
                st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                st.rerun()

        # O formulário de edição só aparece se o botão for clicado
        if st.session_state.get('show_edit_form', False):
            with st.form("form_edit_empresa"):
                st.info("Digite o novo nome da empresa para o veículo selecionado.")
                nova_empresa = st.text_input(
                    "Novo nome da Empresa", 
                    value=state['veiculo_info']['empresa'],
                    label_visibility="collapsed",
                    placeholder="Digite o novo nome da empresa"
                )
                submitted = st.form_submit_button("✅ Salvar Alteração")
                
                if submitted:
                    if nova_empresa:
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    # Comando SQL para atualizar a empresa no banco de dados
                                    query = "UPDATE veiculos SET empresa = %s WHERE id = %s"
                                    cursor.execute(query, (nova_empresa, state['veiculo_id']))
                                    conn.commit()
                                
                                # Atualiza a informação na tela (no session_state)
                                state['veiculo_info']['empresa'] = nova_empresa
                                # Esconde o formulário de edição
                                st.session_state.show_edit_form = False
                                st.success("Empresa do veículo atualizada com sucesso!")
                                st.rerun()
                                    
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao atualizar a empresa: {e}")
                            finally:
                                release_connection(conn)
                    else:
                        st.warning("O nome da empresa não pode ser vazio.")
    
    elif state["placa_input"]:
        with st.expander("Cadastrar Novo Veículo", expanded=True):
            with st.form("form_novo_veiculo_rapido"):
                empresa, modelo = st.text_input("Empresa"), st.text_input("Modelo do Veículo")
                if st.form_submit_button("Cadastrar e Continuar") and empresa and modelo:
                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor() as cursor:
                                query = "INSERT INTO veiculos (placa, empresa, modelo, data_entrada) VALUES (%s, %s, %s, %s) RETURNING id;"
                                cursor.execute(query, (state["placa_input"], empresa, modelo, datetime.now(MS_TZ)))
                                new_id = cursor.fetchone()[0]
                                conn.commit()
                                state["veiculo_id"], state["veiculo_info"] = new_id, {"modelo": modelo, "empresa": empresa}
                                st.success("🚚 Veículo cadastrado com sucesso!")
                                st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erro ao cadastrar veículo: {e}")
                        finally:
                            release_connection(conn)

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
                servico_selecionado = st.selectbox(
                    f"Selecione o serviço de {nome_area}",
                    options=[""] + servicos_disponiveis,
                    key=f"select_{chave_area}",
                    label_visibility="collapsed"
                )
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

    if st.button("Limpar tela e iniciar novo cadastro"):
        st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
        st.session_state.servicos_para_adicionar = []
        st.rerun()