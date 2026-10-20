"""Endpoints da API (todas as respostas em JSON)."""
from flask import Blueprint, jsonify, request

from . import consultas
from .protecao import protegido
from .validacao import ErroValidacao, validar_busca, validar_termo_autocompletar

api = Blueprint("api", __name__, url_prefix="/api")


@api.get("/servidores")
@protegido
def servidores():
    """
    GET /api/servidores?nome=<nome>                 busca exata
    GET /api/servidores?similar=%NO%ME%&limit=100   similaridade (máx. 100)
    GET /api/servidores?cargo=<cargo>
    GET /api/servidores?uf=<uf>
    GET /api/servidores?orgao=<orgao>
    GET /api/servidores?nome=..&cargo=..&uf=..      combinada
    Opcionais: situacao=ATIVO|APOSENTADO, pagina=N, por_pagina=1..100
    """
    filtros = validar_busca(request.args)
    resultado = consultas.buscar_servidores(filtros)

    total = resultado["total"]
    if total == 1:
        mensagem = "1 registro encontrado."
        resultado["registro"] = resultado["resultados"][0]
    else:
        mais = "" if resultado["total_exato"] else " (exibindo os primeiros; refine a busca)"
        mensagem = f"{total} registros encontrados{mais}."
        if "nome" in filtros:
            mensagem += " O nome informado retornou múltiplos registros."

    filtros_publicos = {k: v for k, v in filtros.items() if k != "similar_texto"}
    return jsonify({
        "sucesso": True,
        "mensagem": mensagem,
        "multiplos": total > 1,
        "filtros": filtros_publicos,
        **resultado,
    })


@api.get("/servidores/<int:servidor_id>")
@protegido
def servidor_por_id(servidor_id: int):
    return jsonify({"sucesso": True, "registro": consultas.buscar_por_id(servidor_id)})


def _limite_lista() -> int:
    try:
        limite = int(request.args.get("limit", 20))
    except ValueError:
        raise ErroValidacao("PARAMETRO_INVALIDO", "'limit' deve ser um número inteiro.") from None
    return max(1, min(limite, 50))


def _valida_args_lista():
    extras = set(request.args.keys()) - {"q", "limit"}
    if extras:
        raise ErroValidacao("PARAMETRO_INVALIDO", f"Parâmetro(s) não reconhecido(s): {', '.join(sorted(extras))}.")


@api.get("/cargos")
@protegido
def cargos():
    _valida_args_lista()
    termo = validar_termo_autocompletar(request.args.get("q"))
    return jsonify({"sucesso": True, "resultados": consultas.listar_dominio("cargo", termo, _limite_lista())})


@api.get("/orgaos")
@protegido
def orgaos():
    _valida_args_lista()
    termo = validar_termo_autocompletar(request.args.get("q"))
    return jsonify({"sucesso": True, "resultados": consultas.listar_dominio("orgao", termo, _limite_lista())})


@api.get("/ufs")
@protegido
def ufs():
    return jsonify({"sucesso": True, "resultados": consultas.listar_ufs()})


@api.get("/saude")
def saude():
    """Healthcheck usado pelo Docker e pelo front-end."""
    try:
        return jsonify({"sucesso": True, "status": "ok", **consultas.estatisticas()})
    except Exception as exc:  # banco fora do ar
        return jsonify({"sucesso": False, "status": "banco_indisponivel", "detalhe": type(exc).__name__}), 503
