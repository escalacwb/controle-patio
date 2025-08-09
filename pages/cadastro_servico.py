import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa, buscar_clientes_por_similaridade

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    # ... (O início da função app e a Parte 1 permanecem os mesmos) ...

    # --- FLUXO 2: VEÍCULO NÃO ENCONTRADO ---
    elif state.get("search_triggered") and not state.get("veiculo_id"):
        # ... (A lógica de busca e confirmação da API permanece a mesma) ...

        if not st.session_state.get('api_vehicle_data'):
            with st.expander("Cadastrar Novo Veículo", expanded=True):
                with st.form("form_novo_veiculo_rapido"):
                    
                    # --- MUDANÇA: SUBSTITUIÇÃO DO CAMPO DE TEXTO PELA BUSCA INTELIGENTE ---
                    st.subheader("Vincular a uma Empresa Cliente")
                    
                    busca_empresa = st.text_input("Digite para buscar a empresa", help="Digite pelo menos 3 letras.")
                    
                    # Inicializa as variáveis para garantir que sempre existam
                    cliente_id_selecionado = None
                    nome_empresa_selecionada = busca_empresa

                    if len(busca_empresa) >= 3:
                        resultados_busca = buscar_clientes_por_similaridade(busca_empresa)
                        
                        if resultados_busca:
                            opcoes_cliente = {f"{nome} (ID: {id})": id for id, nome in resultados_busca}
                            cliente_selecionado_str = st.selectbox(
                                "Selecione a empresa encontrada",
                                options=[""] + list(opcoes_cliente.keys()) # Adiciona uma opção vazia
                            )
                            if cliente_selecionado_str:
                                cliente_id_selecionado = opcoes_cliente[cliente_selecionado_str]
                                nome_empresa_selecionada = cliente_selecionado_str.split(" (ID:")[0]
                        else:
                            st.warning("Nenhuma empresa encontrada com nome similar. O nome digitado será usado para um novo cadastro de cliente.")
                    
                    st.markdown("---")
                    st.subheader("Dados do Veículo")
                    modelo_aceito = st.session_state.get('modelo_aceito', '')
                    ano_aceito_str = st.session_state.get('ano_aceito', '')
                    modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                    # (Resto dos campos: ano, motorista, etc.)
                    
                    if st.form_submit_button("Cadastrar e Continuar"):
                        if not all([nome_empresa_selecionada, modelo]):
                            st.warning("A seleção ou digitação de uma Empresa e do Modelo são obrigatórios.")
                        else:
                            conn = get_connection()
                            if conn:
                                try:
                                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                                        # Se um cliente existente não foi selecionado, cadastra um novo
                                        if not cliente_id_selecionado and nome_empresa_selecionada:
                                            cursor.execute(
                                                "INSERT INTO clientes (nome_empresa) VALUES (%s) RETURNING id",
                                                (nome_empresa_selecionada,)
                                            )
                                            cliente_id_selecionado = cursor.fetchone()['id']

                                        # Insere o veículo com o cliente_id correto
                                        # (Sua lógica de INSERT INTO veiculos aqui, usando 'cliente_id_selecionado' e 'nome_empresa_selecionada')
                                        pass
                                finally:
                                    release_connection(conn)
    # (O restante do arquivo permanece o mesmo)
    # ...