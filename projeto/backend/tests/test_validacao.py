"""Testes unitários (não precisam de banco).  Rodar em backend/:
    python -m unittest discover -s tests -v
"""
import unittest

from werkzeug.datastructures import MultiDict

from app.validacao import ErroValidacao, normalizar, validar_busca


def validar(**kw):
    return validar_busca(MultiDict(kw))


class TestValidacao(unittest.TestCase):
    def assertErro(self, codigo, **kw):
        with self.assertRaises(ErroValidacao) as ctx:
            validar(**kw)
        self.assertEqual(ctx.exception.codigo, codigo, ctx.exception.mensagem)
        return ctx.exception

    def test_normalizar(self):
        self.assertEqual(normalizar("  José   da  Conceição "), "JOSE DA CONCEICAO")

    def test_nome_exato(self):
        f = validar(nome="maria da silva")
        self.assertEqual(f["nome"], "MARIA DA SILVA")
        self.assertEqual(f["pagina"], 1)
        self.assertEqual(f["por_pagina"], 20)

    def test_similar_com_aspas_e_limit(self):
        f = validar(similar='"<%jo%silva%>"', limit="100")
        self.assertEqual(f["similar"], "%JO%SILVA%")
        self.assertEqual(f["limit"], 100)
        self.assertEqual(f["similar_texto"], "JO SILVA")

    def test_similar_sem_curinga_vira_contem(self):
        self.assertEqual(validar(similar="maria silva")["similar"], "%MARIA SILVA%")

    def test_similar_formatos_do_enunciado(self):
        self.assertEqual(validar(similar="%NOME%SOBRENOME%")["similar"], "%NOME%SOBRENOME%")
        self.assertEqual(validar(similar="NOME SOBRENOME%")["similar"], "NOME SOBRENOME%")
        self.assertEqual(validar(similar="NOME%SOBRENOME")["similar"], "NOME%SOBRENOME")

    def test_similar_limit_maximo(self):
        self.assertErro("PARAMETRO_INVALIDO", similar="%ana%", limit="101")

    def test_similar_poucas_letras(self):
        self.assertErro("NOME_INVALIDO", similar="%a%")

    def test_combinada(self):
        f = validar(nome="Ana", cargo="professor", uf="sp")
        self.assertEqual((f["nome"], f["cargo"], f["uf"]), ("ANA", "PROFESSOR", "SP"))

    def test_sql_injection(self):
        for ataque in ["x' OR 1=1 --", "a'; DROP TABLE servidor;", "ana' or 'a'='a",
                       "1 UNION SELECT senha", "pg_sleep(10)", "abc/*comentario*/"]:
            with self.subTest(ataque=ataque):
                self.assertErro("SQL_INJECTION_DETECTADA", nome=ataque)
        self.assertErro("SQL_INJECTION_DETECTADA", cargo="x; delete from cargo")
        self.assertErro("SQL_INJECTION_DETECTADA", uf="SP'--")

    def test_nome_com_apostrofo_valido(self):
        self.assertEqual(validar(nome="Joana D'Arc")["nome"], "JOANA D'ARC")

    def test_strings_invalidas(self):
        self.assertErro("NOME_INVALIDO", nome="<script>alert(1)</script>")
        self.assertErro("NOME_INVALIDO", nome="ana123")
        self.assertErro("TAMANHO_INVALIDO", nome="a")
        self.assertErro("TAMANHO_INVALIDO", nome="a" * 101)
        self.assertErro("CARGO_INVALIDO", cargo="prof@ssor")
        self.assertErro("ORGAO_INVALIDO", orgao="minist#rio")

    def test_uf_invalida(self):
        self.assertErro("UF_INVALIDA", uf="XX")
        self.assertErro("UF_INVALIDA", uf="SAO PAULO")

    def test_parametros_invalidos(self):
        self.assertErro("PARAMETRO_INVALIDO", nome="ana", foo="1")
        self.assertErro("FILTRO_OBRIGATORIO", pagina="2")
        self.assertErro("PARAMETRO_VAZIO", nome="")
        self.assertErro("PARAMETRO_INVALIDO", nome="ana", similar="%ana%")
        self.assertErro("PARAMETRO_INVALIDO", nome="ana", pagina="abc")
        self.assertErro("PARAMETRO_INVALIDO", nome="ana", pagina="0")
        self.assertErro("PARAMETRO_INVALIDO", nome="ana", por_pagina="1000")
        self.assertErro("PARAMETRO_INVALIDO", situacao="morto", uf="SP")

    def test_parametro_repetido(self):
        with self.assertRaises(ErroValidacao):
            validar_busca(MultiDict([("uf", "SP"), ("uf", "RJ")]))

    def test_limit_sem_similar_vira_por_pagina(self):
        self.assertEqual(validar(uf="DF", limit="50")["por_pagina"], 50)


if __name__ == "__main__":
    unittest.main()
