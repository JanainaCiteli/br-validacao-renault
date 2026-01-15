import re
import os
import time
import base64
import pytest
import pytest_html
from playwright.sync_api import Page, expect

# Padrões e URLs
KNOWN_TITLE_PATTERN = re.compile(r"Renault", re.IGNORECASE)
# Expandimos o regex para cobrir CTAs comuns da home
CTA_CONFIGURE_RESERVA_REGEX = re.compile(r"(configure\s*e\s*reserve|configure|monte\s*o\s*seu|monte|reservar)", re.I)
URL_CFG_REGEX = re.compile(r"/configurador/.+/(versoes|design|cores|rodas|interior)", re.I)
URL_VERSOES_REGEX = re.compile(r"/configurador/.+/versoes|/r-pass/pre-venda/configurador/.+/versoes")
URL_JORNADA_REGEX = re.compile(r"/jornada-de-reserva")
URL_CONCESSIONARIA_REGEX = re.compile(r"/concessionari(a|as)|/dealers|/lojas|/ponto-de-venda|/r-pass/pre-venda/concessionaria", re.I)

# Limites opcionais (0 = sem limite)
MODELOS_LIMIT = int(os.getenv("MODELOS_LIMIT", "0") or "0")
VERSOES_LIMIT = int(os.getenv("VERSOES_LIMIT", "0") or "0")
CORES_LIMIT = int(os.getenv("CORES_LIMIT", "0") or "0")
RODAS_LIMIT = int(os.getenv("RODAS_LIMIT", "0") or "0")
INTERIOR_LIMIT = int(os.getenv("INTERIOR_LIMIT", "0") or "0")


def _aceitar_cookies(page: Page):
    # Similar ao teste da HOME, com variações e fallback em iframes
    page.wait_for_load_state("domcontentloaded")
    seletores = [
        '#onetrust-accept-btn-handler',
        'button:has-text("aceitar")',
        'button:has-text("Aceitar")',
        'button:has-text("ACEITAR")',
        'role=button[name=/aceitar|accept|concordo|ok/i]',
        '.chakra-modal__content-container button:has-text("aceitar")',
        '[data-testid*="cookie"] button:has-text("aceitar")',
        '[aria-modal="true"] button:has-text("aceitar")',
    ]
    clicou = False
    for s in seletores:
        try:
            btn = page.locator(s).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(force=True, timeout=5000)
                clicou = True
                break
        except Exception:
            pass

    if not clicou:
        for frame in page.frames:
            try:
                fb = frame.get_by_role("button", name=re.compile("aceitar|accept|ok|concordo", re.I))
                if fb and fb.count() > 0:
                    b = fb.first
                    if b.is_visible():
                        b.click(timeout=5000)
                        break
            except Exception:
                pass

    # Persistência de consentimento
    try:
        page.evaluate("""() => {
            localStorage.setItem("cookie-consent", "true");
            localStorage.setItem("consentAccepted", "true");
        }""")
        page.context.add_cookies([{
            "name": "cookie-consent",
            "value": "true",
            "domain": "loja.renault.com.br",
            "path": "/",
            "expires": int(time.time()) + 31536000,
            "sameSite": "Lax",
            "httpOnly": False,
            "secure": True,
        }])
    except Exception:
        pass

    # Remove overlay residual, se necessário
    try:
        page.locator('#onetrust-accept-btn-handler').first.wait_for(state="detached", timeout=2500)
    except Exception:
        page.evaluate("""() => {
            const selectors = [
              '.chakra-modal__overlay',
              '.chakra-modal__content-container',
              '[role="dialog"]',
              '[aria-modal="true"]'
            ];
            selectors.forEach(sel => {
              document.querySelectorAll(sel).forEach(el => { try { el.remove(); } catch (e) {} });
            });
        }""")


def _carregar_toda_pagina(page: Page):
    """Rola a página (HOME) para disparar lazy-loading (igual ao teste da home)."""
    try:
        page.evaluate("window.scrollTo(0, 0)")
        altura_total = page.evaluate("() => document.body.scrollHeight")
        pos = 0
        while pos < altura_total:
            pos += 1200
            page.evaluate(f"window.scrollTo(0, {pos})")
            page.wait_for_timeout(250)
            altura_total = page.evaluate("() => document.body.scrollHeight")
    except Exception:
        pass


def _anexar_screenshot(request, page_or_frame, titulo: str):
    """Anexa screenshot ao relatório HTML."""
    try:
        # page_or_frame pode ser Page ou Frame; screenshot só existe em Page
        page = page_or_frame if hasattr(page_or_frame, "screenshot") else None
        if not page:
            return
        shot = page.screenshot(full_page=False)
        b64 = base64.b64encode(shot).decode("utf-8")
        html = f"<details><summary>{titulo}</summary><img src='data:image/png;base64,{b64}' style='max-width:640px;border:1px solid #ccc'/></details>"
        if hasattr(request.node, "rep_call"):
            extra = getattr(request.node.rep_call, "extra", [])
            extra.append(pytest_html.extras.html(html))
            request.node.rep_call.extra = extra
    except Exception:
        pass


def _get_configurator_ctx(page: Page):
    """
    Retorna o contexto do configurador: frame com /configurador/ quando existir; senão a própria page.
    """
    for f in page.frames:
        try:
            if re.search(r"/configurador/", f.url or ""):
                return f
        except Exception:
            pass
    return page


def _is_versoes_page(ctx) -> bool:
    try:
        return bool(re.search(r"/configurador/.+/versoes", getattr(ctx, "url", "") or "", re.I))
    except Exception:
        return False

# ==== Versões via COMBOBOX (ARIA) ====

def _combo_versao_info(ctx):
    """
    Retorna (combo, listbox_id) para o combobox 'Versão' quando existir.
    """
    try:
        combo = ctx.get_by_role("combobox", name=re.compile(r"Vers[aã]o", re.I)).first
        if combo and combo.count() > 0:
            el = combo.element_handle()
            if not el:
                return None, None
            cid = el.get_attribute("aria-controls")
            return combo, cid
    except Exception:
        pass
    return None, None


def _forcar_carregamento_imagens_lazy(ctx):
    """
    Replica a estratégia da HOME: força eager e recarrega imagens lazy.
    """
    try:
        ctx.evaluate(
            """
            (() => {
              document.querySelectorAll('img').forEach(img => {
                try {
                  img.loading = 'eager';
                  img.decoding = 'sync';
                  if ('fetchPriority' in img) img.fetchPriority = 'high';
                  const ds = img.getAttribute('data-src') || img.getAttribute('data-original');
                  if (ds && !img.getAttribute('src')) img.setAttribute('src', ds);
                  const src = img.getAttribute('src');
                  if (src) {
                    const u = new URL(src, window.location.href);
                    u.searchParams.set('_force', Date.now());
                    img.setAttribute('src', u.toString());
                  }
                } catch (e) {}
              });
            })()
            """
        )
    except Exception:
        pass


def _esperar_imagens_visiveis(ctx, contexto: str, timeout_ms: int = 12000):
    """
    Aguarda todas as imagens visíveis carregarem (complete && naturalWidth > 0).
    Para domínios 3dv.renault.com, usa timeout maior e faz um retry com cache-busting.
    """
    erros = []
    try:
        imgs = ctx.locator("img").all()
    except Exception:
        imgs = []

    for i, img in enumerate(imgs):
        try:
            if not img.is_visible():
                continue
            el = img.element_handle()
            if not el:
                continue
            # Scroll até a imagem
            try:
                ctx.evaluate("(el) => el.scrollIntoView({behavior:'auto', block:'center', inline:'center'})", el)
            except Exception:
                pass

            src = ""
            try:
                src = img.evaluate("node => node.src || ''") or ""
            except Exception:
                pass

            # Timeout por imagem
            is_3dv = "3dv.renault.com" in src
            per_timeout = 25000 if is_3dv else timeout_ms

            # Primeira tentativa
            try:
                ctx.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=el, timeout=per_timeout)
                continue
            except Exception:
                # Retry para 3dv: força cache-busting e tenta novamente
                if is_3dv:
                    try:
                        ctx.evaluate("""(el) => {
                          try {
                            const u = new URL(el.src, window.location.href);
                            u.searchParams.set('_retry', Date.now());
                            el.src = u.toString();
                          } catch (e) {}
                        }""", el)
                    except Exception:
                        pass
                    try:
                        ctx.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=el, timeout=per_timeout)
                        continue
                    except Exception:
                        try:
                            if hasattr(ctx, "wait_for_load_state"):
                                ctx.wait_for_load_state("networkidle", timeout=3000)
                        except Exception:
                            pass

            html_elemento = ""
            try:
                html_elemento = img.evaluate("node => node.outerHTML")
            except Exception:
                pass
            erros.append(f"IMG visível não carregou (timeout) | SRC: {src} | HTML: {html_elemento}")

        except Exception:
            pass

    assert len(erros) == 0, f"[{contexto}] Imagens visíveis com problema:\n" + "\n".join(erros)


def _validar_textos(ctx, contexto: str):
    """
    Valida textos “quebrados” com heurística segura:
    - Normaliza espaços e remove duplicidades
    - Ignora textos muito longos (ex.: avisos legais)
    - Detecta placeholders reais, encoding inválido e conteúdos não renderizados
    """
    textos_raw = []
    try:
        textos_raw = ctx.locator("h1,h2,h3,h4,h5,h6,button,a,p,span,li,div").all_text_contents()
    except Exception:
        pass

    # normaliza e dedup
    textos = []
    vistos = set()
    for t in textos_raw:
        if not t:
            continue
        s = " ".join(t.split())
        if s and s not in vistos:
            vistos.add(s)
            textos.append(s)

    # placeholders e problemas reais
    padrao_quebra = re.compile(
        r"(undefined|null|NaN|lorem ipsum|LOREM IPSUM|�|\{\{[^}]+\}\}|\[\[[^\]]+\]\])",
        re.I,
    )

    # Ignora textos muito longos (evita falso-positivos em Avisos legais, termos, etc.)
    ruins = [t for t in textos if padrao_quebra.search(t) and len(t) <= 300]

    assert len(ruins) == 0, f"[{contexto}] Textos quebrados/ruins identificados: {ruins[:5]}"


def _validar_valores(ctx, contexto: str):
    """
    Valida presença de valores/indicadores (ex.: 'R$' ou elementos de preço).
    """
    seletores = ["text=R$", ".price", "[class*=price]", ".valor", "[data-testid*=price]"]
    for sel in seletores:
        try:
            loc = ctx.locator(sel).first
            if loc and loc.count() > 0 and loc.is_visible():
                return
        except Exception:
            pass
    # Fallback: regex no body
    try:
        body = ctx.evaluate("() => document.body.innerText || ''")
        if re.search(r"R\$\s?\d", body):
            return
    except Exception:
        pass
    raise AssertionError(f"[{contexto}] Nenhum indicador de preço/valor encontrado.")


def _garantir_ctx_configurador(page: Page):
    """
    Garante que estamos em /configurador/... (versoes|design|cores|rodas|interior).
    Navega a partir da jornada se necessário.
    """
    _aceitar_cookies(page)
    if URL_CFG_REGEX.search(page.url):
        return
    if URL_JORNADA_REGEX.search(page.url):
        iniciar_btn = page.get_by_role("button", name=re.compile("Iniciar|Configurar", re.I)).first
        expect(iniciar_btn).to_be_visible(timeout=15000)
        iniciar_btn.click(timeout=8000)
        page.wait_for_url(URL_CFG_REGEX, timeout=30000)
        _aceitar_cookies(page)
        return
    page.wait_for_url(URL_CFG_REGEX, timeout=30000)
    _aceitar_cookies(page)


def _contar_versoes(page, ctx) -> int:
    """
    Conta versões disponíveis:
    - Se houver combobox 'Versão', conta options (mais fidedigno)
    - Caso contrário, se estiver na rota /versoes, conta botões/cards 'Configurar/Selecionar'
    - Fallback: 1 (versão default)
    """
    # Combobox tem prioridade quando existir
    combo, cid = _combo_versao_info(ctx)
    if combo:
        combo.click(timeout=6000)
        try:
            options = ctx.locator(f'#{cid} [role="option"]') if cid else ctx.locator('[role="listbox"] [role="option"]')
            qtd = options.count()
        finally:
            try:
                ctx.keyboard.press("Escape")
            except Exception:
                pass
        return qtd if qtd > 0 else 1

    # Página de versões: botões/cards 'Configurar/Selecionar'
    if _is_versoes_page(ctx):
        try:
            btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
            if btns.count() > 0:
                return btns.count()
        except Exception:
            pass
        try:
            cards = ctx.locator('[data-testid*="versao"], [data-testid*="version"], [class*="versao"], [class*="version"]')
            return max(cards.count(), 1)
        except Exception:
            pass

    return 1


def _selecionar_versao(page, ctx, idx: int):
    """
    Seleciona versão:
    - Preferência: combobox 'Versão'
    - Alternativa: botões/cards 'Configurar/Selecionar' na página /versoes
    - Se nada existir e idx==0: no-op (versão única)
    Após seleção via /versoes, aguarda navegação para /design|/cores|/rodas|/interior (não /versoes).
    """
    # 1) Combobox
    combo, cid = _combo_versao_info(ctx)
    if combo:
        combo.click(timeout=6000)
        options = ctx.locator(f'#{cid} [role="option"]') if cid else ctx.locator('[role="listbox"] [role="option"]')
        total = options.count()
        assert idx < total, f"Índice de versão inválido (combobox). total={total}, idx={idx}"
        options.nth(idx).click(timeout=8000)
        return

    # 2) Página /versoes: botões/cards
    if _is_versoes_page(ctx):
        btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
        total_btns = btns.count()
        if total_btns > idx:
            btns.nth(idx).click(timeout=10000)
            page.wait_for_url(re.compile(r"/configurador/.+/(design|cores|rodas|interior)", re.I), timeout=35000)
            return
        # Cards com botão interno
        cards = ctx.locator('[data-testid*="versao"], [data-testid*="version"], [class*="versao"], [class*="version"]')
        total_cards = cards.count()
        if total_cards > idx:
            interno = cards.nth(idx).locator('button, a, [role="button"]').first
            if interno and interno.count() > 0 and interno.is_visible():
                interno.click(timeout=10000)
            else:
                cards.nth(idx).click(timeout=10000)
            page.wait_for_url(re.compile(r"/configurador/.+/(design|cores|rodas|interior)", re.I), timeout=35000)
            return

    # 3) Única versão (default)
    assert idx == 0, "Índice de versão inválido."


def _ir_para_etapa(ctx, tipo: str):
    """
    Tenta focar a etapa (quando há abas/botões de navegação internos).
    tipo: cor | rodas | interior
    """
    mapa = {
        "cor": re.compile(r"Cor|Color", re.I),
        "rodas": re.compile(r"Roda(s)?|Wheel(s)?", re.I),
        "interior": re.compile(r"Interior|Revestimento|Upholstery|Acabamento", re.I),
    }
    alvo = mapa.get(tipo)
    if not alvo:
        return
    # tenta tabs
    try:
        tab = ctx.get_by_role("tab", name=alvo).first
        if tab and tab.count() > 0 and tab.is_visible():
            tab.click(timeout=5000)
            return
    except Exception:
        pass
    # tenta botões/links
    for role in ("button", "link"):
        try:
            comp = ctx.get_by_role(role, name=alvo).first
            if comp and comp.count() > 0 and comp.is_visible():
                comp.click(timeout=5000)
                return
        except Exception:
            pass
    # fallback: nada a fazer (alguns configuradores já exibem as opções sem abas)


def _coletar_opcoes(ctx, tipo: str):
    """
    Retorna Locator para opções do tipo.
    """
    seletores_map = {
        "cor": [
            '[data-testid*="color"] [role="radio"]',
            '[data-testid*="color"] button',
            '[aria-label*="cor"] [role="radio"]',
            '[aria-label*="color"] [role="radio"]',
            '[role="radiogroup"] [role="radio"]',  # fallback
        ],
        "rodas": [
            '[data-testid*="wheel"] [role="radio"]',
            '[data-testid*="wheel"] button',
            '[aria-label*="rodas"] [role="radio"]',
            '[aria-label*="wheel"] [role="radio"]',
            '[role="radiogroup"] [role="radio"]',
        ],
        "interior": [
            '[data-testid*="interior"] [role="radio"]',
            '[data-testid*="interior"] button',
            '[data-testid*="upholstery"] [role="radio"]',
            '[data-testid*="upholstery"] button',
            '[aria-label*="interior"] [role="radio"]',
            '[role="radiogroup"] [role="radio"]',
        ],
    }
    seletores = seletores_map.get(tipo, [])
    for sel in seletores:
        try:
            loc = ctx.locator(sel)
            if loc and loc.count() > 0:
                return loc
        except Exception:
            pass
    return ctx.locator('[role="radiogroup"] [role="radio"]')  # último fallback


def _selecionar_todas_opcoes(ctx, tipo: str, contexto: str, limit: int = 0):
    """
    Seleciona todas as opções do tipo (ou até o limite).
    Para cada seleção:
      - Aguarda imagens visíveis carregarem (HOME-like)
      - Valida textos e valores
    """
    _ir_para_etapa(ctx, tipo)
    loc = _coletar_opcoes(ctx, tipo)
    total = loc.count()
    if total == 0:
        # ausência de opções pode ser uma condição do veículo/versão
        print(f"[AVISO] Sem opções para '{tipo}' em {contexto}.")
        return

    alvo_total = total if limit == 0 else min(total, limit)

    for idx in range(alvo_total):
        # Recoleta a cada iteração para evitar stale references
        loc = _coletar_opcoes(ctx, tipo)
        if loc.count() <= idx:
            break
        btn = loc.nth(idx)
        try:
            if btn.is_visible():
                btn.click(force=True, timeout=8000)
                _forcar_carregamento_imagens_lazy(ctx)
                _esperar_imagens_visiveis(ctx, f"{contexto} | {tipo} idx={idx}")
                _validar_textos(ctx, f"{contexto} | {tipo} idx={idx}")
                _validar_valores(ctx, f"{contexto} | {tipo} idx={idx}")
        except Exception as e:
            raise AssertionError(f"[{contexto}] Falha ao selecionar {tipo} idx={idx}: {str(e)}")


def _clicar_avancar(ctx, contexto: str):
    """
    Clica em CTAs de avanço típicos.
    """
    nomes = re.compile(r"Avançar|Continuar|Prosseguir|Próximo|Seguir|Ir para|Concessionária", re.I)
    for by in ("button", "link"):
        try:
            alvo = ctx.get_by_role(by, name=nomes).first
            if alvo and alvo.count() > 0 and alvo.is_visible():
                alvo.click(timeout=12000)
                return
        except Exception:
            pass
    # fallback por texto
    try:
        ctx.get_by_text(nomes).first.click(timeout=10000)
    except Exception:
        raise AssertionError(f"[{contexto}] CTA de avanço não encontrado.")


def _esperar_concessionaria(page: Page, timeout_ms: int = 30000) -> bool:
    """
    Espera chegada à Concessionária por page.url ou algum frame com essa URL.
    """
    try:
        page.wait_for_url(URL_CONCESSIONARIA_REGEX, timeout=timeout_ms)
        return True
    except Exception:
        pass

    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        for f in page.frames:
            try:
                if URL_CONCESSIONARIA_REGEX.search(f.url or ""):
                    return True
            except Exception:
                pass
        page.wait_for_timeout(500)
    return False


@pytest.mark.smoke
@pytest.mark.jornada
def test_configuracao_veiculo_para_todos_modelos_e_versoes(page: Page, request):
    """
    - Home -> clicar 'configure e reserve' para cada modelo
    - Jornada/Config -> selecionar cada versão (combobox/cards ou default=1)
    - Para cada versão:
        * Cores: selecionar TODAS (ou LIMIT), validando textos, imagens, valores
        * Rodas: se houver mais de uma, selecionar TODAS (ou LIMIT), validando
        * Interior: selecionar TODOS (ou LIMIT), validando
      Em todas as etapas, aguardar imagens carregarem como no teste da HOME.
    - Ao final (após Interior), clicar avançar e validar chegada à página de Concessionária
    """
    page.set_default_timeout(25000)
    page.set_default_navigation_timeout(45000)

    # HOME
    page.goto("/", wait_until="domcontentloaded", timeout=35000)
    _aceitar_cookies(page)
    expect(page).to_have_title(KNOWN_TITLE_PATTERN)
    _carregar_toda_pagina(page)

    # Coleta CTAs 'configure e reserve'
    btns = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX)
    links = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX)
    total_ctas = btns.count() + links.count()
    if total_ctas == 0:
        total_ctas = page.get_by_text(CTA_CONFIGURE_RESERVA_REGEX).count()

    assert total_ctas > 0, "Nenhum CTA 'configure e reserve' encontrado na home."

    modelos_iter = total_ctas if MODELOS_LIMIT == 0 else min(total_ctas, MODELOS_LIMIT)

    erros = []
    sucessos = 0

    for m_idx in range(modelos_iter):
        try:
            # Garante HOME limpo por iteração
            page.goto("/", wait_until="domcontentloaded", timeout=35000)
            _aceitar_cookies(page)
            _carregar_toda_pagina(page)

            # Recoleta CTAs e seleciona alvo
            btns = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX)
            links = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX)

            if btns.count() > m_idx:
                target = btns.nth(m_idx)
            elif links.count() > (m_idx - btns.count()):
                target = links.nth(m_idx - btns.count())
            else:
                target = page.get_by_text(CTA_CONFIGURE_RESERVA_REGEX).nth(m_idx)

            # Clica e aguarda configurador/jornada
            target.scroll_into_view_if_needed()
            target.click(force=True, timeout=8000)
            page.wait_for_url(re.compile(r"/jornada-de-reserva|/configurador/.+"), timeout=35000)
            _garantir_ctx_configurador(page)

            # Contexto do configurador
            ctx = _get_configurator_ctx(page)
            _anexar_screenshot(request, page, f"Modelo #{m_idx} - Configurador")

            # Versões
            qtd_versoes = _contar_versoes(page, ctx)
            versoes_iter = qtd_versoes if VERSOES_LIMIT == 0 else min(qtd_versoes, VERSOES_LIMIT)

            for v_idx in range(versoes_iter):
                try:
                    # Guarda URL para retorno (se for Page)
                    versoes_url = page.url

                    # Seleciona a versão (no-op se só existir 1 e v_idx=0)
                    _selecionar_versao(page, ctx, v_idx)
                    # Dá um respiro para assets pesados (3D) começarem a baixar
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    # Aguarda imagens e validações iniciais
                    _forcar_carregamento_imagens_lazy(ctx)
                    _esperar_imagens_visiveis(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                    _validar_textos(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                    _validar_valores(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                    _anexar_screenshot(request, page, f"Modelo #{m_idx} - Versão #{v_idx} - Inicial")

                    # Cores (todas)
                    _selecionar_todas_opcoes(ctx, "cor", f"Modelo {m_idx} | Versão {v_idx}", CORES_LIMIT)

                    # Rodas (todas, se houver > 1)
                    loc_rodas = _coletar_opcoes(ctx, "rodas")
                    if loc_rodas and loc_rodas.count() > 1:
                        _selecionar_todas_opcoes(ctx, "rodas", f"Modelo {m_idx} | Versão {v_idx}", RODAS_LIMIT)
                    else:
                        print(f"[INFO] Rodas únicas ou não aplicáveis em Modelo {m_idx} | Versão {v_idx}")

                    # Interior (todas)
                    _selecionar_todas_opcoes(ctx, "interior", f"Modelo {m_idx} | Versão {v_idx}", INTERIOR_LIMIT)

                    # Avançar para Concessionária
                    _clicar_avancar(ctx, f"Modelo {m_idx} | Versão {v_idx} | Final")
                    assert _esperar_concessionaria(page, 35000), (
                        f"[MODELO {m_idx} | VERSÃO {v_idx}] Não chegou à página de concessionária. URL atual: {page.url}"
                    )
                    _anexar_screenshot(request, page, f"Modelo #{m_idx} - Versão #{v_idx} - Concessionária")

                    # Retorna para seleção de versões (se possível) ou volta para URL de versões/design
                    try:
                        voltar = page.get_by_role("link", name=re.compile(r"Vers(ões|oes)|Voltar", re.I)).first
                        if voltar and voltar.count() > 0 and voltar.is_visible():
                            voltar.click(timeout=8000)
                            page.wait_for_url(URL_VERSOES_REGEX, timeout=30000)
                        else:
                            page.goto(versoes_url, wait_until="domcontentloaded", timeout=35000)
                    except Exception:
                        page.goto(versoes_url, wait_until="domcontentloaded", timeout=35000)

                    sucessos += 1
                    print(f"[OK] Modelo {m_idx} | Versão {v_idx} configurada (cores/rodas/interior) e navegou à concessionária.")

                except Exception as e:
                    _anexar_screenshot(request, page, f"Erro - Modelo #{m_idx} | Versão #{v_idx}")
                    erros.append(f"[MODELO {m_idx} | VERSÃO {v_idx}] {str(e)}")

        except Exception as e:
            _anexar_screenshot(request, page, f"Erro - Modelo #{m_idx}")
            erros.append(f"[MODELO {m_idx}] {str(e)}")

    msg = f"Sucessos: {sucessos} | Erros: {len(erros)}" + ("\n" + "\n".join(erros) if erros else "")
    assert len(erros) == 0, msg
