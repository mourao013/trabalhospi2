"""Configuração do Gunicorn (servidor WSGI).

Modelo: workers (processos) x threads (gthread) -> várias requisições em paralelo.
Os limites abaixo protegem o servidor contra sobrecarga (ver relatório).
"""
import multiprocessing
import os

bind = "0.0.0.0:5000"

# gthread = cada worker atende várias requisições em threads (multi-threading)
worker_class = "gthread"
workers = int(os.getenv("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 4)))
threads = int(os.getenv("GUNICORN_THREADS", 8))

# Fila de conexões aguardando aceite no socket. Acima disso o SO recusa.
backlog = int(os.getenv("GUNICORN_BACKLOG", 256))

# Worker travado por mais de 30 s é morto e recriado pelo master.
timeout = int(os.getenv("GUNICORN_TIMEOUT", 30))
graceful_timeout = 10
keepalive = 5

# Recicla workers periodicamente (evita vazamento de memória a longo prazo).
max_requests = 2000
max_requests_jitter = 200

# Rejeita requisições com URL gigante (strings inválidas / ataques).
limit_request_line = 2048
limit_request_fields = 50

# NÃO usar preload_app: o pool de conexões deve ser criado depois do fork,
# em cada worker (ver REGISTRO_DE_ERROS.md, ERR-007).
preload_app = False

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
