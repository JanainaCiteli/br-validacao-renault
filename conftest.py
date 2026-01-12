import os
import html as _html
from pathlib import Path
import pytest
import pytest_html

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DE DIRETÓRIOS
# -----------------------------------------------------------------------------

def _get_reports_root(config=None) -> Path:
    """
    Recupera o diretório de relatório único definido pelo run_tests.py.
    Se não houver variável de ambiente (rodando pytest direto), cria um fallback.
    """
    # Tenta pegar a variável definida no run_tests.py (Recomendado)
    env_path = os.getenv("REPORTS_DIR")
    if env_path:
        return Path(env_path)
    
    # Fallback caso rode 'pytest' direto no terminal sem o script python
    # (Ainda pode gerar pastas duplicadas em paralelo se usar este modo)
    base_opt = getattr(config.option, "reports_dir", None) if config else None
    if base_opt:
        return Path(base_opt)
        
    return Path("reports") / "temp_execution"

@pytest.fixture(scope="session")
def reports_dir():
    root = _get_reports_root()
    # Garante estrutura básica
    for folder in ["logs"]:
        (root / folder).mkdir(parents=True, exist_ok=True)
    return root

def pytest_configure(config):
    """Configura caminhos do relatório HTML e Output do Playwright"""
    root = _get_reports_root(config)
    
    # Se o output do Playwright não foi definido via CLI, define aqui
    if not config.option.output:
        config.option.output = str(root)

    # Configura relatório HTML se não definido
    html_plugin = config.pluginmanager.getplugin("html")
    if html_plugin:
        if not getattr(config.option, "htmlpath", None):
            config.option.htmlpath = str(root / "relatorio_renault.html")
        setattr(config.option, "self_contained_html", True)

def pytest_html_report_title(report):
    report.title = "Relatório Unificado Renault"

# -----------------------------------------------------------------------------
# SETUP E ARTEFATOS
# -----------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "geolocation": {"latitude": -23.5505, "longitude": -46.6333},
        "permissions": ["geolocation"],
        "locale": "pt-BR",
        "timezone_id": "America/Sao_Paulo",
        # Viewport maior para garantir que o vídeo fique bom
        "viewport": {"width": 1280, "height": 720}
    }

# Hook para capturar logs (Mantido igual)
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)

@pytest.fixture(autouse=True)
def _attach_logs_extras(request, page, reports_dir: Path):
    logs = []
    page.on("console", lambda msg: logs.append(f"[console] {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"[error] {err}"))
    
    yield

    if logs:
        # Salva log na pasta correta (logs/) dentro do report_root
        log_file = reports_dir / "logs" / f"{request.node.name}.txt"
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(logs))
        except: pass
        
        # Anexa ao HTML
        if hasattr(request.node, "rep_call"):
            extra = getattr(request.node.rep_call, "extra", [])
            escaped = _html.escape("\n".join(logs))
            html = f'<details><summary>Logs</summary><pre>{escaped}</pre></details>'
            extra.append(pytest_html.extras.html(html))
            request.node.rep_call.extra = extra