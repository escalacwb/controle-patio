# pages/exportar_contatos.py
import streamlit as st
import pandas as pd
import io
import re  # Importa a biblioteca de expressões regulares
from database import get_connection, release_connection

# NOVA FUNÇÃO, MAIS ROBUSTA, PARA PADRONIZAR TELEFONES
def padronizar_telefone(numero):
    """
    Recebe um número de telefone em qualquer formato e o retorna
    no padrão internacional E.164 (+55DDD9XXXXXXXX), adicionando
    o nono dígito para celulares quando necessário.
    """
    if not numero or not isinstance(numero, str):
        return ""

    # 1. Remove todos os caracteres não numéricos
    numero_limpo = re.sub(r'\D', '', numero)

    # 2. Se tiver '55' no início, remove temporariamente para análise
    if numero_limpo.startswith('55'):
        numero_limpo = numero_limpo[2:]

    # 3. Se tiver '0' no início do DDD, remove
    if len(numero_limpo) > 10 and numero_limpo.startswith('0'):
        numero_limpo = numero_limpo[1:]

    # 4. Verifica se precisa adicionar o nono dígito
    #    Aplica a regra para números com DDD e 8 dígitos (total 10)
    #    que parecem ser celulares (começam com 6, 7, 8 ou 9)
    if len(numero_limpo) == 10:
        ddd = numero_limpo[:2]
        telefone = numero_limpo[2:]
        if telefone.startswith(('6', '7', '8', '9')):
            numero_limpo = f"{ddd}9{telefone}"

    # 5. Se o número resultante (sem 55) for válido (10 para fixo, 11 para celular),
    #    remonta com o +55.
    if len(numero_limpo) in [10, 11]:
        return f"+55{numero_limpo}"
    
    # 6. Se for um número inválido, retorna o que conseguiu limpar, sem o +55
    #    para que o erro seja evidente na exportação.
    return numero_limpo


def get_contacts_to_export(re_export_all=False):
    """
    Busca contatos de responsáveis e motoristas que são novos ou foram
    atualizados desde a última exportação.
    """
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        return pd.DataFrame(), pd.DataFrame()

    try:
        # Query para responsáveis de empresas
        query_responsaveis = """
            SELECT nome_responsavel, contato_responsavel, nome_empresa, id AS cliente_id
            FROM clientes
            WHERE 
                (nome_responsavel IS NOT NULL AND nome_responsavel <> '') AND
                (contato_responsavel IS NOT NULL AND contato_responsavel <> '')
        """
        if not re_export_all:
            query_responsaveis += " AND (data_ultima_exportacao IS NULL OR data_atualizacao_contato > data_ultima_exportacao)"

        # Query para motoristas de veículos
        query_motoristas = """
            SELECT v.nome_motorista, v.contato_motorista, c.nome_empresa, v.placa, v.modelo, v.id AS veiculo_id
            FROM veiculos v
            LEFT JOIN clientes c ON v.cliente_id = c.id
            WHERE
                (v.nome_motorista IS NOT NULL AND v.nome_motorista <> '') AND
                (v.contato_motorista IS NOT NULL AND v.contato_motorista <> '')
        """
        if not re_export_all:
            query_motoristas += " AND (v.data_ultima_exportacao IS NULL OR v.data_atualizacao_contato > v.data_ultima_exportacao)"

        df_responsaveis = pd.read_sql(query_responsaveis, conn)
        df_motoristas = pd.read_sql(query_motoristas, conn)
        
        return df_responsaveis, df_motoristas

    except Exception as e:
        st.error(f"Erro ao buscar contatos: {e}")
        return pd.DataFrame(), pd.DataFrame()
    finally:
        release_connection(conn)

def format_for_google_contacts(df_responsaveis, df_motoristas):
    """
    Formata os dataframes no padrão CSV do Google Contacts.
    """
    contacts_list = []

    for _, row in df_responsaveis.iterrows():
        contacts_list.append({
            "Name Prefix": "Responsável",
            "First Name": row["nome_responsavel"],
            "Middle Name": row["nome_empresa"],
            "Last Name": "",
            "Name Suffix": "",
            "Phone 1 - Type": "Celular",
            "Phone 1 - Value": padronizar_telefone(row["contato_responsavel"]),
            "Notes": f"Contato da empresa {row['nome_empresa']}",
            "internal_id": f"cliente_{row['cliente_id']}"
        })

    for _, row in df_motoristas.iterrows():
        contacts_list.append({
            "Name Prefix": "Motorista",
            "First Name": row["nome_motorista"],
            "Middle Name": row["nome_empresa"] or "",
            "Last Name": row["placa"],
            "Name Suffix": row["modelo"] or "",
            "Phone 1 - Type": "Celular",
            "Phone 1 - Value": padronizar_telefone(row["contato_motorista"]),
            "Notes": f"Motorista do veículo {row['placa']} da empresa {row['nome_empresa']}",
            "internal_id": f"veiculo_{row['veiculo_id']}"
        })
    
    if not contacts_list:
        return pd.DataFrame()

    df_final = pd.DataFrame(contacts_list)
    google_columns_order = [
        "Name Prefix", "First Name", "Middle Name", "Last Name", "Name Suffix",
        "Phone 1 - Type", "Phone 1 - Value", "Notes", "internal_id"
    ]
    # Garante que todas as colunas existam, preenchendo com vazio se necessário
    for col in google_columns_order:
        if col not in df_final.columns:
            df_final[col] = ""
            
    return df_final[google_columns_order]

def mark_contacts_as_exported(exported_ids):
    """
    Atualiza a coluna 'data_ultima_exportacao' com a data e hora atuais.
    """
    if not exported_ids:
        return

    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados para marcar contatos.")
        return

    cliente_ids = [int(id.split('_')[1]) for id in exported_ids if id.startswith('cliente_')]
    veiculo_ids = [int(id.split('_')[1]) for id in exported_ids if id.startswith('veiculo_')]

    try:
        with conn.cursor() as cursor:
            if cliente_ids:
                cursor.execute(
                    "UPDATE clientes SET data_ultima_exportacao = NOW() WHERE id = ANY(%s)",
                    (cliente_ids,)
                )
            if veiculo_ids:
                cursor.execute(
                    "UPDATE veiculos SET data_ultima_exportacao = NOW() WHERE id = ANY(%s)",
                    (veiculo_ids,)
                )
            conn.commit()
            st.success(f"{len(exported_ids)} contatos marcados como exportados com sucesso!")
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao marcar contatos como exportados: {e}")
    finally:
        release_connection(conn)


def app():
    """
    Função principal da página.
    """
    st.title("📤 Exportar Contatos para o Google")

    st.markdown("""
    Esta página gera um arquivo CSV com os contatos de **responsáveis de empresas** e **motoristas de veículos** que foram **adicionados ou atualizados** desde a última exportação.
    """)

    re_export_all = st.checkbox("Forçar re-exportação de TODOS os contatos")

    if st.button("Gerar Arquivo CSV", type="primary"):
        with st.spinner("Buscando e formatando contatos..."):
            df_responsaveis, df_motoristas = get_contacts_to_export(re_export_all)
            
            if df_responsaveis.empty and df_motoristas.empty:
                st.info("Nenhum contato novo ou atualizado para exportar.")
                st.stop()

            df_final = format_for_google_contacts(df_responsaveis, df_motoristas)

            if df_final.empty:
                st.info("Nenhum contato formatado para exportar.")
                st.stop()
            
            internal_ids = df_final["internal_id"].tolist()
            df_to_export = df_final.drop(columns=["internal_id"])

            output = io.StringIO()
            df_to_export.to_csv(output, index=False, encoding='utf-8-sig')
            csv_data = output.getvalue()

            st.session_state.csv_data_to_download = csv_data
            st.session_state.ids_to_mark_exported = internal_ids
    
    if 'csv_data_to_download' in st.session_state and st.session_state.csv_data_to_download:
        total_contacts = len(st.session_state.ids_to_mark_exported)
        st.success(f"Arquivo com {total_contacts} contatos pronto para download!")

        st.download_button(
            label="Clique aqui para baixar o CSV",
            data=st.session_state.csv_data_to_download,
            file_name="google_contacts.csv",
            mime="text/csv",
        )

        if not re_export_all:
            if st.button("Confirmar e Marcar Contatos como Exportados"):
                with st.spinner("Atualizando banco de dados..."):
                    mark_contacts_as_exported(st.session_state.ids_to_mark_exported)
                    del st.session_state.csv_data_to_download
                    del st.session_state.ids_to_mark_exported
                    st.rerun()

# Ponto de entrada da página
app()