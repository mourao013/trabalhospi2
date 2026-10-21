"""Testes das funções de tratamento do ETL (sem banco)."""
import io
import unittest
import zipfile
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from etl.importar import (detectar_codificacao, detectar_separador, ler_csv, listar_fontes,
                          mapear_colunas, tratar_data, tratar_situacao, tratar_uf, transformar_linha)


class TestETL(unittest.TestCase):
    def test_mapeamento_cabecalho_portal_transparencia(self):
        cab = ["Id_SERVIDOR_PORTAL", "NOME", "CPF", "MATRICULA", "DESCRICAO_CARGO",
               "ORGAO_LOTACAO", "UF_EXERCICIO", "SITUACAO_VINCULO", "DATA_INGRESSO_SERVICOPUBLICO"]
        mapa = mapear_colunas(cab)
        self.assertEqual(mapa["nome"], 1)
        self.assertEqual(mapa["cargo"], 4)
        self.assertEqual(mapa["orgao"], 5)
        self.assertEqual(mapa["uf"], 6)
        self.assertEqual(mapa["data_ingresso"], 8)

    def test_cabecalho_com_acento_e_bom(self):
        mapa = mapear_colunas(["\ufeffNome", "Descrição Cargo", "Órgão", "UF"])
        self.assertEqual(mapa, {"nome": 0, "cargo": 1, "orgao": 2, "uf": 3})

    def test_datas(self):
        self.assertEqual(tratar_data("05/03/1990"), date(1990, 3, 5))
        self.assertEqual(tratar_data("1990-03-05"), date(1990, 3, 5))
        self.assertEqual(tratar_data("19900305"), date(1990, 3, 5))
        self.assertIsNone(tratar_data("Sem informação"))
        self.assertIsNone(tratar_data("31/02/2000"))
        self.assertIsNone(tratar_data("01/01/0001"))

    def test_uf(self):
        self.assertEqual(tratar_uf(" sp "), "SP")
        self.assertIsNone(tratar_uf("-1"))
        self.assertIsNone(tratar_uf("Sem informação"))

    def test_situacao(self):
        self.assertEqual(tratar_situacao("APOSENTADO", "x.csv"), "APOSENTADO")
        self.assertEqual(tratar_situacao("ATIVO PERMANENTE", "x.csv"), "ATIVO")
        self.assertEqual(tratar_situacao(None, "Aposentados_202501.csv"), "APOSENTADO")
        self.assertEqual(tratar_situacao(None, "Servidores_Cadastro.csv"), "ATIVO")

    def test_codificacao_e_separador(self):
        self.assertEqual(detectar_codificacao("José".encode("cp1252")), "cp1252")
        self.assertEqual(detectar_codificacao("José".encode("utf-8")), "utf-8")
        self.assertEqual(detectar_separador("A;B;C"), ";")
        self.assertEqual(detectar_separador("A,B,C"), ",")

    def test_linha_sem_nome_descartada(self):
        self.assertIsNone(transformar_linha(["", "X"], {"nome": 0, "cargo": 1}, "a.csv"))

    def test_leitura_csv_latin1_e_zip(self):
        conteudo = "NOME;DESCRICAO_CARGO;UF_EXERCICIO\nJOSÉ CONCEIÇÃO;MÉDICO;df\n".encode("cp1252")
        with TemporaryDirectory() as tmp:
            Path(tmp, "aposentados.csv").write_bytes(conteudo)
            with zipfile.ZipFile(Path(tmp, "pacote.zip"), "w") as z:
                z.writestr("dentro/servidores.csv", conteudo)
            fontes = list(listar_fontes(Path(tmp)))
            self.assertEqual([n for n, _ in fontes], ["aposentados.csv", "pacote.zip:dentro/servidores.csv"])
            for nome, abrir in fontes:
                cab, linhas, texto = ler_csv(abrir)
                mapa = mapear_colunas(cab)
                reg = transformar_linha(next(linhas), mapa, nome)
                texto.close()
                self.assertEqual(reg[0], "JOSÉ CONCEIÇÃO")
                self.assertEqual(reg[1], "JOSE CONCEICAO")
                self.assertEqual(reg[6], "MEDICO")
                self.assertEqual(reg[9], "DF")
                self.assertEqual(reg[4], "APOSENTADO" if "aposent" in nome else "ATIVO")


if __name__ == "__main__":
    unittest.main()
