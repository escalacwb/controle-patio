import streamlit as st
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
# --- MUDANÇA: Importar as novas funções de formatação ---
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa

MS_TZ = pytz.timezone('America/Campo_Grande')

def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")
    
    # (O restante das inicializações permanece o mesmo)
    # ...

    if state["veiculo_id"]:
        # ... (código de exibição de dados e botão "Alterar Dados" permanece o mesmo) ...

        if st.session_state.get('show_edit_form', False):
            with st.form("form_edit_veiculo"):
                st.info("Altere os dados do veículo e salve.")
                
                nova_empresa = st.text_input("Empresa", value=state['veiculo_info']['empresa'])
                novo_modelo = st.text_input("Modelo", value=state['veiculo_info']['modelo'])
                novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(state['veiculo_info']['ano_modelo'] or 0), step=1)
                novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                novo_contato = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])
                
                submitted = st.form_submit_button("✅ Salvar Alterações")
                
                if submitted:
                    # --- MUDANÇA: Formatar o telefone antes de salvar ---
                    contato_formatado = formatar_telefone(novo_contato)

                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor() as cursor:
                                # Usa a variável formatada no UPDATE
                                query = "UPDATE veiculos SET empresa = %s, modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s WHERE id = %s"
                                cursor.execute(query, (nova_empresa, novo_modelo, novo_ano if novo_ano > 0 else None, novo_motorista, contato_formatado, state['veiculo_id']))
                                conn.commit()
                            
                            # Atualiza o estado com o valor formatado
                            state['veiculo_info'].update({
                                'empresa': nova_empresa, 'modelo': novo_modelo, 'ano_modelo': novo_ano,
                                'nome_motorista': novo_motorista, 'contato_motorista': contato_formatado
                            })
                            st.session_state.show_edit_form = False
                            st.success("Dados do veículo atualizados!")
                            st.rerun()
                        finally:
                            release_connection(conn)
    
    elif state["placa_input"] and not st.session_state.get('api_vehicle_data'):
        with st.expander("Cadastrar Novo Veículo", expanded=True):
            with st.form("form_novo_veiculo_rapido"):
                empresa = st.text_input("Empresa *")
                modelo_aceito = st.session_state.get('modelo_aceito', '')
                ano_aceito = st.session_state.get('ano_aceito', 0)
                modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)
                ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=int(ano_aceito if ano_aceito else 0), step=1)
                nome_motorista = st.text_input("Nome do Motorista")
                contato_motorista = st.text_input("Contato do Motorista")

                if st.form_submit_button("Cadastrar e Continuar"):
                    if not all([empresa, modelo]):
                        st.warning("Empresa e Modelo são obrigatórios.")
                    else:
                        # --- MUDANÇA: Formatar placa e telefone antes de salvar ---
                        placa_formatada = formatar_placa(state["placa_input"])
                        contato_formatado = formatar_telefone(contato_motorista)

                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    # Usa as variáveis formatadas no INSERT
                                    query = """
                                        INSERT INTO veiculos (placa, empresa, modelo, ano_modelo, nome_motorista, contato_motorista, data_entrada) 
                                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                                    """
                                    cursor.execute(query, (placa_formatada, empresa, modelo, ano_modelo if ano_modelo > 0 else None, nome_motorista, contato_formatado, datetime.now(MS_TZ)))
                                    new_id = cursor.fetchone()[0]
                                    conn.commit()
                                    
                                    for key in ['modelo_aceito', 'ano_aceito']:
                                        if key in st.session_state: del st.session_state[key]
                                    st.success("🚚 Veículo cadastrado com sucesso!")
                                    st.rerun()
                            finally:
                                release_connection(conn)

    # (O restante do arquivo, como a seção de seleção de serviços, permanece o mesmo)
    # ...