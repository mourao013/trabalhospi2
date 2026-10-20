"""Consultas SQL (sempre parametrizadas - nunca concatenar entrada do usuário)."""
import math
from datetime import date

from . import config
from .db import obter_pool
from .validacao import ErroValidacao

COLUNAS = """
    s.id, s.nome, s.cpf_mascarado, s.matricula, s.situacao,
    c.nome AS cargo, o.nome AS orgao, s.uf, u.nome AS uf_nome,
    s.tipo_aposentadoria, s.data_ingresso, s.data_aposentadoria
"""
JOINS = """
    LEFT JOIN cargo c ON c.id = s.cargo_id
    LEFT JOIN orgao o ON o.id = s.orgao_id
    LEFT JOIN uf    u ON u.sigla = s.uf
"""
MAX_IDS_DOMINIO = 500  # máx. de cargos/órgãos casados numa busca parcial


def _serializar(linha: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in linha.items()}


def _aplicar_timeout(cur) -> None:
    # SET LOCAL não aceita parâmetro ($1) no psycopg 3 -> usar set_config (ERR-009)
    cur.execute("SELECT set_config('statement_timeout', %s, true)", (str(config.BUSCA_TIMEOUT_MS),))


def _ids_dominio(cur, tabela: str, termo: str, campo: str, codigo: str) -> list[int]:
    """Resolve cargo/órgão: primeiro exato, depois parcial (LIKE %termo% via índice trigram)."""
    # 'tabela' vem de constante interna ('cargo'/'orgao'), nunca do usuário.
    cur.execute(f"SELECT id FROM {tabela} WHERE nome_busca = %s", (termo,))
    ids = [r["id"] for r in cur.fetchall()]
    if not ids:
        cur.execute(
            f"SELECT id FROM {tabela} WHERE nome_busca LIKE %s LIMIT %s",
            (f"%{termo}%", MAX_IDS_DOMINIO),
        )
        ids = [r["id"] for r in cur.fetchall()]
    if not ids:
        rotulo = "Cargo" if tabela == "cargo" else "Órgão/instituição"
        raise ErroValidacao(codigo, f"{rotulo} '{termo}' não encontrado na base.", status=404, campo=campo)
    return ids


def buscar_servidores(f: dict) -> dict:
    with obter_pool().connection() as conn, conn.cursor() as cur:
        _aplicar_timeout(cur)

        where, params = [], []
        if "nome" in f:
            where.append("s.nome_busca = %s")
            params.append(f["nome"])
        if "similar" in f:
            where.append("s.nome_busca LIKE %s")
            params.append(f["similar"])
        if "uf" in f:
            where.append("s.uf = %s")
            params.append(f["uf"])
        if "situacao" in f:
            where.append("s.situacao = %s")
            params.append(f["situacao"])
        if "cargo" in f:
            where.append("s.cargo_id = ANY(%s)")
            params.append(_ids_dominio(cur, "cargo", f["cargo"], "cargo", "CARGO_INVALIDO"))
        if "orgao" in f:
            where.append("s.orgao_id = ANY(%s)")
            params.append(_ids_dominio(cur, "orgao", f["orgao"], "orgao", "ORGAO_INVALIDO"))
        clausula = " AND ".join(where)

        por_pagina, pagina = f["por_pagina"], f["pagina"]
        offset = (pagina - 1) * por_pagina

        if "similar" in f:
            # Busca por similaridade: no máximo 'limit' nomes, ordenados por semelhança.
            teto = f["limit"]
            cur.execute(
                f"SELECT count(*) AS n FROM (SELECT 1 FROM servidor s WHERE {clausula} LIMIT %s) t",
                (*params, teto),
            )
            total = cur.fetchone()["n"]
            total_exato = True
            consulta = f"""
                WITH candidatos AS (
                    SELECT s.id, similarity(s.nome_busca, %s) AS sim
                      FROM servidor s
                     WHERE {clausula}
                     ORDER BY sim DESC, s.nome_busca, s.id
                     LIMIT %s
                )
                SELECT {COLUNAS}, round(k.sim::numeric, 3)::float AS similaridade
                  FROM candidatos k
                  JOIN servidor s ON s.id = k.id
                  {JOINS}
                 ORDER BY k.sim DESC, s.nome_busca, s.id
                 LIMIT %s OFFSET %s
            """
            valores = (f["similar_texto"], *params, teto, por_pagina, offset)
        else:
            # Conta até MAX_RESULTADOS+1 (COUNT(*) completo em milhões de linhas é caro)
            teto = config.MAX_RESULTADOS
            cur.execute(
                f"SELECT count(*) AS n FROM (SELECT 1 FROM servidor s WHERE {clausula} LIMIT %s) t",
                (*params, teto + 1),
            )
            n = cur.fetchone()["n"]
            total_exato = n <= teto
            total = min(n, teto)
            consulta = f"""
                SELECT {COLUNAS}
                  FROM servidor s
                  {JOINS}
                 WHERE {clausula}
                 ORDER BY s.nome_busca, s.id
                 LIMIT %s OFFSET %s
            """
            valores = (*params, por_pagina, offset)

        if total == 0:
            raise ErroValidacao("NAO_ENCONTRADO", "Nenhum servidor encontrado para os filtros informados.",
                                status=404)

        total_paginas = max(1, math.ceil(total / por_pagina))
        if pagina > total_paginas:
            extra = "" if total_exato else " Refine os filtros para ver mais resultados."
            raise ErroValidacao(
                "PAGINA_INEXISTENTE",
                f"Página {pagina} não existe. Total de páginas: {total_paginas}.{extra}",
                status=404, campo="pagina",
            )

        cur.execute(consulta, valores)
        resultados = [_serializar(r) for r in cur.fetchall()]
        conn.rollback()  # somente leitura: encerra a transação

    return {
        "total": total,
        "total_exato": total_exato,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total_paginas": total_paginas,
        "resultados": resultados,
    }


def buscar_por_id(servidor_id: int) -> dict:
    with obter_pool().connection() as conn, conn.cursor() as cur:
        _aplicar_timeout(cur)
        cur.execute(f"SELECT {COLUNAS} FROM servidor s {JOINS} WHERE s.id = %s", (servidor_id,))
        linha = cur.fetchone()
        conn.rollback()
    if not linha:
        raise ErroValidacao("NAO_ENCONTRADO", f"Servidor {servidor_id} não encontrado.", status=404)
    return _serializar(linha)


def listar_dominio(tabela: str, termo: str, limite: int) -> list[str]:
    """Lista cargos/órgãos (autocompletar do front-end)."""
    assert tabela in ("cargo", "orgao")
    with obter_pool().connection() as conn, conn.cursor() as cur:
        _aplicar_timeout(cur)
        if termo:
            cur.execute(
                f"SELECT nome FROM {tabela} WHERE nome_busca LIKE %s "
                f"ORDER BY similarity(nome_busca, %s) DESC, nome LIMIT %s",
                (f"%{termo}%", termo, limite),
            )
        else:
            cur.execute(f"SELECT nome FROM {tabela} ORDER BY nome LIMIT %s", (limite,))
        nomes = [r["nome"] for r in cur.fetchall()]
        conn.rollback()
    return nomes


def listar_ufs() -> list[dict]:
    with obter_pool().connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT sigla, nome FROM uf ORDER BY sigla")
        ufs = cur.fetchall()
        conn.rollback()
    return ufs


def estatisticas() -> dict:
    with obter_pool().connection() as conn, conn.cursor() as cur:
        _aplicar_timeout(cur)
        # reltuples = estimativa rápida (count(*) exato seria lento)
        cur.execute("SELECT reltuples::bigint AS n FROM pg_class WHERE relname = 'servidor'")
        estimado = cur.fetchone()["n"]
        cur.execute("SELECT (SELECT count(*) FROM cargo) AS cargos, (SELECT count(*) FROM orgao) AS orgaos")
        dom = cur.fetchone()
        # consulta na tabela de controle (pequena) e não em servidor.fonte (sem índice)
        cur.execute("SELECT EXISTS(SELECT 1 FROM controle_importacao "
                    "WHERE arquivo = 'AMOSTRA_FICTICIA') AS amostra")
        amostra = cur.fetchone()["amostra"]
        conn.rollback()
    return {"servidores_estimado": max(estimado, 0), **dom, "dados_ficticios": amostra}
