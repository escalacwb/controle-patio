import psycopg2

def get_connection():
    return psycopg2.connect(
        dbname="postgres",
        user="postgres",
        password="Jokojoko22..",
        host="db.zufsdeqzkwskdlkwpclu.supabase.co",
        port="5432"
    )
