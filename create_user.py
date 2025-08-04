import psycopg2
from dotenv import load_dotenv
import os
import hashlib

# Função para criar o hash da senha
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Carrega a URL do banco do arquivo .env
load_dotenv()
db_url = os.getenv("DB_URL")

# Coleta as informações do novo usuário
nome = input("Digite o nome completo do usuário: ")
username = input("Digite o nome de login (username): ")
password = input("Digite a senha: ")
role = input("Digite a permissão (role) [admin/funcionario]: ")

# Gera o hash da senha
password_hash = hash_password(password)

try:
    # Conecta e insere o novo usuário no banco de dados
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usuarios (nome, username, password_hash, role) VALUES (%s, %s, %s, %s)",
        (nome, username, password_hash, role)
    )
    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n✅ Usuário '{username}' criado com sucesso!")

except Exception as e:
    print(f"\n❌ Erro ao criar usuário: {e}")