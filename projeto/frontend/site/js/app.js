/* Front-end: consome a API Flask via /api (proxy reverso do Nginx). */
(() => {
  "use strict";

  const API = "/api";
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

  const DICAS = {
    nome: "Busca <b>exata</b> pelo nome completo (acentos e maiúsculas são ignorados).",
    similar: "Use <code>%</code> como curinga: <code>%NOME%SOBRENOME%</code>, <code>NOME SOBRENOME%</code> ou <code>NOME%SOBRENOME</code>. Resultados ordenados por semelhança.",
    cargo: "Informe um cargo ou profissão (busca parcial: <code>professor</code> encontra todos os cargos de professor).",
    uf: "Selecione a unidade federativa.",
    orgao: "Informe a instituição ou órgão (busca parcial).",
    avancada: "Combine vários critérios: por exemplo <b>cargo + estado</b> ou <b>órgão + estado</b>.",
  };
  const CAMPOS_MODO = {
    nome: ["nome"], similar: ["similar", "limit"], cargo: ["cargo"], uf: ["uf"], orgao: ["orgao"],
    avancada: ["nome", "similar", "cargo", "orgao", "uf"],
  };

  const estado = { modo: "nome", parametros: null, pagina: 1, controlador: null };

  // ------------------------------------------------------------ utilidades
  const escapar = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const formatarData = (iso) => (iso ? iso.split("-").reverse().join("/") : "—");

  const iniciais = (nome) => nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("");

  function debounce(fn, ms) {
    let t;
    return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  }

  async function chamarApi(caminho, params = {}, sinal) {
    const url = new URL(API + caminho, window.location.origin);
    Object.entries(params).forEach(([k, v]) => v !== "" && v != null && url.searchParams.set(k, v));
    const resp = await fetch(url, { signal: sinal, headers: { Accept: "application/json" } });
    let corpo;
    try { corpo = await resp.json(); } catch { corpo = null; }
    if (!resp.ok || !corpo || corpo.sucesso === false) {
      const erro = corpo?.erro || { codigo: `HTTP_${resp.status}`, mensagem: "Resposta inesperada da API." };
      const e = new Error(erro.mensagem);
      Object.assign(e, erro, { status: resp.status, campo: erro.campo });
      throw e;
    }
    return { corpo, url: url.pathname + url.search };
  }

  // ------------------------------------------------------------ status da API
  async function verificarStatus() {
    const el = $("#status-api");
    try {
      const { corpo } = await chamarApi("/saude");
      el.className = "status ok";
      const n = Number(corpo.servidores_estimado || 0).toLocaleString("pt-BR");
      $(".texto", el).innerHTML = `API online · ~${n} registros` +
        (corpo.dados_ficticios ? '<span class="selo">amostra fictícia</span>' : "");
    } catch {
      el.className = "status erro";
      $(".texto", el).textContent = "API indisponível (tentando novamente…)";
      setTimeout(verificarStatus, 5000);
    }
  }

  async function carregarUfs() {
    const sel = $("#f-uf");
    try {
      const { corpo } = await chamarApi("/ufs");
      corpo.resultados.forEach(({ sigla, nome }) => sel.add(new Option(`${sigla} — ${nome}`, sigla)));
    } catch {
      "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
        .split(" ").forEach((uf) => sel.add(new Option(uf, uf)));
    }
  }

  function autocompletar(input, lista, caminho) {
    input.addEventListener("input", debounce(async () => {
      const q = input.value.trim();
      if (q.length < 2) return;
      try {
        const { corpo } = await chamarApi(caminho, { q, limit: 15 });
        lista.innerHTML = corpo.resultados.map((n) => `<option value="${escapar(n)}">`).join("");
      } catch { /* autocompletar é opcional */ }
    }, 300));
  }

  // ------------------------------------------------------------ abas
  function trocarModo(modo) {
    estado.modo = modo;
    $$(".aba").forEach((b) => b.classList.toggle("ativa", b.dataset.modo === modo));
    $$(".campo[data-modos]").forEach((c) => { c.hidden = !c.dataset.modos.split(" ").includes(modo); });
    $("#dica-modo").innerHTML = DICAS[modo];
    $$("input.invalido").forEach((i) => i.classList.remove("invalido"));
    const primeiro = $(".campo:not([hidden]) input, .campo:not([hidden]) select");
    primeiro?.focus();
  }

  function coletarParametros() {
    const p = {};
    CAMPOS_MODO[estado.modo].forEach((nome) => {
      const v = $(`[name="${nome}"]`).value.trim();
      if (v) p[nome] = v;
    });
    if (p.nome && p.similar) delete p.similar; // a API aceita só um dos dois
    if (!p.similar) delete p.limit;
    const situacao = $("#f-situacao").value;
    if (situacao) p.situacao = situacao;
    p.por_pagina = $("#f-por-pagina").value;
    return p;
  }

  // ------------------------------------------------------------ busca
  async function buscar(pagina = 1) {
    if (!estado.parametros) return;
    estado.controlador?.abort();
    estado.controlador = new AbortController();
    estado.pagina = pagina;

    const botao = $("#btn-buscar");
    botao.disabled = true;
    botao.classList.add("carregando-busca");
    $("#area-resultado").innerHTML = `<div class="cartao skeleton">${"<span></span>".repeat(6)}</div>`;

    try {
      const { corpo, url } = await chamarApi("/servidores", { ...estado.parametros, pagina }, estado.controlador.signal);
      $("#url-api").textContent = url;
      renderizarResultado(corpo);
    } catch (e) {
      if (e.name === "AbortError") return;
      renderizarErro(e);
    } finally {
      botao.disabled = false;
      botao.classList.remove("carregando-busca");
    }
  }

  function chipsFiltros(filtros) {
    const rotulos = { nome: "Nome", similar: "Similar", cargo: "Cargo", uf: "UF", orgao: "Órgão", situacao: "Situação", limit: "Limite" };
    return Object.entries(filtros)
      .filter(([k]) => rotulos[k])
      .map(([k, v]) => `<span class="chip">${rotulos[k]}: ${escapar(v)}</span>`).join("");
  }

  function htmlDetalhe(r) {
    const linhas = [
      ["Cargo", r.cargo], ["Órgão / instituição", r.orgao],
      ["Estado", r.uf ? `${r.uf}${r.uf_nome ? " — " + r.uf_nome : ""}` : null],
      ["Situação", r.situacao], ["Matrícula", r.matricula], ["CPF", r.cpf_mascarado],
      ["Ingresso no serviço público", r.data_ingresso && formatarData(r.data_ingresso)],
      ["Tipo de aposentadoria", r.tipo_aposentadoria],
      ["Data da aposentadoria", r.data_aposentadoria && formatarData(r.data_aposentadoria)],
    ];
    return `
      <div class="detalhe">
        <div class="detalhe-topo">
          <div class="avatar">${escapar(iniciais(r.nome))}</div>
          <div>
            <h3>${escapar(r.nome)}</h3>
            <span class="tag ${escapar(r.situacao)}">${escapar(r.situacao)}</span>
          </div>
        </div>
        <dl class="info">
          ${linhas.map(([k, v]) => `<div><dt>${k}</dt><dd>${escapar(v || "—")}</dd></div>`).join("")}
        </dl>
      </div>`;
  }

  function htmlPaginacao(atual, total) {
    const inicio = Math.max(1, Math.min(atual - 2, total - 4));
    const fim = Math.min(total, inicio + 4);
    let botoes = `<button class="pag" data-pag="1" ${atual === 1 ? "disabled" : ""} title="Primeira">«</button>
                  <button class="pag" data-pag="${atual - 1}" ${atual === 1 ? "disabled" : ""} title="Anterior">‹</button>`;
    for (let i = inicio; i <= fim; i++) {
      botoes += `<button class="pag ${i === atual ? "atual" : ""}" data-pag="${i}">${i}</button>`;
    }
    botoes += `<button class="pag" data-pag="${atual + 1}" ${atual === total ? "disabled" : ""} title="Próxima">›</button>
               <button class="pag" data-pag="${total}" ${atual === total ? "disabled" : ""} title="Última">»</button>`;
    return `
      <div class="paginacao">
        <div class="paginas">${botoes}</div>
        <form class="ir-para" id="form-ir">
          Página ${atual} de ${total} · ir para
          <input type="number" min="1" max="${total}" value="${atual}" aria-label="Número da página">
          <button class="pag" type="submit">Ir</button>
        </form>
      </div>`;
  }

  function renderizarResultado(c) {
    const area = $("#area-resultado");
    const cabecalho = `
      <div class="resumo">
        <h2><span class="total">${c.total.toLocaleString("pt-BR")}${c.total_exato ? "" : "+"}</span>
            ${c.total === 1 ? "registro encontrado" : "registros encontrados"}</h2>
        <div class="chips">${chipsFiltros(c.filtros)}</div>
      </div>`;

    if (c.total === 1) {                       // único resultado: mostra os dados completos
      area.innerHTML = `<div class="cartao">${cabecalho}${htmlDetalhe(c.registro)}</div>`;
      return;
    }

    const mostraSim = c.resultados.some((r) => r.similaridade != null);
    const linhas = c.resultados.map((r, i) => `
      <tr data-indice="${i}" style="animation-delay:${i * 15}ms">
        <td class="nome">${escapar(r.nome)}${mostraSim ? ` <span class="sim">${Math.round(r.similaridade * 100)}%</span>` : ""}</td>
        <td>${escapar(r.cargo || "—")}</td>
        <td>${escapar(r.orgao || "—")}</td>
        <td class="uf-badge">${escapar(r.uf || "—")}</td>
        <td><span class="tag ${escapar(r.situacao)}">${escapar(r.situacao)}</span></td>
      </tr>`).join("");

    area.innerHTML = `
      <div class="cartao">
        ${cabecalho}
        ${c.total_exato ? "" : `<p class="dica" style="padding:12px 22px 0">⚠️ Busca muito ampla: exibindo os primeiros ${c.total.toLocaleString("pt-BR")}. Refine os filtros.</p>`}
        <div class="tabela-wrap">
          <table>
            <thead><tr><th>Nome</th><th>Cargo</th><th>Órgão</th><th>UF</th><th>Situação</th></tr></thead>
            <tbody>${linhas}</tbody>
          </table>
        </div>
        ${htmlPaginacao(c.pagina, c.total_paginas)}
      </div>`;

    $$("tbody tr", area).forEach((tr) =>
      tr.addEventListener("click", () => abrirModal(c.resultados[Number(tr.dataset.indice)])));
    $$(".pag[data-pag]", area).forEach((b) =>
      b.addEventListener("click", () => { buscar(Number(b.dataset.pag)); window.scrollTo({ top: area.offsetTop - 20, behavior: "smooth" }); }));
    $("#form-ir", area).addEventListener("submit", (ev) => {
      ev.preventDefault();
      const n = Number($("input", ev.target).value);
      if (n >= 1 && n <= c.total_paginas) buscar(n);
    });
  }

  function renderizarErro(e) {
    const icones = { 404: "🔍", 429: "⏳", 503: "🚧", 504: "⌛" };
    if (e.campo) $(`[name="${e.campo}"]`)?.classList.add("invalido");
    const status = e.status || 0;
    $("#area-resultado").innerHTML = `
      <div class="cartao erro-caixa">
        <div class="icone">${icones[status] || (status === 0 ? "📡" : "⚠️")}</div>
        <div>
          <h3>${status === 0 ? "Não foi possível conectar à API" : escapar(e.message)}</h3>
          <code>${escapar(e.codigo || "ERRO_REDE")} · HTTP ${status || "—"}</code>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------ modal
  function abrirModal(registro) {
    $("#modal-conteudo").innerHTML = htmlDetalhe(registro);
    $("#modal").hidden = false;
  }
  const fecharModal = () => { $("#modal").hidden = true; };

  // ------------------------------------------------------------ eventos
  $$(".aba").forEach((b) => b.addEventListener("click", () => trocarModo(b.dataset.modo)));

  $("#form-busca").addEventListener("submit", (ev) => {
    ev.preventDefault();
    $$("input.invalido").forEach((i) => i.classList.remove("invalido"));
    const p = coletarParametros();
    if (!["nome", "similar", "cargo", "uf", "orgao"].some((k) => p[k])) {
      renderizarErro({ message: "Preencha ao menos um campo de busca.", codigo: "FILTRO_OBRIGATORIO", status: 400 });
      return;
    }
    estado.parametros = p;
    buscar(1);
  });

  $("#btn-limpar").addEventListener("click", () => {
    $("#form-busca").reset();
    estado.parametros = null;
    $("#area-resultado").innerHTML = `<div class="vazio"><div class="ilustracao">📊</div><h2>Faça uma consulta</h2><p>Escolha um tipo de busca acima.</p></div>`;
  });

  $$("[data-fechar]").forEach((el) => el.addEventListener("click", fecharModal));
  document.addEventListener("keydown", (e) => e.key === "Escape" && fecharModal());

  autocompletar($("#f-cargo"), $("#lista-cargos"), "/cargos");
  autocompletar($("#f-orgao"), $("#lista-orgaos"), "/orgaos");
  trocarModo("nome");
  carregarUfs();
  verificarStatus();
})();
