"""Teste de sobrecarga paralela na API (/api/servidores).

Requisito 7 (Avaliação):
"Durante a avaliação serão feitos testes exaustivos de busca na API do backend.
Realizem testes de sobrecarga paralela para garantir que o sistema não entre em
colapso e trave. Crie um mecanismo de segurança para garantir e evitar que isso
não ocorra."

Uso:
    python scripts/teste_sobrecarga.py [URL_BASE] [CONCORRENCIA] [TOTAL_REQ]

Exemplo:
    python scripts/teste_sobrecarga.py http://localhost:5000 40 200
"""
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CONSULTAS = [
    "/api/servidores?uf=DF&por_pagina=20",
    "/api/servidores?cargo=PROFESSOR&uf=MG",
    "/api/servidores?similar=%MARIA%SILVA%&limit=50",
    "/api/servidores?orgao=MINISTERIO%20DA%20SAUDE&situacao=ATIVO",
    "/api/servidores?nome=ANA%20SILVA%20SANTOS",
    "/api/servidores?uf=SP&situacao=APOSENTADO&pagina=2",
    "/api/cargos?q=ANALISTA",
    "/api/orgaos?q=UNIVERSIDADE",
]


def requisitar(url_base: str, idx: int) -> tuple[int, float]:
    caminho = CONSULTAS[idx % len(CONSULTAS)]
    url = url_base.rstrip("/") + caminho
    inicio = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
            return resp.status, (time.perf_counter() - inicio) * 1000
    except urllib.error.HTTPError as e:
        return e.code, (time.perf_counter() - inicio) * 1000
    except Exception:
        return 0, (time.perf_counter() - inicio) * 1000


def executar(url_base: str, concorrencia: int = 32, total: int = 160) -> dict:
    print(f"[sobrecarga] Alvo: {url_base} | Concorrência: {concorrencia} threads | Total: {total} reqs")
    inicio = time.perf_counter()
    codigos: dict[int, int] = {}
    latencias: list[float] = []

    with ThreadPoolExecutor(max_workers=concorrencia) as pool:
        futuros = [pool.submit(requisitar, url_base, i) for i in range(total)]
        for fut in as_completed(futuros):
            codigo, ms = fut.result()
            codigos[codigo] = codigos.get(codigo, 0) + 1
            latencias.append(ms)

    duracao = time.perf_counter() - inicio
    latencias.sort()
    p50 = statistics.median(latencias) if latencias else 0
    p95 = latencias[int(len(latencias) * 0.95) - 1] if latencias else 0
    p99 = latencias[int(len(latencias) * 0.99) - 1] if latencias else 0

    resumo = {
        "duracao_s": round(duracao, 2),
        "req_por_s": round(total / duracao, 1) if duracao > 0 else 0,
        "codigos_http": codigos,
        "latencia_p50_ms": round(p50, 1),
        "latencia_p95_ms": round(p95, 1),
        "latencia_p99_ms": round(p99, 1),
    }
    print(f"[sobrecarga] Concluído em {resumo['duracao_s']}s ({resumo['req_por_s']} req/s)")
    print(f"[sobrecarga] Códigos HTTP : {codigos}")
    print(f"[sobrecarga] Latência (ms): p50={resumo['latencia_p50_ms']} | p95={resumo['latencia_p95_ms']} | p99={resumo['latencia_p99_ms']}")
    erros_fatais = codigos.get(0, 0) + codigos.get(500, 0)
    if erros_fatais == 0:
        print("[sobrecarga] OK: Servidor manteve estabilidade (respostas 200/404 ou proteção 429/503 controlada).")
    else:
        print(f"[sobrecarga] ATENCAO: {erros_fatais} falhas de conexão/erro 500.")
    return resumo


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
    conc = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    tot = int(sys.argv[3]) if len(sys.argv) > 3 else 160
    executar(alvo, conc, tot)
