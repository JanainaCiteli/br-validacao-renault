import re
import time
import pytest
from playwright.sync_api import Page, expect

# Reutiliza padrão de título
KNOWN_TITLE_PATTERN = re.compile(r"Renault", re.IGNORECASE)


def _aceitar_cookies(page: Page):
    """Aceita o banner de cookies quando presente para evitar sobreposição da UI."""
    try:
        botao_cookies = page.locator("#onetrust-accept-btn-handler")
        if botao_cookies.count() > 0 and botao_cookies.is_visible():
            botao_cookies.click()
            print("Banner de cookies aceito.")
            return
    except Exception:
        pass

    # Fallbacks por role/text
    try:
        page.get_by_role("button", name=re.compile("Aceitar|Accept|Concordo|OK", re.I)).click(timeout=3000)
        print("Banner de cookies aceito (fallback).")
    except Exception:
        print("Aviso: Banner de cookies não interferiu.")


def _carregar_toda_pagina(page: Page):
    """Rola a página para disparar lazy-loading dos componentes."""
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


@pytest.mark.jornada
def test_fluxo_jornada_de_reserva(page: Page):
    """
    Fluxo: Home -> clicar "configure e reserve" de cada veículo -> Jornada de Reserva -> Iniciar configuração -> Versões.
    - Suporta 5+ veículos (iterando pelos CTAs encontrados na home)
    - Usa base-url do pytest-playwright (page.goto("/"))
    - Aceita cookies e trata lazy-loading/viewport.
    """
    page.set_default_timeout(20000)
    page.set_default_navigation_timeout(40000)

    # Abre Home
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)
    expect(page).to_have_title(KNOWN_TITLE_PATTERN)

    _carregar_toda_pagina(page)

    # 1. Localiza CTAs (Botões OU Links que contenham o texto)
    cta_regex = re.compile(r"configure\s*e\s*reserve", re.I)
    
    # Cria um "Locator" unificado: busca tags 'a' ou 'button' que tenham esse texto
    loc_ctas = page.locator("a, button").filter(has_text=cta_regex)

    print("Aguardando renderização dos botões...")

    # 2. ESPERA EXPLÍCITA
    try:
        loc_ctas.first.wait_for(state="visible", timeout=15000)
    except Exception:
        print("Timeout: Botões não apareceram. Tirando print de debug.")
        page.screenshot(path="debug_erro_botoes.png")

    # 3. Contagem segura
    total_ctas = loc_ctas.count()

    print(f"Total de CTAs 'configure e reserve' encontrados: {total_ctas}")
    assert total_ctas > 0, "Nenhum CTA 'configure e reserve' encontrado na home."

    erros = []
    sucesso = 0

    # Itera pelos CTAs encontrados
    for idx in range(total_ctas):
        # Volta/garante Home em cada iteração
        page.goto("/", wait_until="domcontentloaded", timeout=30000)
        _aceitar_cookies(page)
        _carregar_toda_pagina(page)

        # Recria o locator após o refresh
        loc_ctas = page.locator("a, button").filter(has_text=cta_regex)
        
        # Espera novamente o elemento reaparecer
        try:
            loc_ctas.first.wait_for(state="visible", timeout=15000)
        except:
            pass # Se falhar aqui, o target.click vai falhar e cair no except abaixo

        # SELEÇÃO SIMPLIFICADA
        target = loc_ctas.nth(idx)

        try:
            # Traz elemento para viewport
            el = target.element_handle()
            if el:
                page.evaluate("(el) => el.scrollIntoView({behavior:'auto', block:'center', inline:'center'})", el)
                page.wait_for_timeout(250)

            # Clica CTA
            target.click(force=True, timeout=5000)

            # Espera redirecionar
            page.wait_for_url(
                re.compile(r"/jornada-de-reserva|/configurador/.+/versoes|/r-pass/pre-venda/configurador/.+/versoes"), 
                timeout=60000, 
                wait_until="domcontentloaded"
            )
            _aceitar_cookies(page)

            # Se caiu na Jornada de Reserva, clica "Iniciar configuração"
            if "/jornada-de-reserva" in page.url:
                iniciar_btn = page.get_by_role("button", name=re.compile("Iniciar", re.I))
                expect(iniciar_btn).to_be_visible(timeout=10000)
                iniciar_btn.click()
                page.wait_for_url(re.compile(r"/configurador/.+/versoes|/r-pass/pre-venda/configurador/.+/versoes"), timeout=30000)

            # Valida que está na página de Versões
            assert re.search(r"/versoes", page.url), f"URL inesperada após iniciar configuração: {page.url}"

            # Heurística: texto típico de versões
            texto_versoes = page.get_by_text(re.compile(r"versões\s*a partir de", re.I))
            if texto_versoes.count() == 0:
                print(f"[AVISO] Não encontrou texto 'versões a partir de' em {page.url}")

            sucesso += 1
            print(f"[OK] Fluxo jornada de reserva concluído para CTA #{idx}. URL: {page.url}")

        except Exception as e:
            erros.append(f"[ERRO IDX {idx}] {str(e)}")

    # Resultado final
    msg = f"Sucessos: {sucesso} | Erros: {len(erros)}" + ("\n" + "\n".join(erros) if erros else "")
    assert len(erros) == 0, msg
