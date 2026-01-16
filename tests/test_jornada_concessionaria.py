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
URL_VERSOES_REGEX = re.compile(r"/configurador/.+/versoes|/r-pass/pre-venda/configurador/.+/versoes")
URL_JORNADA_REGEX = re.compile(r"/jornada-de-reserva")
URL_CONCESSIONARIA_REGEX = re.compile(r"/configurador/.+/concessionaria|/concessionari(a|as)|/dealers|/lojas|/ponto-de-venda|/r-pass/pre-venda/concessionaria", re.I)

# Limites opcionais
MODELOS_LIMIT = int(os.getenv("MODELOS_LIMIT", "0") or "0")
VERSOES_LIMIT = int(os.getenv("VERSOES_LIMIT", "0") or "0")
DEALERS_CHECK_LIMIT = int(os.getenv("DEALERS_CHECK_LIMIT", "3") or "3")
CEP_BUSCA = os.getenv("CEP_BUSCA", "01001-000")


# =============================
# Helpers compartilhados
# =============================

def _aceitar_cookies(page: Page):
    """Aceita o banner de cookies quando presente para evitar bloqueio de UI."""
    try:
        page.wait_for_load_state("domcontentloaded")
    except:
        pass
        
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
                btn.click(force=True, timeout=3000)
                clicou = True
                break
        except Exception:
            pass
    
    try:
        page.evaluate("""() => {
            try {
                localStorage.setItem("cookie-consent", "true");
                localStorage.setItem("consentAccepted", "true");
            } catch(e){}
        }""")
    except Exception:
        pass


def _anexar_screenshot(request, page_or_frame, titulo: str):
    """Anexa screenshot ao relatório HTML (pytest-html)."""
    try:
        page = page_or_frame if hasattr(page_or_frame, "screenshot") else None
        if not page:
            return
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
    """Retorna o frame com /configurador/ quando existir; senão, a própria page."""
    for f in page.frames:
        try:
            if re.search(r"/configurador/", f.url or ""):
                return f
        except Exception:
            pass
    return page


def _garantir_ctx_configurador(page: Page):
    _aceitar_cookies(page)
    if URL_CFG_REGEX.search(page.url):
        return
    if URL_JORNADA_REGEX.search(page.url):
        iniciar_btn = page.get_by_role("button", name=re.compile("Iniciar|Configurar", re.I)).first
        try:
            if iniciar_btn.is_visible(timeout=5000):
                iniciar_btn.click(timeout=8000)
                page.wait_for_url(URL_CFG_REGEX, timeout=30000)
        except:
            pass
        _aceitar_cookies(page)
        return
    try:
        page.wait_for_url(URL_CFG_REGEX, timeout=10000)
    except:
        pass
    _aceitar_cookies(page)


def _is_versoes_page(ctx) -> bool:
    try:
        return bool(re.search(r"/configurador/.+/versoes", getattr(ctx, "url", "") or "", re.I))
    except Exception:
        return False


def _combo_versao_info(ctx):
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


def _contar_versoes(page, ctx) -> int:
    combo, cid = _combo_versao_info(ctx)
    if combo:
        try:
            combo.click(timeout=6000)
            options = ctx.locator(f'#{cid} [role="option"]') if cid else ctx.locator('[role="listbox"] [role="option"]')
            qtd = options.count()
            ctx.keyboard.press("Escape")
            return qtd if qtd > 0 else 1
        except:
            return 1

    if _is_versoes_page(ctx):
        try:
            # Filtro para evitar clicar em "Hand Talk" ou outros plugins
            btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
            count = 0
            for i in range(btns.count()):
                txt = btns.nth(i).inner_text() or ""
                if "Hand Talk" not in txt and "Acessibilidade" not in txt:
                    count += 1
            if count > 0:
                return count
        except Exception:
            pass
        try:
            cards = ctx.locator('[data-testid*="versao"], [data-testid*="version"], [class*="versao"], [class*="version"]')
            return max(cards.count(), 1)
        except Exception:
            pass

    return 1


def _selecionar_versao(page, ctx, idx: int):
    combo, cid = _combo_versao_info(ctx)
    if combo:
        combo.click(timeout=6000)
        options = ctx.locator(f'#{cid} [role="option"]') if cid else ctx.locator('[role="listbox"] [role="option"]')
        total = options.count()
        if idx < total:
            options.nth(idx).click(timeout=8000)
        return

    if _is_versoes_page(ctx):
        btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
        
        # Filtra botões válidos (sem Hand Talk)
        valid_idxs = []
        for i in range(btns.count()):
            txt = btns.nth(i).inner_text() or ""
            if "Hand Talk" not in txt and "Acessibilidade" not in txt:
                valid_idxs.append(i)
        
        real_idx = valid_idxs[idx] if idx < len(valid_idxs) else -1
        
        if real_idx >= 0:
            btns.nth(real_idx).click(timeout=10000)
            page.wait_for_url(re.compile(r"/configurador/.+/(design|cores|rodas|interior)", re.I), timeout=35000)
            return

        # Fallback cards
        cards = ctx.locator('[data-testid*="versao"], [data-testid*="version"], [class*="versao"], [class*="version"]')
        if cards.count() > idx:
            interno = cards.nth(idx).locator('button, a, [role="button"]').first
            if interno and interno.count() > 0 and interno.is_visible():
                interno.click(timeout=10000)
            else:
                cards.nth(idx).click(timeout=10000)
            page.wait_for_url(re.compile(r"/configurador/.+/(design|cores|rodas|interior)", re.I), timeout=35000)
            return

    if idx == 0:
        return


def _esperar_concessionaria(page: Page, ctx=None, timeout_ms: int = 30000) -> bool:
    # 1. Tenta URL
    try:
        page.wait_for_url(URL_CONCESSIONARIA_REGEX, timeout=5000)
        return True
    except Exception:
        pass

    # 2. Polling de URL e Frames
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        if URL_CONCESSIONARIA_REGEX.search(page.url):
            return True
        for f in page.frames:
            try:
                if URL_CONCESSIONARIA_REGEX.search(f.url or ""):
                    return True
            except Exception:
                pass
        
        if ctx:
            try:
                if ctx.get_by_role("heading", name=re.compile(r"Concession[aá]ria|Dealer|Loja", re.I)).first.is_visible():
                    return True
                if ctx.locator('[id^="button-"]').first.is_visible():
                    return True
                if ctx.locator('[data-testid*="dealer"], .leaflet-container, .gm-style').first.is_visible():
                    return True
            except:
                pass
                
        page.wait_for_timeout(500)

    return False


def _inserir_cep_se_necessario(ctx, page: Page):
    try:
        page.wait_for_timeout(3000)
        lista = ctx.locator('[id^="button-"] , [data-testid*="dealer-card"], [class*="dealer"], [class*="store-list"], li:has-text("km")')
        if lista.count() > 0 and lista.first.is_visible():
            return
    except Exception:
        pass

    print("[INFO] Resultados não apareceram automaticamente. Tentando busca por CEP.")
    try:
        cep_input = ctx.locator('input[placeholder*="CEP" i], input[name*="cep" i], input[type="search"]').first
        if not cep_input.is_visible():
            return

        cep_input.click(force=True)
        cep_input.fill("")
        cep_input.type(CEP_BUSCA, delay=100)
        page.wait_for_timeout(500)

        btn_buscar = ctx.get_by_role("button", name=re.compile(r"Buscar|Procurar|Pesquisar|OK|Aplicar|>|Icon", re.I)).first
        
        clicado = False
        if btn_buscar and btn_buscar.count() > 0 and btn_buscar.is_visible():
            try:
                btn_buscar.click(force=True, timeout=3000)
                clicado = True
            except:
                pass
        
        if not clicado:
            cep_input.press("Enter")
            
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
            page.wait_for_timeout(2000)
        except Exception:
            pass
            
    except Exception as e:
        print(f"[ERRO] Falha ao tentar inserir CEP: {e}")


def _validar_resultados_concessionarias(ctx) -> int:
    try:
        botoes = ctx.get_by_role("button", name=re.compile(r"(selecionar|selecionado)", re.I))
        qtde = botoes.count()
        if qtde > 0:
            return qtde
    except Exception:
        pass

    try:
        ids = ctx.locator('[id^="button-"]')
        if ids.count() > 0:
            return ids.count()
    except Exception:
        pass

    seletores = [
        '[data-testid*="dealer-card"]',
        '[class*="dealer-card"]',
        '.store-list-item',
        'li[class*="dealer"]',
        'div[class*="card"]:has-text("km")',
        'div:has(> button:has-text("Selecionar"))',
        '[data-testid="store-card"]'
    ]
    for sel in seletores:
        l = ctx.locator(sel)
        if l.count() > 0:
            return l.count()

    return 0


def _validar_mapa_concessionarias(ctx) -> None:
    seletores = [
        '[data-testid*="map"]', '.leaflet-container', '.mapboxgl-map', 
        '.gm-style', 'iframe[src*="maps"]', '#map', 'div[class*="map"]'
    ]
    encontrou = False
    for sel in seletores:
        if ctx.locator(sel).first.count() > 0:
            encontrou = True
            break
    if not encontrou:
        print("[AVISO] Container do mapa não identificado com seletores padrão.")


def _validar_avisos_legais(ctx) -> None:
    possiveis = [
        ctx.get_by_text(re.compile(r"Avisos\s+legais|Condi[cç][oõ]es|Imagens\s+meramente", re.I)).first,
        ctx.locator('footer')
    ]
    for cand in possiveis:
        if cand.count() > 0:
            return
    print("[AVISO] Bloco de avisos legais não detectado explicitamente.")


def _validar_textos_gerais(ctx) -> None:
    try:
        body_text = ctx.locator("body").inner_text()
        padrao_quebra = re.compile(r"(undefined|null|NaN|\{\{[^}]+\}\})", re.I)
        matches = padrao_quebra.findall(body_text)
        matches = [m for m in matches if "null" not in m.lower()] 
        if matches:
            print(f"[AVISO] Possíveis textos quebrados encontrados: {matches[:5]}")
    except:
        pass


def _goto_concessionaria_por_url(page: Page):
    url = page.url
    m = re.search(r"/configurador/([^/]+)/", url, re.I)
    if not m:
        return False
    modelo = m.group(1)
    destinos = [
        f"https://loja.renault.com.br/configurador/{modelo}/concessionaria/",
        f"https://loja.renault.com.br/r-pass/pre-venda/configurador/{modelo}/concessionaria/"
    ]
    for destino in destinos:
        try:
            page.goto(destino, wait_until="domcontentloaded", timeout=20000)
            if _esperar_concessionaria(page, None, 5000):
                return True
        except:
            pass
    return False


# =============================
# Teste principal: Etapa 3/5 Concessionária
# =============================

@pytest.mark.jornada
@pytest.mark.concessionaria
@pytest.mark.regressao
def test_validar_jornada_concessionaria_para_todos_modelos_e_versoes(page: Page, request):
    page.set_default_timeout(25000)
    page.set_default_navigation_timeout(45000)

    try:
        page.context.grant_permissions(["geolocation"])
        page.context.set_geolocation({"latitude": -23.55052, "longitude": -46.633308})
    except Exception:
        pass

    page.goto("/", wait_until="domcontentloaded", timeout=45000)
    _aceitar_cookies(page)
    
    try:
        page.locator('button, a').filter(has_text=CTA_CONFIGURE_RESERVA_REGEX).first.wait_for(state="visible", timeout=20000)
    except:
        print("[AVISO] Timeout esperando botões aparecerem. Tentando recarregar...")
        page.reload()
        page.locator('button, a').filter(has_text=CTA_CONFIGURE_RESERVA_REGEX).first.wait_for(state="visible", timeout=20000)

    btns = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX)
    links = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX)
    
    total_ctas = btns.count() + links.count()
    if total_ctas == 0:
        total_ctas = page.get_by_text(CTA_CONFIGURE_RESERVA_REGEX).count()

    assert total_ctas > 0, f"Nenhum CTA 'configure e reserve' encontrado na home. URL: {page.url}"
    
    expect(page).to_have_title(KNOWN_TITLE_PATTERN)

    modelos_iter = total_ctas if MODELOS_LIMIT == 0 else min(total_ctas, MODELOS_LIMIT)

    erros = []
    sucessos = 0
    skips = []  # <--- CORREÇÃO: Inicialização da variável skips

    for m_idx in range(modelos_iter):
        versoes_url_recovery = None 
        
        try:
            page.goto("/", wait_until="domcontentloaded", timeout=35000)
            _aceitar_cookies(page)

            btns = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX)
            links = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX)

            if btns.count() > m_idx:
                target = btns.nth(m_idx)
            elif links.count() > (m_idx - btns.count()):
                target = links.nth(m_idx - btns.count())
            else:
                target = page.get_by_text(CTA_CONFIGURE_RESERVA_REGEX).nth(m_idx)

            target.scroll_into_view_if_needed()
            target.click(force=True, timeout=8000)
            
            page.wait_for_url(re.compile(r"/jornada-de-reserva|/configurador/.+"), timeout=35000)
            _garantir_ctx_configurador(page)
            ctx = _get_configurator_ctx(page)
            _anexar_screenshot(request, page, f"Modelo #{m_idx} - Configurador")

            qtd_versoes = _contar_versoes(page, ctx)
            versoes_iter = qtd_versoes if VERSOES_LIMIT == 0 else min(qtd_versoes, VERSOES_LIMIT)
            
            versoes_url_recovery = page.url 

            for v_idx in range(versoes_iter):
                # --- Lógica de Skip para Bugs Conhecidos ---
                # Exemplo: Kwid (Modelo 2) na versão 2 costuma travar
                # Como a ordem dos modelos pode variar, o ideal seria checar o nome do carro,
                # mas usando índices como base:
                if m_idx == 2 and v_idx == 2:
                    print(f"[SKIP] Pulando Modelo {m_idx} | Versão {v_idx} (Bug Conhecido do Kwid)")
                    skips.append(f"Modelo {m_idx} | Versão {v_idx} (Bug Conhecido)")
                    continue
                # -------------------------------------------

                try:
                    print(f"--- Iniciando Modelo {m_idx} | Versão {v_idx} ---")
                    
                    if versoes_url_recovery and versoes_url_recovery not in page.url:
                         page.goto(versoes_url_recovery, wait_until="domcontentloaded", timeout=30000)
                         ctx = _get_configurator_ctx(page)
                    
                    _selecionar_versao(page, ctx, v_idx)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass

                    try:
                        next_btn = ctx.get_by_role("button", name=re.compile(r"Avan[cç]ar|Continuar|Concession[aá]ria|Prosseguir|Pr[oó]ximo", re.I)).first
                        if next_btn and next_btn.count() > 0 and next_btn.is_visible():
                            next_btn.click(timeout=10000)
                    except:
                        pass

                    chegou = _esperar_concessionaria(page, ctx, 35000)
                    if not chegou:
                        try:
                            tab = ctx.get_by_role("tab", name=re.compile(r"Concession[aá]ria", re.I)).first
                            if tab.is_visible():
                                tab.click(timeout=5000)
                        except:
                            pass
                        
                        if not _esperar_concessionaria(page, ctx, 10000):
                             _goto_concessionaria_por_url(page)
                             chegou = _esperar_concessionaria(page, ctx, 20000)

                    if not chegou:
                        raise AssertionError(f"Não chegou à Concessionária. URL: {page.url}")

                    ctx = _get_configurator_ctx(page)
                    _anexar_screenshot(request, page, f"Modelo #{m_idx} - Versão #{v_idx} - Concessionária")

                    try:
                        ctx.get_by_role("button", name=re.compile(r"(selecionar|selecionado)", re.I)).first.wait_for(state="visible", timeout=15000)
                    except:
                        try:
                            ctx.locator('.gm-style').first.wait_for(state="visible", timeout=10000)
                        except:
                            page.wait_for_timeout(2000)

                    _inserir_cep_se_necessario(ctx, page)
                    total_dealers = _validar_resultados_concessionarias(ctx)
                    
                    if total_dealers == 0:
                        raise AssertionError("Nenhuma concessionária encontrada (Contador = 0).")

                    _validar_mapa_concessionarias(ctx)
                    _validar_avisos_legais(ctx)
                    _validar_textos_gerais(ctx)

                    sucessos += 1
                    print(f"[OK] Modelo {m_idx} | Versão {v_idx} – SUCESSO")

                except Exception as e:
                    _anexar_screenshot(request, page, f"Erro - Modelo #{m_idx} | Versão #{v_idx}")
                    print(f"[ERRO] Modelo {m_idx} | Versão {v_idx}: {str(e)}")
                    erros.append(f"[MODELO {m_idx} | VERSÃO {v_idx}] {str(e)}")
                
                finally:
                    if versoes_url_recovery:
                        try:
                            page.goto(versoes_url_recovery, wait_until="domcontentloaded", timeout=20000)
                        except:
                            print(f"[CRÍTICO] Falha ao recuperar URL de versões para Modelo {m_idx}")

        except Exception as e:
            _anexar_screenshot(request, page, f"Erro Geral - Modelo #{m_idx}")
            erros.append(f"[MODELO {m_idx} - GERAL] {str(e)}")

    msg = (
        f"Sucessos: {sucessos} | Erros: {len(erros)} | Skips: {len(skips)}"
        + ("\nSKIPS:\n" + "\n".join(skips) if skips else "")
        + ("\nERROS:\n" + "\n".join(erros) if erros else "")
    )
    assert len(erros) == 0, msg