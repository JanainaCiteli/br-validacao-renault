import re
import time
import pytest
import base64
import pytest_html
from playwright.sync_api import Page, expect

def _aceitar_cookies(page: Page):
    # Aguarda o DOM estar pronto
    page.wait_for_load_state("domcontentloaded")

    # Variações de seletores para o botão "aceitar"
    seletores = [
        'button:has-text("aceitar")',
        'button:has-text("Aceitar")',
        'button:has-text("ACEITAR")',
        'role=button[name=/aceitar/i]',
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

    # Se não clicou, tenta dentro de iframes que possam conter o banner
    if not clicou:
        for frame in page.frames:
            try:
                fb = frame.get_by_role("button", name=re.compile("aceitar", re.I))
                # get_by_role retorna Locator; testamos visibilidade e clicamos
                if fb and fb.count() > 0:
                    target = fb.first
                    if target.is_visible():
                        target.click(timeout=5000)
                        clicou = True
                        break
            except Exception:
                pass

    # Persiste consentimento para evitar reaparecer
    try:
        page.evaluate("""() => {
            localStorage.setItem("cookie-consent", "true");
            localStorage.setItem("consentAccepted", "true");
        }""")
    except Exception:
        pass

    try:
        page.context.add_cookies([{
            "name": "cookie-consent",
            "value": "true",
            "domain": "loja.renault.com.br",
            "path": "/",
            "expires": int(time.time()) + 31536000,  # 1 ano
            "sameSite": "Lax",
            "httpOnly": False,
            "secure": True,
        }])
    except Exception:
        pass

    # Aguarda o sumiço do botão/modal; se persistir, remove overlay/modais por JS como fallback
    try:
        page.locator('button:has-text("aceitar")').first.wait_for(state="detached", timeout=2500)
    except Exception:
        # Fallback: remove overlay/modal
        page.evaluate("""() => {
            const selectors = [
              '.chakra-modal__overlay',
              '.chakra-modal__content-container',
              '[role="dialog"]',
              '[aria-modal="true"]'
            ];
            selectors.forEach(sel => {
              document.querySelectorAll(sel).forEach(el => {
                try { el.remove(); } catch (e) {}
              });
            });
        }""")

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
    Valida integridade das imagens evitando falso-positivos de lazy-loading/carrossel.
    """
    page.set_default_timeout(15000)
    page.set_default_navigation_timeout(30000)
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    _carregar_toda_pagina(page)

    # Força carregamento imediato das imagens lazy (IIFE para executar)
    print("[TESTE] Forçando eager nas imagens...")
    page.evaluate(
        """
        (() => {
          document.querySelectorAll('img').forEach(img => {
            try {
              // Remove lazy
              img.loading = 'eager';
              img.decoding = 'sync';
              if ('fetchPriority' in img) img.fetchPriority = 'high';

              // Migra data-src/data-original para src se necessário
              const ds = img.getAttribute('data-src') || img.getAttribute('data-original');
              if (ds && !img.getAttribute('src')) img.setAttribute('src', ds);

              // Opcional: força um reload leve do src para garantir fetch
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

    imagens = page.locator("img").all()
    print(f"Total de imagens analisadas: {len(imagens)}")

    lista_quebradas = []

    for i, img in enumerate(imagens):
        src = img.get_attribute("src")
        if not src:
            continue

        if img.is_visible():
            el = img.element_handle()
            if not el:
                continue

            # Traz a imagem para o viewport (carrossel/overflow)
            page.evaluate("(el) => el.scrollIntoView({behavior:'auto', block:'center', inline:'center'})", el)

            try:
                # Aguarda carregamento real (evita falso-positivo de lazy)
                page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=el, timeout=8000)
            except Exception:
                # Se não carregou dentro do timeout, registra como erro
                html_elemento = img.evaluate("node => node.outerHTML")
                erro_msg = f"Imagem #{i} | SRC: {src} | Motivo: timeout de carregamento | HTML: {html_elemento}"
                print(f"[FALHA] {erro_msg}")
                lista_quebradas.append(erro_msg)
                continue  # vai para a próxima imagem

            # Revalida após a espera
            is_broken = page.evaluate("(node) => node.naturalWidth === 0 || node.complete === false", el)
            if is_broken:
                html_elemento = img.evaluate("node => node.outerHTML")
                erro_msg = f"Imagem #{i} | SRC: {src} | HTML: {html_elemento}"
                print(f"[FALHA] {erro_msg}")
                lista_quebradas.append(erro_msg)

    qtd_erros = len(lista_quebradas)
    mensagem_relatorio = (
        f"\n⚠️ FORAM ENCONTRADAS {qtd_erros} IMAGENS QUEBRADAS:\n" + "\n".join(lista_quebradas)
    )
    assert qtd_erros == 0, mensagem_relatorio



def test_imagens_status_http(page: Page, request):
    """
    Valida integridade de TODAS as imagens verificando o Status Code (200)
    e coleta screenshots de cada uma para o relatório.
    """
    # 1. Acessa e carrega
    page.goto("/", wait_until="domcontentloaded", timeout=30000)
    _aceitar_cookies(page)

    # Força carregamento de lazy-loading rolando a página
    for _ in range(5):
        page.keyboard.press("PageDown")
        page.wait_for_timeout(500)

    # 2. Coleta todos os elementos de imagem
    imagens = page.locator("img").all()
    print(f"\nTotal de imagens encontradas: {len(imagens)}")

    erros = []
    extras = []

    # Injeta CSS no relatório para exibir as imagens em grid (opcional, mas fica bonito)
    extras.append(
        pytest_html.extras.html(
            """
            <style>
                .galeria-imagens { display: flex; flex-wrap: wrap; gap: 10px; }
                .img-card { border: 1px solid #ccc; padding: 5px; width: 150px; text-align: center; }
                .img-card img { max-width: 100%; height: auto; display: block; margin: 0 auto; }
                .img-card.erro { border-color: red; background: #ffe6e6; }
                .status { font-size: 10px; display: block; margin-top: 5px; word-break: break-all;}
            </style>
            <h3>Galeria de Evidências das Imagens</h3>
            <div class="galeria-imagens">
            """
        )
    )

    for i, img in enumerate(imagens):
        # Pega a URL absoluta (resolve problemas de caminhos relativos)
        src = img.evaluate("node => node.src")

        if not src:
            continue

        status_code = "N/A"
        classe_css = "sucesso"
        screenshot_b64 = ""

        try:
            # A. Validação Técnica: Faz uma requisição GET leve para ver se existe
            response = page.request.get(src)
            status_code = response.status

            if status_code != 200:
                erros.append(f"Imagem #{i} [Status {status_code}]: {src}")
                classe_css = "erro"

            # B. Evidência Visual: Tira print SÓ do elemento da imagem
            if img.is_visible():
                screenshot_bytes = img.screenshot(timeout=2000)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # Adiciona ao HTML do relatório
            html_card = f"""
                <div class="img-card {classe_css}">
                    <a href="{src}" target="_blank">
                        <img src="data:image/png;base64,{screenshot_b64}" title="{src}"/>
                    </a>
                    <span class="status">#{i} Status: <b>{status_code}</b></span>
                </div>
            """
            extras.append(pytest_html.extras.html(html_card))

        except Exception as e:
            print(f"Erro ao processar imagem {src}: {e}")
            erros.append(f"Erro processamento #{i}: {src}")

    # Fecha a div da galeria
    extras.append(pytest_html.extras.html("</div>"))

    # Anexa as evidências ao relatório HTML
    if hasattr(request.node, "rep_call"):
        extra = getattr(request.node.rep_call, "extra", [])
        extra.extend(extras)
        request.node.rep_call.extra = extra

    # 3. Asserção Final
    if erros:
        pytest.fail(
            f"Foram encontradas {len(erros)} imagens com problemas:\n" + "\n".join(erros)
        )


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
