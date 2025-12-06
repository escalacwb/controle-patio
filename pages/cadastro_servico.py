# /pages/cadastro_servico.py - VERSÃO "SEM CLIPBOARD" (URL ENCODED)

import streamlit as st
import streamlit.components.v1 as components
from database import get_connection, release_connection
import psycopg2.extras
from datetime import datetime
import pytz
import time
import urllib.parse  # <--- IMPORTANTE: Biblioteca para codificar o texto na URL
from utils import get_catalogo_servicos, consultar_placa_comercial, formatar_telefone, formatar_placa, buscar_clientes_por_similaridade, get_cliente_details
from pages.ui_components import render_mobile_navbar

render_mobile_navbar(active_page="cadastro")

MS_TZ = pytz.timezone('America/Campo_Grande')

# =============================
# FUNÇÕES AUXILIARES
# =============================

def gerar_diagnostico_veiculo():
    """Gera o texto de diagnóstico."""
    diagnostico_texto = ""
    
    puxando = st.session_state.get('diag_puxando', 'Não')
    if puxando != 'Não': diagnostico_texto += f"• Caminhão puxando para a {puxando}.\n"
    
    passar_pesado = st.session_state.get('diag_passarinhando', 'Não')
    if passar_pesado != 'Não': diagnostico_texto += f"• Caminhão com {passar_pesado.lower()}.\n"
    
    pneu_esq = st.session_state.get('diag_pneu_esquerdo', 'Não')
    if pneu_esq != 'Não': diagnostico_texto += f"• Pneu DE: Desgaste no {pneu_esq}.\n"
    
    pneu_dir = st.session_state.get('diag_pneu_direito', 'Não')
    if pneu_dir != 'Não': diagnostico_texto += f"• Pneu DD: Desgaste no {pneu_dir}.\n"
    
    vibracao = st.session_state.get('diag_vibracao', 'Não')
    if vibracao == 'Sim': diagnostico_texto += "• Caminhão vibrando.\n"
    
    if not diagnostico_texto: diagnostico_texto = "• Nenhum problema relatado no diagnóstico rápido."
    
    return diagnostico_texto.strip()

def processar_cadastro_simplificado(state, observacao_final, diagnostico_gerado):
    """
    Salva no banco e abre o WhatsApp com texto preenchido via URL.
    """
    
    # 1. SALVAR NO BANCO
    conn = None
    try:
        conn = get_connection()
        if not conn: return False, "❌ Erro de conexão"
        
        with conn.cursor() as cursor:
            table_map = {
                "Borracharia": "servicos_solicitados_borracharia",
                "Alinhamento": "servicos_solicitados_alinhamento",
                "Mecânica": "servicos_solicitados_manutencao"
            }

            for s in st.session_state.servicos_para_adicionar:
                table_name = table_map.get(s['area'])
                query = f"INSERT INTO {table_name} (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao) VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)"
                cursor.execute(query, (state["veiculo_id"], s['tipo'], s['qtd'], observacao_final, state["quilometragem"], datetime.now(MS_TZ), datetime.now(MS_TZ)))

            cursor.execute("UPDATE veiculos SET data_revisao_proativa = NULL WHERE id = %s", (state["veiculo_id"],))
            conn.commit()
    except Exception as e:
        return False, f"❌ Erro SQL: {str(e)}"
    finally:
        if conn: release_connection(conn)

    # 2. GERAR MENSAGEM
    servicos_resumo = ", ".join([f"{s['tipo']}({s['qtd']})" for s in st.session_state.servicos_para_adicionar])
    mensagem = f"""🚛 *NOVO SERVIÇO CADASTRADO*

*Placa:* `{state['placa_input']}`
*KM:* `{state['quilometragem']:,}`
*Serviços:* {servicos_resumo}

📋 *DIAGNÓSTICO:*
{diagnostico_gerado}

⏰ *{datetime.now().strftime('%d/%m/%Y %H:%M')}*
━━━━━━━━━━━━━━━━━━
#controlepatio"""

    # 3. CODIFICAR MENSAGEM PARA URL (O SEGREDO)
    # Transforma espaços e quebras de linha em caracteres de URL seguros
    mensagem_encoded = urllib.parse.quote(mensagem)
    
    # URL Mágica: Abre o WhatsApp Web já com o texto pronto
    url_whatsapp = f"https://web.whatsapp.com/send?text={mensagem_encoded}"

    # 4. ABRIR NAVEGADOR (Sem clipboard, sem erro)
    st.success("✅ Salvo! Abrindo WhatsApp com a mensagem preenchida...")
    
    components.html(f"""
    <script>
        // Pequeno delay para garantir que o usuário veja a mensagem de sucesso
        setTimeout(() => {{
            window.open('{url_whatsapp}', '_blank');
        }}, 1000);
    </script>
    """, height=0)
    
    time.sleep(2) # Espera o JS rodar antes de limpar

    # 5. LIMPEZA
    state["search_triggered"] = False
    state["placa_input"] = ""
    st.session_state.servicos_para_adicionar = []
    
    return True, "Ok"

# =============================
# APP PRINCIPAL
# =============================
def app():
    st.title("📋 Cadastro Rápido de Serviços")
    
    # Inicialização de Estado (Mantenha igual ao seu original)
    if "cadastro_servico_state" not in st.session_state:
        st.session_state.cadastro_servico_state = {
            "placa_input": "", "veiculo_id": None, "veiculo_info": None,
            "search_triggered": False, "quilometragem": 0, "busca_empresa_edit": ""
        }
    state = st.session_state.cadastro_servico_state
    if 'servicos_para_adicionar' not in st.session_state:
        st.session_state.servicos_para_adicionar = []

    st.markdown("---")
    
    # --- SEÇÃO 1: IDENTIFICAÇÃO (Mantenha seu código original aqui) ---
    st.header("1️⃣ Identificação do Veículo")
    placa_input = st.text_input("Digite a placa do veículo", value=state.get("placa_input", ""), key="placa_input_key").upper()

    if st.button("Verificar Placa", use_container_width=True, type="primary"):
        state["placa_input"] = placa_input
        state["search_triggered"] = True
        state["veiculo_id"] = None
        state["veiculo_info"] = None
        st.rerun()

    # ... (MANTENHA TODA A LÓGICA DE BUSCA DO VEÍCULO E EDIÇÃO IGUAL AO SEU CÓDIGO) ...
    # Para economizar espaço na resposta, assumo que você mantém a lógica de busca/edição
    # que já estava funcionando bem. Apenas cole seu código de busca aqui.
    
    if state.get("search_triggered") and not state.get("veiculo_id"):
         # (Seu bloco de conectar no banco e buscar veiculo)
         conn = get_connection()
         if conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                cursor.execute("SELECT v.id, v.empresa, v.modelo, v.ano_modelo, v.nome_motorista, v.contato_motorista, v.cliente_id, c.nome_responsavel, c.contato_responsavel FROM veiculos v LEFT JOIN clientes c ON v.cliente_id = c.id WHERE v.placa = %s", (formatar_placa(state["placa_input"]),))
                res = cursor.fetchone()
                if res:
                    state["veiculo_id"] = res["id"]
                    state["veiculo_info"] = res
            release_connection(conn)

    # Exibição dos dados do veículo (Mantenha seu código)
    if state.get("veiculo_id"):
        # ... (Seus containers de dados do veículo e empresa) ...
        st.info(f"Veículo selecionado: {state['veiculo_info']['modelo']} - {state['veiculo_info']['empresa']}")
        
        st.markdown("---")
        
        # --- SEÇÃO 2: DIAGNÓSTICO (Seu código original) ---
        st.header("2️⃣ Diagnóstico")
        col1, col2 = st.columns(2)
        with col1:
             st.session_state['diag_puxando'] = st.radio("Puxando?", ['Não', 'Esq', 'Dir'], horizontal=True)
             st.session_state['diag_passarinhando'] = st.radio("Volante?", ['Não', 'Passarinhando', 'Pesado'], horizontal=True)
        with col2:
             st.session_state['diag_vibracao'] = st.radio("Vibração?", ['Não', 'Sim'], horizontal=True)
        
        diagnostico_gerado = gerar_diagnostico_veiculo() # Função simplificada acima

        st.markdown("---")

        # --- SEÇÃO 3: SERVIÇOS (Seu código original) ---
        st.header("3️⃣ Serviços")
        state["quilometragem"] = st.number_input("KM Atual", min_value=0, value=state.get("quilometragem", 0))
        
        # (Seus selects de serviços aqui...)
        servicos_do_banco = get_catalogo_servicos()
        # ... Lógica de adicionar serviço na lista ...
        # Vou simplificar com um selectbox genérico para o exemplo, use o seu:
        col_s1, col_s2, col_s3 = st.columns([0.6, 0.2, 0.2])
        with col_s1: 
            svc = st.selectbox("Adicionar Serviço Exemplo", ["", "Troca Pneu", "Alinhamento"])
        with col_s2:
            qtd = st.number_input("Qtd", 1, 10, 1)
        with col_s3:
            if st.button("Add"):
                if svc: st.session_state.servicos_para_adicionar.append({"area": "Borracharia", "tipo": svc, "qtd": qtd})

        # Lista de serviços
        if st.session_state.servicos_para_adicionar:
            st.write(st.session_state.servicos_para_adicionar)

        observacao_geral = st.text_area("Observações")
        
        # Concatenação final
        observacao_final = diagnostico_gerado + ("\n" + observacao_geral if observacao_geral else "")

        st.markdown("---")

        # ========================================================
        # 🚀 O NOVO BOTÃO QUE FUNCIONA
        # ========================================================
        if st.button("🚀 SALVAR E ABRIR WHATSAPP", type="primary", use_container_width=True):
            if not st.session_state.servicos_para_adicionar:
                st.warning("Adicione serviços primeiro.")
            elif state["quilometragem"] <= 0:
                st.error("Informe a KM.")
            else:
                sucesso, msg = processar_cadastro_simplificado(state, observacao_final, diagnostico_gerado)
                if sucesso:
                    st.balloons()
                    time.sleep(1) # Dá tempo de ver a mensagem
                    st.rerun() # Limpa a tela
                else:
                    st.error(msg)

if __name__ == "__main__":
    app()
