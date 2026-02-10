from datetime import datetime, timedelta
from typing import List

import pandas as pd
import pytz
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from api.auth import create_access_token, get_current_user
from api.db import get_connection, release_connection
from api.schemas import (
    AllocationRequest,
    AddBoxServiceRequest,
    BoxFinalizeRequest,
    CreateClientRequest,
    LoginRequest,
    LoginResponse,
    LinkCompanyRequest,
    RegisterServiceRequest,
    RevertVisitRequest,
    UpdateClientRequest,
    UpdateServiceTypeRequest,
    UpdateVehicleRequest,
)
from api.utils import formatar_placa, formatar_telefone, hash_password

app = FastAPI(title="Controle Patio API")
MS_TZ = pytz.timezone("America/Campo_Grande")


def _recalcular_media_veiculo(conn, veiculo_id: int) -> None:
    query = """
    SELECT id, fim_execucao, quilometragem
    FROM (
        SELECT
            id,
            fim_execucao,
            quilometragem,
            ROW_NUMBER() OVER (PARTITION BY fim_execucao, quilometragem ORDER BY id) as rn
        FROM execucao_servico
        WHERE veiculo_id = %s AND status = 'finalizado'
          AND quilometragem IS NOT NULL AND quilometragem > 0
    ) as ranked
    WHERE rn = 1
    ORDER BY fim_execucao ASC;
    """

    df_veiculo = pd.read_sql(query, conn, params=(veiculo_id,))
    df_veiculo = df_veiculo.drop_duplicates(subset=["quilometragem"], keep="last")

    last_valid_km = -1
    valid_indices = []
    for index, row in df_veiculo.iterrows():
        if row["quilometragem"] > last_valid_km:
            valid_indices.append(index)
            last_valid_km = row["quilometragem"]

    valid_group = df_veiculo.loc[valid_indices]
    media_km_diaria = None
    if len(valid_group) >= 2:
        ultimas_3 = valid_group.iloc[-3:] if len(valid_group) >= 3 else valid_group
        primeira_visita = ultimas_3.iloc[0]
        ultima_visita = ultimas_3.iloc[-1]
        delta_km = int(ultima_visita["quilometragem"]) - int(primeira_visita["quilometragem"])
        delta_dias = (ultima_visita["fim_execucao"] - primeira_visita["fim_execucao"]).days
        if delta_dias > 0 and delta_km >= 0:
            media_km_diaria = float(delta_km / delta_dias)

    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE veiculos SET media_km_diaria = %s WHERE id = %s",
            (media_km_diaria, veiculo_id),
        )


@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, nome, password_hash, role FROM usuarios WHERE username = %s",
                (payload.username,),
            )
            user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Credenciais invalidas")
        if hash_password(payload.password) != user[2]:
            raise HTTPException(status_code=401, detail="Credenciais invalidas")
        token = create_access_token({"sub": str(user[0]), "role": user[3]})
        return LoginResponse(
            access_token=token,
            user_id=user[0],
            user_name=user[1],
            user_role=user[3],
        )
    finally:
        release_connection(conn)


@app.get("/catalog/services")
def get_catalogo_servicos(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT nome FROM servicos_borracharia ORDER BY nome")
            borracharia = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT nome FROM servicos_alinhamento ORDER BY nome")
            alinhamento = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT nome FROM servicos_manutencao ORDER BY nome")
            manutencao = [r[0] for r in cursor.fetchall()]
        return {
            "borracharia": borracharia,
            "alinhamento": alinhamento,
            "manutencao": manutencao,
        }
    finally:
        release_connection(conn)


@app.get("/vehicles/by-plate/{placa}")
def get_vehicle_by_plate(placa: str, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        placa_fmt = formatar_placa(placa)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.id, v.placa, v.empresa, v.modelo, v.ano_modelo,
                       v.nome_motorista, v.contato_motorista, v.cliente_id,
                       c.nome_responsavel, c.contato_responsavel
                FROM veiculos v
                LEFT JOIN clientes c ON v.cliente_id = c.id
                WHERE v.placa = %s
                """,
                (placa_fmt,),
            )
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Veiculo nao encontrado")
        return {
            "id": row[0],
            "placa": row[1],
            "empresa": row[2],
            "modelo": row[3],
            "ano_modelo": row[4],
            "nome_motorista": row[5],
            "contato_motorista": row[6],
            "cliente_id": row[7],
            "nome_responsavel": row[8],
            "contato_responsavel": row[9],
        }
    finally:
        release_connection(conn)


@app.post("/services/register")
def register_service(payload: RegisterServiceRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    table_map = {
        "borracharia": "servicos_solicitados_borracharia",
        "alinhamento": "servicos_solicitados_alinhamento",
        "manutencao": "servicos_solicitados_manutencao",
    }
    try:
        with conn.cursor() as cursor:
            for item in payload.itens:
                table_name = table_map.get(item.area.lower())
                if not table_name:
                    raise HTTPException(status_code=400, detail="Area invalida")
                cursor.execute(
                    f"""
                    INSERT INTO {table_name}
                        (veiculo_id, tipo, quantidade, observacao, quilometragem, status, data_solicitacao, data_atualizacao)
                    VALUES (%s, %s, %s, %s, %s, 'pendente', %s, %s)
                    """,
                    (
                        payload.veiculo_id,
                        item.tipo,
                        item.qtd,
                        payload.observacao or "",
                        payload.quilometragem,
                        datetime.now(MS_TZ),
                        datetime.now(MS_TZ),
                    ),
                )
            cursor.execute(
                "UPDATE veiculos SET data_revisao_proativa = NULL WHERE id = %s",
                (payload.veiculo_id,),
            )
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.get("/clients/search")
def search_clients(term: str, user=Depends(get_current_user)):
    if not term or len(term) < 3:
        return []
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, nome_empresa, nome_fantasia
                FROM clientes
                WHERE similarity(nome_empresa, %(termo)s) > 0.2 OR similarity(nome_fantasia, %(termo)s) > 0.2
                ORDER BY GREATEST(similarity(nome_empresa, %(termo)s), similarity(nome_fantasia, %(termo)s)) DESC, nome_empresa
                LIMIT 10;
                """,
                {"termo": term},
            )
            rows = cursor.fetchall()
        return [
            {"id": r[0], "nome_empresa": r[1], "nome_fantasia": r[2]} for r in rows
        ]
    finally:
        release_connection(conn)


@app.get("/clients/{client_id}")
def get_client_details(client_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT nome_responsavel, contato_responsavel FROM clientes WHERE id = %s",
                (client_id,),
            )
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Cliente nao encontrado")
        return {"nome_responsavel": row[0], "contato_responsavel": row[1]}
    finally:
        release_connection(conn)


@app.post("/clients")
def create_client(payload: CreateClientRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO clientes (nome_empresa, nome_fantasia) VALUES (%s, %s) RETURNING id",
                (payload.nome_empresa, payload.nome_fantasia),
            )
            client_id = cursor.fetchone()[0]
        conn.commit()
        return {"id": client_id}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.put("/clients/{client_id}")
def update_client(client_id: int, payload: UpdateClientRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE clientes
                   SET nome_responsavel = %s,
                       contato_responsavel = %s,
                       data_atualizacao_contato = NOW()
                 WHERE id = %s
                """,
                (
                    payload.nome_responsavel,
                    formatar_telefone(payload.contato_responsavel or ""),
                    client_id,
                ),
            )
        conn.commit()
        return {"status": "ok"}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.put("/vehicles/{veiculo_id}")
def update_vehicle(veiculo_id: int, payload: UpdateVehicleRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE veiculos
                   SET modelo = %s,
                       ano_modelo = %s,
                       nome_motorista = %s,
                       contato_motorista = %s,
                       data_atualizacao_contato = NOW()
                 WHERE id = %s
                """,
                (
                    payload.modelo,
                    payload.ano_modelo,
                    payload.nome_motorista,
                    formatar_telefone(payload.contato_motorista or ""),
                    veiculo_id,
                ),
            )
        conn.commit()
        return {"status": "ok"}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.put("/vehicles/{veiculo_id}/company")
def update_vehicle_company(veiculo_id: int, payload: LinkCompanyRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE veiculos SET empresa = %s, cliente_id = %s WHERE id = %s",
                (payload.empresa, payload.cliente_id, veiculo_id),
            )
        conn.commit()
        return {"status": "ok"}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.get("/allocation/pending-vehicles")
def get_pending_vehicles(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH status_por_veiculo AS (
                    SELECT
                        veiculo_id,
                        COUNT(*) FILTER (WHERE status = 'pendente') AS pendentes,
                        COUNT(*) FILTER (WHERE status = 'em_andamento') AS em_andamento
                    FROM (
                        SELECT veiculo_id, status FROM servicos_solicitados_borracharia WHERE status IN ('pendente', 'em_andamento')
                        UNION ALL
                        SELECT veiculo_id, status FROM servicos_solicitados_alinhamento WHERE status IN ('pendente', 'em_andamento')
                        UNION ALL
                        SELECT veiculo_id, status FROM servicos_solicitados_manutencao WHERE status IN ('pendente', 'em_andamento')
                    ) AS todos_servicos
                    GROUP BY veiculo_id
                )
                SELECT v.id, v.placa, v.empresa
                FROM veiculos v
                JOIN status_por_veiculo sv ON v.id = sv.veiculo_id
                WHERE sv.pendentes > 0 AND sv.em_andamento = 0
                ORDER BY v.placa;
                """
            )
            rows = cursor.fetchall()
        return [{"id": r[0], "placa": r[1], "empresa": r[2]} for r in rows]
    finally:
        release_connection(conn)


@app.get("/allocation/areas/{veiculo_id}")
def get_pending_areas(veiculo_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 'borracharia' AS area FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente'
                UNION
                SELECT 'alinhamento' AS area FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente'
                UNION
                SELECT 'manutencao' AS area FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente';
                """,
                (veiculo_id, veiculo_id, veiculo_id),
            )
            areas = [r[0] for r in cursor.fetchall()]
            cursor.execute(
                """
                (SELECT quilometragem FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                UNION
                (SELECT quilometragem FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                UNION
                (SELECT quilometragem FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                LIMIT 1;
                """,
                (veiculo_id, veiculo_id, veiculo_id),
            )
            km_row = cursor.fetchone()
        return {"areas": areas, "quilometragem": km_row[0] if km_row else 0}
    finally:
        release_connection(conn)


@app.get("/allocation/funcionarios")
def get_funcionarios(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome FROM funcionarios WHERE id > 0 ORDER BY nome")
            rows = cursor.fetchall()
        return [{"id": r[0], "nome": r[1]} for r in rows]
    finally:
        release_connection(conn)


@app.get("/allocation/boxes")
def get_boxes(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM boxes WHERE ocupado = FALSE AND id > 0 ORDER BY id")
            rows = cursor.fetchall()
        return [{"id": r[0]} for r in rows]
    finally:
        release_connection(conn)


@app.post("/allocation/assign")
def assign_service(payload: AllocationRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT nome_motorista, contato_motorista FROM veiculos WHERE id = %s",
                (payload.veiculo_id,),
            )
            motorista_info = cursor.fetchone()
            nome_motorista_atual = motorista_info[0] if motorista_info else None
            contato_motorista_atual = motorista_info[1] if motorista_info else None

            cursor.execute(
                """
                (SELECT quilometragem FROM servicos_solicitados_borracharia WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                UNION
                (SELECT quilometragem FROM servicos_solicitados_alinhamento WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                UNION
                (SELECT quilometragem FROM servicos_solicitados_manutencao WHERE veiculo_id = %s AND status = 'pendente' AND quilometragem IS NOT NULL LIMIT 1)
                LIMIT 1;
                """,
                (payload.veiculo_id, payload.veiculo_id, payload.veiculo_id),
            )
            km_row = cursor.fetchone()
            quilometragem = km_row[0] if km_row else 0

            cursor.execute(
                """
                INSERT INTO execucao_servico
                    (veiculo_id, box_id, funcionario_id, quilometragem, status, inicio_execucao, usuario_alocacao_id, nome_motorista, contato_motorista)
                VALUES (%s, %s, %s, %s, 'em_andamento', %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    payload.veiculo_id,
                    payload.box_id,
                    payload.funcionario_id,
                    quilometragem,
                    datetime.now(MS_TZ),
                    user.get("user_id"),
                    nome_motorista_atual,
                    contato_motorista_atual,
                ),
            )
            execucao_id = cursor.fetchone()[0]
            tabela_servico = f"servicos_solicitados_{payload.area.lower()}"
            cursor.execute(
                f"""
                UPDATE {tabela_servico}
                   SET box_id = %s, funcionario_id = %s, status = 'em_andamento', data_atualizacao = %s, execucao_id = %s
                 WHERE veiculo_id = %s AND status = 'pendente';
                """,
                (payload.box_id, payload.funcionario_id, datetime.now(MS_TZ), execucao_id, payload.veiculo_id),
            )
            cursor.execute("UPDATE boxes SET ocupado = TRUE WHERE id = %s", (payload.box_id,))
        conn.commit()
        return {"status": "ok"}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.get("/queues")
def get_queues(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH servicos_em_andamento AS (
                    SELECT
                        execucao_id,
                        STRING_AGG(tipo || ' (Qtd: ' || quantidade || ')', ', ') as lista_servicos
                    FROM (
                        SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_borracharia WHERE status = 'em_andamento'
                        UNION ALL
                        SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_alinhamento WHERE status = 'em_andamento'
                        UNION ALL
                        SELECT execucao_id, tipo, quantidade FROM servicos_solicitados_manutencao WHERE status = 'em_andamento'
                    ) s
                    GROUP BY execucao_id
                )
                SELECT
                    b.id as box_id,
                    v.placa,
                    v.empresa,
                    f.nome as funcionario,
                    sa.lista_servicos
                FROM boxes b
                JOIN execucao_servico es ON b.id = es.box_id
                JOIN veiculos v ON es.veiculo_id = v.id
                LEFT JOIN funcionarios f ON es.funcionario_id = f.id
                LEFT JOIN servicos_em_andamento sa ON es.id = sa.execucao_id
                WHERE es.status = 'em_andamento' AND b.id > 0
                ORDER BY b.id;
                """
            )
            boxes = cursor.fetchall()
            cursor.execute(
                """
                SELECT
                    v.placa,
                    v.empresa,
                    STRING_AGG(s.tipo || ' (Qtd: ' || s.quantidade || ')', ', ') as servicos
                FROM (
                    SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_borracharia WHERE status = 'pendente'
                    UNION ALL
                    SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_alinhamento WHERE status = 'pendente'
                    UNION ALL
                    SELECT veiculo_id, tipo, quantidade, data_solicitacao FROM servicos_solicitados_manutencao WHERE status = 'pendente'
                ) s
                JOIN veiculos v ON s.veiculo_id = v.id
                GROUP BY v.placa, v.empresa, s.veiculo_id
                ORDER BY MIN(s.data_solicitacao) ASC;
                """
            )
            fila = cursor.fetchall()
        return {
            "boxes": [
                {
                    "box_id": r[0],
                    "placa": r[1],
                    "empresa": r[2],
                    "funcionario": r[3],
                    "servicos": r[4],
                }
                for r in boxes
            ],
            "fila": [
                {"placa": r[0], "empresa": r[1], "servicos": r[2]} for r in fila
            ],
        }
    finally:
        release_connection(conn)


@app.get("/boxes/active")
def get_boxes_active(user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    b.id,
                    b.area,
                    es.id as execucao_id,
                    v.placa,
                    v.empresa,
                    v.nome_motorista,
                    v.contato_motorista,
                    v.modelo,
                    f.nome as funcionario_nome
                FROM boxes b
                LEFT JOIN execucao_servico es ON b.id = es.box_id AND es.status = 'em_andamento'
                LEFT JOIN veiculos v ON es.veiculo_id = v.id
                LEFT JOIN funcionarios f ON es.funcionario_id = f.id
                WHERE b.id > 0
                ORDER BY b.id;
                """
            )
            rows = cursor.fetchall()
        return [
            {
                "box_id": r[0],
                "box_area": r[1],
                "execucao_id": r[2],
                "placa": r[3],
                "empresa": r[4],
                "nome_motorista": r[5],
                "contato_motorista": r[6],
                "modelo": r[7],
                "funcionario": r[8],
            }
            for r in rows
        ]
    finally:
        release_connection(conn)


@app.get("/boxes/{box_id}/details")
def get_box_details(box_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT es.id as execucao_id, es.veiculo_id, es.quilometragem,
                       v.placa, v.empresa, v.modelo, v.nome_motorista, v.contato_motorista,
                       f.nome as funcionario
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                LEFT JOIN funcionarios f ON es.funcionario_id = f.id
                WHERE es.box_id = %s AND es.status = 'em_andamento'
                """,
                (box_id,),
            )
            execucao = cursor.fetchone()
            if not execucao:
                return {"execucao": None, "servicos": []}

            cursor.execute(
                """
                                (SELECT 'borracharia' AS area, id, tipo, quantidade, observacao, observacao_execucao
                   FROM servicos_solicitados_borracharia
                  WHERE box_id = %s AND status = 'em_andamento')
                UNION ALL
                                (SELECT 'alinhamento' AS area, id, tipo, quantidade, observacao, observacao_execucao
                   FROM servicos_solicitados_alinhamento
                  WHERE box_id = %s AND status = 'em_andamento')
                UNION ALL
                                (SELECT 'manutencao' AS area, id, tipo, quantidade, observacao, observacao_execucao
                   FROM servicos_solicitados_manutencao
                  WHERE box_id = %s AND status = 'em_andamento')
                """,
                (box_id, box_id, box_id),
            )
            servicos = cursor.fetchall()

        return {
            "execucao": {
                "execucao_id": execucao[0],
                "veiculo_id": execucao[1],
                "quilometragem": execucao[2],
                "placa": execucao[3],
                "empresa": execucao[4],
                "modelo": execucao[5],
                "nome_motorista": execucao[6],
                "contato_motorista": execucao[7],
                "funcionario": execucao[8],
            },
            "servicos": [
                {
                    "area": s[0],
                    "id": s[1],
                    "tipo": s[2],
                    "quantidade": s[3],
                    "observacao_cadastro": s[4],
                    "observacao_execucao": s[5],
                }
                for s in servicos
            ],
        }
    finally:
        release_connection(conn)


@app.post("/boxes/{box_id}/services")
def add_box_service(box_id: int, payload: AddBoxServiceRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, veiculo_id, quilometragem FROM execucao_servico WHERE box_id = %s AND status = 'em_andamento'",
                (box_id,),
            )
            execucao = cursor.fetchone()
            if not execucao:
                raise HTTPException(status_code=404, detail="Execucao nao encontrada")
            execucao_id, veiculo_id, quilometragem = execucao

            cursor.execute(
                """
                SELECT 'borracharia' FROM servicos_borracharia WHERE nome = %s
                UNION ALL
                SELECT 'alinhamento' FROM servicos_alinhamento WHERE nome = %s
                UNION ALL
                SELECT 'manutencao' FROM servicos_manutencao WHERE nome = %s
                LIMIT 1
                """,
                (payload.tipo, payload.tipo, payload.tipo),
            )
            area_row = cursor.fetchone()
            if not area_row:
                raise HTTPException(status_code=400, detail="Tipo de servico invalido")
            area = area_row[0]
            tabela = f"servicos_solicitados_{area}"

            cursor.execute(
                f"""
                INSERT INTO {tabela}
                    (veiculo_id, tipo, quantidade, status, box_id, execucao_id, data_solicitacao, data_atualizacao, quilometragem)
                VALUES (%s, %s, %s, 'em_andamento', %s, %s, %s, %s, %s)
                """,
                (
                    veiculo_id,
                    payload.tipo,
                    payload.quantidade,
                    box_id,
                    execucao_id,
                    datetime.now(MS_TZ),
                    datetime.now(MS_TZ),
                    quilometragem,
                ),
            )
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.post("/boxes/{box_id}/unassign")
def unassign_box(box_id: int, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, veiculo_id FROM execucao_servico WHERE box_id = %s AND status = 'em_andamento'",
                (box_id,),
            )
            execucao = cursor.fetchone()
            if not execucao:
                raise HTTPException(status_code=404, detail="Execucao nao encontrada")
            execucao_id = execucao[0]
            veiculo_id = execucao[1]

            for tabela in [
                "servicos_solicitados_borracharia",
                "servicos_solicitados_alinhamento",
                "servicos_solicitados_manutencao",
            ]:
                cursor.execute(
                    f"""
                    UPDATE {tabela}
                       SET status = 'pendente',
                           box_id = NULL,
                           funcionario_id = NULL,
                           execucao_id = NULL,
                           data_atualizacao = %s
                     WHERE execucao_id = %s
                    """,
                    (datetime.now(MS_TZ), execucao_id),
                )

            cursor.execute("DELETE FROM execucao_servico WHERE id = %s", (execucao_id,))
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))

        conn.commit()
        _recalcular_media_veiculo(conn, veiculo_id)
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.post("/boxes/{box_id}/finalize")
def finalize_box(box_id: int, payload: BoxFinalizeRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM execucao_servico WHERE box_id = %s AND status = 'em_andamento'",
                (box_id,),
            )
            execucao = cursor.fetchone()
            if not execucao:
                raise HTTPException(status_code=404, detail="Execucao nao encontrada")
            execucao_id = execucao[0]

            for srv in payload.servicos:
                tabela = f"servicos_solicitados_{srv.area.lower()}"
                cursor.execute(
                    f"""
                    UPDATE {tabela}
                       SET quantidade = %s,
                           observacao_execucao = %s,
                           status = 'finalizado',
                           data_atualizacao = %s
                     WHERE id = %s
                    """,
                    (srv.quantidade, payload.obs_final or "", datetime.now(MS_TZ), srv.id),
                )

            cursor.execute(
                """
                UPDATE execucao_servico
                   SET status = 'finalizado', fim_execucao = %s, usuario_finalizacao_id = %s
                 WHERE id = %s
                """,
                (datetime.now(MS_TZ), user.get("user_id"), execucao_id),
            )
            cursor.execute("UPDATE boxes SET ocupado = FALSE WHERE id = %s", (box_id,))

        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.get("/services/completed")
def get_completed(start_date: str | None = None, end_date: str | None = None, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d") if start_date else datetime.now() - timedelta(days=30)
        end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        end_inclusive = end + timedelta(days=1)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    es.id as execucao_id,
                    es.veiculo_id, es.quilometragem, es.fim_execucao,
                    v.placa, v.empresa,
                    serv.service_id, serv.area, serv.tipo, serv.quantidade, f.nome as funcionario_nome,
                    serv.observacao_execucao, serv.tipo_atendimento
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                LEFT JOIN (
                    SELECT id as service_id, execucao_id, 'Borracharia' as area, tipo, quantidade, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_borracharia
                    UNION ALL
                    SELECT id as service_id, execucao_id, 'Alinhamento' as area, tipo, quantidade, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_alinhamento
                    UNION ALL
                    SELECT id as service_id, execucao_id, 'Manutencao' as area, tipo, quantidade, funcionario_id, observacao_execucao, tipo_atendimento FROM servicos_solicitados_manutencao
                ) serv ON es.id = serv.execucao_id
                LEFT JOIN funcionarios f ON serv.funcionario_id = f.id
                WHERE es.status = 'finalizado' AND es.fim_execucao >= %s AND es.fim_execucao < %s
                ORDER BY es.fim_execucao DESC, serv.area;
                """,
                (start, end_inclusive),
            )
            rows = cursor.fetchall()
        return [
            {
                "execucao_id": r[0],
                "veiculo_id": r[1],
                "quilometragem": r[2],
                "fim_execucao": r[3].isoformat() if r[3] else None,
                "placa": r[4],
                "empresa": r[5],
                "service_id": r[6],
                "area": r[7],
                "tipo": r[8],
                "quantidade": r[9],
                "funcionario": r[10],
                "observacao": r[11],
                "tipo_atendimento": r[12],
            }
            for r in rows
        ]
    finally:
        release_connection(conn)


@app.put("/services/{service_id}/tipo-atendimento")
def update_service_type(service_id: int, payload: UpdateServiceTypeRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    table_map = {
        "Borracharia": "servicos_solicitados_borracharia",
        "Alinhamento": "servicos_solicitados_alinhamento",
        "Manutencao": "servicos_solicitados_manutencao",
    }
    tabela = table_map.get(payload.area)
    if not tabela:
        raise HTTPException(status_code=400, detail="Area invalida")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE {tabela} SET tipo_atendimento = %s WHERE id = %s",
                (payload.tipo_atendimento, service_id),
            )
        conn.commit()
        return {"status": "ok"}
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.post("/services/revert")
def revert_visit(payload: RevertVisitRequest, user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM execucao_servico
                WHERE veiculo_id = %s AND quilometragem = %s AND status = 'finalizado'
                """,
                (payload.veiculo_id, payload.quilometragem),
            )
            execucao_ids = [row[0] for row in cursor.fetchall()]
            if not execucao_ids:
                raise HTTPException(status_code=404, detail="Execucao nao encontrada")

            for tabela in [
                "servicos_solicitados_borracharia",
                "servicos_solicitados_alinhamento",
                "servicos_solicitados_manutencao",
            ]:
                cursor.execute(
                    f"""
                    UPDATE {tabela}
                       SET status = 'pendente', box_id = NULL, funcionario_id = NULL, execucao_id = NULL
                     WHERE execucao_id = ANY(%s)
                    """,
                    (execucao_ids,),
                )
            cursor.execute(
                "UPDATE execucao_servico SET status = 'cancelado' WHERE id = ANY(%s)",
                (execucao_ids,),
            )
        conn.commit()
        return {"status": "ok"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        release_connection(conn)


@app.get("/terms/{execucao_id}", response_class=HTMLResponse)
def get_term(execucao_id: int,
             avarias: List[str] = Query(default=[]),
             carreta_carregada: bool = False,
             cambagem: bool = False,
             user=Depends(get_current_user)):
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Falha na conexao com o banco")
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT v.placa, v.modelo, v.empresa, es.nome_motorista
                FROM execucao_servico es
                JOIN veiculos v ON es.veiculo_id = v.id
                WHERE es.id = %s
                """,
                (execucao_id,),
            )
            row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Servico nao encontrado")

        placa, modelo, empresa, nome_motorista = row
        marca = (modelo or "").split(" ")[0] if modelo else ""
        modelo_str = " ".join((modelo or "").split(" ")[1:]) if modelo else ""
        agora = datetime.now(MS_TZ).strftime("%d/%m/%Y")

        texto_base = (
            f"Eu, {nome_motorista or ''}, responsavel pelo veiculo {marca} {modelo_str} de placa {placa}, "
            f"pertencente a empresa {empresa}, declaro que autorizo a execucao do servico de alinhamento, "
            "ciente de que o servico sera realizado mesmo diante das condicoes abaixo descritas:"
        )

        partes = [texto_base]
        if avarias:
            partes.append("- O veiculo apresenta as seguintes avarias:")
            partes.extend([f"  {item}" for item in avarias])
            partes.append(
                "Estou ciente de que folgas na suspensao e direcao podem comprometer o alinhamento."
            )
        if carreta_carregada:
            partes.append(
                "O caminhao encontra-se carregado e isso pode alterar a geometria durante o alinhamento."
            )
        if cambagem:
            partes.append(
                "Foi constatado que a cambagem esta fora dos parametros recomendados."
            )

        partes.append(
            "Assumo responsabilidade pelas consequencias decorrentes da realizacao do alinhamento nessas condicoes."
        )

        html = "<br><br>".join(partes)
        return f"""
        <html>
        <head><meta charset='utf-8'></head>
        <body style='font-family: Arial, sans-serif; padding: 24px;'>
            <h3 style='text-align:center;'>TERMO DE RESPONSABILIDADE</h3>
            <p style='text-align: justify; line-height: 1.5;'>{html}</p>
            <p style='text-align:center; margin-top: 32px;'>Dourados - MS, {agora}</p>
            <p style='text-align:center; margin-top: 48px;'>______________________________</p>
            <p style='text-align:center;'><b>{nome_motorista or ''}</b></p>
        </body>
        </html>
        """
    finally:
        release_connection(conn)
