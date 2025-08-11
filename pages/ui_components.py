# /pages/ui_components.py (NOVO ARQUIVO SUGERIDO PARA ORGANIZAÇÃO)

import streamlit as st

NAVBAR_CSS = """
<style>
    /* espaço extra no fim da página para não encobrir conteúdo */
    .block-container {{ padding-bottom: 7rem; }}

    .ctc-bottom-nav {{
        position: fixed; left: 0; right: 0; bottom: 0;
        z-index: 9999;
        background: rgba(16,16,20,0.98);
        border-top: 1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(6px);
        -webkit-backdrop-filter: blur(6px);
        font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    }}
    .ctc-bottom-nav .wrap {{
        max-width: 1100px; margin: 0 auto; padding: 10px 16px;
        display: flex; justify-content: space-around; align-items: center; gap: 8px;
    }}
    .ctc-bottom-nav a {{
        text-decoration: none; text-align: center; font-size: 12px; line-height: 1.2;
        color: #fff;
        opacity: .72; transition: opacity .15s ease, transform .15s ease;
        display: inline-flex; flex-direction: column; align-items: center; gap: 6px;
    }}
    .ctc-bottom-nav a .ico {{
        font-size: 20px; width: 28px; height: 28px; display: grid; place-items: center;
        border-radius: 10px; border: 1px solid rgba(255,255,255,.1);
    }}
    .ctc-bottom-nav a.active {{ opacity: 1; font-weight: 600; }}
    .ctc-bottom-nav a:active {{ transform: translateY(1px); }}
</style>
"""

def render_mobile_navbar(active_page):
    is_admin = st.session_state.get('user_role') == 'admin'

    nav_items = {
        "cadastro": {"href": "cadastro_servico", "icon": "🧾", "label": "Cadastro", "admin_only": False},
        "alocar": {"href": "alocar_servicos", "icon": "🧲", "label": "Alocar", "admin_only": False},
        "filas": {"href": "filas_servico", "icon": "📋", "label": "Filas", "admin_only": False},
        "boxes": {"href": "visao_boxes", "icon": "🧰", "label": "Boxes", "admin_only": False},
        "feedback": {"href": "feedback_servicos", "icon": "📞", "label": "Feedback", "admin_only": True},
        "revisao": {"href": "revisao_proativa", "icon": "🔄", "label": "Revisão", "admin_only": True}
    }
    
    nav_html = NAVBAR_CSS + '<div class="ctc-bottom-nav"><div class="wrap">'
    
    for key, item in nav_items.items():
        if not item["admin_only"] or (item["admin_only"] and is_admin):
            active_class = 'active' if active_page == key else ''
            nav_html += f"""
                <a class="{active_class}" href="{item['href']}">
                    <span class="ico">{item['icon']}</span><span>{item['label']}</span>
                </a>
            """
            
    nav_html += '</div></div>'
    st.markdown(nav_html, unsafe_allow_html=True)