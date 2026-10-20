"""Fábrica da aplicação Flask (chamada pelo Gunicorn: "app:create_app()")."""
import logging

import psycopg
from flask import Flask, jsonify, request
from psycopg_pool import PoolTimeout
from werkzeug.exceptions import HTTPException

from .rotas import api
from .validacao import ErroValidacao

log = logging.getLogger("api")


def _erro(codigo: str, mensagem: str, status: int, **extra):
    corpo = {"sucesso": False, "erro": {"codigo": codigo, "mensagem": mensagem, "status": status, **extra}}
    return jsonify(corpo), status


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False   # acentos legíveis no JSON
    app.json.sort_keys = False
    app.register_blueprint(api)

    @app.get("/")
    def raiz():
        return jsonify({
            "api": "Servidores do Poder Executivo Federal",
            "endpoints": [
                "GET /api/servidores?nome=&similar=&limit=&cargo=&uf=&orgao=&situacao=&pagina=&por_pagina=",
                "GET /api/servidores/<id>",
                "GET /api/cargos?q=", "GET /api/orgaos?q=", "GET /api/ufs", "GET /api/saude",
            ],
        })

    @app.after_request
    def cabecalhos(resp):
        # CORS liberado para leitura (app desktop / testes no navegador)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.errorhandler(ErroValidacao)
    def erro_validacao(e: ErroValidacao):
        extra = {"campo": e.campo} if e.campo else {}
        resp, status = _erro(e.codigo, e.mensagem, e.status, **extra)
        if getattr(e, "retry_after", None):
            resp.headers["Retry-After"] = str(e.retry_after)
        return resp, status

    @app.errorhandler(psycopg.errors.QueryCanceled)
    def erro_timeout(_e):
        return _erro("TEMPO_EXCEDIDO",
                     "A busca excedeu o tempo limite. Use filtros mais específicos.", 504)

    @app.errorhandler(PoolTimeout)
    def erro_pool(_e):
        return _erro("SERVIDOR_OCUPADO", "Todas as conexões com o banco estão ocupadas. Tente novamente.", 503)

    @app.errorhandler(psycopg.OperationalError)
    def erro_banco(e):
        log.error("Banco indisponível: %s", e)
        return _erro("BANCO_INDISPONIVEL", "Banco de dados indisponível no momento.", 503)

    @app.errorhandler(HTTPException)
    def erro_http(e: HTTPException):
        mensagens = {
            404: ("ROTA_INEXISTENTE", f"A rota '{request.path}' não existe."),
            405: ("METODO_NAO_PERMITIDO", f"Método {request.method} não permitido. Use GET."),
            414: ("URL_MUITO_LONGA", "URL muito longa."),
        }
        codigo, msg = mensagens.get(e.code, ("ERRO_HTTP", e.description or "Erro HTTP."))
        return _erro(codigo, msg, e.code or 500)

    @app.errorhandler(Exception)
    def erro_generico(e: Exception):
        log.exception("Erro inesperado: %s", e)
        return _erro("ERRO_INTERNO", "Erro interno no servidor.", 500)

    return app
