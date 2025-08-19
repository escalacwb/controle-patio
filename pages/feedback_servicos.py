import streamlit as st
import pandas as pd
from pages.ui_components import render_mobile_navbar
from database import get_connection, release_connection
from datetime import date, timedelta
from urllib.parse import quote_plus
import re

def app():
    st.title("📝 Controle de Feedback de Serviços")
    st.markdown("Acompanhe e registre o feedback dos serviços concluídos há 5 dias ou mais.")

     # NOVO: Botão para recarregar os dados da página
    col1, col2 = st.columns([0.8, 0.2])
    with col2:
        if st.button("🔄 Atualizar Dados", use_container_width=True, help="Recarrega todos os dados do banco de dados para esta página."):
            st.rerun()

    # --- LÓGICA DO BOTÃO DE FEEDBACK ---
    # Itera sobre as chaves da sessão para encontrar um botão de feedback que foi clicado
    for key in list(st.session_state.keys()):
        if key.startswith("feedback_ok_") and st.session_state[key]:
            # Extrai os IDs de execução da chave, que agora é uma string de IDs separados por vírgula
            execucao_ids_str = key.split("_")[2]
            execucao_ids = [int(id) for id in execucao_ids_str.split(',')]
            
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor() as cursor:
                        # Atualiza TODOS os IDs de execução associados a esta visita de uma só vez
                        cursor.execute(
                            "UPDATE execucao_servico SET data_feedback = NOW() WHERE id = ANY(%s::int[])",
                            (execucao_ids,)
                        )
                        conn.commit()
                        st.toast(f"Feedback para a visita registrada com sucesso!", icon="✅")
                    st.session_state[key] = False # Reseta o estado do botão
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao registrar feedback: {e}")
                finally:
                    release_connection(conn)

    # --- FILTRO DE DATA ---
    st.markdown("---")
    st.subheader("Filtro de Período")
    today = date.today()
    
    start_date = st.date_input(
        "Mostrar serviços concluídos a partir de:",
        value=today - timedelta(days=30),
        max_value=today - timedelta(days=5),
        help="A lista mostrará apenas os serviços concluídos entre esta data e 5 dias atrás."
    )
    st.markdown("---")

    # --- BUSCA E EXIBIÇÃO DOS DADOS ---
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        # ATUALIZADO: A query agora agrupa por visita (placa e quilometragem)
        query = """
            WITH servicos_agrupados AS (
                SELECT 
                    execucao_id, 
                    STRING_AGG(DISTINCT tipo, '; ') as lista_servicos
                FROM (
                    SELECT execucao_id, tipo FROM servicos_solicitados_borracharia WHERE status = 'finalizado'
                    UNION ALL
                    SELECT execucao_id, tipo FROM servicos_solicitados_alinhamento WHERE status = 'finalizado'
                    UNION ALL
                    SELECT execucao_id, tipo FROM servicos_solicitados_manutencao WHERE status = 'finalizado'
                ) s
                GROUP BY execucao_id
            )
            SELECT
                v.placa,
                v.modelo,
                v.nome_motorista,    -- CORRIGIDO: Nome exato da coluna na tabela 'veiculos'
                v.contato_motorista, -- CORRIGIDO: Nome exato da coluna na tabela 'veiculos'
                es.quilometragem,
                MAX(es.fim_execucao) as ultima_data_servico,
                STRING_AGG(sa.lista_servicos, '; ') as todos_os_servicos,
                ARRAY_AGG(es.id) as lista_execucao_ids
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN servicos_agrupados sa ON es.id = sa.execucao_id
            WHERE 
                es.status = 'finalizado'
                AND es.data_feedback IS NULL
                AND es.fim_execucao <= NOW() - INTERVAL '5 days'
                AND es.fim_execucao::date >= %s
            GROUP BY
                v.placa, v.modelo, es.quilometragem, v.nome_motorista, v.contato_motorista -- CORRIGIDO
            ORDER BY
                ultima_data_servico ASC;
        """
        df_feedback = pd.read_sql(query, conn, params=(start_date,))

        if df_feedback.empty:
            st.info("🎉 Nenhum serviço pendente de feedback para o período selecionado.")
            st.stop()
        
        st.subheader(f"Encontradas: {len(df_feedback)} visitas pendentes de feedback")

        for _, row in df_feedback.iterrows():
            with st.container(border=True):
                
                # Prepara as variáveis para a mensagem
                nome_contato = row['nome_motorista'] or "Cliente"
                data_servico = pd.to_datetime(row['ultima_data_servico']).strftime('%d/%m/%Y')
                modelo_caminhao = row['modelo']
                placa_caminhao = row['placa']
                km_caminhao = f"{row['quilometragem']:,}".replace(',', '.') if row['quilometragem'] else "N/A"
                # Consolida todos os serviços da visita
                servicos_executados = row['todos_os_servicos'] or "Não especificado"
                
                mensagem_whatsapp = f"""Prezado {nome_contato},

Somos da Capital Truck Center e estamos fazendo o acompanhamento do serviço realizado no seu veículo {modelo_caminhao}, placa {placa_caminhao}, no dia {data_servico}.

Nossos registros indicam que os serviços foram: {servicos_executados}, na quilometragem de {km_caminhao} km.

Nosso compromisso é com a máxima qualidade e transparência. Por isso, seu feedback é uma etapa essencial do nosso processo. Gostaríamos de saber:

1. O serviço realizado resolveu completamente o problema que o motivou a nos procurar?
2. Como você avalia a agilidade e o conhecimento técnico demonstrado por nossa equipe?
3. Em relação ao nosso atendimento na recepção e à estrutura da loja, sua experiência foi satisfatória?

Sua avaliação, seja ela positiva ou uma crítica construtiva, é confidencial e será direcionada à nossa equipe de qualidade para aprimoramento contínuo.

Agradecemos sua parceria e ficamos à disposição no (67) 98417-3800.

Atenciosamente,
Equipe de Qualidade | Capital Truck Center"""

                numero_limpo = ""
                if row['contato_motorista'] and isinstance(row['contato_motorista'], str):
                    numero_limpo = "55" + re.sub(r'\D', '', row['contato_motorista'])

                mensagem_codificada = quote_plus(mensagem_whatsapp)
                link_whatsapp = f"https://wa.me/{numero_limpo}?text={mensagem_codificada}"

                col1, col2 = st.columns([0.7, 0.3])
                with col1:
                    st.markdown(f"**Veículo:** `{row['placa']}` - {row['modelo']}")
                    st.markdown(f"**Motorista:** {row['nome_motorista'] or 'Não informado'} | **Contato:** {row['contato_motorista'] or 'N/A'}")
                    st.markdown(f"**Todos os Serviços da Visita:** *{servicos_executados}*")
                    st.caption(f"Data do Último Serviço: {data_servico}")
                
                with col2:
                    if len(numero_limpo) > 11:
                        st.link_button(
                            "📲 Enviar WhatsApp", 
                            url=link_whatsapp, 
                            use_container_width=True
                        )
                    else:
                        st.button("📲 Contato Inválido", use_container_width=True, disabled=True, key=f"whatsapp_disabled_{row['placa']}_{row['quilometragem']}")
                    
                    # ATUALIZADO: A chave do botão agora contém todos os IDs da visita
                    ids_string = ",".join(map(str, row['lista_execucao_ids']))
                    st.button(
                        "✅ Feedback Realizado", 
                        key=f"feedback_ok_{ids_string}",
                        use_container_width=True
                    )
    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
    finally:
        release_connection(conn)
