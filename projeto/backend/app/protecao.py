"""Mecanismos de segurança contra sobrecarga.

1) Rate limit por IP (janela deslizante)       -> HTTP 429
2) Limite de buscas simultâneas por worker     -> HTTP 503
   (as demais esperam até ESPERA_VAGA_S segundos por uma vaga)

Junto com o limit_req do Nginx, o pool de conexões e o statement_timeout do
PostgreSQL, isso impede que o sistema trave sob testes de sobrecarga paralela.
"""
import threading
import time
from collections import deque
from functools import wraps

from flask import request

from . import config
from .validacao import ErroValidacao


class LimitadorTaxa:
    def __init__(self, maximo: int, janela_s: int):
        self.maximo = maximo
        self.janela = janela_s
        self._acessos: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._ultima_limpeza = time.monotonic()

    def permitir(self, chave: str) -> tuple[bool, int]:
        agora = time.monotonic()
        with self._lock:
            fila = self._acessos.setdefault(chave, deque())
            while fila and agora - fila[0] > self.janela:
                fila.popleft()
            if len(fila) >= self.maximo:
                espera = int(self.janela - (agora - fila[0])) + 1
                return False, espera
            fila.append(agora)
            self._limpar(agora)
            return True, 0

    def _limpar(self, agora: float) -> None:
        # remove IPs inativos para o dicionário não crescer sem limite
        if agora - self._ultima_limpeza < self.janela:
            return
        self._ultima_limpeza = agora
        for chave in [k for k, f in self._acessos.items() if not f or agora - f[-1] > self.janela]:
            del self._acessos[chave]


limitador = LimitadorTaxa(config.RATE_LIMIT_REQUISICOES, config.RATE_LIMIT_JANELA_S)
vagas_busca = threading.BoundedSemaphore(config.MAX_BUSCAS_SIMULTANEAS)


def ip_cliente() -> str:
    # Atrás do Nginx o IP real vem em X-Real-IP (definido no nginx.conf)
    return request.headers.get("X-Real-IP") or request.remote_addr or "desconhecido"


def protegido(func):
    """Aplica rate limit + limite de concorrência a um endpoint."""

    @wraps(func)
    def envoltorio(*args, **kwargs):
        ok, espera = limitador.permitir(ip_cliente())
        if not ok:
            erro = ErroValidacao(
                "MUITAS_REQUISICOES",
                f"Limite de {config.RATE_LIMIT_REQUISICOES} buscas a cada "
                f"{config.RATE_LIMIT_JANELA_S}s excedido. Tente novamente em {espera}s.",
                status=429,
            )
            erro.retry_after = espera
            raise erro
        if not vagas_busca.acquire(timeout=config.ESPERA_VAGA_S):
            erro = ErroValidacao(
                "SERVIDOR_OCUPADO",
                "Excesso de buscas simultâneas no momento. Tente novamente em instantes.",
                status=503,
            )
            erro.retry_after = 2
            raise erro
        try:
            return func(*args, **kwargs)
        finally:
            vagas_busca.release()

    return envoltorio
