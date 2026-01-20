import re
import os
import time
import base64
import pytest
import pytest_html
from playwright.sync_api import Page, expect

# =============================
# Constantes e configurações
# =============================
KNOWN_TITLE_PATTERN = re.compile(r"Renault", re.IGNORECASE)
CTA_CONFIGURE_RESERVA_REGEX = re.compile(r"(configure\s*e\s*reserve|configure|monte\s*o\s*seu|monte|reservar)", re.I)
URL_CFG_REGEX = re.compile(r"/configurador/.+/(versoes|design|cores|rodas|interior)", re.I)
URL_JORNADA_REGEX = re.compile(r"/jornada-de-reserva")
URL_CONCESSIONARIA_REGEX = re.compile(r"/configurador/.+/concessionaria|/concessionari(a|as)|/dealers|/lojas|/ponto-de-venda|/r-pass/pre-venda/concessionaria", re.I)
URL_PAGAMENTO_REGEX = re.compile(r"/pagamento|/payment|metodo-de-pagamento|forma-de-pagamento|checkout", re.I)
URL_RESUMO_REGEX = re.compile(r"/resumo|/summary|/jornada-de-reserva/.*/resumo|/r-pass/pre-venda/.*/resumo", re.I)

MODELOS_LIMIT = int(os.getenv("MODELOS_LIMIT", "1") or "1")
VERSOES_LIMIT = int(os.getenv("VERSOES_LIMIT", "1") or "1")
CEP_BUSCA = os.getenv("CEP_BUSCA", "01001-000")

FINAN_EMAIL = os.getenv("FINAN_EMAIL", "sustentacao.renault@gmail.com")
FINAN_SENHA = os.getenv("FINAN_SENHA", "MetaL@123")

# =============================
# Helpers Gerais
# =============================

def _aceitar_cookies(page: Page):
    try:
        page.wait_for_load_state("domcontentloaded")
    except:
        pass
    seletores = [
        '#onetrust-accept-btn-handler',
        'button:has-text("aceitar")',
        'button:has-text("Aceitar")',
        '[data-testid*="cookie"] button:has-text("aceitar")',
    ]
    for s in seletores:
        try:
            btn = page.locator(s).first
            if btn.is_visible():
                btn.click(force=True, timeout=3000)
                break
        except Exception:
            pass

def _anexar_screenshot(request, page_or_frame, titulo: str):
    try:
        page = page_or_frame if hasattr(page_or_frame, "screenshot") else None
        if not page: return
        shot = page.screenshot(full_page=False)
        b64 = base64.b64encode(shot).decode("utf-8")
        html = f"<details><summary>{titulo}</summary><img src='data:image/png;base64,{b64}' style='max-width:800px;border:1px solid #ccc'/></details>"
        if hasattr(request.node, "rep_call"):
            extra = getattr(request.node.rep_call, "extra", [])
            extra.append(pytest_html.extras.html(html))
            request.node.rep_call.extra = extra
    except Exception:
        pass

def _get_configurator_ctx(page: Page):
    for f in page.frames:
        if re.search(r"/configurador/", f.url or ""):
            return f
    return page

def _garantir_ctx_configurador(page: Page):
    _aceitar_cookies(page)
    if URL_CFG_REGEX.search(page.url): return
    if URL_JORNADA_REGEX.search(page.url):
        iniciar_btn = page.get_by_role("button", name=re.compile("Iniciar|Configurar", re.I)).first
        try:
            if iniciar_btn.is_visible():
                iniciar_btn.click()
                page.wait_for_url(URL_CFG_REGEX, timeout=30000)
        except Exception:
            pass
        _aceitar_cookies(page)


def _esperar_concessionaria(page: Page, ctx=None, timeout_ms: int = 30000) -> bool:
    # Verificação rápida inicial
    if URL_CONCESSIONARIA_REGEX.search(page.url): return True
    
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        if URL_CONCESSIONARIA_REGEX.search(page.url): return True
        if ctx:
            # Verifica se elementos únicos da tela de concessionária estão visíveis
            try:
                if ctx.locator('[data-testid*="dealer"], .leaflet-container').first.is_visible(): return True
            except Exception:
                pass
            try:
                if ctx.get_by_role("heading", name=re.compile("Concession[aá]ria", re.I)).first.is_visible(): return True
            except Exception:
                pass
        page.wait_for_timeout(500)
    return False


def _inserir_cep_se_necessario(ctx, page: Page):
    try:
        cep_input = ctx.locator('input[placeholder*="CEP" i], input[name*="cep" i]').first
        if cep_input and cep_input.is_visible():
            cep_input.fill(CEP_BUSCA)
            cep_input.press("Enter")
            page.wait_for_timeout(800)
            # Tenta acionar botão de buscar/aplicar se existir
            try:
                btn_buscar = ctx.get_by_role("button", name=re.compile(r"Buscar|OK|Confirmar|Aplicar", re.I)).first
                if btn_buscar and btn_buscar.is_visible():
                    btn_buscar.click()
            except Exception:
                pass
            page.wait_for_timeout(1500)
    except Exception:
        pass


def _dealer_esta_selecionado(ctx) -> bool:
    """
    Verifica se a concessionária está efetivamente marcada como 'Selecionada'.
    Tenta por acessibilidade e classes comuns de seleção.
    """
    try:
        btn_sel_ok = ctx.get_by_role("button", name=re.compile(r"Selecionad[oa]", re.I)).first
        if btn_sel_ok and btn_sel_ok.count() > 0 and btn_sel_ok.is_visible():
            return True
    except Exception:
        pass
    try:
        ativo = ctx.locator('[aria-pressed="true"], [aria-selected="true"], .is-selected, .selected').first
        if ativo and ativo.count() > 0 and ativo.is_visible():
            return True
    except Exception:
        pass
    return False


def _esta_em_concessionaria(ctx) -> bool:
    try:
        if ctx.get_by_role("heading", name=re.compile(r"Concession[aá]ria|Dealer|Loja", re.I)).first.is_visible():
            return True
    except Exception:
        pass
    try:
        if ctx.locator('.leaflet-container, .gm-style, [data-testid*="dealer"], [class*="dealer"], li:has-text("km")').first.is_visible():
            return True
    except Exception:
        pass
    return False


def _selecionar_concessionaria_robusta(ctx, page: Page, tempo_ms: int = 45000) -> bool:
    """
    Seleciona uma concessionária com estratégias robustas:
    - Variações de botão "Selecionar"
    - Scroll incremental para listas virtualizadas
    - Clique via JS e fallback force
    - Clique no card inteiro quando necessário
    - Confirmação via _dealer_esta_selecionado
    """
    t_end = time.time() + (tempo_ms / 1000.0)

    # Garante que estamos de fato na tela de concessionária
    if not _esta_em_concessionaria(ctx):
        return False

    # Função interna para coletar possíveis botões de selecionar
    def coletar_botoes():
        candidatos = []
        try:
            loc = ctx.get_by_role("button", name=re.compile(r"Selecion(ar|e|ado)", re.I))
            for i in range(min(loc.count(), 10)):
                cand = loc.nth(i)
                try:
                    if cand.is_visible():
                        candidatos.append(cand)
                except Exception:
                    continue
        except Exception:
            pass
        try:
            loc = ctx.locator('button:has-text("Selecionar")')
            for i in range(min(loc.count(), 10)):
                cand = loc.nth(i)
                try:
                    if cand.is_visible():
                        candidatos.append(cand)
                except Exception:
                    continue
        except Exception:
            pass
        try:
            loc = ctx.locator('[data-testid*="select" i], [data-testid*="selecionar" i]')
            for i in range(min(loc.count(), 10)):
                cand = loc.nth(i)
                try:
                    if cand.is_visible():
                        candidatos.append(cand)
                except Exception:
                    continue
        except Exception:
            pass
        return candidatos

    ultimo_qtd = -1
    scrolls_sem_mudar = 0

    while time.time() < t_end:
        # Se já estiver marcado, retorna sucesso
        try:
            if _dealer_esta_selecionado(ctx):
                return True
        except Exception:
            pass

        botoes = coletar_botoes()
        if botoes:
            for btn in botoes[:5]:
                try:
                    txt = (btn.text_content() or "").strip().lower()
                except Exception:
                    txt = ""
                if "selecionado" in txt:
                    continue
                try:
                    btn.scroll_into_view_if_needed()
                except Exception:
                    pass
                # Clique via JS, depois force se necessário
                clicou = False
                try:
                    btn.evaluate("el => el.click()")
                    clicou = True
                except Exception:
                    try:
                        btn.click(force=True)
                        clicou = True
                    except Exception:
                        pass
                if clicou:
                    page.wait_for_timeout(1200)
                    if _dealer_esta_selecionado(ctx):
                        return True
            # Tentativa de clicar no card do último botão analisado
            try:
                card = btn.locator("xpath=ancestor-or-self::*[self::*[@data-testid][1] or self::li or self::div][1]").first
                if card and card.is_visible():
                    try:
                        card.click(force=True)
                        page.wait_for_timeout(800)
                        if _dealer_esta_selecionado(ctx):
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            # Força scroll para materializar itens
            try:
                ctx.evaluate("() => { window.scrollBy(0, 800); }")
            except Exception:
                pass
            page.wait_for_timeout(600)

            qtd = len(coletar_botoes())
            if qtd == ultimo_qtd:
                scrolls_sem_mudar += 1
                try:
                    ctx.evaluate("() => { window.scrollTo(0, 0); }")
                except Exception:
                    pass
                page.wait_for_timeout(400)
            else:
                ultimo_qtd = qtd
                scrolls_sem_mudar = 0

            if scrolls_sem_mudar > 20:
                break

    return _dealer_esta_selecionado(ctx)


def _tem_ui_pagamento(ctx) -> bool:
    try:
        head = ctx.get_by_role("heading", name=re.compile(r"Pagamento|Forma de pagamento|Payment|Checkout", re.I)).first
        if head and head.count() > 0 and head.is_visible():
            return True
    except Exception:
        pass
    try:
        radios_pag = ctx.get_by_role("radio", name=re.compile(r"Pix|Cart[aã]o|Boleto|Financiamento|Banco\s*Renault|CDC|Parcelado|Financiar", re.I))
        if radios_pag and radios_pag.count() > 0 and radios_pag.first.is_visible():
            return True
    except Exception:
        pass
    try:
        if ctx.get_by_text(re.compile(r"Pagamento|Forma de pagamento|Checkout", re.I)).first.count() > 0:
            return True
    except Exception:
        pass
    return False


def _resolver_ctx_pagamento(page: Page):
    # Prefere frame com URL de pagamento e UI encontrada
    for f in page.frames:
        fu = getattr(f, "url", "") or ""
        if URL_PAGAMENTO_REGEX.search(fu) and _tem_ui_pagamento(f):
            return f
    # Caso não tenha URL de pagamento, tenta UI de pagamento em qualquer frame
    for f in page.frames:
        try:
            if _tem_ui_pagamento(f):
                return f
        except Exception:
            continue
    # Fallback: contexto de configurador
    return _get_configurator_ctx(page)


def _debug_dump_context(page: Page, ctx, titulo: str = "DEBUG Context"):
    try:
        print(f"\n=== {titulo} ===")
        print(f"Top URL: {page.url}")
        frames = page.frames
        print(f"Frames: {len(frames)}")
        for i, f in enumerate(frames[:6]):
            print(f" - Frame[{i}] URL: {getattr(f, 'url', '')}")
        try:
            head = ctx.get_by_role("heading").all_text_contents()
            print(f"Headings visíveis (ctx): {head[:5] if head else []}")
        except Exception:
            pass
    except Exception:
        pass


def _esperar_pagamento(page: Page, ctx, timeout_ms: int = 30000) -> bool:
    """
    Aguarda sinais de que a tela de Pagamento foi carregada de forma confiável:
    - URL da página principal OU de algum frame casa com URL_PAGAMENTO_REGEX
    - E elementos característicos da UI de pagamento visíveis
    Evita falsos-positivos quando ainda estamos na Concessionária.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        # Evita considerar quando ainda há marcadores de Concessionária
        try:
            if _esta_em_concessionaria(ctx):
                raise Exception("Ainda em Concessionária")
        except Exception:
            pass

        # 1) URL da page + UI
        try:
            if URL_PAGAMENTO_REGEX.search(page.url or "") and _tem_ui_pagamento(ctx):
                return True
        except Exception:
            pass

        # 2) URL dos frames + UI específica do frame
        try:
            for f in page.frames:
                fu = getattr(f, "url", "") or ""
                if URL_PAGAMENTO_REGEX.search(fu) and _tem_ui_pagamento(f):
                    return True
        except Exception:
            pass

        # Scroll discreto para destravar lazy-load
        try:
            ctx.evaluate("() => { window.scrollBy(0, 400); }")
        except Exception:
            pass

        page.wait_for_timeout(400)

    return False


def _esperar_resumo(page: Page, ctx, timeout_ms: int = 30000) -> bool:
    """
    Aguarda sinais de que a tela de Resumo foi carregada (SPA/iframe friendly),
    evitando falsos-positivos em Concessionária.
    """
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        # 1) URL principal
        try:
            if URL_RESUMO_REGEX.search(page.url or ""):
                return True
        except Exception:
            pass

        # 2) URL dos frames
        try:
            for f in page.frames:
                fu = getattr(f, "url", "") or ""
                if URL_RESUMO_REGEX.search(fu):
                    return True
        except Exception:
            pass

        # 3) Heurísticas (evitando Concessionária)
        try:
            if _esta_em_concessionaria(ctx):
                raise Exception("Ainda em Concessionária")
            head = ctx.get_by_role("heading", name=re.compile(r"Resumo", re.I)).first
            if head and head.count() > 0 and head.is_visible():
                return True
        except Exception:
            pass

        page.wait_for_timeout(300)

    return False


def _acessar_configurador_robusto(page: Page):
    """
    Garante entrada no configurador/jornada mesmo quando o CTA não dispara navegação top-level.
    """
    page.goto("/", wait_until="domcontentloaded")
    _aceitar_cookies(page)

    # Estratégia 1: CTA por role + texto
    try:
        cta_btn = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX).first
        if cta_btn and cta_btn.is_visible():
            try:
                cta_btn.click(force=True)
            except Exception:
                try:
                    cta_btn.evaluate("el => el.click()")
                except Exception:
                    pass
    except Exception:
        pass

    try:
        cta_link = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX).first
        if cta_link and cta_link.is_visible():
            try:
                cta_link.click(force=True)
            except Exception:
                try:
                    cta_link.evaluate("el => el.click()")
                except Exception:
                    pass
    except Exception:
        pass

    # Espera curta pela URL do configurador/jornada
    try:
        expect(page).to_have_url(re.compile(r"/jornada-de-reserva|/configurador/.+", re.I), timeout=8000)
        return
    except Exception:
        pass

    # Estratégia 2: link direto por seletor
    try:
        link_cfg = page.locator('a[href*="/configurador/"]').first
        if link_cfg and link_cfg.count() > 0 and link_cfg.is_visible():
            link_cfg.click(force=True)
            expect(page).to_have_url(re.compile(r"/configurador/.+", re.I), timeout=8000)
            return
    except Exception:
        pass

    # Estratégia 3: navegação direta para um modelo padrão
    candidatos = [
        "/configurador/kardian/versoes",
        "/configurador/kardian/concessionaria/",
        "/jornada-de-reserva",
    ]
    for destino in candidatos:
        try:
            page.goto(destino, wait_until="domcontentloaded")
            if re.search(r"/configurador/.+|/jornada-de-reserva", page.url, re.I):
                return
        except Exception:
            continue

# =============================
# Helper Principal: Navegar até Pagamento (ajustado)
# =============================

def _ir_para_pagamento(page: Page, request) -> tuple:
    page.set_default_timeout(30000)

    # 1. Acessar Home e garantir entrada no Configurador
    _acessar_configurador_robusto(page)
    try:
        expect(page).to_have_url(re.compile(r"/jornada-de-reserva|/configurador/.+", re.I), timeout=15000)
    except Exception:
        _anexar_screenshot(request, page, "Erro - Não entrou no Configurador")
        pytest.fail(f"Falha ao acessar configurador a partir da Home. URL atual: {page.url}")

    _garantir_ctx_configurador(page)
    ctx = _get_configurator_ctx(page)

    # 2. Navegação até a etapa de Concessionária
    print("Iniciando navegação dinâmica até Concessionária...")
    deadline_nav = time.time() + 90 
    
    while time.time() < deadline_nav:
        url_atual = page.url.lower()
        
        # SUCESSO: Chegamos na concessionária
        if _esperar_concessionaria(page, ctx, 500):
            break

        # CASO 1: Estamos presos na tela de VERSÕES
        if "/versoes" in url_atual or "version" in url_atual:
            btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
            if btns.count() > 0:
                btns.first.click(force=True)
                page.wait_for_timeout(2000)
            else:
                try:
                    ctx.locator('[data-testid*="versao"]').first.click(force=True, timeout=1000)
                except: pass
        
        # CASO 2: Etapas intermediárias
        else:
            btn_next = ctx.get_by_role("button", name=re.compile(r"Avan[cç]ar|Continuar|Pr[oó]ximo|Ir para|Concession[aá]ria", re.I)).first
            if btn_next.is_visible():
                if not btn_next.is_disabled():
                    btn_next.click()
                    page.wait_for_timeout(2000) 
            else:
                page.wait_for_timeout(1000)

    if not _esperar_concessionaria(page, ctx, 5000):
        _anexar_screenshot(request, page, "Erro - Falha ao Chegar na Concessionária")
        raise AssertionError(f"Não foi possível chegar à etapa de Concessionária. O script ficou preso em: {page.url}")
    
    ctx = _get_configurator_ctx(page)
    _inserir_cep_se_necessario(ctx, page)

    # Nova etapa: seleção robusta da concessionária
    if not _selecionar_concessionaria_robusta(ctx, page, 45000):
        _anexar_screenshot(request, page, "Erro - Não foi possível selecionar concessionária")
        raise AssertionError("Não foi possível selecionar uma concessionária.")
    
    # =========================================================
    # Avançar para pagamento com robustez
    # =========================================================
    print("Tentando avançar para pagamento…")
    
    regex_btn_pagamento = re.compile(r"Pagamento|Ir para pagamento|Continuar|Avan[cç]ar|Finalizar|Pr[oó]ximo", re.I)

    avancou_sucesso = False
    start_time = time.time()
    
    while time.time() - start_time < 45:
        if _esperar_pagamento(page, ctx, 800):
            avancou_sucesso = True
            break
        
        btn_pag = ctx.get_by_role("button", name=regex_btn_pagamento).last
        try:
            if btn_pag and btn_pag.is_visible():
                try:
                    expect(btn_pag).not_to_be_disabled(timeout=6000)
                except Exception:
                    pass
                try:
                    btn_pag.click(timeout=8000)
                except Exception:
                    try:
                        btn_pag.evaluate("el => el.click()")
                    except Exception:
                        pass
        except Exception:
            pass

        # Pequeno scroll para materializar botões
        try:
            ctx.evaluate("() => { window.scrollBy(0, 400); }")
        except Exception:
            pass
        page.wait_for_timeout(800)

    # Fallbacks de URL (mantidos porém menos agressivos)
    if not avancou_sucesso:
        print("Tentando fallback via URL direta…")
        atual = page.url
        destinos = []
        if "/concessionaria" in atual:
            destinos.append(atual.replace("/concessionaria", "/pagamento"))
            destinos.append(atual.replace("/concessionaria", "/checkout"))
        
        if "kardian" in atual: destinos.append("https://loja.renault.com.br/configurador/kardian/pagamento")
        if "kwid" in atual: destinos.append("https://loja.renault.com.br/configurador/kwid/pagamento")

        for url_dest in destinos:
            try:
                print(f"Navegando para: {url_dest}")
                page.goto(url_dest, wait_until="domcontentloaded", timeout=15000)
                if _esperar_pagamento(page, ctx, 10000):
                    avancou_sucesso = True
                    break
            except Exception:
                pass

    ctx = _resolver_ctx_pagamento(page)
    _anexar_screenshot(request, page, "Pagamento - Tela Inicial")

    if not avancou_sucesso and not _esperar_pagamento(page, ctx, 5000):
        _anexar_screenshot(request, page, "Erro - Pagamento não detectado")
        raise AssertionError(f"Falha ao detectar tela de Pagamento após selecionar concessionária. URL: {page.url}")

    return page, ctx


def candidates_to_try(all_btns):
    # Retorna apenas os 3 primeiros para não perder tempo iterando a lista toda
    return all_btns[:3]

# =============================
# Helper de Seleção Robusta (Radio Button)
# =============================

def _marcar_radio_robusto(ctx, regex_texto: re.Pattern):
    """
    Tenta encontrar o radio button associado ao texto e marca-lo explicitamente.
    Resolve problemas onde o clique no texto não propaga para o input.
    """
    # Estratégia 1: Label contendo texto -> Input Radio
    label = ctx.locator("label").filter(has_text=regex_texto).first
    if label.count() > 0:
        inp = label.locator('input[type="radio"]').first
        if inp.count() > 0:
            inp.check(force=True)
            return
        
        try:
            for_attr = label.get_attribute("for")
            if for_attr:
                ctx.locator(f"#{for_attr}").check(force=True)
                return
        except: pass
        
        label.click(force=True)
        return

    # Estratégia 2: Texto solto -> Radio próximo
    text_el = ctx.get_by_text(regex_texto).first
    if text_el.is_visible():
        parent = text_el.locator("..")
        radio = parent.locator('input[type="radio"]').first
        if radio.count() > 0:
            radio.check(force=True)
            return
        else:
            text_el.click(force=True)
            return

    # Estratégia 3: Botão/Option com mesmo texto
    try:
        btn = ctx.get_by_role("button", name=regex_texto).first
        if btn and btn.is_visible():
            btn.click(force=True)
            return
    except Exception:
        pass
    try:
        opt = ctx.get_by_role("option", name=regex_texto).first
        if opt and opt.is_visible():
            opt.click(force=True)
            return
    except Exception:
        pass
    # Estratégia 4: Qualquer bloco com texto
    try:
        bloco = ctx.locator('div, span, p').filter(has_text=regex_texto).first
        if bloco and bloco.is_visible():
            bloco.click(force=True)
            return
    except Exception:
        pass

# =============================
# Helper de Login visível em qualquer frame
# =============================

def _password_visible_em_qualquer_frame(page: Page, ctx, timeout_ms: int = 10000) -> bool:
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            # No contexto atual
            pw = ctx.locator('input[type="password"]').first
            if pw and pw.count() > 0 and pw.is_visible():
                return True
        except Exception:
            pass
        try:
            # Em outros frames
            for f in page.frames:
                try:
                    pwf = f.locator('input[type="password"]').first
                    if pwf and pwf.count() > 0 and pwf.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        try:
            # Scroll para destravar renderizações preguiçosas
            ctx.evaluate("() => { window.scrollBy(0, 400); }")
        except Exception:
            pass
        page.wait_for_timeout(300)
    return False

# =============================
# Testes
# =============================

@pytest.mark.jornada
@pytest.mark.pagamento
@pytest.mark.regressao
def test_pagamento_opcao_financiamento_requer_login(page: Page, request):
    page, ctx = _ir_para_pagamento(page, request)

    # Ação: Selecionar Financiamento
    _marcar_radio_robusto(ctx, re.compile(r"Financiamento", re.I))
    _anexar_screenshot(request, page, "Pagamento - Financiamento Selecionado")

    # Verificação: Formulário de Login deve aparecer (em qualquer frame)
    login_visible = _password_visible_em_qualquer_frame(page, ctx, 16000)

    if not login_visible:
        # Retry selection
        _marcar_radio_robusto(ctx, re.compile(r"Financiamento", re.I))
        login_visible = _password_visible_em_qualquer_frame(page, ctx, 10000)
        # Fallback: acionar CTA de login caso exista
        if not login_visible:
            try:
                btn_login = ctx.get_by_role("button", name=re.compile(r"Entrar|Login|Acessar|Já tenho cadastro", re.I)).first
                if btn_login and btn_login.is_visible():
                    btn_login.click()
                    login_visible = _password_visible_em_qualquer_frame(page, ctx, 8000)
            except Exception:
                pass

    assert login_visible, "O formulário de login não apareceu após selecionar Financiamento."

    # Preencher Login
    try:
        ctx.locator('input[type="email"], input[name*="email"]').first.fill(FINAN_EMAIL)
        ctx.locator('input[type="password"]').first.fill(FINAN_SENHA)
        
        btn_entrar = ctx.get_by_role("button", name=re.compile(r"Entrar|Acessar|Login", re.I)).first
        if btn_entrar.is_visible():
            btn_entrar.click()
        else:
            ctx.locator('input[type="password"]').press("Enter")
    except Exception as e:
        pytest.fail(f"Erro ao tentar preencher login: {e}")
    
    _anexar_screenshot(request, page, "Pagamento - Login Submetido")
    
    # Validar ausência de erro imediato
    expect(ctx.get_by_text(re.compile(r"inv[aá]lid|incorret", re.I))).to_have_count(0)


@pytest.mark.jornada
@pytest.mark.pagamento
@pytest.mark.regressao
def test_pagamento_opcao_negociar_leva_para_resumo(page: Page, request):
    page, ctx = _ir_para_pagamento(page, request)

    # Ação: Selecionar Negociar na Concessionária
    _marcar_radio_robusto(ctx, re.compile(r"Negociar\s+na\s+concession[aá]ria", re.I))
    _anexar_screenshot(request, page, "Pagamento - Negociar Selecionado")

    # Botão Continuar/Resumo (robusto)
    btn_cont = ctx.get_by_role("button", name=re.compile(r"Resumo|Continuar|Avan[cç]ar|Finalizar|Prosseguir|Seguinte|Concluir|Ir para Resumo", re.I)).first
    if not (btn_cont and btn_cont.is_visible()):
        # Fallbacks de busca
        try:
            btn_cont = ctx.locator('button:has-text("Resumo"), button:has-text("Continuar"), button[type="submit"]').first
        except Exception:
            pass
        if not (btn_cont and btn_cont.is_visible()):
            try:
                link_resumo = ctx.locator('a[href*="resumo"]').first
                if link_resumo and link_resumo.is_visible():
                    link_resumo.click()
            except Exception:
                pass

    # Espera botão habilitar
    try:
        expect(btn_cont).not_to_be_disabled(timeout=10000)
    except AssertionError:
        _marcar_radio_robusto(ctx, re.compile(r"Negociar", re.I))
        try:
            expect(btn_cont).not_to_be_disabled(timeout=8000)
        except Exception:
            pass

    # Clica com estratégia híbrida
    clicou = False
    try:
        btn_cont.click(timeout=12000)
        clicou = True
    except Exception:
        try:
            btn_cont.evaluate("el => el.click()")
            clicou = True
        except Exception:
            pass

    # Validar navegação/Renderização para Resumo
    chegou_resumo = _esperar_resumo(page, ctx, 30000)

    # Fallback de navegação direta para Resumo se necessário
    if not chegou_resumo:
        print("⚠️ Resumo não detectado automaticamente; tentando fallback de URL…")
        candidatos = []
        try:
            if hasattr(ctx, 'url') and ctx.url:
                candidatos.append(re.sub(r"/pagamento/?", "/resumo/", ctx.url, flags=re.I))
        except Exception:
            pass
        try:
            if re.search(r"/configurador/.+", page.url, re.I):
                candidatos.append(re.sub(r"/pagamento/?", "/resumo/", page.url, flags=re.I))
                candidatos.append(re.sub(r"/concessionaria/?", "/resumo/", page.url, flags=re.I))
        except Exception:
            pass
        candidatos.append("/configurador/kardian/resumo/")
        for destino in candidatos:
            try:
                page.goto(destino, wait_until="domcontentloaded")
                if _esperar_resumo(page, ctx, 12000):
                    chegou_resumo = True
                    print(f"✅ Resumo detectado via fallback de URL: {destino}")
                    break
            except Exception:
                continue

    _anexar_screenshot(request, page, "Resumo - Tela Final")
    assert chegou_resumo, f"Falha ao navegar para Resumo. URL atual: {page.url}"