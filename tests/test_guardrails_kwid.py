import re
import os
import pytest
from playwright.sync_api import Page, expect

URL_BASE = os.getenv("BASE_URL", "https://loja.renault.com.br/")

def _aceitar_cookies(page: Page):
    try:
        page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass
    for sel in [
        '#onetrust-accept-btn-handler',
        'button:has-text("aceitar")',
        'button:has-text("Aceitar")',
        'role=button[name=/aceitar|accept|concordo|ok/i]',
    ]:
        try:
            btn = page.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                btn.click(force=True, timeout=4000)
                break
        except Exception:
            pass

def _get_configurator_ctx(page: Page):
    for f in page.frames:
        try:
            if "/configurador/" in (f.url or ""):
                return f
        except Exception:
            pass
    return page

def _combo_versao_info(ctx):
    try:
        combo = ctx.get_by_role("combobox", name=re.compile(r"Vers[aã]o", re.I)).first
        if combo and combo.count() > 0:
            el = combo.element_handle()
            if el:
                cid = el.get_attribute("aria-controls")
                return combo, cid
    except Exception:
        pass
    return None, None

@pytest.mark.smoke
@pytest.mark.regressao
# @pytest.mark.xfail(reason="Bug Conhecido: Kwid Versão 2 não carrega opções de Design") # Descomente se quiser que fique Laranja (XFAIL)
def test_kwid_versao2_avanca_para_design(page: Page):
    # Vai direto para /configurador/kwid/versoes
    page.goto(URL_BASE.rstrip("/") + "/configurador/kwid/versoes", wait_until="domcontentloaded", timeout=45000)
    _aceitar_cookies(page)
    ctx = _get_configurator_ctx(page)

    # Tenta selecionar a versão 2 (idx=1)
    print("Tentando selecionar Kwid Versão 2...")
    combo, cid = _combo_versao_info(ctx)
    
    if combo:
        combo.click(timeout=6000)
        options = ctx.locator(f'#{cid} [role="option"]') if cid else ctx.locator('[role="listbox"] [role="option"]')
        total = options.count()
        assert total >= 2, f"Esperado ao menos 2 versões para KWID, encontrado: {total}"
        options.nth(1).click(timeout=8000)
    else:
        # Botões/cartas na rota de versões
        btns = ctx.get_by_role("button", name=re.compile(r"Configurar|Selecionar|Escolher", re.I))
        # Filtra botões de acessibilidade se necessário
        valid_btns = btns.locator("visible=true") 
        if valid_btns.count() >= 2:
             valid_btns.nth(1).click(timeout=10000)
        else:
             # Fallback agressivo se não achar botões
             btns.first.click(timeout=10000)

    # Aguarda avançar para /design
    page.wait_for_url(re.compile(r"/configurador/kwid/design"), timeout=35000)
    
    # --- AQUI ESTA A CORREÇÃO ---
    # O teste antigo parava aqui. Agora vamos verificar se a tela NÃO está branca/quebrada.
    
    print("Validando carregamento das opções de Design (Cor/Interior)...")
    
    # Procura por elementos típicos de seleção de cor ou loaders infinitos
    # Se a página estiver em branco ou com erro, isso vai falhar (o que queremos para reportar o bug)
    try:
        # Tentativa 1: Seletores CSS válidos (sem misturar com text)
        seletor_opcoes = ctx.locator('[data-testid*="color"], [role="radio"], .color-selector').first
        # Tentativa 2: Busca por texto separadamente
        texto_cor = ctx.get_by_text(re.compile(r"Cor|Color", re.I)).first
        
        # Verifica se pelo menos um dos seletores encontra elementos visíveis
        opcoes_encontradas = False
        if seletor_opcoes.count() > 0:
            try:
                expect(seletor_opcoes).to_be_visible(timeout=5000)
                opcoes_encontradas = True
            except AssertionError:
                pass
        
        if not opcoes_encontradas and texto_cor.count() > 0:
            try:
                expect(texto_cor).to_be_visible(timeout=5000)
                opcoes_encontradas = True
            except AssertionError:
                pass
        
        if not opcoes_encontradas:
            raise AssertionError("Nenhuma opção de Design visível encontrada")
            
    except AssertionError as e:
        # Tira um screenshot para evidência no relatório antes de falhar
        page.screenshot(path="evidencia_erro_kwid.png")
        raise AssertionError("O KWID Versão 2 avançou a URL, mas não carregou as opções de Design (Tela branca ou sem interatividade).") from e

    print("Opções de design carregadas com sucesso.")