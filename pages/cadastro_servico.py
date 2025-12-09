#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# /pages/cadastro_servico.py - VERSÃO COM DIAGNÓSTICO POR EIXO
# Data: 09/12/2025
# Status: ✅ Pronto para Produção

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
# FORMULÁRIO DE DIAGNÓSTICO POR EIXO
# =============================

def formulario_diagnostico_por_eixo():
    """
    Formulário dinâmico para diagnóstico de alinhamento por eixo.
    Preenche o session_state com dados dos eixos e comportamentos globais.
    
    Session State criadas:
    - num_eixos: int (1-10)
    - alinhamento_eixo_{i}: bool (para cada eixo)
    - desgaste_motorista_eixo_{i}: list (para cada eixo)
    - desgaste_passageiro_eixo_{i}: list (para cada eixo)
    - diag_puxando: str
    - diag_passarinhando: str
    - diag_vibracao: str
    """
    
    st.markdown("## 📋 Diagnóstico do Veículo")
    
    # Campo para número de eixos
    num_eixos = st.number_input(
        "Número de eixos do conjunto",
        min_value=1,
        max_value=10,
        step=1,
        key="num_eixos",
        help="Digite a quantidade total de eixos (ex: 2, 3, 4)"
    )
    
    if num_eixos > 0:
        st.markdown("### 🔧 Alinhamento por Eixo e Condição dos Pneus")
        
        # Para cada eixo, cria bloco de seleção
        for i in range(1, int(num_eixos) + 1):
            with st.container():
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    st.markdown(f"#### Eixo {i}")
                
                with col2:
                    alinhar_key = f"alinhamento_eixo_{i}"
                    alinhar = st.checkbox(f"Alinhar eixo {i}", key=alinhar_key)
                
                # Se marcado para alinhar, mostra opções de pneus
                if alinhar:
                    st.markdown(f"**Condição dos pneus do eixo {i}:**")
                    
                    col_m, col_p = st.columns(2)
                    
                    # Pneu lado motorista
                    with col_m:
                        desgaste_motorista_key = f"desgaste_motorista_eixo_{i}"
                        st.multiselect(
                            "Lado motorista",
                            options=["Interno", "Centro", "Externo"],
                            key=desgaste_motorista_key,
                            help="Selecione tipo(s) de desgaste"
                        )
                    
                    # Pneu lado passageiro
                    with col_p:
                        desgaste_passageiro_key = f"desgaste_passageiro_eixo_{i}"
                        st.multiselect(
                            "Lado passageiro",
                            options=["Interno", "Centro", "Externo"],
                            key=desgaste_passageiro_key,
                            help="Selecione tipo(s) de desgaste"
                        )
                    
                    st.divider()
    
    st.markdown("### 🏎️ Comportamento em Rodagem")
    
    # Estes três campos seguem exatamente como você já utiliza
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.radio(
            "Puxando?",
            options=["Não", "Esquerda", "Direita"],
            key="diag_puxando",
            horizontal=False
        )
    
    with col2:
        st.radio(
            "Passarinhando?",
            options=["Não", "Leve", "Pesado"],
            key="diag_passarinhando",
            horizontal=False
        )
    
    with col3:
        st.radio(
            "Vibração?",
            options=["Não", "Sim"],
            key="diag_vibracao",
            horizontal=False
        )


# =============================
# GERAÇÃO DO DIAGNÓSTICO COM BASE NOS EIXOS
# =============================

def gerar_diagnostico_veiculo():
    """
    Gera um texto descritivo baseado nos eixos e comportamentos.
    Retorna uma string formatada para concatenar com observações.
    
    Processa:
    1. Número de eixos informado
    2. Quais eixos foram marcados para alinhamento
    3. Desgastes de pneus (motorista + passageiro) por eixo
    4. Comportamentos globais (puxando, passarinhando, vibração)
    
    Retorna string formatada com bullets e texto legível
    """
    
    linhas = []
    
    num_eixos = st.session_state.get("num_eixos", 0)
    
    # BLOCO 1: Eixos e Alinhamento
    if num_eixos and num_eixos > 0:
        linhas.append(f"Conjunto com {num_eixos} eixo(s).")
        
        eixos_alinhamento = []
        detalhes_eixos = []
        
        for i in range(1, int(num_eixos) + 1):
            alinhar = st.session_state.get(f"alinhamento_eixo_{i}", False)
            
            if not alinhar:
                continue
            
            # Marca que este eixo será alinhado
            eixos_alinhamento.append(str(i))
            
            desgaste_motorista = st.session_state.get(f"desgaste_motorista_eixo_{i}", [])
            desgaste_passageiro = st.session_state.get(f"desgaste_passageiro_eixo_{i}", [])
            
            # Montagem do texto por eixo
            texto_eixo = f"- Eixo {i}: alinhamento recomendado"
            
            detalhes_pneu = []
            
            if desgaste_motorista:
                tipos = ", ".join(desgaste_motorista)
                detalhes_pneu.append(f"pneu motorista com desgaste em {tipos.lower()}")
            
            if desgaste_passageiro:
                tipos = ", ".join(desgaste_passageiro)
                detalhes_pneu.append(f"pneu passageiro com desgaste em {tipos.lower()}")
            
            if detalhes_pneu:
                texto_eixo += " (" + ", ".join(detalhes_pneu) + ")."
            else:
                texto_eixo += "."
            
            detalhes_eixos.append(texto_eixo)
        
        # Adiciona resumo dos eixos
        if eixos_alinhamento:
            if len(eixos_alinhamento) == 1:
                linhas.append(f"Eixo a alinhar: Eixo {eixos_alinhamento[0]}.")
            else:
                lista_eixos = ", ".join(eixos_alinhamento)
                linhas.append(f"Eixos a alinhar: {lista_eixos}.")
            
            # Adiciona detalhes de cada eixo
            linhas.extend(detalhes_eixos)
        else:
            linhas.append("Nenhum eixo marcado para alinhamento.")
    
    else:
        linhas.append("Número de eixos não informado.")
    
    # BLOCO 2: Puxando
    diag_puxando = st.session_state.get("diag_puxando", "Não")
    if diag_puxando == "Não":
        linhas.append("- Veículo NÃO está puxando para nenhum lado.")
    elif diag_puxando == "Esquerda":
        linhas.append("- Veículo está puxando para a ESQUERDA.")
    elif diag_puxando == "Direita":
        linhas.append("- Veículo está puxando para a DIREITA.")
    
    # BLOCO 3: Passarinhando
    diag_passarinhando = st.session_state.get("diag_passarinhando", "Não")
    if diag_passarinhando == "Não":
        linhas.append("- Veículo NÃO está passarinhando (comportamento normal).")
    elif diag_passarinhando == "Leve":
        linhas.append("- Veículo apresenta leve instabilidade (passarinhando leve).")
    elif diag_passarinhando == "Pesado":
        linhas.append("- Veículo apresenta instabilidade acentuada (passarinhando pesado).")
    
    # BLOCO 4: Vibração
    diag_vibracao = st.session_state.get("diag_vibracao", "Não")
    if diag_vibracao == "Não":
        linhas.append("- Veículo NÃO apresenta vibração perceptível.")
    elif diag_vibracao == "Sim":
        linhas.append("- Veículo apresenta VIBRAÇÃO em rodagem.")
    
    # Junta todas as linhas em um texto único
    diagnostico = "\n".join(linhas)
    return diagnostico.strip()


# =============================
# FILA DE EVENTOS ROBUSTA
# =============================

def processar_cadastro_completo(state, observacao_final, diagnostico_gerado):
    """
    Processa o cadastro de serviços de forma robusta e sequencial.
    
    ETAPA 1: Salvar no banco de dados
    ETAPA 2: Formatar mensagem WhatsApp
    ETAPA 3-6: Feedback visual e abertura do WhatsApp
    """
    
    # ETAPA 1: SALVAR NO BANCO
    print("⏱️ [ETAPA 1] Salvando no banco de dados...")
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
        if conn:
            release_connection(conn)
        return False, f"❌ Erro ao salvar no banco: {str(e)}"
    
    # ETAPA 2: FORMATAR MENSAGEM COMPLETA
    print("⏱️ [ETAPA 2] Formatando mensagem WhatsApp...")
    
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

👨💼 *DADOS DO MOTORISTA:*

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
    print("⏱️ [ETAPA 3] Exibindo feedback positivo...")
    st.success("✅ ETAPA 1: Serviço cadastrado no banco com sucesso!")
    time.sleep(0.5)
    
    # ETAPA 4: PREPARANDO LINK
    print("⏱️ [ETAPA 4] Preparando link WhatsApp com mensagem...")
    st.info("✅ ETAPA 2: Preparando mensagem para envio...")
    time.sleep(0.5)
    
    # ETAPA 5: EXIBIR INSTRUÇÃO
    st.info("✅ ETAPA 2: Abrindo WhatsApp em alguns segundos...")
    time.sleep(0.5)
    
    # ETAPA 6: ABRIR WHATSAPP COM MENSAGEM NO LINK
    print("⏱️ [ETAPA 6] Abrindo WhatsApp com mensagem no link...")
    
    try:
        # URL encode a mensagem para usar no link wa.me
        mensagem_encoded = urllib.parse.quote(mensagem)
        whatsapp_link = f"https://wa.me/?text={mensagem_encoded}"
        
        components.html(f"""
        <script>
            window.open("{whatsapp_link}", "_blank");
        </script>
        """, height=0)
        
        print("✅ [ETAPA 6] CONCLUÍDO - WhatsApp aberto")
        return True, "✅ Serviço cadastrado e WhatsApp aberto!"
    
    except Exception as e:
        return False, f"❌ Erro ao abrir WhatsApp: {str(e)}"


# =============================
# FUNÇÃO PRINCIPAL (app)
# =============================

def app():
    """
    Fluxo principal da página de cadastro de serviço.
    """
    
    st.title("🔧 Cadastro de Serviço")
    
    # SEÇÃO 1: BUSCA DO VEÍCULO
    st.markdown("---")
    st.markdown("## 🚛 Identificação do Veículo")
    
    placa_input = st.text_input(
        "Placa do veículo (ex: ABC1234)",
        key="placa_temp"
    )
    
    if placa_input:
        placa_formatada = formatar_placa(placa_input)
        
        try:
            veiculo_info = consultar_placa_comercial(placa_formatada)
            
            if veiculo_info:
                st.session_state.placa_input = placa_formatada
                st.session_state.veiculo_id = veiculo_info.get('id')
                st.session_state.veiculo_info = veiculo_info
                
                st.success(f"✅ Veículo encontrado: {veiculo_info.get('modelo')} ({veiculo_info.get('ano_modelo')})")
                
                # Input de quilometragem
                quilometragem = st.number_input(
                    "Quilometragem atual",
                    min_value=0,
                    step=1000,
                    key="quilometragem"
                )
                st.session_state.quilometragem = quilometragem
            else:
                st.error("❌ Veículo não encontrado. Verifique a placa.")
                return
        
        except Exception as e:
            st.error(f"❌ Erro ao buscar veículo: {str(e)}")
            return
    else:
        st.info("Digite a placa do veículo para continuar.")
        return
    
    # SEÇÃO 2: DIAGNÓSTICO DO VEÍCULO
    st.markdown("---")
    formulario_diagnostico_por_eixo()
    
    # SEÇÃO 3: SELEÇÃO DE SERVIÇOS
    st.markdown("---")
    st.markdown("## 🛠️ Serviços Solicitados")
    
    try:
        catalogo = get_catalogo_servicos()
        
        # Inicializar session state para serviços
        if 'servicos_para_adicionar' not in st.session_state:
            st.session_state.servicos_para_adicionar = []
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            area = st.selectbox(
                "Área de serviço",
                options=[s['area'] for s in catalogo],
                key="area_select"
            )
        
        tipos_disponiveis = [s['tipos'] for s in catalogo if s['area'] == area]
        tipos = tipos_disponiveis[0] if tipos_disponiveis else []
        
        with col2:
            tipo = st.selectbox(
                "Tipo de serviço",
                options=tipos,
                key="tipo_select"
            )
        
        with col3:
            qtd = st.number_input(
                "Quantidade",
                min_value=1,
                step=1,
                key="qtd_select"
            )
        
        if st.button("➕ Adicionar Serviço"):
            st.session_state.servicos_para_adicionar.append({
                'area': area,
                'tipo': tipo,
                'qtd': qtd
            })
            st.success(f"✅ {tipo} adicionado!")
            time.sleep(0.5)
            st.rerun()
        
        # Mostrar serviços adicionados
        if st.session_state.servicos_para_adicionar:
            st.markdown("### Serviços selecionados:")
            for idx, s in enumerate(st.session_state.servicos_para_adicionar, 1):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"{idx}. {s['tipo']} (Qtd: {s['qtd']}) - {s['area']}")
                with col2:
                    if st.button("❌", key=f"remove_{idx}"):
                        st.session_state.servicos_para_adicionar.pop(idx - 1)
                        st.rerun()
    
    except Exception as e:
        st.error(f"❌ Erro ao carregar catálogo de serviços: {str(e)}")
        return
    
    # SEÇÃO 4: OBSERVAÇÕES ADICIONAIS
    st.markdown("---")
    st.markdown("## 📝 Observações Adicionais")
    
    observacoes_digitadas = st.text_area(
        "Digite observações que não foram capturadas no diagnóstico",
        key="observacao_texto",
        height=100
    )
    
    # SEÇÃO 5: BOTÃO DE CADASTRO
    st.markdown("---")
    
    if st.button("✅ CADASTRAR SERVIÇO", type="primary", use_container_width=True):
        
        # Validações
        if 'veiculo_id' not in st.session_state or not st.session_state.veiculo_id:
            st.error("❌ Selecione um veículo primeiro.")
            return
        
        if not st.session_state.servicos_para_adicionar:
            st.error("❌ Adicione pelo menos um serviço.")
            return
        
        # Gerar diagnóstico
        diagnostico_gerado = gerar_diagnostico_veiculo()
        
        # Montar observação final
        if observacoes_digitadas and observacoes_digitadas.strip():
            observacao_final = diagnostico_gerado + "\n\nObservações adicionais:\n" + observacoes_digitadas.strip()
        else:
            observacao_final = diagnostico_gerado
        
        # Processar cadastro
        sucesso, msg = processar_cadastro_completo(
            st.session_state,
            observacao_final=observacao_final,
            diagnostico_gerado=diagnostico_gerado
        )
        
        if not sucesso:
            st.error(msg)
        else:
            st.success(msg)
            # Limpar formulário
            if st.button("🔄 Novo Cadastro"):
                st.session_state.clear()
                st.rerun()


# Executa a aplicação
if __name__ == "__main__":
    app()
