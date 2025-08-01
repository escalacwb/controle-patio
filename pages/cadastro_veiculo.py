import streamlit as st
from database import get_connection, release_connection
import psycopg2
import pandas as pd

def app():
    st.title("➕ Cadastro de Veículos e Serviços")
    st.markdown("---")

    # --- Formulário de Cadastro de Veículo ---
    st.header("1. Dados do Veículo")
    with st.form("form_veiculo", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            placa = st.text_input("Placa do Veículo (ex: ABC1234)", max_chars=7).upper()
            empresa = st.text_input("Empresa/Cliente", help="Nome da empresa ou do cliente proprietário.")
        with col2:
            modelo = st.text_input("Modelo do Veículo")
            # A quilometragem aqui é a do veículo, não necessariamente a do serviço.
            # É bom ter este registro inicial.
            quilometragem_veiculo = st.number_input("Quilometragem Atual do Veículo (km)", min_value=0, step=100)

        submitted_veiculo = st.form_submit_button("Cadastrar Novo Veículo")

        if submitted_veiculo:
            if not all([placa, empresa, modelo]):
                st.error("❌ Por favor, preencha todos os campos do veículo (Placa, Empresa, Modelo).")
            else:
                conn = get_connection()
                if not conn:
                    st.error("Falha ao conectar ao banco de dados.")
                    return
                
                try:
                    with conn.cursor() as cursor:
                        # Inserir veículo e retornar o ID gerado.
                        # Usando NOW() do próprio PostgreSQL para a data de entrada.
                        query = """
                            INSERT INTO veiculos (placa, empresa, modelo, quilometragem, data_entrada) 
                            VALUES (%s, %s, %s, %s, NOW()) 
                            RETURNING id;
                        """
                        cursor.execute(query, (placa, empresa, modelo, quilometragem_veiculo))
                        veiculo_id = cursor.fetchone()[0]
                        conn.commit()

                        # Salva na sessão para uso posterior no formulário de serviço
                        st.session_state['last_registered_veiculo_id'] = veiculo_id
                        st.session_state['last_registered_placa'] = placa
                        
                        st.success(f"✅ Veículo '{placa}' cadastrado com sucesso! ID: {veiculo_id}")
                        st.info("👇 Agora, adicione os serviços para este veículo no formulário abaixo.")

                except psycopg2.IntegrityError as e:
                    conn.rollback()
                    # Verifica se o erro foi de placa duplicada
                    if "veiculos_placa_key" in str(e) or "unique_placa" in str(e):
                        st.error(f"❌ Erro: A placa '{placa}' já está cadastrada no sistema.")
                    else:
                        st.error(f"❌ Erro de integridade no banco de dados: {e}")
                except Exception as e:
                    conn.rollback()
                    st.error(f"❌ Erro inesperado ao cadastrar veículo: {e}")
                finally:
                    release_connection(conn)

    st.markdown("---")

    # --- Formulário para Adicionar Serviços ---
    st.header("2. Adicionar Serviços a um Veículo")

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados para listar veículos.")
        return

    try:
        # Carrega a lista de veículos para o selectbox
        df_veiculos = pd.read_sql("SELECT id, placa, empresa FROM veiculos ORDER BY placa;", conn)
        # Cria uma coluna formatada para exibição no selectbox
        df_veiculos['display'] = df_veiculos.apply(lambda row: f"{row['placa']} - {row['empresa']} (ID: {row['id']})", axis=1)
        
        veiculos_options = ["Selecione um veículo..."] + df_veiculos['display'].tolist()
        
        # Tenta pré-selecionar o último veículo cadastrado
        default_index = 0
        if 'last_registered_placa' in st.session_state:
            last_display_option = f"{st.session_state['last_registered_placa']} - {df_veiculos[df_veiculos['id'] == st.session_state['last_registered_veiculo_id']].iloc[0]['empresa']} (ID: {st.session_state['last_registered_veiculo_id']})"
            if last_display_option in veiculos_options:
                default_index = veiculos_options.index(last_display_option)

        selected_veiculo_display = st.selectbox(
            "Selecione o veículo:",
            veiculos_options,
            index=default_index
        )
    except Exception as e:
        st.error(f"Erro ao carregar lista de veículos: {e}")
        selected_veiculo_display = None
    finally:
        release_connection(conn)


    # Extrai o ID do veículo selecionado
    selected_veiculo_id = None
    if selected_veiculo_display and "ID:" in selected_veiculo_display:
        try:
            selected_veiculo_id = int(selected_veiculo_display.split("ID: ")[1].strip(")"))
        except (ValueError, IndexError):
            pass

    if selected_veiculo_id:
        st.info(f"Veículo selecionado para adicionar serviços: **{selected_veiculo_display.split(' (ID:')[0]}**")

        with st.form("form_servico", clear_on_submit=True):
            area_servico = st.selectbox(
                "Área do Serviço",
                ["Borracharia", "Alinhamento", "Manutenção Mecânica"]
            )

            # Carrega os serviços disponíveis para a área selecionada
            conn = get_connection()
            if not conn:
                st.error("Falha ao conectar para carregar serviços.")
                return
            
            try:
                if area_servico == "Borracharia":
                    df_servicos = pd.read_sql("SELECT nome FROM servicos_borracharia ORDER BY nome;", conn)
                elif area_servico == "Alinhamento":
                    df_servicos = pd.read_sql("SELECT nome FROM servicos_alinhamento ORDER BY nome;", conn)
                else: # Manutenção Mecânica
                    df_servicos = pd.read_sql("SELECT nome FROM servicos_manutencao ORDER BY nome;", conn)
                
                servicos_disponiveis = [""] + df_servicos['nome'].tolist()
            except Exception as e:
                st.error(f"Erro ao carregar serviços disponíveis: {e}")
                servicos_disponiveis = [""]
            finally:
                release_connection(conn)

            tipo_servico = st.selectbox("Tipo de Serviço", servicos_disponiveis)
            quantidade = st.number_input("Quantidade", min_value=1, value=1, step=1)
            descricao = st.text_area("Descrição/Observações do Serviço", help="Detalhes específicos sobre o serviço a ser realizado.")

            submitted_servico = st.form_submit_button("Adicionar Serviço")

            if submitted_servico:
                if not tipo_servico:
                    st.warning("⚠️ Por favor, selecione um tipo de serviço.")
                else:
                    table_map = {
                        "Borracharia": "servicos_solicitados_borracharia",
                        "Alinhamento": "servicos_solicitados_alinhamento",
                        "Manutenção Mecânica": "servicos_solicitados_manutencao"
                    }
                    table_name = table_map.get(area_servico)
                    
                    conn = get_connection()
                    if not conn:
                        st.error("Falha ao conectar para salvar o serviço.")
                        return

                    try:
                        with conn.cursor() as cursor:
                            # Query parametrizada para inserir o serviço solicitado.
                            # Usando NOW() para data_solicitacao e data_atualizacao.
                            query = f"""
                                INSERT INTO {table_name} 
                                (veiculo_id, tipo, quantidade, descricao, observacao, status, data_solicitacao, data_atualizacao)
                                VALUES (%s, %s, %s, %s, %s, 'pendente', NOW(), NOW());
                            """
                            cursor.execute(query, (selected_veiculo_id, tipo_servico, quantidade, descricao, descricao))
                            conn.commit()
                            st.success(f"✅ Serviço '{tipo_servico}' adicionado com sucesso para o veículo selecionado!")
                    except Exception as e:
                        conn.rollback()
                        st.error(f"❌ Erro ao adicionar serviço: {e}")
                    finally:
                        release_connection(conn)
    else:
        st.info("☝️ Cadastre um novo veículo ou selecione um existente na lista para poder adicionar serviços.")