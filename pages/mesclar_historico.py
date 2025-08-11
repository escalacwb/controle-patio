# /pages/mesclar_historico.py

import streamlit as st
import pandas as pd
from database import get_connection, release_connection
from utils import recalcular_media_veiculo
import psycopg2.extras

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
                    cliente_id = COALESCE(v_novo.cliente_id, v_antigo.cliente_id),
                    modelo = COALESCE(v_novo.modelo, v_antigo.modelo),
                    ano_modelo = COALESCE(v_novo.ano_modelo, v_antigo.ano_modelo)
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
    st.markdown("Esta ferramenta analisa todos os veículos e sugere fusões para placas que mudaram do modelo antigo para o Mercosul.")
    st.warning("⚠️ **Atenção:** A mesclagem é uma operação permanente e irá apagar o registro do veículo com a placa antiga. Faça um backup do banco de dados antes de prosseguir.")
    st.markdown("---")

    conn = get_connection()
    if not conn:
        st.error("Não foi possível conectar ao banco de dados.")
        st.stop()

    try:
        # Nova query que faz um self-join para encontrar todos os pares de placas correspondentes
        query_pares = """
            SELECT
                v_antigo.id AS id_antigo,
                v_antigo.placa AS placa_antiga,
                v_novo.id AS id_novo,
                v_novo.placa AS placa_nova
            FROM
                veiculos AS v_antigo
            JOIN
                veiculos AS v_novo ON
                    -- Garante que estamos comparando uma placa antiga com uma nova
                    SUBSTRING(v_antigo.placa, 5, 1) ~ '[0-9]' AND
                    SUBSTRING(v_novo.placa, 5, 1) ~ '[A-Z]' AND
                    -- Compara as partes que não mudam na placa
                    SUBSTRING(v_novo.placa, 1, 4) = SUBSTRING(v_antigo.placa, 1, 4) AND
                    SUBSTRING(v_novo.placa, 6, 2) = SUBSTRING(v_antigo.placa, 6, 2) AND
                    -- Aplica a regra de conversão da letra
                    SUBSTRING(v_novo.placa, 5, 1) = CASE SUBSTRING(v_antigo.placa, 5, 1)
                                                        WHEN '0' THEN 'A' WHEN '1' THEN 'B'
                                                        WHEN '2' THEN 'C' WHEN '3' THEN 'D'
                                                        WHEN '4' THEN 'E' WHEN '5' THEN 'F'
                                                        WHEN '6' THEN 'G' WHEN '7' THEN 'H'
                                                        WHEN '8' THEN 'I' WHEN '9' THEN 'J'
                                                      END;
        """
        
        with st.spinner("Procurando por placas para mesclar..."):
            df_pares = pd.read_sql(query_pares, conn)

        if df_pares.empty:
            st.success("✅ Nenhuma placa com potencial de mesclagem foi encontrada no sistema.")
            st.stop()
        
        st.subheader(f"Encontrados {len(df_pares)} pares de placas para possível mesclagem:")

        for _, par in df_pares.iterrows():
            id_antigo = int(par['id_antigo'])
            placa_antiga = par['placa_antiga']
            id_novo = int(par['id_novo'])
            placa_nova = par['placa_nova']
            
            with st.container(border=True):
                cols = st.columns([0.4, 0.4, 0.2])
                cols[0].metric("Placa Antiga (será removida)", placa_antiga)
                cols[1].metric("Placa Nova (será mantida)", placa_nova)
                
                with cols[2]:
                    st.write("") # Espaçamento para alinhar o botão
                    if st.button("Mesclar Históricos", key=f"merge_{id_antigo}", type="primary", use_container_width=True):
                        with st.spinner(f"Mesclando {placa_antiga} -> {placa_nova}..."):
                            sucesso, mensagem = mesclar_dados_veiculos(conn, id_antigo, id_novo)
                            if sucesso:
                                st.success(mensagem)
                                st.rerun()
                            else:
                                st.error(mensagem)
                                
    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os pares de placas: {e}")
    finally:
        release_connection(conn)