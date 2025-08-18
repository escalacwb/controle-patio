import streamlit as st
import pandas as pd
from pages.ui_components import render_mobile_navbar
render_mobile_navbar(active_page="feedback")
from database import get_connection, release_connection
from datetime import date, timedelta
from urllib.parse import quote_plus
import re

def app():
    st.title("📝 Controle de Feedback de Serviços")
    st.markdown("Acompanhe e registre o feedback dos serviços concluídos há 7 dias ou mais.")

    # --- LÓGICA DO BOTÃO DE FEEDBACK ---
    for key in st.session_state:
        if key.startswith("feedback_ok_") and st.session_state[key]:
            execucao_id = int(key.split("_")[2])
            conn = get_connection()
            if conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            "UPDATE execucao_servico SET data_feedback = NOW() WHERE id = %s",
                            (execucao_id,)
                        )
                        conn.commit()
                        st.toast(f"Feedback para serviço {execucao_id} registrado com sucesso!", icon="✅")
                    st.session_state[key] = False
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
        max_value=today - timedelta(days=7),
        help="A lista mostrará apenas os serviços concluídos entre esta data e 7 dias atrás."
    )
    st.markdown("---")

    # --- BUSCA E EXIBIÇÃO DOS DADOS ---
    conn = get_connection()
    if not conn:
        st.error("Falha ao conectar ao banco de dados.")
        st.stop()

    try:
        query = """
            WITH servicos_agrupados AS (
                SELECT 
                    execucao_id, 
                    STRING_AGG(tipo, '; ') as lista_servicos
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
                es.id as execucao_id,
                es.fim_execucao,
                es.quilometragem,
                v.placa,
                v.modelo,
                es.nome_motorista,
                es.contato_motorista,
                sa.lista_servicos
            FROM execucao_servico es
            JOIN veiculos v ON es.veiculo_id = v.id
            LEFT JOIN servicos_agrupados sa ON es.id = sa.execucao_id
            WHERE 
                es.status = 'finalizado'
                AND es.data_feedback IS NULL
                AND es.fim_execucao <= NOW() - INTERVAL '5 days'
                AND es.fim_execucao >= %s
            ORDER BY es.fim_execucao ASC;
        """
        df_feedback = pd.read_sql(query, conn, params=(start_date,))

        if df_feedback.empty:
            st.info("🎉 Nenhum serviço pendente de feedback para o período selecionado.")
            st.stop()
        
        st.subheader(f"Encontrados: {len(df_feedback)} serviços pendentes de feedback")

        for _, row in df_feedback.iterrows():
            with st.container(border=True):
                
                nome_contato = row['nome_motorista'] or "Cliente"
                data_servico = pd.to_datetime(row['fim_execucao']).strftime('%d/%m/%Y')
                modelo_caminhao = row['modelo']
                placa_caminhao = row['placa']
                km_caminhao = f"{row['quilometragem']:,}".replace(',', '.') if row['quilometragem'] else "N/A"
                servicos_executados = row['lista_servicos'] or "Não especificado"
                
                mensagem_whatsapp = f"""Prezado(a) {nome_contato},

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
                    st.markdown(f"**Serviços:** *{row['lista_servicos']}*")
                    st.caption(f"Data de Conclusão: {data_servico}")
                
                with col2:
                    if len(numero_limpo) > 11:
                        # --- MUDANÇA: Removido o argumento 'key' que estava causando o erro ---
                        st.link_button(
                            "📲 Enviar WhatsApp", 
                            url=link_whatsapp, 
                            use_container_width=True
                        )
                    else:
                        st.button("📲 Contato Inválido", use_container_width=True, disabled=True, key=f"whatsapp_disabled_{row['execucao_id']}")
                    
                    st.button(
                        "✅ Feedback Realizado", 
                        key=f"feedback_ok_{row['execucao_id']}",
                        use_container_width=True
                    )
    except Exception as e:
        st.error(f"Ocorreu um erro ao buscar os dados: {e}")
    finally:
        release_connection(conn)