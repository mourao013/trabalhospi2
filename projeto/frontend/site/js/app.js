/* ==========================================================================
   Painel de Consulta — Servidores do Poder Executivo Federal
   Cliente HTTP/JSON para a API Flask (/api/servidores, /cargos, /orgaos, /ufs, /saude)
   Acessibilidade WCAG 2.2 AA: Navegação por teclado nas abas, gestão de foco no modal,
   anúncio de estados assíncronos e validação associada aos controles.
   ========================================================================== */
(() => {
  "use strict";

  const API_BASE = "/api";
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => [...raiz.querySelectorAll(sel)];

  const ORIENTACOES_MODO = {
    nome: "<strong>Busca por Nome Exato:</strong> informe o nome completo do servidor. A API normaliza acentos e caixa alta automaticamente (ex.: <code>GET /api/servidores?nome=MARIA DIAS SILVA</code>).",
    similar: "<strong>Busca por Similaridade de Nome:</strong> utilize <code>%</code> como curinga (<code>%NOME%SOBRENOME%</code>, <code>NOME SOBRENOME%</code> ou <code>NOME%SOBRENOME</code>) e defina o limite máximo de até 100 resultados ordenados por score de trigramas (<code>pg_trgm</code>).",
    cargo: "<strong>Busca por Cargo / Profissão:</strong> consulte servidores ativos e aposentados filtrando pela carreira ou denominação do cargo.",
    uf: "<strong>Busca por Estado (UF):</strong> liste os servidores vinculados a uma Unidade Federativa específica.",
    orgao: "<strong>Busca por Instituição / Órgão:</strong> filtre por ministério, autarquia, universidade federal ou instituto.",
    avancada: "<strong>Busca Combinada Avançada:</strong> combine múltiplos filtros simultaneamente (ex.: <em>Cargo + UF</em>, <em>Órgão + UF + Situação</em> ou <em>Nome + Cargo</em>).",
  };

  const CAMPOS_POR_MODO = {
    nome: ["nome"],
    similar: ["similar", "limit"],
    cargo: ["cargo"],
    uf: ["uf"],
    orgao: ["orgao"],
    avancada: ["nome", "similar", "cargo", "orgao", "uf"],
  };

  const estado = {
    modo: "nome",
    parametros: null,
    pagina: 1,
    controlador: null,
    ultimoFocoModal: null,
    ultimosResultados: [],
  };

  // ---------------------------------------------------------------- Utilitários
  const escapar = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const formatarData = (iso) => (iso ? iso.split("-").reverse().join("/") : "Não informado");

  const iniciais = (nome) =>
    String(nome || "SF")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0])
      .join("");

  function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  async function requisitarApi(caminho, params = {}, signal) {
    const inicio = performance.now();
    const url = new URL(API_BASE + caminho, window.location.origin);
    Object.entries(params).forEach(([k, v]) => {
      if (v !== "" && v != null) url.searchParams.set(k, v);
    });

    const resp = await fetch(url, {
      signal,
      headers: { Accept: "application/json" },
    });

    let corpo = null;
    try {
      corpo = await resp.json();
    } catch {
      corpo = null;
    }

    const duracaoMs = Math.round(performance.now() - inicio);

    if (!resp.ok || !corpo || corpo.sucesso === false) {
      const erroObj = corpo?.erro || {
        codigo: `HTTP_${resp.status}`,
        mensagem: "Não foi possível concluir a consulta na API.",
      };
      const err = new Error(erroObj.mensagem);
      Object.assign(err, erroObj, {
        status: resp.status,
        campo: erroObj.campo,
        urlRelativa: url.pathname + url.search,
      });
      throw err;
    }

    return {
      corpo,
      urlRelativa: url.pathname + url.search,
      duracaoMs,
    };
  }

  // ---------------------------------------------------------------- Tema Claro / Escuro
  function inicializarTema() {
    const salvo = localStorage.getItem("tema_servidores");
    const temaInicial = salvo === "escuro" ? "escuro" : "claro";
    aplicarTema(temaInicial);

    $("#btn-tema").addEventListener("click", () => {
      const atual = document.documentElement.getAttribute("data-tema") === "escuro" ? "claro" : "escuro";
      aplicarTema(atual);
      localStorage.setItem("tema_servidores", atual);
    });
  }

  function aplicarTema(tema) {
    document.documentElement.setAttribute("data-tema", tema);
    $("#rotulo-tema").textContent = tema === "escuro" ? "Tema claro" : "Tema escuro";
  }

  // ---------------------------------------------------------------- Saúde e Domínios
  async function verificarSaudeApi() {
    const badge = $("#status-api");
    try {
      const { corpo } = await requisitarApi("/saude");
      badge.className = "status-badge ok";
      const qtd = Number(corpo.servidores_estimado || 0).toLocaleString("pt-BR");
      $(".status-texto", badge).textContent = `API Online · ${qtd} registros`;

      $("#met-servidores").textContent = qtd;
      $("#met-cargos").textContent = Number(corpo.cargos || 0).toLocaleString("pt-BR");
      $("#met-orgaos").textContent = Number(corpo.orgaos || 0).toLocaleString("pt-BR");
      $("#met-fonte").textContent = corpo.dados_ficticios
        ? "Base de demonstração ativa (20.000 servidores)"
        : "CSVs oficiais do dados.gov.br carregados";
    } catch {
      badge.className = "status-badge erro";
      $(".status-texto", badge).textContent = "API Offline — reconectando…";
      $("#met-fonte").textContent = "Sem conexão com o contêiner backend";
      setTimeout(verificarSaudeApi, 5000);
    }
  }

  async function carregarUfs() {
    const sel = $("#f-uf");
    try {
      const { corpo } = await requisitarApi("/ufs");
      corpo.resultados.forEach(({ sigla, nome }) => {
        sel.add(new Option(`${sigla} — ${nome}`, sigla));
      });
      $("#met-ufs").textContent = `${corpo.resultados.length} UFs`;
    } catch {
      "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
        .split(" ")
        .forEach((uf) => sel.add(new Option(uf, uf)));
    }
  }

  function configurarAutocompletar(input, datalist, endpoint) {
    input.addEventListener(
      "input",
      debounce(async () => {
        const q = input.value.trim();
        if (q.length < 2) return;
        try {
          const { corpo } = await requisitarApi(endpoint, { q, limit: 15 });
          datalist.innerHTML = corpo.resultados.map((item) => `<option value="${escapar(item)}">`).join("");
        } catch {
          /* falha silenciosa no autocomplete não bloqueia digitação */
        }
      }, 280)
    );
  }

  // ---------------------------------------------------------------- Abas (WAI-ARIA Tabs)
  function selecionarModo(modo, focarPrimeiroCampo = false) {
    estado.modo = modo;
    const abas = $$(".aba[role='tab']");
    abas.forEach((aba) => {
      const ativa = aba.dataset.modo === modo;
      aba.setAttribute("aria-selected", String(ativa));
      aba.tabIndex = ativa ? 0 : -1;
      if (ativa) {
        $("#form-busca").setAttribute("aria-labelledby", aba.id);
      }
    });

    $$(".grupo-campo[data-modos]").forEach((grupo) => {
      const modos = grupo.dataset.modos.split(" ");
      grupo.hidden = !modos.includes(modo);
    });

    $("#dica-modo").innerHTML = ORIENTACOES_MODO[modo] || "";
    limparErrosValidacao();
    atualizarPreviewEndpoint();

    if (focarPrimeiroCampo) {
      const primeiro = $(".grupo-campo:not([hidden]) input, .grupo-campo:not([hidden]) select");
      primeiro?.focus();
    }
  }

  function configurarTecladoAbas() {
    const listaAbas = $(".abas-lista");
    const abas = $$(".aba[role='tab']", listaAbas);

    listaAbas.addEventListener("keydown", (ev) => {
      const idx = abas.indexOf(document.activeElement);
      if (idx === -1) return;

      let novoIdx = idx;
      if (ev.key === "ArrowRight") novoIdx = (idx + 1) % abas.length;
      else if (ev.key === "ArrowLeft") novoIdx = (idx - 1 + abas.length) % abas.length;
      else if (ev.key === "Home") novoIdx = 0;
      else if (ev.key === "End") novoIdx = abas.length - 1;
      else return;

      ev.preventDefault();
      abas[novoIdx].focus();
      selecionarModo(abas[novoIdx].dataset.modo, false);
    });
  }

  // ---------------------------------------------------------------- Parâmetros e Preview
  function coletarParametrosFormulario() {
    const params = {};
    CAMPOS_POR_MODO[estado.modo].forEach((campo) => {
      const el = $(`[name="${campo}"]`);
      const val = el ? el.value.trim() : "";
      if (val !== "") params[campo] = val;
    });

    if (!params.similar) {
      delete params.limit;
    }

    const situacao = $("#f-situacao").value;
    if (situacao) params.situacao = situacao;

    params.por_pagina = $("#f-por-pagina").value || "20";
    return params;
  }

  function atualizarPreviewEndpoint() {
    const p = coletarParametrosFormulario();
    const qs = new URLSearchParams(p).toString();
    $("#url-api").textContent = qs ? `/api/servidores?${qs}` : "/api/servidores";
  }

  function limparErrosValidacao() {
    const alerta = $("#alerta-validacao");
    alerta.hidden = true;
    alerta.textContent = "";
    $$("[aria-invalid='true']").forEach((el) => el.removeAttribute("aria-invalid"));
  }

  function exibirErroValidacao(mensagem, campo) {
    const alerta = $("#alerta-validacao");
    alerta.textContent = mensagem;
    alerta.hidden = false;
    if (campo) {
      const input = $(`[name="${campo}"]`);
      if (input && !input.closest(".grupo-campo")?.hidden) {
        input.setAttribute("aria-invalid", "true");
        input.focus();
      }
    }
  }

  // ---------------------------------------------------------------- Execução da Busca
  async function executarBusca(pagina = 1) {
    if (!estado.parametros) return;

    estado.controlador?.abort();
    estado.controlador = new AbortController();
    estado.pagina = pagina;

    const painel = $("#painel-resultados");
    const btnBuscar = $("#btn-buscar");

    painel.setAttribute("aria-busy", "true");
    btnBuscar.disabled = true;
    btnBuscar.classList.add("carregando-busca");

    painel.innerHTML = `
      <div class="skeleton-grade" aria-label="Carregando resultados da consulta">
        <div class="skeleton-linha"></div>
        <div class="skeleton-linha"></div>
        <div class="skeleton-linha"></div>
        <div class="skeleton-linha"></div>
        <div class="skeleton-linha"></div>
      </div>`;

    try {
      const { corpo, urlRelativa, duracaoMs } = await requisitarApi(
        "/servidores",
        { ...estado.parametros, pagina },
        estado.controlador.signal
      );
      $("#url-api").textContent = urlRelativa;
      renderizarResultados(corpo, duracaoMs);
    } catch (err) {
      if (err.name === "AbortError") return;
      if (err.urlRelativa) $("#url-api").textContent = err.urlRelativa;
      if (err.status === 400 && err.campo) {
        exibirErroValidacao(err.message, err.campo);
      }
      renderizarEstadoErro(err);
    } finally {
      painel.setAttribute("aria-busy", "false");
      btnBuscar.disabled = false;
      btnBuscar.classList.remove("carregando-busca");
    }
  }

  function renderizarChipsFiltros(filtros) {
    const rotulos = {
      nome: "Nome exato",
      similar: "Similaridade",
      cargo: "Cargo",
      uf: "UF",
      orgao: "Órgão",
      situacao: "Situação",
      limit: "Limite máx.",
    };
    return Object.entries(filtros || {})
      .filter(([k]) => rotulos[k])
      .map(([k, v]) => `<span class="chip-filtro">${rotulos[k]}: ${escapar(v)}</span>`)
      .join("");
  }

  function montarHtmlFichaServidor(r) {
    const campos = [
      ["Nome completo", r.nome],
      ["Situação funcional", r.situacao],
      ["Cargo / Carreira", r.cargo || "Não informado"],
      ["Órgão / Instituição de lotação", r.orgao || "Não informado"],
      ["Unidade Federativa (UF)", r.uf ? `${r.uf}${r.uf_nome ? " — " + r.uf_nome : ""}` : "Não informado"],
      ["CPF (Mascarado)", r.cpf_mascarado || "Não informado"],
      ["Matrícula SIAPE", r.matricula || "Não informado"],
      ["Data de ingresso no serviço público", formatarData(r.data_ingresso)],
      ["Tipo de aposentadoria", r.tipo_aposentadoria || (r.situacao === "ATIVO" ? "Não aplicável (Servidor Ativo)" : "Não informado")],
      ["Data da aposentadoria", r.data_aposentadoria ? formatarData(r.data_aposentadoria) : (r.situacao === "ATIVO" ? "Não aplicável" : "Não informado")],
    ];

    if (r.similaridade != null) {
      campos.push(["Índice de similaridade (pg_trgm)", `${Math.round(r.similaridade * 100)}% (${r.similaridade})`]);
    }

    return `
      <div class="ficha-servidor">
        <div class="ficha-cabecalho">
          <div class="ficha-identificacao">
            <div class="ficha-iniciais" aria-hidden="true">${escapar(iniciais(r.nome))}</div>
            <div>
              <h3>${escapar(r.nome)}</h3>
              <span class="sub-doc mono">Registro ID #${escapar(r.id)} · Matrícula ${escapar(r.matricula || "—")}</span>
            </div>
          </div>
          <span class="badge-situacao ${escapar(r.situacao)}">${escapar(r.situacao)}</span>
        </div>
        <dl class="grade-ficha">
          ${campos
            .map(
              ([rotulo, valor]) => `
            <div class="item-ficha">
              <dt>${escapar(rotulo)}</dt>
              <dd>${escapar(valor)}</dd>
            </div>`
            )
            .join("")}
        </dl>
      </div>`;
  }

  function montarHtmlPaginacao(atual, totalPaginas) {
    const inicio = Math.max(1, Math.min(atual - 2, totalPaginas - 4));
    const fim = Math.min(totalPaginas, inicio + 4);

    let botoes = `
      <button type="button" class="btn-pag" data-pag="1" ${atual === 1 ? "disabled" : ""} aria-label="Primeira página">« Primeira</button>
      <button type="button" class="btn-pag" data-pag="${atual - 1}" ${atual === 1 ? "disabled" : ""} aria-label="Página anterior">‹ Anterior</button>`;

    for (let p = inicio; p <= fim; p++) {
      botoes += `<button type="button" class="btn-pag" data-pag="${p}" ${p === atual ? 'aria-current="page"' : ""} aria-label="Página ${p}">${p}</button>`;
    }

    botoes += `
      <button type="button" class="btn-pag" data-pag="${atual + 1}" ${atual === totalPaginas ? "disabled" : ""} aria-label="Próxima página">Próxima ›</button>
      <button type="button" class="btn-pag" data-pag="${totalPaginas}" ${atual === totalPaginas ? "disabled" : ""} aria-label="Última página">Última »</button>`;

    return `
      <nav class="barra-paginacao" aria-label="Paginação dos resultados">
        <div class="grupo-paginas">${botoes}</div>
        <form id="form-ir-pagina" class="form-pular-pagina">
          <label for="input-ir-pag">Página <strong>${atual}</strong> de <strong>${totalPaginas}</strong> · Ir para:</label>
          <input id="input-ir-pag" type="number" min="1" max="${totalPaginas}" value="${atual}">
          <button type="submit" class="btn-pag">Ir</button>
        </form>
      </nav>`;
  }

  function renderizarResultados(corpo, duracaoMs) {
    const painel = $("#painel-resultados");
    estado.ultimosResultados = corpo.resultados || [];

    const sufixoMais = corpo.total_exato ? "" : "+";
    const barraTopo = `
      <div class="resumo-barra">
        <div class="resumo-contagem">
          <strong>${Number(corpo.total).toLocaleString("pt-BR")}${sufixoMais}</strong>
          <span>${corpo.total === 1 ? "servidor encontrado" : "servidores encontrados"}</span>
          <span class="tempo-resposta">(${duracaoMs} ms)</span>
        </div>
        <div class="chips-ativos" aria-label="Filtros aplicados">${renderizarChipsFiltros(corpo.filtros)}</div>
      </div>`;

    // Requisito funcional 5: Caso exista apenas 1 resultado, apresentar seus dados completos diretamente
    if (corpo.total === 1 && corpo.registro) {
      painel.innerHTML = `${barraTopo}${montarHtmlFichaServidor(corpo.registro)}`;
      return;
    }

    const avisoTeto = corpo.total_exato
      ? ""
      : `<div class="aviso-teto" role="status">Consulta ampla: exibindo e paginando os primeiros ${Number(corpo.total).toLocaleString("pt-BR")} registros para preservar o tempo de resposta. Refine os filtros para resultados mais específicos.</div>`;

    const temSimilaridade = estado.ultimosResultados.some((r) => r.similaridade != null);

    const linhasHtml = estado.ultimosResultados
      .map((r, idx) => {
        const scoreHtml =
          temSimilaridade && r.similaridade != null
            ? `<span class="score-sim" title="Similaridade por trigramas">${Math.round(r.similaridade * 100)}%</span>`
            : "";
        return `
          <tr>
            <td class="celula-nome">
              ${escapar(r.nome)}${scoreHtml}
              <span class="sub-doc mono">CPF: ${escapar(r.cpf_mascarado || "—")} · Mat.: ${escapar(r.matricula || "—")}</span>
            </td>
            <td>${escapar(r.cargo || "—")}</td>
            <td>${escapar(r.orgao || "—")}</td>
            <td><span class="uf-pill" title="${escapar(r.uf_nome || "")}">${escapar(r.uf || "—")}</span></td>
            <td><span class="badge-situacao ${escapar(r.situacao)}">${escapar(r.situacao)}</span></td>
            <td>
              <button type="button" class="btn-detalhe" data-abrir-idx="${idx}" aria-label="Ver ficha completa de ${escapar(r.nome)}">
                Ver ficha
              </button>
            </td>
          </tr>`;
      })
      .join("");

    painel.innerHTML = `
      ${barraTopo}
      ${avisoTeto}
      <div class="tabela-container">
        <table>
          <thead>
            <tr>
              <th scope="col">Servidor / Identificação</th>
              <th scope="col">Cargo / Profissão</th>
              <th scope="col">Instituição / Órgão</th>
              <th scope="col">UF</th>
              <th scope="col">Situação</th>
              <th scope="col">Ação</th>
            </tr>
          </thead>
          <tbody>${linhasHtml}</tbody>
        </table>
      </div>
      ${montarHtmlPaginacao(corpo.pagina, corpo.total_paginas)}`;

    // Eventos de abertura da ficha modal
    $$("[data-abrir-idx]", painel).forEach((btn) => {
      btn.addEventListener("click", () => {
        const item = estado.ultimosResultados[Number(btn.dataset.abrirIdx)];
        if (item) abrirModal(item, btn);
      });
    });

    // Eventos de paginação
    $$(".btn-pag[data-pag]", painel).forEach((btn) => {
      btn.addEventListener("click", () => {
        const destino = Number(btn.dataset.pag);
        executarBusca(destino);
        painel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    const formIr = $("#form-ir-pagina", painel);
    formIr?.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const destino = Number($("#input-ir-pag", formIr).value);
      if (destino >= 1 && destino <= corpo.total_paginas) {
        executarBusca(destino);
      }
    });
  }

  function renderizarEstadoErro(err) {
    const painel = $("#painel-resultados");
    const status = err.status || 0;
    const codigo = err.codigo || "ERRO_CONSULTA";

    const titulos = {
      400: "Parâmetro de consulta inválido",
      404: "Nenhum registro encontrado",
      429: "Limite de requisições atingido (Proteção Anti-Sobrecarga)",
      503: "Servidor temporariamente ocupado",
      504: "Tempo limite da consulta excedido (Timeout de 5s)",
    };

    painel.innerHTML = `
      <div class="estado-erro" role="alert">
        <h2>${escapar(titulos[status] || "Não foi possível concluir a busca")}</h2>
        <p>${escapar(err.message || "Verifique os filtros informados e tente novamente.")}</p>
        <span class="codigo-erro-pill mono">Código: ${escapar(codigo)} · HTTP ${status || "REDE"}</span>
      </div>`;
  }

  // ---------------------------------------------------------------- Modal Acessível (Focus Trap)
  function abrirModal(registro, elementoGatilho) {
    estado.ultimoFocoModal = elementoGatilho || document.activeElement;
    $("#modal-titulo").textContent = registro.nome || "Ficha do Servidor";
    $("#modal-conteudo").innerHTML = montarHtmlFichaServidor(registro);
    const modal = $("#modal");
    modal.hidden = false;
    $("#btn-fechar-modal").focus();
  }

  function fecharModal() {
    const modal = $("#modal");
    if (modal.hidden) return;
    modal.hidden = true;
    estado.ultimoFocoModal?.focus?.();
  }

  // ---------------------------------------------------------------- Inicialização de Eventos
  $$(".aba[role='tab']").forEach((aba) => {
    aba.addEventListener("click", () => selecionarModo(aba.dataset.modo, true));
  });
  configurarTecladoAbas();

  $("#form-busca").addEventListener("input", atualizarPreviewEndpoint);
  $("#form-busca").addEventListener("change", atualizarPreviewEndpoint);

  $("#form-busca").addEventListener("submit", (ev) => {
    ev.preventDefault();
    limparErrosValidacao();

    if (estado.modo === "avancada" && $("#f-nome").value.trim() && $("#f-similar").value.trim()) {
      exibirErroValidacao("Informe apenas 'Nome completo (exato)' OU 'Padrão de similaridade', não ambos simultaneamente.", "similar");
      return;
    }

    const params = coletarParametrosFormulario();
    const temFiltro = ["nome", "similar", "cargo", "uf", "orgao"].some((k) => params[k]);
    if (!temFiltro) {
      const primeiroCampo = CAMPOS_POR_MODO[estado.modo][0];
      exibirErroValidacao("Preencha ao menos um critério de busca antes de consultar.", primeiroCampo);
      return;
    }

    estado.parametros = params;
    executarBusca(1);
  });

  $("#btn-limpar").addEventListener("click", () => {
    $("#form-busca").reset();
    limparErrosValidacao();
    estado.parametros = null;
    atualizarPreviewEndpoint();
    $("#painel-resultados").innerHTML = `
      <div class="estado-inicial">
        <div class="estado-icone" aria-hidden="true">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/><path d="M11 8v6"/></svg>
        </div>
        <h2>Filtros limpos</h2>
        <p>Informe um novo critério de busca acima ou utilize um dos botões de exemplo.</p>
      </div>`;
  });

  // Botões de exemplo rápido
  $$(".chip-exemplo").forEach((chip) => {
    chip.addEventListener("click", () => {
      $("#form-busca").reset();
      const modo = chip.dataset.exemplo;
      selecionarModo(modo, false);

      if (modo === "similar") {
        $("#f-similar").value = chip.dataset.valor || "%MARIA%SILVA%";
        $("#f-limit").value = chip.dataset.limit || "50";
      } else if (modo === "cargo") {
        $("#f-cargo").value = chip.dataset.valor || "PROFESSOR";
      } else if (modo === "uf") {
        $("#f-uf").value = chip.dataset.valor || "DF";
      } else if (modo === "avancada") {
        $("#f-cargo").value = chip.dataset.cargo || "";
        $("#f-uf").value = chip.dataset.uf || "";
        $("#f-situacao").value = chip.dataset.situacao || "";
      }

      estado.parametros = coletarParametrosFormulario();
      executarBusca(1);
    });
  });

  $("#btn-copiar-url").addEventListener("click", async () => {
    const urlTexto = window.location.origin + $("#url-api").textContent;
    try {
      await navigator.clipboard.writeText(urlTexto);
      const btn = $("#btn-copiar-url");
      const original = btn.textContent;
      btn.textContent = "Copiado!";
      setTimeout(() => {
        btn.textContent = original;
      }, 1500);
    } catch {
      /* fallback silencioso */
    }
  });

  $("#btn-fechar-modal").addEventListener("click", fecharModal);
  $("#modal").addEventListener("click", (ev) => {
    if (ev.target === $("#modal")) fecharModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") fecharModal();
  });

  // Inicialização
  inicializarTema();
  configurarAutocompletar($("#f-cargo"), $("#lista-cargos"), "/cargos");
  configurarAutocompletar($("#f-orgao"), $("#lista-orgaos"), "/orgaos");
  selecionarModo("nome", false);
  carregarUfs();
  verificarSaudeApi();
})();
