import os
import time
import shutil
import html as _html
from pathlib import Path
import datetime
import pytest
import pytest_html

# -----------------------------------------------------------------------------
# 1. GERENCIAMENTO DE DIRETÓRIOS (RESTAURANDO O PADRÃO ANTIGO)
# -----------------------------------------------------------------------------

def _get_reports_root(config=None) -> Path:
    """
    Recupera o diretório definido pelo run_tests.py.
    Se não existir (rodando via pycharm/terminal direto), cria um timestamp.
    """
    env_path = os.getenv("REPORTS_DIR")
    if env_path:
        return Path(env_path)

    base_opt = getattr(config.option, "reports_dir", None) if config else None
    if base_opt:
        return Path(base_opt)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("reports") / ts

def _ensure_dir_exists(p: Path, retries: int = 5, delay: float = 0.2) -> Path:
    """Criação segura de diretórios em paralelo."""
    for _ in range(retries):
        try:
            p.mkdir(parents=True, exist_ok=True)
            if p.exists(): return p
        except PermissionError:
            time.sleep(delay)
    p.mkdir(parents=True, exist_ok=True)
    return p

@pytest.fixture(scope="session")
def reports_dir(pytestconfig):
    return _get_reports_root(pytestconfig)

def pytest_configure(config):
    """
    Configura o pytest-html e o Playwright para usarem a MESMA pasta.
    Isso evita a criação da pasta 'test-results' solta na raiz.
    """
    root = _get_reports_root(config)
    setattr(config, "_reports_dir", str(root))
    setattr(config, "_skip_count", 0)

    # Apenas o processo principal cria as pastas
    if not hasattr(config, "workerinput"):
        _ensure_dir_exists(root)
        _ensure_dir_exists(root / "logs")

    # 1. Configura Output do Playwright (Vídeos/Traces)
    if not getattr(config.option, "output", None):
        config.option.output = str(root)

    # 2. Configura Relatório HTML
    html_plugin = config.pluginmanager.getplugin("html")
    if html_plugin:
        if not getattr(config.option, "htmlpath", None):
            config.option.htmlpath = str(root / "relatorio_renault.html")
        setattr(config.option, "self_contained_html", True)

def pytest_html_report_title(report):
    report.title = "Relatório Unificado Renault"

# -----------------------------------------------------------------------------
# 2. PONTE PARA EVITAR ERROS E COLETAR EVIDÊNCIAS (FIX CRÍTICO)
# -----------------------------------------------------------------------------

class MockReport:
    """Objeto falso para receber anexos durante a execução do teste."""
    def __init__(self):
        self.extra = []

@pytest.fixture(scope="function", autouse=True)
def patch_rep_call(request):
    """
    INJETA 'rep_call' no node do teste ANTES dele rodar.
    Isso corrige o 'AttributeError: Function object has no attribute rep_call'.
    """
    # Cria o mock e anexa ao item (request.node)
    mock = MockReport()
    setattr(request.node, "rep_call", mock)
    
    yield
    
    # Opcional: limpeza pós-teste
    pass

@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """
    Hook que roda DEPOIS de cada etapa (setup, call, teardown).
    Aqui pegamos as evidências do Mock e passamos para o Relatório Real.
    """
    outcome = yield
    rep = outcome.get_result()
    
    # Define rep_... no item para acesso posterior (padrão pytest-html)
    setattr(item, "rep_" + rep.when, rep)

    # Agora processa anexos tanto no 'call' quanto no 'teardown'
    if rep.when in ("call", "teardown"):
        # Inicializa lista de extras se não existir
        current_extras_attr = getattr(rep, "extra", [])
        current_extras = list(current_extras_attr) if isinstance(current_extras_attr, list) else []
        
        # 1. Recupera extras que o teste colocou no Mock (item.rep_call.extra)
        mock_rep = getattr(item, "rep_call", None)
        if mock_rep and hasattr(mock_rep, "extra") and mock_rep.extra:
            current_extras.extend(mock_rep.extra)
        
        # 2. Recupera extras colocados diretamente em item.extras (conftest antigo)
        item_extras = getattr(item, "extras", [])
        if item_extras:
            current_extras.extend(item_extras)
        
        rep.extra = current_extras

    # Contagem de Skips
    try:
        if rep.outcome == "skipped":
            config = item.config
            c = getattr(config, "_skip_count", 0)
            setattr(config, "_skip_count", c + 1)
    except:
        pass

# -----------------------------------------------------------------------------
# 3. CAPTURA DE LOGS E DETALHES VISUAIS
# -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _attach_logs_extras(request, page, reports_dir):
    """Captura logs do console do browser e anexa ao relatório."""
    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"[ERROR] {err}"))

    yield

    if logs:
        # Salva em arquivo
        log_file = reports_dir / "logs" / f"{request.node.name}.txt"
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(logs))
        except: pass

        # Anexa ao HTML (usando a ponte do Mock ou direto se o hook já rodou)
        # Como este fixture roda no teardown, anexamos ao mock que o hook vai ler depois
        html_log = f"<details><summary>Logs do Console ({len(logs)})</summary><pre>{_html.escape(chr(10).join(logs))}</pre></details>"
        
        target = getattr(request.node, "rep_call", None)
        if target:
            target.extra.append(pytest_html.extras.html(html_log))

# Fixture global para consentimento e geolocalização (antes da navegação)
@pytest.fixture(autouse=True)
def _consent_and_geo(page):
    try:
        # Permissões e geolocalização fixa (SP)
        page.context.grant_permissions(["geolocation"])  # type: ignore[attr-defined]
        page.context.set_geolocation({"latitude": -23.55052, "longitude": -46.633308})  # type: ignore[attr-defined]
    except Exception:
        pass

    # Injeta consentimento no init script (antes de qualquer script da página)
    try:
        page.add_init_script(
            """
            (() => {
              try {
                localStorage.setItem('REN_ACCEPTED_TRUST', JSON.stringify([
                  'web-analysis','content-preferences','marketing','social-media'
                ]));
                localStorage.setItem('REN_BYPASS', 'true');
                // Local opcional para reduzir efeitos de geolocalização
                localStorage.setItem('REN_LOCATION', JSON.stringify({
                  city: { name: 'São Paulo', location: { latitude: -23.55, longitude: -46.63 } }
                }));
              } catch(e) {}
            })();
            """
        )
    except Exception:
        pass

    # Cookie opcional para reforçar bypass
    try:
        page.context.add_cookies([{
            "name": "REN_BYPASS", "value": "true",
            "domain": "loja.renault.com.br", "path": "/",
            "expires": int(time.time()) + 86400*180,
            "sameSite": "Lax", "httpOnly": False, "secure": True,
        }])
    except Exception:
        pass

    # Remoção best-effort de overlays modais residuais
    try:
        page.evaluate("""
            (() => {
              const sels = ['.chakra-modal__overlay', '.chakra-modal__content-container', '[role="dialog"]', '[aria-modal="true"]'];
              sels.forEach(sel => document.querySelectorAll(sel).forEach(el => { try { el.remove(); } catch(e){} }));
            })();
        """)
    except Exception:
        pass

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {"width": 1280, "height": 720},
        "locale": "pt-BR",
        "timezone_id": "America/Sao_Paulo",
        "geolocation": {"latitude": -23.5505, "longitude": -46.6333},
        "permissions": ["geolocation"],
        "ignore_https_errors": True
    }

@pytest.fixture(scope="function", autouse=True)
def setup_timeouts(page):
    page.set_default_timeout(45000)
    page.set_default_navigation_timeout(60000)
    yield

def pytest_html_results_summary(prefix, summary, postfix):
    try:
        config = summary.session.config
        skips = getattr(config, "_skip_count", 0)
        report_path = getattr(config, "_reports_dir", "N/A")
        
        prefix.extend([pytest_html.extras.html(f"<p><strong>📂 Pasta de Evidências:</strong> {report_path}</p>")])
        if skips > 0:
            prefix.extend([pytest_html.extras.html(f"<p style='color:orange'>⚠️ <strong>Skips:</strong> {skips} testes pulados.</p>")])
    except:
        pass
