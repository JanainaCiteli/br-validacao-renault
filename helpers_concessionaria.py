import re
import time
from typing import Optional
from playwright.sync_api import Page

# Regex amplo padrão para reconhecer URLs de Concessionária (pode ser sobrescrito via parâmetro)
DEFAULT_URL_CONCESSIONARIA_REGEX = re.compile(r"/configurador/.+/concessionaria|/concessionari(a|as)|/dealers|/lojas|/ponto-de-venda|/r-pass/pre-venda/concessionaria", re.I)


def esperar_concessionaria(page: Page, ctx=None, timeout_ms: int = 30000, url_regex: Optional[re.Pattern] = None) -> bool:
    """
    Aguarda sinais de Concessionária de forma robusta:
    - URL principal (page) casa com regex
    - URL de algum frame casa com regex
    - Heurísticas de UI no contexto (heading 'Concessionária', mapa, lista de dealers, botões 'Selecionar')
    """
    url_rx = url_regex or DEFAULT_URL_CONCESSIONARIA_REGEX

    # 1. Tentativa por URL (page)
    try:
        page.wait_for_url(url_rx, timeout=min(timeout_ms, 5000))
        return True
    except Exception:
        pass

    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        # URL atual
        try:
            if url_rx.search(page.url or ""):
                return True
        except Exception:
            pass

        # URLs de frames
        try:
            for f in page.frames:
                fu = getattr(f, "url", "") or ""
                if url_rx.search(fu):
                    return True
        except Exception:
            pass

        # Heurísticas visuais
        if ctx is not None:
            try:
                if ctx.get_by_role("heading", name=re.compile(r"Concession[aá]ria|Dealer|Loja", re.I)).first.is_visible():
                    return True
            except Exception:
                pass
            try:
                if ctx.locator('[data-testid*="dealer"], .leaflet-container, .gm-style, li:has-text("km")').first.is_visible():
                    return True
            except Exception:
                pass

        page.wait_for_timeout(400)

    return False


def inserir_cep_robusto(ctx, page: Page, cep_busca: str = "01001-000") -> None:
    """
    Preenche CEP com robustez:
    - Tenta localizar input por placeholder/name/type=search
    - Pressiona Enter e/ou clica botão de Buscar/Aplicar quando existir
    - Aguarda pequeno intervalo e quiet network
    """
    try:
        # Se já há lista/elementos de dealers visíveis, não força CEP
        try:
            lista = ctx.locator('[id^="button-"] , [data-testid*="dealer-card"], [class*="dealer"], [class*="store-list"], li:has-text("km")')
            if lista.count() > 0 and lista.first.is_visible():
                return
        except Exception:
            pass

        cep_input = ctx.locator('input[placeholder*="CEP" i], input[name*="cep" i], input[type="search"]').first
        if not (cep_input and cep_input.count() > 0 and cep_input.is_visible()):
            return

        cep_input.click(force=True)
        try:
            cep_input.fill("")
        except Exception:
            pass
        cep_input.type(cep_busca, delay=60)
        page.wait_for_timeout(300)

        # Tenta botão Buscar/Aplicar
        clicado = False
        try:
            btn_buscar = ctx.get_by_role("button", name=re.compile(r"Buscar|Procurar|Pesquisar|OK|Confirmar|Aplicar|Ir", re.I)).first
            if btn_buscar and btn_buscar.count() > 0 and btn_buscar.is_visible():
                try:
                    btn_buscar.click(force=True, timeout=3000)
                    clicado = True
                except Exception:
                    pass
        except Exception:
            pass

        if not clicado:
            cep_input.press("Enter")

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
    except Exception:
        pass


def dealer_esta_selecionado(ctx) -> bool:
    """Heurística para identificar se algum dealer foi efetivamente selecionado."""
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


def esta_em_concessionaria(ctx) -> bool:
    """Heurística de UI para identificar a tela de concessionária pelo contexto/frame."""
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


def selecionar_concessionaria_robusta(ctx, page: Page, tempo_ms: int = 45000) -> bool:
    """
    Seleciona uma concessionária com estratégias robustas:
    - Variações de botão "Selecionar" (role, texto, data-testid)
    - Scroll incremental para listas virtualizadas/lazy-load
    - Clique via JS e fallback force
    - Clique no card inteiro quando necessário
    - Confirmação por dealer_esta_selecionado()
    """
    t_end = time.time() + (tempo_ms / 1000.0)

    if not esta_em_concessionaria(ctx):
        return False

    def coletar_botoes():
        candidatos = []
        try:
            loc = ctx.get_by_role("button", name=re.compile(r"Selecion(ar|e|ado)", re.I))
            total = min(loc.count(), 20)
            for i in range(total):
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
            total = min(loc.count(), 20)
            for i in range(total):
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
            total = min(loc.count(), 20)
            for i in range(total):
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
        try:
            if dealer_esta_selecionado(ctx):
                return True
        except Exception:
            pass

        botoes = coletar_botoes()
        if botoes:
            for btn in botoes[:6]:
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
                    page.wait_for_timeout(1000)
                    if dealer_esta_selecionado(ctx):
                        return True

            # Fallback: clicar card do último botão
            try:
                card = btn.locator("xpath=ancestor-or-self::*[self::*[@data-testid][1] or self::li or self::div][1]").first  # type: ignore[name-defined]
                if card and card.is_visible():
                    try:
                        card.click(force=True)
                        page.wait_for_timeout(800)
                        if dealer_esta_selecionado(ctx):
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            # Scroll para materializar mais itens
            try:
                ctx.evaluate("() => { window.scrollBy(0, 900); }")
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

    return dealer_esta_selecionado(ctx)
