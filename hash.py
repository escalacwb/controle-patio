# Arquivo: gerar_hash.py
import streamlit_authenticator as stauth
import sys

# Pede para você digitar a senha no terminal
senha_texto_plano = input("Digite a senha do usuário para gerar o novo hash: ")

# Verifica se a senha não está vazia
if not senha_texto_plano:
    print("\nErro: A senha não pode ser vazia.")
    sys.exit(1)

try:
    # A biblioteca espera uma LISTA de senhas.
    senhas_para_hashear = [senha_texto_plano]

    # Gera o hash.
    hashed_passwords = stauth.Hasher(senhas_para_hashear).generate()

    # Pega o primeiro (e único) hash da lista
    hash_final = hashed_passwords[0]

    # Imprime o resultado para você copiar
    print("\n✅ Hash gerado com sucesso!")
    print("Copie a linha abaixo e cole na coluna 'password_hash' do seu banco de dados:")
    print(f"\n{hash_final}\n")

except Exception as e:
    print(f"\nOcorreu um erro inesperado: {e}")
    print("Verifique se a biblioteca 'streamlit-authenticator' e 'bcrypt' estão instaladas corretamente.")
    print("Tente executar: pip install --upgrade streamlit-authenticator")