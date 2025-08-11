# /pages/mesclar_historico.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import recalcular_media_veiculo
import psycopg2.extras

# Dicionário para converter o 5º dígito da placa antiga para o padrão Mercosul
CONVERSAO_PLACA = {
    '0': 'A', '1': 'B', '2': 'C', '3': 'D', '4': 'E',
    '5': 'F', '6': 'G', '7': 'H', '8': 'I', '9': 'J'
}

def converter_placa_antiga_para_nova(placa_antiga):
    """Converte uma placa no formato antigo (ex: ABC1234) para o novo (ex: ABC1B34)."""
    if len(placa_antiga) != 7 or not placa_antiga[4].isdigit():
        return None
    quinto_digito = placa_antiga[4]
    if quinto_digito in CONVERSAO_PLACA:
        return f"{placa_antiga[:4]}{CONVERSAO_PLACA[quinto_digito]}{placa_antiga[5:]}"
    return None

def mesclar_dados_veiculos(conn, id_antigo, id_novo):
    """
    Executa a fusão dos dados, transferindo o histórico e consolidando as informações.
    """
    try:
        with conn.cursor() as cursor:
            # 1. Consolida as informações do veículo (pega dados do antigo se o novo não tiver)
            cursor.execute("""
                UPDATE veiculos v_novo
                SET 
                    nome_motorista = COALESCE(v_novo.nome_motorista, v_antigo.nome_motorista),
                    contato_motorista = COALESCE(v_novo.contato_motorista, v_antigo.contato_motorista),
                    empresa = COALESCE(v_novo.empresa, v_antigo.empresa),
                    cliente_id = COALESCE(v_novo.cliente_id, v_antigo.cliente_id)
                FROM veiculos v_antigo
                WHERE v_novo.id = %s AND v_antigo.id = %s;
            """, (id_novo, id_antigo))

            # 2. Re-atribui o histórico de serviços para o novo veículo
            tabelas_servicos = [
                "execucao_servico", 
                "servicos_solicitados_borracharia",
                "servicos_solicitados_alinhamento",
                "servicos_solicitados_manutencao"
            ]
            for tabela in tabelas_servicos:
                cursor.execute(
                    f"UPDATE {tabela} SET veiculo_id = %s WHERE veiculo_id = %s;",
                    (id_novo, id_antigo)
                )

            # 3. Remove o registro do veículo antigo para evitar duplicidade
            cursor.execute("DELETE FROM veiculos WHERE id = %s;", (id_antigo,))

            conn.commit()
            
            # 4. Recalcula a média de KM do veículo novo, agora com o histórico completo
            recalcular_media_veiculo(conn, id_novo)
            
            return True, "Históricos mesclados com sucesso! O registro da placa antiga foi removido."

    except Exception as e:
        conn.rollback()
        return False, f"Ocorreu um erro crítico durante a mesclagem: {e}"

def app():
    st.title("🖇️ Mesclar Históricos de Veículos")
    st.markdown("Use esta ferramenta para fundir o histórico de um veículo que teve a placa alterada do modelo antigo para o Mercosul.")
    st.warning("⚠️ **Atenção:** Esta é uma operação permanente e irá apagar o registro do veículo com a placa antiga. Faça um backup do banco de dados antes de prosseguir.")

    placa_busca = st.text_input("Digite a placa nova (Mercosul) para iniciar a busca", max_chars=7).upper()

    if len(placa_busca) != 7:
        st.info("Por favor, digite uma placa válida com 7 caracteres.")
        st.stop()
    
    conn = get_connection()
    if not conn:
        st.error("Não foi possível conectar ao banco de dados.")
        st.stop()

    try:
        df_novo = pd.read_sql("SELECT * FROM veiculos WHERE placa = %s", conn, params=(placa_busca,))
        
        if df_novo.empty:
            st.error(f"A placa nova '{placa_busca}' não foi encontrada no sistema.")
            st.stop()

        veiculo_novo = df_novo.iloc[0]
        placa_antiga_convertida = converter_placa_antiga_para_nova(placa_busca.replace(placa_busca[4], str(list(CONVERSAO_PLACA.keys())[list(CONVERSAO_PLACA.values()).index(placa_busca[4])]))) if not placa_busca[4].isdigit() else None
        
        placa_antiga_reversa = None
        # Tenta a conversão reversa para encontrar a placa antiga
        for key, value in CONVERSAO_PLACA.items():
            if value == placa_busca[4]:
                placa_antiga_reversa = f"{placa_busca[:4]}{key}{placa_busca[5:]}"
                break
        
        if not placa_antiga_reversa:
            st.warning("A placa digitada não parece ser uma placa Mercosul convertida (o 5º caractere não é uma letra de conversão).")
            st.stop()

        df_antigo = pd.read_sql("SELECT * FROM veiculos WHERE placa = %s", conn, params=(placa_antiga_reversa,))

        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Veículo com Placa Antiga")
            if not df_antigo.empty:
                veiculo_antigo = df_antigo.iloc[0]
                st.success(f"✅ Encontrado: **{veiculo_antigo['placa']}**")
                st.write(f"**ID:** {veiculo_antigo['id']}")
                st.write(f"**Empresa:** {veiculo_antigo['empresa']}")
                st.write(f"**Motorista:** {veiculo_antigo['nome_motorista']}")
            else:
                st.error(f"Placa antiga correspondente '{placa_antiga_reversa}' não encontrada.")

        with col2:
            st.subheader("Veículo com Placa Nova")
            st.info(f"Veículo a ser mantido: **{veiculo_novo['placa']}**")
            st.write(f"**ID:** {veiculo_novo['id']}")
            st.write(f"**Empresa:** {veiculo_novo['empresa']}")
            st.write(f"**Motorista:** {veiculo_novo['nome_motorista']}")

        if not df_antigo.empty and not df_novo.empty:
            st.markdown("---")
            st.subheader("Confirmar Mesclagem")
            st.write(f"O histórico do veículo **{veiculo_antigo['placa']}** será transferido para o veículo **{veiculo_novo['placa']}**. Os dados de contato e empresa serão consolidados, e o registro de **{veiculo_antigo['placa']}** será **permanentemente apagado**.")
            
            if st.button("Confirmar e Mesclar Históricos", type="primary", use_container_width=True):
                with st.spinner("Mesclando dados... Por favor, aguarde."):
                    id_antigo = int(veiculo_antigo['id'])
                    id_novo = int(veiculo_novo['id'])
                    sucesso, mensagem = mesclar_dados_veiculos(conn, id_antigo, id_novo)
                    if sucesso:
                        st.success(mensagem)
                    else:
                        st.error(mensagem)
    finally:
        release_connection(conn)