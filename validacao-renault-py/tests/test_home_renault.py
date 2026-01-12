import re
import time
import pytest
from playwright.sync_api import Page, expect

# Padrão do título esperado (mais resiliente)
KNOWN_TITLE_PATTERN = re.compile(r"Renault", re.IGNORECASE)


def _carregar_toda_pagina(page: Page):
    """Rola a página para disparar lazy-loading das imagens."""
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


def _aceitar_cookies(page: Page):
    """Aceita o banner de cookies quando presente para evitar sobreposição da UI."""
    try:
        botao_cookies = page.locator("#onetrust-accept-btn-handler")
        expect(botao_cookies).to_be_visible(timeout=5000)
        botao_cookies.click()
        print("Banner de cookies aceito.")
    except Exception:
        # Tentativa de fallback por role/text
        try:
            page.get_by_role("button", name=re.compile("Aceitar|Accept|Concordo|OK", re.I)).click(timeout=3000)
            print("Banner de cookies aceito (fallback).")
        except Exception as e:
            print(f"Aviso: Banner de cookies não interferiu. {e}")


def _esperar_indicador_vitrine(page: Page, timeout_ms: int = 15000) -> bool:
    """Espera até encontrar indicador de vitrine (preço ou CTA relevante)."""
    seletores_preco = [
        "text=R$",
        ".price",
        "[class*=price]",
        ".valor",
        "[data-testid*=price]",
    ]
    cta_regex = re.compile(
        r"Oferta|Ofertas|Comprar|Conferir|Proposta|Condições|Monte|Simular|Monte o seu|Ver ofertas|Ver condições",
        re.I,
    )

    inicio = time.time()
    while (time.time() - inicio) * 1000 < timeout_ms:
        # Checa preços
        for sel in seletores_preco:
            try:
                loc = page.locator(sel).first
                if loc.is_visible():
                    return True
            except Exception:
                pass
        # Checa CTAs
        try:
            link = page.get_by_role("link", name=cta_regex).first
            if link.is_visible():
                return True
        except Exception:
            pass
        try:
            btn = page.get_by_role("button", name=cta_regex).first
            if btn.is_visible():
                return True
        except Exception:
            pass
        page.wait_for_timeout(300)
    return False


def test_setup_e_acesso(page: Page):
    print("\n--- Acessando / (usando --base-url) ---")

    # Timeouts padrão por teste
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)

    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    expect(page).to_have_title(KNOWN_TITLE_PATTERN)


def test_validar_imagens_quebradas(page: Page):
    """
    Valida integridade das imagens.
    Gera lista detalhada para o relatório em caso de falha.
    """
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    _carregar_toda_pagina(page)

    imagens = page.locator("img").all()
    print(f"Total de imagens analisadas: {len(imagens)}")

    lista_quebradas = []

    for i, img in enumerate(imagens):
        src = img.get_attribute("src")
        if not src:
            continue

        if img.is_visible():
            is_broken = page.evaluate(
                "(node) => node.naturalWidth === 0 || node.complete === false",
                img.element_handle(),
            )

            if is_broken:
                # erro_msg = f"Imagem #{i} | SRC: {src}"
                # print(f"[FALHA] {erro_msg}")  # Sai no log do relatório
                # lista_quebradas.append(erro_msg)
                # Captura o HTML do elemento para entender o contexto (ex: classe, pai)
                html_elemento = img.evaluate("node => node.outerHTML")
                erro_msg = f"Imagem #{i} | SRC: {src} | HTML: {html_elemento}"
                
                print(f"[FALHA] {erro_msg}")
                lista_quebradas.append(erro_msg)

    qtd_erros = len(lista_quebradas)
    mensagem_relatorio = (
        f"\n⚠️ FORAM ENCONTRADAS {qtd_erros} IMAGENS QUEBRADAS:\n" + "\n".join(lista_quebradas)
    )

    assert qtd_erros == 0, mensagem_relatorio


def test_validar_textos_exibidos(page: Page):
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    seletores = ["h1", "h2", "h3", ".text-primary"]

    erros_texto = []

    for seletor in seletores:
        elementos = page.locator(seletor).all()

        for elem in elementos:
            if elem.is_visible():
                texto = elem.text_content()

                if not texto or len(texto.strip()) == 0:
                    html_elemento = elem.evaluate("el => el.outerHTML")
                    erros_texto.append(f"Elemento vazio visível: {html_elemento}")

    assert len(erros_texto) == 0, "Erros encontrados:\n" + "\n".join(erros_texto)


@pytest.mark.vitrine
def test_vitrine_veiculos(page: Page):
    """
    Validação de vitrine (carregamento de preços/ofertas) com retry inteligente.
    """
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    _carregar_toda_pagina(page)

    assert _esperar_indicador_vitrine(page, 15000), (
        "Nenhum indicador de vitrine encontrado (preços/CTAs). "
        "Verifique se a página carregou corretamente e se o banner de cookies não está bloqueando a UI."
    )

    print("Vitrine carregada com sucesso (preços ou ofertas identificados).")
