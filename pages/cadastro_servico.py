import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
# --- MUDANÇA 1: Importar a função que busca os serviços do banco de dados ---
from utils import get_catalogo_servicos

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido...")
    st.markdown("---")

    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = { "placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0 }
    state = st.session_state.cadastro_servico_state

    st.header("1️⃣ Identificação do Veículo")
    placa_input = st.text_input("Digite a placa do veículo", value=state["placa_input"], key="placa_input_cadastro_servico").upper()
    if placa_input != state["placa_input"]:
        state["placa_input"], state["veiculo_id"], state["veiculo_info"] = placa_input, None, None
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

    if state["veiculo_id"]:
        st.success(f"Veículo selecionado: **{state['veiculo_info']['modelo']}** | Empresa: **{state['veiculo_info']['empresa']}**")
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
        
        # --- MUDANÇA 2: Chamar a função para buscar os serviços do banco ---
        servicos_do_banco = get_catalogo_servicos()

        # Mapeamento para exibir nomes amigáveis para o usuário
        areas_map = {
            "borracharia": "Borracharia",
            "alinhamento": "Alinhamento",
            "manutencao": "Mecânica"
        }
        
        observacao_geral = st.text_area("Observações gerais para todos os serviços")
        
        servicos_a_cadastrar = []
        # --- MUDANÇA 3: Iterar sobre os serviços buscados do banco ---
        for area_db, nome_amigavel in areas_map.items():
            # Pega a lista de serviços para a área atual
            lista_servicos = servicos_do_banco.get(area_db, [])
            if not lista_servicos:
                continue

            st.markdown(f"**{nome_amigavel}**")
            for servico in lista_servicos:
                col_check, col_qtd = st.columns([0.8, 0.2])
                with col_check:
                    selecionado = st.checkbox(servico, key=f"cb_{area_db}_{servico}")
                with col_qtd:
                    qtd = st.number_input("Qtd", min_value=1, value=1, step=1, key=f"qtd_{area_db}_{servico}", label_visibility="collapsed", disabled=not selecionado)
                
                if selecionado:
                    # Adiciona o serviço com o nome da área correto para a inserção no banco
                    servicos_a_cadastrar.append({"area": nome_amigavel, "tipo": servico, "qtd": qtd})
        
        st.markdown("---")
        if st.button("Registrar todos os serviços selecionados", type="primary"):
            if not servicos_a_cadastrar:
                st.warning("⚠️ Nenhum serviço foi selecionado.")
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
                    st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
                    st.balloons()
                    st.rerun()

    if st.button("Limpar tela e iniciar novo cadastro"):
        st.session_state.cadastro_servico_state = {"placa_input": "", "veiculo_id": None, "veiculo_info": None, "quilometragem": 0}
        st.rerun()