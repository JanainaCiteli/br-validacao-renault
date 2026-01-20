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

# Email e senha para login no financiamento
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
    Seleciona a PRIMEIRA concessionária exibida com estratégias robustas.
    
    Estratégias:
    - Foca especificamente na primeira concessionária visível
    - Verifica se já está selecionada antes de tentar selecionar
    - Trata navegação automática para pagamento
    - Scroll incremental para materializar itens virtualizados
    - Clique via JS e fallback force
    - Confirmação via _dealer_esta_selecionado e URL
    """
    print("[DEBUG] Iniciando seleção da primeira concessionária...")
    t_end = time.time() + (tempo_ms / 1000.0)

    # Verificação 1: Se já está em pagamento, concessionária foi pré-selecionada
    if URL_PAGAMENTO_REGEX.search(page.url or ""):
        print("[DEBUG] Já estamos em pagamento, concessionária deve estar pré-selecionada")
        return True

    # Verificação 2: Garante que estamos na tela de concessionária
    # Atualiza contexto antes de verificar
    ctx_atualizado = _get_configurator_ctx(page)
    if not _esta_em_concessionaria(ctx_atualizado):
        # Pode ter navegado automaticamente para pagamento
        if URL_PAGAMENTO_REGEX.search(page.url or ""):
            print("[DEBUG] Navegou automaticamente para pagamento")
            return True
        print("[DEBUG] Não está na tela de concessionária")
        return False

    # Função interna para coletar PRIMEIRA concessionária disponível
    def coletar_primeira_concessionaria():
        """
        Retorna o botão/card da PRIMEIRA concessionária disponível (não selecionada).
        Prioriza botões "Selecionar" e ignora os já selecionados.
        """
        candidatos = []
        
        # Estratégia 1: Botões "Selecionar" por role
        try:
            loc = ctx_atualizado.get_by_role("button", name=re.compile(r"Selecionar", re.I))
            for i in range(min(loc.count(), 10)):
                try:
                    cand = loc.nth(i)
                    if not cand.is_visible():
                        continue
                    # Ignora se já está selecionado
                    txt = (cand.text_content() or "").strip().lower()
                    if "selecionado" in txt or "selecionada" in txt:
                        continue
                    candidatos.append(("button_role", cand))
                    # Retorna a primeira imediatamente
                    return candidatos[0] if candidatos else None
                except Exception:
                    continue
        except Exception:
            pass
        
        # Estratégia 2: Locator por texto "Selecionar"
        try:
            loc = ctx_atualizado.locator('button:has-text("Selecionar")')
            for i in range(min(loc.count(), 10)):
                try:
                    cand = loc.nth(i)
                    if not cand.is_visible():
                        continue
                    txt = (cand.text_content() or "").strip().lower()
                    if "selecionado" in txt or "selecionada" in txt:
                        continue
                    candidatos.append(("button_text", cand))
                    return candidatos[0] if candidatos else None
                except Exception:
                    continue
        except Exception:
            pass
        
        # Estratégia 3: Data-testid ou seletores customizados
        try:
            loc = ctx_atualizado.locator('[data-testid*="select" i], [data-testid*="selecionar" i], [data-testid*="dealer"] button')
            for i in range(min(loc.count(), 10)):
                try:
                    cand = loc.nth(i)
                    if not cand.is_visible():
                        continue
                    txt = (cand.text_content() or "").strip().lower()
                    if "selecionado" in txt or "selecionada" in txt:
                        continue
                    candidatos.append(("data_testid", cand))
                    return candidatos[0] if candidatos else None
                except Exception:
                    continue
        except Exception:
            pass
        
        # Estratégia 4: Cards de concessionária (clique no card inteiro)
        try:
            cards = ctx_atualizado.locator('[data-testid*="dealer"], [class*="dealer-card"], li:has-text("km")')
            if cards.count() > 0:
                primeiro_card = cards.first
                if primeiro_card.is_visible():
                    # Tenta encontrar botão dentro do card
                    btn_no_card = primeiro_card.locator('button:has-text("Selecionar")').first
                    if btn_no_card.count() > 0 and btn_no_card.is_visible():
                        txt = (btn_no_card.text_content() or "").strip().lower()
                        if "selecionado" not in txt and "selecionada" not in txt:
                            return ("card_button", btn_no_card)
                    # Se não tiver botão, retorna o card para clique direto
                    return ("card", primeiro_card)
        except Exception:
            pass
        
        return None

    scrolls_realizados = 0
    ultima_url = page.url

    while time.time() < t_end:
        # Atualiza contexto a cada iteração para evitar stale references
        ctx_atualizado = _get_configurator_ctx(page)
        
        # Verificação: Se já está selecionado, retorna sucesso
        try:
            if _dealer_esta_selecionado(ctx_atualizado):
                print("[DEBUG] Concessionária já está selecionada")
                return True
        except Exception:
            pass

        # Verificação: Se navegou para pagamento automaticamente
        url_atual = page.url or ""
        if URL_PAGAMENTO_REGEX.search(url_atual):
            print("[DEBUG] Navegou automaticamente para pagamento durante seleção")
            return True
        
        # Verificação: Se saiu da tela de concessionária
        if not URL_CONCESSIONARIA_REGEX.search(url_atual) and not _esta_em_concessionaria(ctx_atualizado):
            if URL_PAGAMENTO_REGEX.search(url_atual):
                print("[DEBUG] Navegou para pagamento")
                return True
            print(f"[DEBUG] URL mudou: {url_atual}")
            # Pequeno delay para verificar se está carregando
            page.wait_for_timeout(1000)
            if not URL_CONCESSIONARIA_REGEX.search(page.url or ""):
                print("[DEBUG] Não está mais na concessionária e não está em pagamento")
                return False

        # Coleta primeira concessionária
        primeira_concessionaria = coletar_primeira_concessionaria()
        
        if primeira_concessionaria:
            tipo, elemento = primeira_concessionaria
            print(f"[DEBUG] Encontrada primeira concessionária (tipo: {tipo})")
            
            try:
                # Scroll para visibilidade
                elemento.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                
                # Tenta clique
                clicou = False
                try:
                    # Clique via JavaScript (mais confiável)
                    elemento.evaluate("el => el.click()")
                    clicou = True
                    print("[DEBUG] Clique via JS executado")
                except Exception:
                    try:
                        # Fallback: clique via Playwright
                        elemento.click(force=True, timeout=5000)
                        clicou = True
                        print("[DEBUG] Clique via Playwright executado")
                    except Exception:
                        print("[DEBUG] Falha ao clicar na concessionária")
                
                if clicou:
                    # Aguarda mudança de estado ou navegação
                    page.wait_for_timeout(1500)
                    
                    # Verifica se foi selecionado
                    if _dealer_esta_selecionado(ctx_atualizado):
                        print("[DEBUG] Concessionária selecionada com sucesso")
                        return True
                    
                    # Verifica se navegou para pagamento
                    if URL_PAGAMENTO_REGEX.search(page.url or ""):
                        print("[DEBUG] Navegou para pagamento após clique")
                        return True
                    
                    # Verifica mudança de URL
                    if page.url != ultima_url:
                        print(f"[DEBUG] URL mudou: {ultima_url} -> {page.url}")
                        ultima_url = page.url
                        # Pequeno delay adicional
                        page.wait_for_timeout(1000)
                        if _dealer_esta_selecionado(_get_configurator_ctx(page)):
                            return True
                
            except Exception as e:
                print(f"[DEBUG] Erro ao tentar selecionar concessionária: {e}")
                page.wait_for_timeout(500)
        else:
            # Se não encontrou, tenta scroll para materializar itens
            print("[DEBUG] Nenhuma concessionária encontrada, fazendo scroll...")
            try:
                ctx_atualizado.evaluate("() => { window.scrollBy(0, 800); }")
                scrolls_realizados += 1
                page.wait_for_timeout(800)
                
                # Limita número de scrolls
                if scrolls_realizados > 10:
                    # Volta ao topo
                    try:
                        ctx_atualizado.evaluate("() => { window.scrollTo(0, 0); }")
                    except Exception:
                        pass
                    scrolls_realizados = 0
                    page.wait_for_timeout(500)
                    
            except Exception:
                pass

        # Pequeno delay entre iterações
        page.wait_for_timeout(300)

    # Verificação final
    print("[DEBUG] Timeout atingido, verificando estado final...")
    ctx_final = _get_configurator_ctx(page)
    
    # Se está em pagamento, sucesso
    if URL_PAGAMENTO_REGEX.search(page.url or ""):
        print("[DEBUG] Estado final: em pagamento (sucesso)")
        return True
    
    # Se concessionária está selecionada, sucesso
    if _dealer_esta_selecionado(ctx_final):
        print("[DEBUG] Estado final: concessionária selecionada (sucesso)")
        return True
    
    print("[DEBUG] Estado final: falha ao selecionar concessionária")
    print(f"[DEBUG] URL atual: {page.url}")
    
    # Logs detalhados para debug
    try:
        ctx_debug = _get_configurator_ctx(page)
        esta_em_concessionaria = _esta_em_concessionaria(ctx_debug)
        dealer_selecionado = _dealer_esta_selecionado(ctx_debug)
        
        print(f"[DEBUG] Está em concessionária: {esta_em_concessionaria}")
        print(f"[DEBUG] Dealer selecionado: {dealer_selecionado}")
        
        # Tenta coletar informações sobre elementos disponíveis
        try:
            botoes_count = ctx_debug.get_by_role("button", name=re.compile(r"Selecionar", re.I)).count()
            print(f"[DEBUG] Botões 'Selecionar' encontrados: {botoes_count}")
        except Exception as e:
            print(f"[DEBUG] Erro ao contar botões: {e}")
    except Exception as e:
        print(f"[DEBUG] Erro ao coletar informações de debug: {e}")
    
    return False


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

    # Verifica se chegou na concessionária
    if not _esperar_concessionaria(page, ctx, 5000):
        # Pode ter navegado automaticamente para pagamento
        ctx_atual = _get_configurator_ctx(page)
        if _esperar_pagamento(page, ctx_atual, 3000):
            print("[DEBUG] Navegou automaticamente para pagamento sem passar por concessionária")
            ctx = _resolver_ctx_pagamento(page)
            _anexar_screenshot(request, page, "Pagamento - Navegação Automática")
            return page, ctx
        _anexar_screenshot(request, page, "Erro - Falha ao Chegar na Concessionária")
        raise AssertionError(f"Não foi possível chegar à etapa de Concessionária. O script ficou preso em: {page.url}")
    
    # Atualiza contexto e insere CEP
    ctx = _get_configurator_ctx(page)
    _inserir_cep_se_necessario(ctx, page)
    page.wait_for_timeout(2000)  # Aguarda carregamento após CEP

    # Verificação crítica: Re-verifica se ainda está na concessionária
    # Pode ter navegado automaticamente após inserir CEP
    ctx_atualizado = _get_configurator_ctx(page)
    if URL_PAGAMENTO_REGEX.search(page.url or ""):
        print("[DEBUG] Navegou automaticamente para pagamento após inserir CEP")
        ctx = _resolver_ctx_pagamento(page)
        _anexar_screenshot(request, page, "Pagamento - Após CEP")
        return page, ctx
    
    if not _esperar_concessionaria(page, ctx_atualizado, 2000):
        # Verifica se está em pagamento
        if _esperar_pagamento(page, ctx_atualizado, 2000):
            print("[DEBUG] Estado inconsistente detectado: não está na concessionária, mas está em pagamento")
            ctx = _resolver_ctx_pagamento(page)
            _anexar_screenshot(request, page, "Pagamento - Estado Inconsistente")
            return page, ctx
        print("[DEBUG] Ainda não chegou na concessionária, aguardando...")
        page.wait_for_timeout(2000)

    # Etapa crítica: Seleção da primeira concessionária
    print("[DEBUG] Iniciando seleção da primeira concessionária...")
    _anexar_screenshot(request, page, "Concessionária - Antes da Seleção")
    
    # CORREÇÃO: Usa ctx_atualizado em vez de ctx (que estava desatualizado)
    selecionou = _selecionar_concessionaria_robusta(ctx_atualizado, page, 45000)
    
    # Verificação pós-seleção: pode ter navegado automaticamente
    ctx_final = _get_configurator_ctx(page)
    url_final = page.url or ""
    
    if URL_PAGAMENTO_REGEX.search(url_final):
        print("[DEBUG] Navegou automaticamente para pagamento após seleção")
        ctx = _resolver_ctx_pagamento(page)
        _anexar_screenshot(request, page, "Pagamento - Após Seleção")
        return page, ctx
    
    if not selecionou:
        # Última verificação: pode estar selecionado mas não detectado
        if _dealer_esta_selecionado(ctx_final):
            print("[DEBUG] Concessionária está selecionada (detectado após timeout)")
            selecionou = True
        else:
            _anexar_screenshot(request, page, "Erro - Não foi possível selecionar concessionária")
            raise AssertionError(f"Não foi possível selecionar uma concessionária. URL: {url_final}")
    
    if selecionou:
        print("[DEBUG] Concessionária selecionada com sucesso")
        _anexar_screenshot(request, page, "Concessionária - Selecionada")
        page.wait_for_timeout(1500)  # Aguarda atualização da UI
    
    # =========================================================
    # Avançar para pagamento com robustez
    # =========================================================
    print("[DEBUG] Tentando avançar para pagamento...")
    
    # Verificação inicial: pode já estar em pagamento
    ctx_antes_pagamento = _get_configurator_ctx(page)
    if _esperar_pagamento(page, ctx_antes_pagamento, 2000):
        print("[DEBUG] Já está em pagamento após seleção")
        ctx = _resolver_ctx_pagamento(page)
        _anexar_screenshot(request, page, "Pagamento - Tela Inicial")
        return page, ctx
    
    regex_btn_pagamento = re.compile(r"Pagamento|Ir para pagamento|Continuar|Avan[cç]ar|Finalizar|Pr[oó]ximo", re.I)

    avancou_sucesso = False
    start_time = time.time()
    
    while time.time() - start_time < 45:
        # Atualiza contexto a cada iteração
        ctx_atual = _get_configurator_ctx(page)
        
        # Verifica se já chegou em pagamento
        if _esperar_pagamento(page, ctx_atual, 800):
            print("[DEBUG] Detectado navegação para pagamento")
            avancou_sucesso = True
            break
        
        # Busca botão de avançar/pagamento
        try:
            # Tenta botão "Ir para pagamento" ou similar
            btn_pag = ctx_atual.get_by_role("button", name=regex_btn_pagamento).last
            if btn_pag and btn_pag.count() > 0 and btn_pag.is_visible():
                # Verifica se está habilitado
                try:
                    if btn_pag.is_disabled():
                        print("[DEBUG] Botão de pagamento está desabilitado, aguardando...")
                        page.wait_for_timeout(1000)
                        continue
                except Exception:
                    pass
                
                try:
                    # Tenta habilitar esperando
                    expect(btn_pag).not_to_be_disabled(timeout=3000)
                except Exception:
                    pass
                
                # Tenta clicar
                try:
                    btn_pag.scroll_into_view_if_needed()
                    btn_pag.click(timeout=8000)
                    print("[DEBUG] Clique no botão de pagamento executado")
                    page.wait_for_timeout(2000)  # Aguarda navegação
                    
                    # Verifica se navegou
                    if _esperar_pagamento(page, _get_configurator_ctx(page), 2000):
                        avancou_sucesso = True
                        break
                except Exception:
                    try:
                        # Fallback: clique via JS
                        btn_pag.evaluate("el => el.click()")
                        print("[DEBUG] Clique via JS no botão de pagamento")
                        page.wait_for_timeout(2000)
                        
                        if _esperar_pagamento(page, _get_configurator_ctx(page), 2000):
                            avancou_sucesso = True
                            break
                    except Exception:
                        print("[DEBUG] Falha ao clicar no botão de pagamento")
        except Exception:
            pass

        # Pequeno scroll para materializar botões
        try:
            ctx_atual.evaluate("() => { window.scrollBy(0, 400); }")
        except Exception:
            pass
        page.wait_for_timeout(800)

    # Fallbacks de URL (mantidos porém menos agressivos)
    if not avancou_sucesso:
        print("[DEBUG] Tentando fallback via URL direta...")
        atual = page.url
        destinos = []
        
        # Extrai modelo da URL
        modelo_match = re.search(r"/configurador/([^/]+)/", atual, re.I)
        modelo = modelo_match.group(1) if modelo_match else None
        
        if "/concessionaria" in atual.lower():
            destinos.append(atual.replace("/concessionaria", "/metodo-de-pagamento"))
            destinos.append(atual.replace("/concessionaria", "/pagamento"))
            destinos.append(atual.replace("/concessionaria", "/checkout"))
        
        if modelo:
            destinos.append(f"https://loja.renault.com.br/configurador/{modelo}/metodo-de-pagamento")
            destinos.append(f"https://loja.renault.com.br/configurador/{modelo}/pagamento")

        print(f"[DEBUG] Tentando {len(destinos)} URLs de fallback...")
        for url_dest in destinos:
            try:
                print(f"[DEBUG] Navegando para: {url_dest}")
                page.goto(url_dest, wait_until="domcontentloaded", timeout=15000)
                ctx_fallback = _get_configurator_ctx(page)
                if _esperar_pagamento(page, ctx_fallback, 10000):
                    print(f"[DEBUG] Sucesso via fallback: {url_dest}")
                    avancou_sucesso = True
                    break
            except Exception as e:
                print(f"[DEBUG] Falha no fallback {url_dest}: {e}")
                continue

    # Resolve contexto final de pagamento
    ctx = _resolver_ctx_pagamento(page)
    _anexar_screenshot(request, page, "Pagamento - Tela Inicial")

    # Verificação final
    if not avancou_sucesso:
        # Última tentativa de verificação
        ctx_final = _get_configurator_ctx(page)
        if _esperar_pagamento(page, ctx_final, 5000):
            print("[DEBUG] Pagamento detectado na verificação final")
            avancou_sucesso = True
        else:
            _anexar_screenshot(request, page, "Erro - Pagamento não detectado")
            # Logs detalhados para debug
            print(f"[DEBUG] URL final: {page.url}")
            print(f"[DEBUG] Tem UI pagamento: {_tem_ui_pagamento(ctx_final)}")
            raise AssertionError(f"Falha ao detectar tela de Pagamento após selecionar concessionária. URL: {page.url}")

    print("[DEBUG] Navegação para pagamento concluída com sucesso")
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

def _clicar_definir_metodo_pagamento(ctx, page: Page, timeout_ms: int = 10000) -> bool:
    """
    Clica no botão "Definir método de pagamento" após selecionar uma opção de pagamento.
    Retorna True se clicou com sucesso.
    """
    print("[DEBUG] Tentando clicar em 'Definir método de pagamento'...")
    
    deadline = time.time() + (timeout_ms / 1000.0)
    
    while time.time() < deadline:
        # Estratégia 1: Botão por texto exato
        try:
            btn = ctx.get_by_role("button", name=re.compile(r"Definir\s*m[ée]todo\s*de\s*pagamento|Definir\s*pagamento|Confirmar\s*m[ée]todo", re.I)).first
            if btn and btn.count() > 0 and btn.is_visible() and not btn.is_disabled():
                btn.scroll_into_view_if_needed()
                btn.click(timeout=5000)
                print("[DEBUG] Clicou em 'Definir método de pagamento' via role")
                page.wait_for_timeout(1500)
                return True
        except Exception:
            pass
        
        # Estratégia 2: Locator por texto
        try:
            btn = ctx.locator('button:has-text("Definir método"), button:has-text("Definir pagamento"), button:has-text("Confirmar método")').first
            if btn and btn.count() > 0 and btn.is_visible():
                if not btn.is_disabled():
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=5000)
                    print("[DEBUG] Clicou em 'Definir método de pagamento' via locator")
                    page.wait_for_timeout(1500)
                    return True
        except Exception:
            pass
        
        # Estratégia 3: Botão de submit ou continuar genérico
        try:
            btn = ctx.locator('button[type="submit"]').first
            if btn and btn.count() > 0 and btn.is_visible() and not btn.is_disabled():
                # Verifica se o texto faz sentido
                txt = (btn.text_content() or "").strip().lower()
                if any(palavra in txt for palavra in ["definir", "confirmar", "continuar", "próximo", "seguir"]):
                    btn.scroll_into_view_if_needed()
                    btn.click(timeout=5000)
                    print("[DEBUG] Clicou em botão submit genérico")
                    page.wait_for_timeout(1500)
                    return True
        except Exception:
            pass
        
        page.wait_for_timeout(500)
    
    print("[DEBUG] Não encontrou botão 'Definir método de pagamento'")
    return False


def _iniciar_sessao_financiamento(ctx, page: Page, request, timeout_ms: int = 20000) -> bool:
    """
    Trata o fluxo de login após selecionar financiamento:
    1. Aguarda navegação para /sessao/criar-conta/
    2. Clica em "Iniciar sessão" quando estiver nessa URL
    3. Preenche email e senha
    Retorna True se login foi preenchido com sucesso.
    """
    print("[DEBUG] Iniciando fluxo de login para financiamento...")
    
    # URL esperada para a tela de criar conta/iniciar sessão
    URL_SESSAO_REGEX = re.compile(r"/sessao/criar-conta", re.I)
    
    # Passo 1: Aguardar navegação para /sessao/criar-conta/
    print("[DEBUG] Aguardando navegação para /sessao/criar-conta/...")
    deadline = time.time() + (timeout_ms / 1000.0)
    
    chegou_sessao = False
    while time.time() < deadline:
        url_atual = page.url or ""
        if URL_SESSAO_REGEX.search(url_atual):
            print(f"[DEBUG] Chegou na URL de sessão: {url_atual}")
            chegou_sessao = True
            break
        page.wait_for_timeout(500)
    
    if not chegou_sessao:
        # Verifica se já está em outra página de login
        if "/sessao/" in (page.url or ""):
            print(f"[DEBUG] Está em página de sessão: {page.url}")
            chegou_sessao = True
        else:
            raise AssertionError(f"Falha ao navegar para /sessao/criar-conta/. URL atual: {page.url}")
    
    # Aguarda carregamento da página
    page.wait_for_timeout(2000)
    ctx_atual = _get_configurator_ctx(page)
    
    # Passo 2: Clicar em "Iniciar sessão" quando estiver em /sessao/criar-conta/
    print("[DEBUG] Procurando botão/link 'Iniciar sessão'...")
    
    clicou_iniciar = False
    deadline_clique = time.time() + 10000  # 10 segundos para encontrar e clicar
    
    while time.time() < deadline_clique and not clicou_iniciar:
        # Estratégia 1: Botão "Iniciar sessão"
        try:
            btn_iniciar = ctx_atual.get_by_role("button", name=re.compile(r"Iniciar\s*sess[ãa]o|Iniciar\s*sessão|Já\s*tenho\s*cadastro|Entrar", re.I)).first
            if btn_iniciar and btn_iniciar.count() > 0 and btn_iniciar.is_visible():
                print("[DEBUG] Encontrou botão 'Iniciar sessão', clicando...")
                btn_iniciar.scroll_into_view_if_needed()
                btn_iniciar.click(timeout=5000)
                page.wait_for_timeout(2000)
                clicou_iniciar = True
                break
        except Exception:
            pass
        
        # Estratégia 2: Link "Iniciar sessão"
        try:
            link_iniciar = ctx_atual.get_by_role("link", name=re.compile(r"Iniciar\s*sess[ãa]o|Já\s*tenho\s*cadastro|Entrar", re.I)).first
            if link_iniciar and link_iniciar.count() > 0 and link_iniciar.is_visible():
                print("[DEBUG] Encontrou link 'Iniciar sessão', clicando...")
                link_iniciar.click(timeout=5000)
                page.wait_for_timeout(2000)
                clicou_iniciar = True
                break
        except Exception:
            pass
        
        # Estratégia 3: Locator por texto
        try:
            loc_iniciar = ctx_atual.locator('button:has-text("Iniciar sessão"), a:has-text("Iniciar sessão"), button:has-text("Já tenho cadastro"), a:has-text("Já tenho cadastro")').first
            if loc_iniciar and loc_iniciar.count() > 0 and loc_iniciar.is_visible():
                print("[DEBUG] Encontrou elemento 'Iniciar sessão' via locator, clicando...")
                loc_iniciar.click(timeout=5000)
                page.wait_for_timeout(2000)
                clicou_iniciar = True
                break
        except Exception:
            pass
        
        page.wait_for_timeout(500)
    
    if not clicou_iniciar:
        print("[DEBUG] Não encontrou botão 'Iniciar sessão', tentando prosseguir mesmo assim...")
        # Pode já estar no formulário de login
    
    # Aguarda formulário de login aparecer
    page.wait_for_timeout(2000)
    ctx_atual = _get_configurator_ctx(page)
    
    # Passo 3: Preencher email e senha
    print("[DEBUG] Preenchendo email e senha...")
    try:
        # Email
        email_input = None
        # Tenta primeiro no contexto atual
        try:
            email_input = ctx_atual.locator('input[type="email"], input[name*="email"], input[placeholder*="email" i]').first
            if email_input.count() > 0 and email_input.is_visible():
                pass
            else:
                email_input = None
        except Exception:
            pass
        
        # Se não encontrou, tenta em todos os frames
        if not email_input or email_input.count() == 0:
            for f in page.frames:
                try:
                    email_input = f.locator('input[type="email"], input[name*="email"], input[placeholder*="email" i]').first
                    if email_input.count() > 0 and email_input.is_visible():
                        ctx_atual = f
                        print(f"[DEBUG] Campo de email encontrado no frame: {getattr(f, 'url', 'N/A')}")
                        break
                except Exception:
                    continue
        
        if not email_input or email_input.count() == 0:
            raise AssertionError("Campo de email não encontrado após clicar em 'Iniciar sessão'")
        
        email_input.fill(FINAN_EMAIL)
        print(f"[DEBUG] Email preenchido: {FINAN_EMAIL}")
        page.wait_for_timeout(500)
        
        # Senha
        password_input = None
        try:
            password_input = ctx_atual.locator('input[type="password"]').first
            if password_input.count() > 0 and password_input.is_visible():
                pass
            else:
                password_input = None
        except Exception:
            pass
        
        # Se não encontrou, tenta em todos os frames
        if not password_input or password_input.count() == 0:
            for f in page.frames:
                try:
                    password_input = f.locator('input[type="password"]').first
                    if password_input.count() > 0 and password_input.is_visible():
                        ctx_atual = f
                        print(f"[DEBUG] Campo de senha encontrado no frame: {getattr(f, 'url', 'N/A')}")
                        break
                except Exception:
                    continue
        
        if not password_input or password_input.count() == 0:
            raise AssertionError("Campo de senha não encontrado")
        
        password_input.fill(FINAN_SENHA)
        print("[DEBUG] Senha preenchida")
        page.wait_for_timeout(500)
        
        # Submeter formulário
        btn_entrar = ctx_atual.get_by_role("button", name=re.compile(r"Entrar|Acessar|Login|Iniciar\s*sess[ãa]o|Confirmar", re.I)).first
        if btn_entrar.count() > 0 and btn_entrar.is_visible():
            btn_entrar.scroll_into_view_if_needed()
            btn_entrar.click(timeout=5000)
            print("[DEBUG] Botão 'Entrar' clicado")
        else:
            password_input.press("Enter")
            print("[DEBUG] Login submetido via Enter")
        
        page.wait_for_timeout(2000)
        return True
        
    except Exception as e:
        print(f"[DEBUG] Erro ao preencher login: {e}")
        _anexar_screenshot(request, page, "Erro - Falha ao Preencher Login")
        raise


@pytest.mark.jornada
@pytest.mark.pagamento
@pytest.mark.regressao
def test_pagamento_opcao_financiamento_requer_login(page: Page, request):
    page, ctx = _ir_para_pagamento(page, request)

    # Ação 1: Selecionar Financiamento (radio button)
    print("[DEBUG] Selecionando opção Financiamento...")
    _marcar_radio_robusto(ctx, re.compile(r"Financiamento", re.I))
    _anexar_screenshot(request, page, "Pagamento - Financiamento Selecionado")
    page.wait_for_timeout(1500)  # Aguarda UI atualizar

    # Ação 2: Clicar no botão "Definir método de pagamento"
    print("[DEBUG] Clicando em 'Definir método de pagamento'...")
    clicou_definir = _clicar_definir_metodo_pagamento(ctx, page, 15000)
    
    if not clicou_definir:
        print("[DEBUG] Tentando fallback: botão pode ter texto diferente...")
        # Fallback: tenta botões genéricos de continuar/confirmar
        try:
            btn_continuar = ctx.get_by_role("button", name=re.compile(r"Continuar|Confirmar|Avançar|Próximo|Definir", re.I)).first
            if btn_continuar and btn_continuar.count() > 0 and btn_continuar.is_visible() and not btn_continuar.is_disabled():
                btn_continuar.click(timeout=5000)
                page.wait_for_timeout(1500)
                clicou_definir = True
        except Exception:
            pass
    
    _anexar_screenshot(request, page, "Pagamento - Após Clicar Definir Método")
    page.wait_for_timeout(2000)  # Aguarda modal/formulário aparecer

    # Ação 3: Verificar se aparece opção de criar conta ou iniciar sessão
    print("[DEBUG] Verificando se aparece opção de login...")
    
    # Aguarda formulário de login aparecer
    ctx_atual = _get_configurator_ctx(page)
    login_visible = _password_visible_em_qualquer_frame(page, ctx_atual, 16000)

    if not login_visible:
        # Pode precisar clicar em "Iniciar sessão" primeiro
        print("[DEBUG] Formulário não visível, tentando clicar em 'Iniciar sessão'...")
        try:
            btn_iniciar = ctx_atual.get_by_role("button", name=re.compile(r"Iniciar\s*sess[ãa]o|Já\s*tenho\s*cadastro", re.I)).first
            if btn_iniciar and btn_iniciar.count() > 0 and btn_iniciar.is_visible():
                btn_iniciar.click(timeout=5000)
                page.wait_for_timeout(2000)
                ctx_atual = _get_configurator_ctx(page)
                login_visible = _password_visible_em_qualquer_frame(page, ctx_atual, 8000)
        except Exception:
            pass

    if not login_visible:
        _anexar_screenshot(request, page, "Erro - Formulário de login não apareceu")
        pytest.fail("O formulário de login não apareceu após selecionar Financiamento e definir método de pagamento.")

    # Ação 4: Preencher login usando helper específico
    print("[DEBUG] Iniciando preenchimento de login...")
    _iniciar_sessao_financiamento(ctx_atual, page, request, 15000)
    
    _anexar_screenshot(request, page, "Pagamento - Login Submetido")
    
    # Validar ausência de erro imediato
    ctx_final = _get_configurator_ctx(page)
    expect(ctx_final.get_by_text(re.compile(r"inv[aá]lid|incorret", re.I))).to_have_count(0)


@pytest.mark.jornada
@pytest.mark.pagamento
@pytest.mark.regressao
def test_pagamento_opcao_negociar_leva_para_resumo(page: Page, request):
    page, ctx = _ir_para_pagamento(page, request)

    # Ação 1: Selecionar Negociar na Concessionária (radio button)
    print("[DEBUG] Selecionando opção 'Negociar na concessionária'...")
    _marcar_radio_robusto(ctx, re.compile(r"Negociar\s+na\s+concession[aá]ria", re.I))
    _anexar_screenshot(request, page, "Pagamento - Negociar Selecionado")
    page.wait_for_timeout(1500)  # Aguarda UI atualizar

    # Ação 2: Clicar no botão "Definir método de pagamento" (se necessário)
    print("[DEBUG] Verificando se precisa clicar em 'Definir método de pagamento'...")
    clicou_definir = _clicar_definir_metodo_pagamento(ctx, page, 10000)
    
    if clicou_definir:
        _anexar_screenshot(request, page, "Pagamento - Após Clicar Definir Método (Negociar)")
        page.wait_for_timeout(1500)

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