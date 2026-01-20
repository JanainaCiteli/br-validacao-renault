import re, os, base64, pytest, pytest_html
from playwright.sync_api import Page, expect

CTA_CONFIGURE_RESERVA_REGEX = re.compile(r"(configure\s*e\s*reserve|configure|monte\s*o\s*seu|monte|reservar)", re.I)
URL_CFG_REGEX = re.compile(r"/configurador/.+/(versoes|design|cores|rodas|interior)", re.I)
URL_CONCESSIONARIA_REGEX = re.compile(r"/concessionari(a|as)|/dealers|/lojas|/ponto-de-venda|/r-pass/pre-venda/concessionaria", re.I)
MODELOS_LIMIT = int(os.getenv("MODELOS_LIMIT", "0") or "0")
VERSOES_LIMIT = int(os.getenv("VERSOES_LIMIT", "0") or "0")
CORES_LIMIT = int(os.getenv("CORES_LIMIT", "0") or "0")
RODAS_LIMIT = int(os.getenv("RODAS_LIMIT", "0") or "0")
INTERIOR_LIMIT = int(os.getenv("INTERIOR_LIMIT", "0") or "0")

from tests.test_configuracao_veiculo_v3 import (
    _aceitar_cookies, _carregar_toda_pagina, _get_configurator_ctx,
    _contar_versoes, _selecionar_versao, _forcar_carregamento_imagens_lazy,
    _esperar_imagens_visiveis, _validar_textos, _validar_valores,
    _coletar_opcoes, _ir_para_etapa, _clicar_avancar
)

def _anexar_screenshot(request, page: Page, titulo: str):
    try:
        shot = page.screenshot(full_page=False)
        b64 = base64.b64encode(shot).decode("utf-8")
        html = f"<details><summary>{titulo}</summary><img src='data:image/png;base64,{b64}' style='max-width:640px;border:1px solid #ccc'/></details>"
        extra = getattr(request.node.rep_call, "extra", [])
        extra.append(pytest_html.extras.html(html))
        request.node.rep_call.extra = extra
    except Exception:
        pass

def _status_badge(ok: bool, msg: str = "") -> str:
    if ok:
        return f"✅ OK"
    else:
        safe = (msg or "").replace("<","&lt;").replace(">","&gt;")
        return f"❌ {safe}"

def _adicionar_resumo_html(request, rows):
    headers = ["Modelo", "Versão", "Seleção de Versão", "Design/Inicial", "Cores", "Rodas", "Interior", "Concessionária"]
    th = "".join([f"<th style='padding:6px;border-bottom:1px solid #ccc;text-align:left'>{h}</th>" for h in headers])
    trs = []
    for r in rows:
        tds = "".join([f"<td style='padding:6px;border-bottom:1px solid #eee'>{c}</td>" for c in r])
        trs.append(f"<tr>{tds}</tr>")
    table = f"<details open><summary>📋 Matriz de Fases por Modelo/Versão</summary><table style='border-collapse:collapse'><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table></details>"
    extra = getattr(request.node.rep_call, "extra", [])
    extra.append(pytest_html.extras.html(table))
    request.node.rep_call.extra = extra

@pytest.mark.jornada
@pytest.mark.regressao
def test_e2e_matriz_jornadas(page: Page, request):
    page.set_default_timeout(25000)
    page.set_default_navigation_timeout(45000)

    # HOME
    page.goto("/", wait_until="domcontentloaded", timeout=35000)
    _aceitar_cookies(page)
    expect(page).to_have_title(re.compile("Renault", re.I))
    _carregar_toda_pagina(page)

    btns = page.get_by_role("button", name=CTA_CONFIGURE_RESERVA_REGEX)
    links = page.get_by_role("link", name=CTA_CONFIGURE_RESERVA_REGEX)
    total_ctas = btns.count() + links.count()
    if total_ctas == 0:
        total_ctas = page.get_by_text(CTA_CONFIGURE_RESERVA_REGEX).count()
    assert total_ctas > 0, "Nenhum CTA 'configure e reserve' encontrado na home."

    modelos_iter = total_ctas if MODELOS_LIMIT == 0 else min(total_ctas, MODELOS_LIMIT)

    rows = []
    houve_falha = False

    for m_idx in range(modelos_iter):
        # Reentra na home limpa
        page.goto("/", wait_until="domcontentloaded", timeout=35000)
        _aceitar_cookies(page)
        _carregar_toda_pagina(page)

        # Seleciona CTA
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
        _aceitar_cookies(page)

        ctx = _get_configurator_ctx(page)
        _anexar_screenshot(request, page, f"Modelo #{m_idx} - Configurador")

        qtd_versoes = _contar_versoes(page, ctx)
        versoes_iter = qtd_versoes if VERSOES_LIMIT == 0 else min(qtd_versoes, VERSOES_LIMIT)

        for v_idx in range(versoes_iter):
            fase = {
                "modelo": "DESCONHECIDO",
                "versao": "DESCONHECIDA",
                "sel_versao": (False, ""),
                "inicial": (False, ""),
                "cores": (False, ""),
                "rodas": (False, ""),
                "interior": (False, ""),
                "concessionaria": (False, "")
            }

            # Seleção de versão
            try:
                _selecionar_versao(page, ctx, v_idx)
                fase["sel_versao"] = (True, "")
            except Exception as e:
                fase["sel_versao"] = (False, str(e))
                houve_falha = True

            # Inicial (design/validações)
            try:
                _forcar_carregamento_imagens_lazy(ctx)
                _esperar_imagens_visiveis(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                _validar_textos(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                _validar_valores(ctx, f"Modelo {m_idx} | Versão {v_idx} | Inicial")
                fase["inicial"] = (True, "")
            except Exception as e:
                fase["inicial"] = (False, str(e))
                houve_falha = True
            _anexar_screenshot(request, page, f"Modelo #{m_idx} - Versão #{v_idx} - Inicial")

            # Cores
            try:
                _ir_para_etapa(ctx, "cor")
                loc = _coletar_opcoes(ctx, "cor")
                if loc.count() > 0:
                    total = min(loc.count(), CORES_LIMIT) if CORES_LIMIT > 0 else loc.count()
                    for i in range(total):
                        loc.nth(i).click(force=True, timeout=8000)
                        _forcar_carregamento_imagens_lazy(ctx)
                        _esperar_imagens_visiveis(ctx, f"Modelo {m_idx} | Versão {v_idx} | cor idx={i}")
                        _validar_textos(ctx, f"Modelo {m_idx} | Versão {v_idx} | cor idx={i}")
                        _validar_valores(ctx, f"Modelo {m_idx} | Versão {v_idx} | cor idx={i}")
                fase["cores"] = (True, "")
            except Exception as e:
                fase["cores"] = (False, str(e))
                houve_falha = True

            # Rodas
            try:
                _ir_para_etapa(ctx, "rodas")
                loc = _coletar_opcoes(ctx, "rodas")
                if loc.count() > 1:
                    total = min(loc.count(), RODAS_LIMIT) if RODAS_LIMIT > 0 else loc.count()
                    for i in range(total):
                        loc.nth(i).click(force=True, timeout=8000)
                        _forcar_carregamento_imagens_lazy(ctx)
                        _esperar_imagens_visiveis(ctx, f"Modelo {m_idx} | Versão {v_idx} | rodas idx={i}")
                        _validar_textos(ctx, f"Modelo {m_idx} | Versão {v_idx} | rodas idx={i}")
                        _validar_valores(ctx, f"Modelo {m_idx} | Versão {v_idx} | rodas idx={i}")
                fase["rodas"] = (True, "")
            except Exception as e:
                fase["rodas"] = (False, str(e))
                houve_falha = True

            # Interior
            try:
                _ir_para_etapa(ctx, "interior")
                loc = _coletar_opcoes(ctx, "interior")
                if loc.count() > 0:
                    total = min(loc.count(), INTERIOR_LIMIT) if INTERIOR_LIMIT > 0 else loc.count()
                    for i in range(total):
                        loc.nth(i).click(force=True, timeout=8000)
                        _forcar_carregamento_imagens_lazy(ctx)
                        _esperar_imagens_visiveis(ctx, f"Modelo {m_idx} | Versão {v_idx} | interior idx={i}")
                        _validar_textos(ctx, f"Modelo {m_idx} | Versão {v_idx} | interior idx={i}")
                        _validar_valores(ctx, f"Modelo {m_idx} | Versão {v_idx} | interior idx={i}")
                fase["interior"] = (True, "")
            except Exception as e:
                fase["interior"] = (False, str(e))
                houve_falha = True

            # Concessionária
            try:
                _clicar_avancar(ctx, f"Modelo {m_idx} | Versão {v_idx} | Final")
                page.wait_for_url(URL_CONCESSIONARIA_REGEX, timeout=35000)
                fase["concessionaria"] = (True, "")
            except Exception as e:
                fase["concessionaria"] = (False, str(e))
                houve_falha = True

            # Nome modelo/versão a partir da URL/elementos
            try:
                m = re.search(r"/configurador/([^/]+)/", page.url, re.I)
                if m:
                    fase["modelo"] = m.group(1).upper()
            except Exception:
                pass
            fase["versao"] = f"#{v_idx}"

            rows.append([
                fase["modelo"],
                fase["versao"],
                _status_badge(*fase["sel_versao"]),
                _status_badge(*fase["inicial"]),
                _status_badge(*fase["cores"]),
                _status_badge(*fase["rodas"]),
                _status_badge(*fase["interior"]),
                _status_badge(*fase["concessionaria"]),
            ])

    _adicionar_resumo_html(request, rows)
    assert not houve_falha, "Há falhas nas fases. Consulte a matriz de jornadas anexada ao relatório."
