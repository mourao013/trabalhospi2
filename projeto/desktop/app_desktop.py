"""Aplicação Desktop Multi-plataforma (Tkinter / ttk) — Adicional (Item 4 e 7.5).

Consome a API Flask (/api/servidores) via HTTP/HTTPS sem depender de Docker no cliente.
Pode ser executada diretamente com Python ou compilada em executável único com PyInstaller.

Execução direta:
    python app_desktop.py

Compilação para executável standalone (sem console):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name ConsultaServidoresFederal app_desktop.py
"""
import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import urllib.error
import urllib.parse
import urllib.request

UFS = [
    "", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
    "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


class AppDesktopServidores(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Servidores Federais — Consulta Desktop (Poder Executivo Federal)")
        self.geometry("1120x680")
        self.minsize(920, 560)
        self.configure(bg="#0d1428")

        self.pagina_atual = 1
        self.total_paginas = 1
        self.resultados_atuais: list[dict] = []

        self._configurar_estilo()
        self._construir_interface()
        self._verificar_saude_async()

    def _configurar_estilo(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("TFrame", background="#0d1428")
        st.configure("Card.TFrame", background="#151f38")
        st.configure("TLabel", background="#151f38", foreground="#e8ecf8", font=("Segoe UI", 10))
        st.configure("Header.TLabel", background="#0d1428", foreground="#19d3a2", font=("Segoe UI", 16, "bold"))
        st.configure("Sub.TLabel", background="#0d1428", foreground="#98a3c2", font=("Segoe UI", 9))
        st.configure("Status.TLabel", background="#0d1428", foreground="#ffd23f", font=("Segoe UI", 9, "bold"))
        st.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6)
        st.configure(
            "Treeview",
            background="#10182d",
            foreground="#e8ecf8",
            fieldbackground="#10182d",
            rowheight=28,
            font=("Segoe UI", 9),
        )
        st.configure("Treeview.Heading", background="#1d2b4f", foreground="#ffd23f", font=("Segoe UI", 9, "bold"))
        st.map("Treeview", background=[("selected", "#19d3a2")], foreground=[("selected", "#04121a")])

    def _construir_interface(self):
        topo = ttk.Frame(self, padding=(18, 14))
        topo.pack(fill="x")
        ttk.Label(topo, text="🏛️ Servidores do Poder Executivo Federal", style="Header.TLabel").pack(side="left")
        self.lbl_status = ttk.Label(topo, text="Conectando à API...", style="Status.TLabel")
        self.lbl_status.pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame", padding=14)
        card.pack(fill="x", padx=18, pady=(0, 10))

        # Linha 1: URL da API + Modo de busca
        f1 = ttk.Frame(card, style="Card.TFrame")
        f1.pack(fill="x", pady=(0, 8))
        ttk.Label(f1, text="URL da API:").pack(side="left")
        self.var_url = tk.StringVar(value="http://127.0.0.1:5000")
        ttk.Entry(f1, textvariable=self.var_url, width=28).pack(side="left", padx=(6, 16))

        ttk.Label(f1, text="Modo:").pack(side="left")
        self.var_modo = tk.StringVar(value="combinada")
        for texto, val in [
            ("Avançada / Combinada", "combinada"),
            ("Nome Exato", "nome"),
            ("Similaridade (%NOME%)", "similar"),
        ]:
            ttk.Radiobutton(f1, text=texto, value=val, variable=self.var_modo).pack(side="left", padx=6)

        # Linha 2: Campos de filtro
        grade = ttk.Frame(card, style="Card.TFrame")
        grade.pack(fill="x")

        self.var_nome = tk.StringVar()
        self.var_similar = tk.StringVar()
        self.var_limit = tk.StringVar(value="100")
        self.var_cargo = tk.StringVar()
        self.var_orgao = tk.StringVar()
        self.var_uf = tk.StringVar()
        self.var_situacao = tk.StringVar()

        campos = [
            ("Nome (exato):", self.var_nome, 22),
            ("Similar (%):", self.var_similar, 20),
            ("Limite sim.:", self.var_limit, 6),
            ("Cargo:", self.var_cargo, 20),
            ("Órgão:", self.var_orgao, 22),
        ]
        for col, (rotulo, var, larg) in enumerate(campos):
            ttk.Label(grade, text=rotulo).grid(row=0, column=col, sticky="w", padx=4)
            ttk.Entry(grade, textvariable=var, width=larg).grid(row=1, column=col, sticky="ew", padx=4, pady=2)

        ttk.Label(grade, text="UF:").grid(row=0, column=5, sticky="w", padx=4)
        ttk.Combobox(grade, textvariable=self.var_uf, values=UFS, width=5, state="readonly").grid(
            row=1, column=5, padx=4
        )

        ttk.Label(grade, text="Situação:").grid(row=0, column=6, sticky="w", padx=4)
        ttk.Combobox(
            grade, textvariable=self.var_situacao, values=["", "ATIVO", "APOSENTADO"], width=12, state="readonly"
        ).grid(row=1, column=6, padx=4)

        ttk.Button(grade, text="Buscar", command=lambda: self.buscar(1)).grid(row=1, column=7, padx=6)
        ttk.Button(grade, text="Limpar", command=self.limpar).grid(row=1, column=8, padx=2)

        # Tabela de resultados
        quadro_tab = ttk.Frame(self, padding=(18, 4))
        quadro_tab.pack(fill="both", expand=True)

        colunas = ("id", "nome", "cargo", "orgao", "uf", "situacao")
        self.tree = ttk.Treeview(quadro_tab, columns=colunas, show="headings")
        for col, titulo, larg in [
            ("id", "ID", 60),
            ("nome", "Nome do Servidor", 260),
            ("cargo", "Cargo / Profissão", 240),
            ("orgao", "Instituição / Órgão", 270),
            ("uf", "UF", 50),
            ("situacao", "Situação", 100),
        ]:
            self.tree.heading(col, text=titulo)
            self.tree.column(col, width=larg, anchor="w" if col != "uf" else "center")

        scroll = ttk.Scrollbar(quadro_tab, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._mostrar_detalhe)

        # Rodapé de paginação
        rodape = ttk.Frame(self, padding=(18, 10))
        rodape.pack(fill="x")
        self.lbl_resumo = ttk.Label(rodape, text="Faça uma busca acima. Duplo clique em uma linha abre os detalhes.", style="Sub.TLabel")
        self.lbl_resumo.pack(side="left")

        nav = ttk.Frame(rodape)
        nav.pack(side="right")
        self.btn_ant = ttk.Button(nav, text="◀ Anterior", command=lambda: self.buscar(self.pagina_atual - 1), state="disabled")
        self.btn_ant.pack(side="left", padx=4)
        self.lbl_pag = ttk.Label(nav, text="Página 1/1", style="Sub.TLabel")
        self.lbl_pag.pack(side="left", padx=8)
        self.btn_prox = ttk.Button(nav, text="Próxima ▶", command=lambda: self.buscar(self.pagina_atual + 1), state="disabled")
        self.btn_prox.pack(side="left", padx=4)

    def _base_url(self) -> str:
        """Lê a URL na thread principal (Tkinter não é thread-safe - ERR-014)."""
        return self.var_url.get().strip().rstrip("/") or "http://127.0.0.1:5000"

    @staticmethod
    def _chamar_api(base: str, caminho: str, params: dict | None = None) -> dict:
        """Executa a requisição HTTP. Não toca em widgets: pode rodar em thread."""
        url = f"{base}{caminho}"
        if params:
            qs = urllib.parse.urlencode({k: v for k, v in params.items() if v != "" and v is not None})
            url = f"{url}?{qs}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                corpo = json.loads(e.read().decode("utf-8", errors="replace"))
                mensagem = corpo.get("erro", {}).get("mensagem") or f"Erro HTTP {e.code}"
            except ValueError:  # corpo não-JSON (ex.: página de erro do proxy)
                mensagem = f"Erro HTTP {e.code}"
            raise RuntimeError(mensagem) from None
        except urllib.error.URLError:
            raise RuntimeError(f"Não foi possível conectar à API em {base}. "
                               "Verifique se o backend está rodando.") from None

    def _verificar_saude_async(self):
        base = self._base_url()

        def _worker():
            try:
                dados = self._chamar_api(base, "/api/saude")
                n = dados.get("servidores_estimado", 0)
                texto = f"● API Online (~{n:,} servidores)".replace(",", ".")
            except Exception:
                texto = "○ API Offline (verifique URL/Docker)"
            self.after(0, lambda t=texto: self.lbl_status.configure(text=t))

        threading.Thread(target=_worker, daemon=True).start()

    def limpar(self):
        for v in (self.var_nome, self.var_similar, self.var_cargo, self.var_orgao, self.var_uf, self.var_situacao):
            v.set("")
        self.var_limit.set("100")
        self.tree.delete(*self.tree.get_children())
        self.lbl_resumo.configure(text="Campos limpos.")

    def buscar(self, pagina: int = 1):
        modo = self.var_modo.get()
        params: dict[str, str | int] = {"pagina": max(1, pagina), "por_pagina": 20}
        if modo == "nome":
            params["nome"] = self.var_nome.get().strip()
        elif modo == "similar":
            params["similar"] = self.var_similar.get().strip()
            params["limit"] = self.var_limit.get().strip() or "100"
        else:
            if self.var_nome.get().strip():
                params["nome"] = self.var_nome.get().strip()
            elif self.var_similar.get().strip():
                params["similar"] = self.var_similar.get().strip()
                params["limit"] = self.var_limit.get().strip() or "100"
            if self.var_cargo.get().strip():
                params["cargo"] = self.var_cargo.get().strip()
            if self.var_orgao.get().strip():
                params["orgao"] = self.var_orgao.get().strip()
            if self.var_uf.get().strip():
                params["uf"] = self.var_uf.get().strip()
        if self.var_situacao.get().strip():
            params["situacao"] = self.var_situacao.get().strip()

        self.lbl_resumo.configure(text="Consultando API...")
        base = self._base_url()

        def _worker():
            try:
                resp = self._chamar_api(base, "/api/servidores", params)
                self.after(0, lambda r=resp: self._preencher_resultados(r))
            except Exception as exc:
                # 'exc' deixa de existir ao sair do except: capturar a mensagem agora (ERR-015)
                msg = str(exc)
                self.after(0, lambda m=msg: self._mostrar_erro(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _mostrar_erro(self, mensagem: str):
        self.lbl_resumo.configure(text=f"Erro: {mensagem}")
        messagebox.showwarning("Aviso da API", mensagem, parent=self)

    def _preencher_resultados(self, resp: dict):
        self.tree.delete(*self.tree.get_children())
        self.resultados_atuais = resp.get("resultados", [])
        self.pagina_atual = resp.get("pagina", 1)
        self.total_paginas = resp.get("total_paginas", 1)

        for i, r in enumerate(self.resultados_atuais):
            self.tree.insert(
                "", "end", iid=str(i),
                values=(r.get("id"), r.get("nome"), r.get("cargo") or "—", r.get("orgao") or "—", r.get("uf") or "—", r.get("situacao")),
            )

        self.lbl_resumo.configure(text=resp.get("mensagem", ""))
        self.lbl_pag.configure(text=f"Página {self.pagina_atual}/{self.total_paginas}")
        self.btn_ant.configure(state="normal" if self.pagina_atual > 1 else "disabled")
        self.btn_prox.configure(state="normal" if self.pagina_atual < self.total_paginas else "disabled")

        if resp.get("total") == 1 and resp.get("registro"):
            self._abrir_janela_detalhe(resp["registro"])

    def _mostrar_detalhe(self, _evento):
        selecao = self.tree.selection()
        if not selecao:
            return
        idx = int(selecao[0])
        if 0 <= idx < len(self.resultados_atuais):
            self._abrir_janela_detalhe(self.resultados_atuais[idx])

    def _abrir_janela_detalhe(self, r: dict):
        jan = tk.Toplevel(self)
        jan.title(f"Ficha do Servidor — {r.get('nome')}")
        jan.geometry("520x360")
        jan.configure(bg="#151f38")
        frame = ttk.Frame(jan, style="Card.TFrame", padding=18)
        frame.pack(fill="both", expand=True)

        pares = [
            ("Nome", r.get("nome")),
            ("Situação", r.get("situacao")),
            ("Cargo", r.get("cargo")),
            ("Órgão / Instituição", r.get("orgao")),
            ("UF", f"{r.get('uf') or '—'} ({r.get('uf_nome') or '—'})"),
            ("CPF Mascarado", r.get("cpf_mascarado")),
            ("Matrícula", r.get("matricula")),
            ("Data de Ingresso", r.get("data_ingresso")),
            ("Tipo de Aposentadoria", r.get("tipo_aposentadoria")),
            ("Data da Aposentadoria", r.get("data_aposentadoria")),
        ]
        for i, (k, v) in enumerate(pares):
            ttk.Label(frame, text=f"{k}:", font=("Segoe UI", 9, "bold")).grid(row=i, column=0, sticky="w", pady=3, padx=6)
            ttk.Label(frame, text=str(v or "—")).grid(row=i, column=1, sticky="w", pady=3, padx=6)


if __name__ == "__main__":
    app = AppDesktopServidores()
    app.mainloop()
