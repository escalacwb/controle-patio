import streamlit as st
import database

def app():
    st.title("Cadastro de Veículo")
    with st.form("cadastro_form"):
        placa = st.text_input("Placa")
        motorista = st.text_input("Motorista")
        empresa = st.text_input("Empresa")
        submitted = st.form_submit_button("Cadastrar")
        if submitted:
            conn = database.get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO veiculos (placa, motorista, empresa) VALUES (%s, %s, %s)",
                        (placa, motorista, empresa))
            conn.commit()
            conn.close()
            st.success("Veículo cadastrado!")
