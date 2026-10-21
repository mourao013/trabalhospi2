"""Testes dos endpoints com o banco simulado (mock)."""
import threading
import unittest
from unittest import mock

import psycopg

from app import create_app, protecao
from app.validacao import ErroValidacao

REGISTRO = {"id": 1, "nome": "ANA SILVA", "cargo": "MEDICO", "orgao": "MINISTERIO DA SAUDE", "uf": "DF"}


def resultado(total, pagina=1, por_pagina=20):
    return {"total": total, "total_exato": True, "pagina": pagina, "por_pagina": por_pagina,
            "total_paginas": max(1, -(-total // por_pagina)), "resultados": [REGISTRO] * min(total, por_pagina)}


class TestAPI(unittest.TestCase):
    def setUp(self):
        self.cliente = create_app().test_client()
        protecao.limitador._acessos.clear()

    @mock.patch("app.consultas.buscar_servidores")
    def test_um_resultado_traz_registro(self, buscar):
        buscar.return_value = resultado(1)
        r = self.cliente.get("/api/servidores?nome=ana silva")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["registro"]["nome"], "ANA SILVA")
        self.assertFalse(r.json["multiplos"])

    @mock.patch("app.consultas.buscar_servidores")
    def test_multiplos_resultados(self, buscar):
        buscar.return_value = resultado(45)
        r = self.cliente.get("/api/servidores?nome=ana silva")
        self.assertTrue(r.json["multiplos"])
        self.assertIn("múltiplos", r.json["mensagem"])
        self.assertEqual(r.json["total_paginas"], 3)

    @mock.patch("app.consultas.buscar_servidores")
    def test_nao_encontrado(self, buscar):
        buscar.side_effect = ErroValidacao("NAO_ENCONTRADO", "Nenhum servidor encontrado.", status=404)
        r = self.cliente.get("/api/servidores?nome=fulano inexistente")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json["erro"]["codigo"], "NAO_ENCONTRADO")

    def test_sql_injection_retorna_400(self):
        r = self.cliente.get("/api/servidores?nome=x' OR 1=1 --")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json["erro"]["codigo"], "SQL_INJECTION_DETECTADA")

    def test_uf_invalida(self):
        r = self.cliente.get("/api/servidores?uf=ZZ")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json["erro"]["codigo"], "UF_INVALIDA")

    def test_rota_inexistente_json(self):
        r = self.cliente.get("/api/naoexiste")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json["erro"]["codigo"], "ROTA_INEXISTENTE")

    def test_metodo_nao_permitido(self):
        self.assertEqual(self.cliente.post("/api/servidores").status_code, 405)

    @mock.patch("app.consultas.buscar_servidores")
    def test_timeout_retorna_504(self, buscar):
        buscar.side_effect = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
        r = self.cliente.get("/api/servidores?uf=SP")
        self.assertEqual(r.status_code, 504)
        self.assertEqual(r.json["erro"]["codigo"], "TEMPO_EXCEDIDO")

    @mock.patch("app.consultas.buscar_servidores")
    def test_rate_limit_429(self, buscar):
        buscar.return_value = resultado(1)
        with mock.patch.object(protecao.limitador, "maximo", 3):
            codigos = [self.cliente.get("/api/servidores?uf=SP").status_code for _ in range(5)]
        self.assertEqual(codigos, [200, 200, 200, 429, 429])

    @mock.patch("app.consultas.buscar_servidores")
    def test_excesso_simultaneo_503(self, buscar):
        buscar.return_value = resultado(1)
        sem = threading.BoundedSemaphore(1)
        sem.acquire()  # simula todas as vagas ocupadas
        with mock.patch.object(protecao, "vagas_busca", sem), \
                mock.patch("app.config.ESPERA_VAGA_S", 0.05):
            r = self.cliente.get("/api/servidores?uf=SP")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json["erro"]["codigo"], "SERVIDOR_OCUPADO")
        self.assertIn("Retry-After", r.headers)


if __name__ == "__main__":
    unittest.main()
