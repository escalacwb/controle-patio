

import streamlit as st
import streamlit.components.v1 as components
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
import time
import json
import urllib.parse
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa, buscar_clientes_por_similaridade, get_cliente_details
from pages.ui_components import render_mobile_navbar

render_mobile_navbar(active_page="cadastro")

MS_TZ = pytz.timezone('America/Campo_Grande')

# =============================
# FUNÇÕES PARA GERAR DIAGNÓSTICO
# =============================

def gerar_diagnostico_veiculo():
    """
    Gera um texto descritivo baseado nos inputs de eixos e diagnósticos gerais.
    Retorna uma string formatada para concatenar com observações.
    """
    diagnostico_texto = ""
    
    # --- NOVA LÓGICA DE EIXOS ---
    num_eixos = st.session_state.get('num_eixos', 2)
    eixos_para_alinhar = []
    obs_pneus = []

    for i in range(1, num_eixos + 1):
        # Verifica se o eixo foi marcado para alinhar
        if st.session_state.get(f"check_alinhar_eixo_{i}", False):
            eixos_para_alinhar.append(str(i))
            
            # Verifica desgastes (Lado Esquerdo/Motorista)
            desgaste_le = st.session_state.get(f"desgaste_eixo_{i}_le", [])
            if desgaste_le:
                desc = ", ".join(desgaste_le)
                obs_pneus.append(f"• Eixo {i} (LE/Mot): {desc}")
            
            # Verifica desgastes (Lado Direito/Passageiro)
            desgaste_ld = st.session_state.get(f"desgaste_eixo_{i}_ld", [])
            if desgaste_ld:
                desc = ", ".join(desgaste_ld)
                obs_pneus.append(f"• Eixo {i} (LD/Pass): {desc}")

    # Monta o texto dos eixos
    if eixos_para_alinhar:
        diagnostico_texto += f"🔧 ALINHAMENTO NECESSÁRIO NOS EIXOS: {', '.join(eixos_para_alinhar)}\n"
    else:
        diagnostico_texto += "• Nenhum alinhamento solicitado.\n"

    if obs_pneus:
        diagnostico_texto += "⚠️ DESGASTE DE PNEUS:\n" + "\n".join(obs_pneus) + "\n"
    
    diagnostico_texto += "-" * 20 + "\n"

    # --- DIAGNÓSTICOS GERAIS (MANTIDOS) ---
    puxando = st.session_state.get('diag_puxando', 'Não')
    if puxando == 'Não':
        diagnostico_texto += "• Caminhão NÃO está puxando.\n"
    else:
        diagnostico_texto += f"• Caminhão está PUXANDO para a {puxando}.\n"
    
    passar_pesado = st.session_state.get('diag_passarinhando', 'Não')
    if passar_pesado == 'Não':
        diagnostico_texto += "• Volante normal (não está passarinhando).\n"
    else:
        diagnostico_texto += f"• Caminhão está com {passar_pesado.upper()}.\n"
    
    vibracao = st.session_state.get('diag_vibracao', 'Não')
    if vibracao == 'Sim':
        diagnostico_texto += "• Caminhão está VIBRANDO.\n"
    else:
        diagnostico_texto += "• Caminhão NÃO está vibrando.\n"
    
    return diagnostico_texto.strip()


# =============================
# FILA DE EVENTOS ROBUSTA
# =============================
def processar_cadastro_completo(state, observacao_final, diagnostico_gerado):
    """
    Processa o cadastro de serviços de forma robusta e sequencial.
    """
    
    # ETAPA 1: SALVAR NO BANCO
    print("⏱️  [ETAPA 1] Salvando no banco de dados...")
    conn = None 
    try:
        conn = get_connection()
        if not conn:
            return False, "❌ Erro de conexão com o banco"
        
        with conn.cursor() as cursor:
            table_map = {
                "Borracharia": "servicos_solicitados_borracharia",
                "Alinhamento": "servicos_solicitados_alinhamento",
                "Mecânica": "servicos_solicitados_manutencao"
            }

            for s in st.session_state.servicos_para_adicionar:
                table_name = table_map.get(s['area'])
                if not table_name:
                    return False, f"❌ Área de serviço inválida: {s['area']}"
                
                query = f"INSERT INTO {table_name} (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)"
                cursor.execute(
                    query,
                    (
                        state["veiculo_id"],
                        s['tipo'],
                        s['qtd'],
                        observacao_final,
                        state["quilometragem"],
                        datetime.now(MS_TZ),
                        datetime.now(MS_TZ)
                    )
                )

            cursor.execute(
                "UPDATE veiculos SET data_revisao_proativa = NULL WHERE id = %s",
                (state["veiculo_id"],)
            )

            conn.commit()
        
        release_connection(conn)
        print("✅ [ETAPA 1] CONCLUÍDO - Banco de dados atualizado")
        time.sleep(0.5)
        
    except Exception as e:
        if conn: release_connection(conn)
        return False, f"❌ Erro ao salvar no banco: {str(e)}"

    # ETAPA 2: FORMATAR MENSAGEM COMPLETA
    print("⏱️  [ETAPA 2] Formatando mensagem WhatsApp...")
    try:
        servicos_resumo = ", ".join([f"{s['tipo']}({s['qtd']})" for s in st.session_state.servicos_para_adicionar])
        
        # Extrair dados do veículo
        modelo = state.get('veiculo_info', {}).get('modelo', 'N/A')
        ano = state.get('veiculo_info', {}).get('ano_modelo', 'N/A')
        motorista = state.get('veiculo_info', {}).get('nome_motorista', 'N/A')
        contato_motorista = state.get('veiculo_info', {}).get('contato_motorista', 'N/A')
        empresa = state.get('veiculo_info', {}).get('empresa', 'N/A')
        responsavel = state.get('veiculo_info', {}).get('nome_responsavel', 'N/A')
        contato_responsavel = state.get('veiculo_info', {}).get('contato_responsavel', 'N/A')
        
        # Iniciar a mensagem com dados completos
        mensagem = f"""🚛 *NOVO SERVIÇO CADASTRADO*

📌 *DADOS DO VEÍCULO:*
*Placa:* `{state['placa_input']}`
*Modelo:* {modelo}
*Ano:* {ano}
*KM:* `{state['quilometragem']:,}`

👨‍💼 *DADOS DO MOTORISTA:*
*Nome:* {motorista}
*Contato:* {contato_motorista}

🏢 *DADOS DA EMPRESA:*
*Empresa:* {empresa}
*Responsável:* {responsavel}
*Contato:* {contato_responsavel}

🔧 *SERVIÇOS SOLICITADOS:*
{servicos_resumo}

📋 *DIAGNÓSTICO:*
```
{diagnostico_gerado}
```"""
        # Adicionar observações gerais se existirem
        if observacao_final.strip() and observacao_final != diagnostico_gerado:
            obs_adicionais = observacao_final.replace(diagnostico_gerado, "").strip()
            if obs_adicionais:
                mensagem += f"\n\n📝 *OBSERVAÇÕES ADICIONAIS:*\n{obs_adicionais}"
        
        # Adicionar rodapé
        mensagem += f"""

⏰ *{datetime.now().strftime('%d/%m/%Y %H:%M')}*
━━━━━━━━━━━━━━━━━━━━━━━━━━━
#controlepatio"""
        
        print("✅ [ETAPA 2] CONCLUÍDO - Mensagem formatada com todos os dados")
        time.sleep(0.3)
        
    except Exception as e:
        return False, f"❌ Erro ao formatar mensagem: {str(e)}"

    # ETAPA 3: EXIBIR SUCESSO
    print("⏱️  [ETAPA 3] Exibindo feedback positivo...")
    st.success("✅ ETAPA 1: Serviço cadastrado no banco com sucesso!")
    time.sleep(0.5)

    # ETAPA 4: PREPARANDO LINK
    print("⏱️  [ETAPA 4] Preparando link WhatsApp com mensagem...")
    
    st.info("✅ ETAPA 2: Preparando mensagem para envio...")
    time.sleep(0.5)

    # ETAPA 5: EXIBIR INSTRUÇÃO
    st.info("✅ ETAPA 2: Abrindo WhatsApp em alguns segundos...")
    time.sleep(0.5)

    # ETAPA 6: ABRIR WHATSAPP COM MENSAGEM NO LINK
    print("⏱️  [ETAPA 6] Abrindo WhatsApp com mensagem no link...")
    
    try:
        # URL encode a mensagem para usar no link wa.me
        mensagem_encoded = urllib.parse.quote(mensagem)
        whatsapp_link = f"https://wa.me/?text={mensagem_encoded}"
        
        components.html(f"""
        <script>
            setTimeout(() => {{
                console.log('🚀 Abrindo WhatsApp com mensagem...');
                window.open('{whatsapp_link}', '_blank');
            }}, 500);
        </script>
        """, height=0)
        
        print("✅ [ETAPA 6] CONCLUÍDO - WhatsApp aberto com mensagem no link")
        
    except Exception as e:
        print(f"❌ Erro ao preparar link WhatsApp: {str(e)}")
    
    time.sleep(1)

    # ETAPA 7: FINALIZAÇÃO
    st.balloons()
    st.success("🎉 ETAPA 3: WhatsApp aberto! Agora é só:\n\n1️⃣ Selecione o GRUPO para envio\n2️⃣ A mensagem já está pronta\n3️⃣ Clique em Enviar! 📱")
    time.sleep(1)

    # ETAPA 8: LIMPAR FORMULÁRIO
    print("⏱️  [ETAPA 8] Limpando formulário...")
    state["search_triggered"] = False
    state["placa_input"] = ""
    st.session_state.servicos_para_adicionar = []
    print("✅ [ETAPA 8] CONCLUÍDO - Formulário limpo")
    
    return True, "✅ Processo completo com sucesso!"


def app():
    st.title("📋 Cadastro Rápido de Serviços")
    st.markdown("Use esta página para um fluxo rápido de cadastro de serviços para um veículo.")

    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = {
            "placa_input": "", "veiculo_id": None, "veiculo_info": None,
            "search_triggered": False, "quilometragem": 0,
            "busca_empresa_edit": ""
        }

    state = st.session_state.cadastro_servico_state

    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []

    st.markdown("---")

    st.header("1️⃣ Identificação do Veículo")

    placa_input = st.text_input("Digite a placa do veículo", value=state.get("placa_input", ""), key="placa_input_key").upper()

    if st.button("Verificar Placa no Sistema", use_container_width=True, type="primary"):
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        state["veiculo_id"] = None
        state["veiculo_info"] = None
        for key in ['api_vehicle_data', 'modelo_aceito', 'ano_aceito', 'show_edit_form', 'show_edit_responsavel_form', 'servicos_para_adicionar', 'busca_empresa_edit', 'last_selected_client_id_edit', 'details_responsavel_edit', 'editing_responsavel']:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if state.get("search_triggered"):
        if state.get("veiculo_info") is None and not state.get("veiculo_id"):
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                        query = "SELECT v.id, v.empresa, v.modelo, v.ano_modelo, v.nome_motorista, v.contato_motorista, v.cliente_id, c.nome_responsavel, c.contato_responsavel FROM veiculos v LEFT JOIN clientes c ON v.cliente_id = c.id WHERE v.placa = %s"
                        cursor.execute(query, (formatar_placa(state["placa_input"]),))
                        resultado = cursor.fetchone()
                        if resultado:
                            state["veiculo_id"] = resultado["id"]
                            state["veiculo_info"] = resultado
                finally:
                    release_connection(conn)

        if state.get("veiculo_id"):
            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.subheader("Dados do Veículo")
                    st.markdown(
                        f"**Modelo:** {state['veiculo_info']['modelo']} | **Ano:** {state['veiculo_info']['ano_modelo'] or 'N/A'}\n\n"
                        f"**Motorista:** {state['veiculo_info']['nome_motorista'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_motorista'] or 'N/A'}"
                    )
                with col2:
                    if st.button("✏️ Alterar Veículo", use_container_width=True):
                        st.session_state.show_edit_form = not st.session_state.get('show_edit_form', False)
                        st.rerun()

            with st.container(border=True):
                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.subheader("Dados da Empresa")
                    st.markdown(
                        f"**Empresa:** {state['veiculo_info']['empresa']}\n\n"
                        f"**Responsável Frota:** {state['veiculo_info']['nome_responsavel'] or 'N/A'} | **Contato:** {state['veiculo_info']['contato_responsavel'] or 'N/A'}"
                    )
                with col2:
                    if st.button("✏️ Alterar Empresa/Responsável", use_container_width=True):
                        st.session_state.show_edit_responsavel_form = not st.session_state.get('show_edit_responsavel_form', False)
                        if st.session_state.show_edit_responsavel_form:
                            st.session_state.busca_empresa_edit = state['veiculo_info']['empresa']
                        st.rerun()

            # ============== SEÇÃO DE FORMULÁRIO DE EDIÇÃO DE VEÍCULO ==============
            if st.session_state.get('show_edit_form', False):
                with st.form("form_edit_veiculo"):
                    st.info("Altere os dados específicos deste veículo.")
                    novo_modelo = st.text_input("Modelo", value=state['veiculo_info']['modelo'])
                    novo_ano_val = state['veiculo_info']['ano_modelo'] or datetime.now().year
                    novo_ano = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 1, value=int(novo_ano_val), step=1)
                    novo_motorista = st.text_input("Nome do Motorista", value=state['veiculo_info']['nome_motorista'])
                    novo_contato_motorista = st.text_input("Contato do Motorista", value=state['veiculo_info']['contato_motorista'])

                    if st.form_submit_button("✅ Salvar Dados do Veículo"):
                        conn = get_connection()
                        if conn:
                            try:
                                with conn.cursor() as cursor:
                                    query_veiculo = "UPDATE veiculos SET modelo = %s, ano_modelo = %s, nome_motorista = %s, contato_motorista = %s, data_atualizacao_contato = NOW() WHERE id = %s"
                                    cursor.execute(query_veiculo, (novo_modelo, novo_ano if novo_ano > 0 else None, novo_motorista, formatar_telefone(novo_contato_motorista), state['veiculo_id']))
                                    conn.commit()
                                    st.success("Dados do veículo atualizados!")
                                    st.session_state.show_edit_form = False
                                    st.rerun()
                            finally:
                                release_connection(conn)

            # ============== SEÇÃO DE FORMULÁRIO DE EDIÇÃO DE EMPRESA ==============
            if st.session_state.get('show_edit_responsavel_form', False):
                st.info("Altere a empresa à qual este veículo está vinculado.")
                busca_empresa_edit = st.text_input("Digite para buscar/alterar a empresa", value=st.session_state.get("busca_empresa_edit", ""), help="Digite e pressione Enter para buscar.")
                
                if busca_empresa_edit != st.session_state.get("busca_empresa_edit"):
                    st.session_state.busca_empresa_edit = busca_empresa_edit
                    if 'details_responsavel_edit' in st.session_state:
                        del st.session_state['details_responsavel_edit']
                    st.rerun()

                cliente_id_final = state['veiculo_info']['cliente_id']
                nome_empresa_final = st.session_state.busca_empresa_edit
                cliente_id_selecionado_edit = None

                if len(st.session_state.busca_empresa_edit) >= 3:
                    resultados_busca = buscar_clientes_por_similaridade(st.session_state.busca_empresa_edit)
                    if resultados_busca:
                        opcoes_cliente_edit = {"": None}
                        for id_c, nome_e, nome_f in resultados_busca:
                            texto_exibicao = nome_e
                            if nome_f and nome_f.strip() and nome_f.lower() != nome_e.lower():
                                texto_exibicao += f" (Fantasia: {nome_f})"
                            opcoes_cliente_edit[texto_exibicao] = id_c
                        opcoes_cliente_edit[f"Nenhum destes. Usar/criar '{st.session_state.busca_empresa_edit}' como nova."] = "NOVO"

                        cliente_selecionado_str = st.selectbox("Selecione a empresa ou confirme o novo cadastro:", options=list(opcoes_cliente_edit.keys()), key="select_edit_empresa")
                        cliente_id_selecionado_edit = opcoes_cliente_edit[cliente_selecionado_str]

                        if cliente_id_selecionado_edit and cliente_id_selecionado_edit != "NOVO":
                            cliente_id_final = cliente_id_selecionado_edit
                            nome_empresa_final = next((item[1] for item in resultados_busca if item[0] == cliente_id_final), st.session_state.busca_empresa_edit)
                        elif cliente_id_selecionado_edit == "NOVO":
                            cliente_id_final = None
                        else:
                            cliente_id_final = state['veiculo_info']['cliente_id']

                        if cliente_id_selecionado_edit != st.session_state.get('last_selected_client_id_edit'):
                            st.session_state.last_selected_client_id_edit = cliente_id_selecionado_edit
                            if isinstance(cliente_id_selecionado_edit, int):
                                st.session_state.details_responsavel_edit = get_cliente_details(cliente_id_selecionado_edit)
                            else:
                                st.session_state.details_responsavel_edit = {}
                            st.session_state.editing_responsavel = False
                            st.rerun()

                st.markdown("---")
                st.subheader("Dados do Responsável pela Frota")
                details = st.session_state.get('details_responsavel_edit', {})
                nome_resp = details.get('nome_responsavel', "") if details else ""
                contato_resp = details.get('contato_responsavel', "") if details else ""

                if st.session_state.get('editing_responsavel', False):
                    with st.form("form_edit_responsavel_inplace"):
                        st.info("Você está editando os dados deste responsável para TODOS os veículos da empresa.")
                        novo_nome_resp = st.text_input("Nome do Responsável", value=nome_resp)
                        novo_contato_resp = st.text_input("Contato do Responsável", value=contato_resp)
                        if st.form_submit_button("✅ Salvar Responsável"):
                            id_cliente_para_salvar = cliente_id_final if cliente_id_final else state['veiculo_info']['cliente_id']
                            if id_cliente_para_salvar:
                                conn = get_connection()
                                if conn:
                                    try:
                                        with conn.cursor() as cursor:
                                            cursor.execute(
                                                "UPDATE clientes SET nome_responsavel = %s, contato_responsavel = %s, data_atualizacao_contato = NOW() WHERE id = %s",
                                                (novo_nome_resp, formatar_telefone(novo_contato_resp), int(id_cliente_para_salvar))
                                            )
                                            conn.commit()
                                            st.success("Responsável atualizado com sucesso!")
                                            st.session_state.editing_responsavel = False
                                            st.session_state.last_selected_client_id_edit = None
                                            st.rerun()
                                    finally:
                                        release_connection(conn)
                            else:
                                st.warning("Selecione um cliente existente para poder editar o responsável.")
                else:
                    col_nome, col_contato, col_btn = st.columns([0.4, 0.4, 0.2])
                    col_nome.text_input("Nome do Responsável", value=nome_resp, disabled=True)
                    col_contato.text_input("Contato do Responsável", value=contato_resp, disabled=True)
                    with col_btn:
                        st.write("")
                        st.write("")
                        if st.button("✏️ Alterar", use_container_width=True, help="Alterar dados do responsável"):
                            id_cliente_para_editar = st.session_state.get('last_selected_client_id_edit')
                            if isinstance(id_cliente_para_editar, int):
                                st.session_state.editing_responsavel = True
                                st.rerun()
                            else:
                                st.toast("Selecione um cliente da lista para editar.", icon="⚠️")

                st.markdown("---")
                if st.button("✅ Salvar Vinculação da Empresa", type="primary"):
                    conn = get_connection()
                    if conn:
                        try:
                            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                                if cliente_id_final is None and nome_empresa_final:
                                    st.info(f"Criando novo cliente: {nome_empresa_final}")
                                    cursor.execute("INSERT INTO clientes (nome_empresa) VALUES (%s) RETURNING id", (nome_empresa_final,))
                                    cliente_id_final = cursor.fetchone()['id']
                                query_veiculo = "UPDATE veiculos SET empresa = %s, cliente_id = %s WHERE id = %s"
                                cursor.execute(query_veiculo, (nome_empresa_final, cliente_id_final, state['veiculo_id']))
                                conn.commit()
                                st.success("Vinculação da empresa atualizada com sucesso!")
                                st.session_state.show_edit_responsavel_form = False
                                st.session_state.last_selected_client_id_edit = None
                                if 'details_responsavel_edit' in st.session_state:
                                    del st.session_state['details_responsavel_edit']
                                st.rerun()
                        finally:
                            release_connection(conn)

            st.markdown("---")

            # ============== SEÇÃO DE DIAGNÓSTICO ATUALIZADA ==============
            st.header("2️⃣ Diagnóstico do Veículo")
            st.markdown("**Avalie as condições de funcionamento do caminhão.**")

            # --- INPUT DE EIXOS ---
            with st.container(border=True):
                st.subheader("🚛 Configuração de Eixos e Pneus")
                
                # Input para número de eixos
                st.session_state['num_eixos'] = st.number_input(
                    "Número de Eixos do Conjunto:", 
                    min_value=2, max_value=9, value=st.session_state.get('num_eixos', 2), step=1
                )
                
                st.markdown("---")
                st.markdown("Selececione os eixos que precisam de **Alinhamento** e detalhe os pneus se houver desgaste.")

                # Loop para criar os controles de cada eixo
                num_eixos = st.session_state['num_eixos']
                
                for i in range(1, num_eixos + 1):
                    # Checkbox principal do eixo
                    check_key = f"check_alinhar_eixo_{i}"
                    
                    # Cria uma coluna com cor de fundo ou destaque se selecionado
                    col_check, col_details = st.columns([0.25, 0.75])
                    
                    with col_check:
                        st.write("") # Espaçamento vertical para alinhar
                        alinhar = st.checkbox(f"✅ Alinhar Eixo {i}", key=check_key)
                    
                    with col_details:
                        if alinhar:
                            c1, c2 = st.columns(2)
                            opcoes_desgaste = ["Ombro Interno", "Ombro Externo", "Centro", "Escamado/Irregular"]
                            
                            with c1:
                                st.multiselect(
                                    f"Pneu LE (Motorista) - Eixo {i}",
                                    options=opcoes_desgaste,
                                    key=f"desgaste_eixo_{i}_le",
                                    placeholder="Selecione desgastes..."
                                )
                            with c2:
                                st.multiselect(
                                    f"Pneu LD (Passageiro) - Eixo {i}",
                                    options=opcoes_desgaste,
                                    key=f"desgaste_eixo_{i}_ld",
                                    placeholder="Selecione desgastes..."
                                )
                    
                    if i < num_eixos:
                        st.divider()

            # --- DIAGNÓSTICOS GERAIS (Mantidos) ---
            with st.container(border=True):
                st.subheader("🔍 Comportamento Geral")
                
                # Puxando
                puxando_col1, puxando_col2 = st.columns(2)
                with puxando_col1:
                    st.markdown("**O caminhão está puxando?**")
                with puxando_col2:
                    st.session_state['diag_puxando'] = st.radio(
                        "Puxando", options=['Não', 'Esquerda', 'Direita'],
                        key='radio_puxando', label_visibility='collapsed', horizontal=True
                    )
                
                st.write("") # Espaçador

                # Passarinhando
                passar_col1, passar_col2 = st.columns(2)
                with passar_col1:
                    st.markdown("**Passarinhando ou volante pesado?**")
                with passar_col2:
                    st.session_state['diag_passarinhando'] = st.radio(
                        "Passarinhando", options=['Não', 'Passarinhando', 'Volante Pesado'],
                        key='radio_passarinhando', label_visibility='collapsed', horizontal=True
                    )

                st.write("") # Espaçador

                # Vibração
                vibr_col1, vibr_col2 = st.columns(2)
                with vibr_col1:
                    st.markdown("**Caminhão vibrando?**")
                with vibr_col2:
                    st.session_state['diag_vibracao'] = st.radio(
                        "Vibracao", options=['Não', 'Sim'],
                        key='radio_vibracao', label_visibility='collapsed', horizontal=True
                    )

            diagnostico_gerado = gerar_diagnostico_veiculo()
            with st.container(border=True):
                st.markdown("### 📋 Prévia do Diagnóstico:")
                st.info(diagnostico_gerado)

            st.markdown("---")

            # ============== SEÇÃO DE SELEÇÃO DE SERVIÇOS ==============
            st.header("3️⃣ Seleção de Serviços")

            state["quilometragem"] = st.number_input(
                "Quilometragem (Obrigatório)",
                min_value=1, step=1,
                value=state.get("quilometragem", 0) or None,
                key="km_servico", placeholder="Digite a KM..."
            )

            servicos_do_banco = get_catalogo_servicos()

            def area_de_servico(nome_area, chave_area):
                st.subheader(nome_area)
                servicos_disponiveis = servicos_do_banco.get(chave_area, [])
                col1, col2, col3 = st.columns([0.7, 0.15, 0.15])

                with col1:
                    servico_selecionado = st.selectbox(
                        f"Serviço de {nome_area}",
                        options=[""] + servicos_disponiveis,
                        key=f"select_{chave_area}", label_visibility="collapsed"
                    )

                with col2:
                    quantidade = st.number_input(
                        "Qtd", min_value=1, value=1, step=1,
                        key=f"qtd_{chave_area}", label_visibility="collapsed"
                    )

                with col3:
                    if st.button("➕ Adicionar", key=f"add_{chave_area}", use_container_width=True):
                        if servico_selecionado:
                            st.session_state.servicos_para_adicionar.append(
                                {"area": nome_area, "tipo": servico_selecionado, "qtd": quantidade}
                            )
                            st.rerun()
                        else:
                            st.warning("Selecione um serviço para adicionar.")

            area_de_servico("Borracharia", "borracharia")
            area_de_servico("Alinhamento", "alinhamento")
            area_de_servico("Mecânica", "manutencao")

            st.markdown("---")

            if st.session_state.servicos_para_adicionar:
                st.subheader("Serviços na Lista:")
                for i, servico in enumerate(st.session_state.servicos_para_adicionar):
                    col_serv, col_qtd, col_del = st.columns([0.7, 0.15, 0.15])
                    col_serv.write(f"**{servico['area']}**: {servico['tipo']}")
                    col_qtd.write(f"Qtd: {servico['qtd']}")
                    if col_del.button("❌ Remover", key=f"del_{i}", use_container_width=True):
                        st.session_state.servicos_para_adicionar.pop(i)
                        st.rerun()

            observacao_geral = st.text_area("📝 Observações gerais")

            st.markdown("---")

            observacao_final = diagnostico_gerado
            if observacao_geral.strip():
                observacao_final += "\n\n" + observacao_geral

            if st.button("🚀 CADASTRAR e NOTIFICAR", type="primary", use_container_width=True):
                if not st.session_state.servicos_para_adicionar:
                    st.warning("⚠️ Nenhum serviço foi adicionado à lista.")
                elif not state["quilometragem"] or state["quilometragem"] <= 0:
                    st.error("❌ A quilometragem é obrigatória.")
                else:
                    sucesso, mensagem = processar_cadastro_completo(state, observacao_final, diagnostico_gerado)
                    if sucesso:
                        st.rerun()
                    else:
                        st.error(mensagem)

        else:
            st.warning("Veículo não encontrado no banco de dados.")

            if st.button("🔎 Buscar na API", use_container_width=True):
                with st.spinner("Consultando API..."):
                    sucesso, resultado = consultar_placa_comercial(state["placa_input"])
                    if sucesso:
                        st.session_state.api_vehicle_data = resultado
                    else:
                        st.error(resultado)
                    st.rerun()

            if 'api_vehicle_data' in st.session_state:
                api_data = st.session_state.api_vehicle_data
                with st.container(border=True):
                    st.subheader("Dados da API")
                    st.markdown(f"**Modelo:** `{api_data.get('modelo', 'N/A')}`")
                    st.markdown(f"**Ano:** `{api_data.get('anoModelo', 'N/A')}`")
                    c1, c2 = st.columns(2)

                    with c1:
                        if st.button("✅ Aceitar", use_container_width=True, type="primary"):
                            st.session_state.modelo_aceito = api_data.get('modelo')
                            st.session_state.ano_aceito = api_data.get('anoModelo')
                            del st.session_state.api_vehicle_data
                            st.rerun()

                    with c2:
                        if st.button("❌ Cancelar", use_container_width=True):
                            del st.session_state.api_vehicle_data
                            st.rerun()

            if not st.session_state.get('api_vehicle_data'):
                with st.expander("Cadastrar Novo Veículo", expanded=True):
                    st.subheader("Vincular a uma Empresa")
                    busca_empresa = st.text_input("Digite para buscar empresa", value=st.session_state.get("busca_empresa_novo", ""))

                    if busca_empresa != st.session_state.get("busca_empresa_novo"):
                        st.session_state.busca_empresa_novo = busca_empresa
                        st.rerun()

                    cliente_id_selecionado = None
                    nome_empresa_final = st.session_state.busca_empresa_novo

                    if len(st.session_state.busca_empresa_novo) >= 3:
                        resultados_busca = buscar_clientes_por_similaridade(st.session_state.busca_empresa_novo)
                        if resultados_busca:
                            opcoes_cliente = {}
                            for id_cliente, nome_empresa, nome_fantasia in resultados_busca:
                                texto_exibicao = nome_empresa
                                if nome_fantasia and nome_fantasia.strip() and nome_fantasia.lower() != nome_empresa.lower():
                                    texto_exibicao += f" (Fantasia: {nome_fantasia})"
                                opcoes_cliente[texto_exibicao] = id_cliente

                            opcoes_cliente[f"Cadastrar '{st.session_state.busca_empresa_novo}'"] = None

                            cliente_selecionado_str = st.selectbox("Selecione ou cadastre nova empresa:", options=list(opcoes_cliente.keys()))
                            cliente_id_selecionado = opcoes_cliente[cliente_selecionado_str]

                            if cliente_id_selecionado:
                                nome_empresa_final = next((item[1] for item in resultados_busca if item[0] == cliente_id_selecionado), st.session_state.busca_empresa_novo)

                    with st.form("form_novo_veiculo_rapido"):
                        st.markdown("---")
                        st.subheader("Dados do Veículo")

                        modelo_aceito = st.session_state.get('modelo_aceito', '')
                        ano_aceito_str = st.session_state.get('ano_aceito', '')

                        modelo = st.text_input("Modelo do Veículo *", value=modelo_aceito)

                        try:
                            default_year = int(ano_aceito_str) if ano_aceito_str else datetime.now().year
                        except (ValueError, TypeError):
                            default_year = datetime.now().year

                        ano_modelo = st.number_input("Ano do Modelo", min_value=1950, max_value=datetime.now().year + 2, value=default_year, step=1)
                        nome_motorista = st.text_input("Nome do Motorista")
                        contato_motorista = st.text_input("Contato do Motorista")

                        if st.form_submit_button("Cadastrar e Continuar"):
                            if not all([nome_empresa_final, modelo]):
                                st.warning("Empresa e Modelo são obrigatórios.")
                            else:
                                placa_formatada = formatar_placa(state["placa_input"])
                                contato_formatado = formatar_telefone(contato_motorista)

                                conn = get_connection()
                                if conn:
                                    try:
                                        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                                            if not cliente_id_selecionado and nome_empresa_final:
                                                cursor.execute("INSERT INTO clientes (nome_empresa) VALUES (%s) RETURNING id", (nome_empresa_final,))
                                                cliente_id_selecionado = cursor.fetchone()['id']

                                            query_insert = "INSERT INTO veiculos (placa, empresa, modelo, ano_modelo, nome_motorista, contato_motorista, cliente_id, data_entrada, data_atualizacao_contato) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());"

                                            cursor.execute(
                                                query_insert,
                                                (
                                                    placa_formatada, nome_empresa_final, modelo,
                                                    ano_modelo if ano_modelo > 1950 else None,
                                                    nome_motorista, contato_formatado,
                                                    cliente_id_selecionado, datetime.now(MS_TZ)
                                                )
                                            )

                                            conn.commit()
                                            st.success("🚚 Veículo cadastrado com sucesso!")
                                            state['search_triggered'] = False
                                            for key in ['modelo_aceito', 'ano_aceito']:
                                                if key in st.session_state:
                                                    del st.session_state[key]
                                            st.rerun()
                                    finally:
                                        release_connection(conn)

        if state.get("placa_input"):
            if st.button("Limpar e Iniciar Nova Busca"):
                keys_to_delete = [
                    'cadastro_servico_state', 'servicos_para_adicionar', 'api_vehicle_data',
                    'modelo_aceito', 'ano_aceito', 'show_edit_form', 'show_edit_responsavel_form',
                    'busca_empresa_edit', 'busca_empresa_novo', 'last_selected_client_id_edit',
                    'details_responsavel_edit', 'editing_responsavel',
                    'diag_puxando', 'diag_passarinhando', 'diag_pneu_esquerdo',
                    'diag_pneu_direito', 'diag_vibracao',
                    'num_eixos'
                ]
                # Adiciona chaves de eixos dinâmicos para limpeza
                for k in list(st.session_state.keys()):
                    if k.startswith("check_alinhar_eixo_") or k.startswith("desgaste_eixo_"):
                        keys_to_delete.append(k)

                for key in keys_to_delete:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()


if __name__ == "__main__":
    app()
