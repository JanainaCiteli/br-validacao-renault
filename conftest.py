import os
import time
import html as _html
from pathlib import Path
import datetime
import pytest
import pytest_html

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO DE DIRETÓRIOS E RESUMO
# -----------------------------------------------------------------------------

def _get_reports_root(config=None) -> Path:
    """
    Recupera o diretório de relatório único definido pelo run_tests.py via REPORTS_DIR.
    Se não houver variável de ambiente (rodando pytest direto), cria um fallback temporal.
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
    """Cria diretórios de forma resiliente a condição de corrida no Windows.
    Se outro worker criar a pasta "ao mesmo tempo", tolera PermissionError e segue.
    """
    for _ in range(retries):
        try:
            p.mkdir(parents=True, exist_ok=True)
            if p.exists() and p.is_dir():
                return p
        except PermissionError:
            # Outro processo pode ter criado no exato momento
            if p.exists() and p.is_dir():
                return p
            time.sleep(delay)
    # Última tentativa (propaga erro se realmente não conseguir)
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture(scope="session")
def reports_dir(pytestconfig):
    """Retorna o diretório raiz de relatórios definido em pytest_configure."""
    root = getattr(pytestconfig, "_reports_dir", None)
    if root:
        return Path(root)
    # Fallback extremo (não deveria ocorrer, pois pytest_configure sempre roda antes)
    return _get_reports_root(pytestconfig)

@pytest.fixture(scope="function", autouse=True)
def setup_timeouts(page):
    """
    Aumenta os timeouts padrão para evitar flakiness no CI/GitHub Actions.
    """
    # Timeout para ações (click, fill, etc) - Aumentar de 30s para 45s
    page.set_default_timeout(45000)
    
    # Timeout para navegação (goto, reload) - Aumentar de 30s para 60s
    page.set_default_navigation_timeout(60000)
    
    yield

def pytest_configure(config):
    """Configura caminhos do relatório HTML e Output do Playwright, além de variáveis de execução."""
    root = _get_reports_root(config)

    # Armazena caminhos/coletores globais no config
    setattr(config, "_reports_dir", str(root))
    setattr(config, "_incidentes", [])
    setattr(config, "_diagnostico_linhas", [])

    # Evita condição de corrida: apenas o controlador cria as pastas
    is_worker = hasattr(config, "workerinput")  # True nos workers do xdist
    if not is_worker:
        _ensure_dir_exists(root)
        _ensure_dir_exists(root / "logs")

    # Se o output do Playwright não foi definido via CLI, define aqui
    if not getattr(config.option, "output", None):
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
        "viewport": {"width": 1280, "height": 720},
    }


# Hook para registrar fases e permitir anexar extras posteriormente
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
    # Mescla extras acumulados em item.extras no rep_call
    if rep.when == "call":
        rep.extra = getattr(rep, "extra", [])
        extras = getattr(item, "extras", [])
        if extras:
            rep.extra.extend(extras)
            item.extras = []


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
            _ensure_dir_exists(log_file.parent)
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("\n".join(logs))
        except Exception:
            pass

        # Anexa ao HTML
        if hasattr(request.node, "rep_call"):
            extra = getattr(request.node.rep_call, "extra", [])
            escaped = _html.escape("\n".join(logs))
            html = f'<details><summary>Logs</summary><pre>{escaped}</pre></details>'
            extra.append(pytest_html.extras.html(html))
            request.node.rep_call.extra = extra


# -----------------------------------------------------------------------------
# HELPERS PARA EXTRAS E RESUMO HTML
# -----------------------------------------------------------------------------

def _add_html_extra(item, html_str: str):
    """Permite que os testes anexem blocos HTML ricos ao relatório."""
    ex = getattr(item, "extras", [])
    ex.append(pytest_html.extras.html(html_str))
    item.extras = ex


# Resumo no topo do HTML

def pytest_html_results_summary(prefix, summary, postfix):
    try:
        session = summary.session  # pytest-html >=4
        config = session.config
    except Exception:
        config = None
    reports_dir = getattr(config, "_reports_dir", None) if config else None
    incidentes = getattr(config, "_incidentes", []) if config else []

    # pytest-html >= 4 removeu o helper `html` baseado em py.xml
    # Para inserir HTML no resumo, use extras.html com markup explícito
    if reports_dir:
        prefix.extend([pytest_html.extras.html(f"<p>Pasta de evidências: {reports_dir}</p>")])
    if incidentes:
        prefix.extend([pytest_html.extras.html(f"<p>⚠️ Incidentes detectados: {len(incidentes)} (detalhes nos extras)</p>")])
    else:
        prefix.extend([pytest_html.extras.html("<p>✅ Nenhum incidente detectado.</p>")])
