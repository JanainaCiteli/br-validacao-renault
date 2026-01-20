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

    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
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
    return _get_reports_root(pytestconfig)

def pytest_configure(config):
    """
    Configura caminhos do relatório HTML e Output do Playwright, além de variáveis de execução.
    Mantém a mesma estrutura da pasta antiga para garantir coleta correta de relatórios.
    """
    root = _get_reports_root(config)

    # Armazena caminhos/coletores globais no config
    setattr(config, "_reports_dir", str(root))
    setattr(config, "_skip_count", 0)

    # Evita condição de corrida: apenas o controlador cria as pastas
    is_worker = hasattr(config, "workerinput")  # True nos workers do xdist
    if not is_worker:
        _ensure_dir_exists(root)
        _ensure_dir_exists(root / "logs")

    # Se o output do Playwright não foi definido via CLI, define aqui
    # Mesmo quando definido via CLI, garantimos que está usando o caminho correto
    output_path = getattr(config.option, "output", None)
    if not output_path:
        config.option.output = str(root)
    else:
        # Normaliza os caminhos para comparação
        try:
            output_resolved = Path(output_path).resolve()
            root_resolved = root.resolve()
            if output_resolved != root_resolved:
                config.option.output = str(root)
        except Exception:
            # Se houver erro na comparação, força o uso do root
            config.option.output = str(root)

    # Configura relatório HTML se não definido
    html_plugin = config.pluginmanager.getplugin("html")
    if html_plugin:
        # Sempre força o caminho correto do HTML, mesmo se definido no pytest.ini
        config.option.htmlpath = str(root / "relatorio_renault.html")
        setattr(config.option, "self_contained_html", True)

    # Configura junitxml se não definido ou se não estiver apontando para a pasta correta
    junit_path = getattr(config.option, "junitxml", None)
    if not junit_path or not str(junit_path).startswith(str(root)):
        config.option.junitxml = str(root / "junit.xml")

def pytest_html_report_title(report):
    report.title = "Relatório Unificado Renault"

# -----------------------------------------------------------------------------
# 2. HOOKS PARA ANEXAR EVIDÊNCIAS SEM INTERFERIR NO CICLO DO PYTEST
# -----------------------------------------------------------------------------

# Hook para registrar fases e permitir anexar extras posteriormente
@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """
    Hook que roda DEPOIS de cada etapa (setup, call, teardown).
    Mantém compatibilidade com a estrutura antiga.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
    
    # Mescla extras acumulados em item.extras no rep_call (padrão da pasta antiga)
    if rep.when == "call":
        rep.extra = getattr(rep, "extra", [])
        extras = getattr(item, "extras", [])
        if extras:
            rep.extra.extend(extras)
            item.extras = []
    
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
def _attach_logs_extras(request, page, reports_dir: Path):
    """Captura logs do console do browser e anexa ao relatório."""
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

        # Anexa ao HTML (compatível com estrutura antiga)
        if hasattr(request.node, "rep_call"):
            extra = getattr(request.node.rep_call, "extra", [])
            escaped = _html.escape("\n".join(logs))
            html = f'<details><summary>Logs</summary><pre>{escaped}</pre></details>'
            extra.append(pytest_html.extras.html(html))
            request.node.rep_call.extra = extra
        else:
            # Fallback: adiciona em item.extras se rep_call não existir
            if not hasattr(request.node, "extras"):
                request.node.extras = []
            escaped = _html.escape("\n".join(logs))
            html = f'<details><summary>Logs</summary><pre>{escaped}</pre></details>'
            request.node.extras.append(pytest_html.extras.html(html))

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
    """Resumo no topo do HTML - mantém estrutura da pasta antiga."""
    try:
        session = summary.session  # pytest-html >=4
        config = session.config
    except Exception:
        config = None
    reports_dir = getattr(config, "_reports_dir", None) if config else None
    skips = getattr(config, "_skip_count", 0) if config else 0

    # pytest-html >= 4 removeu o helper `html` baseado em py.xml
    # Para inserir HTML no resumo, use extras.html com markup explícito
    if reports_dir:
        prefix.extend([pytest_html.extras.html(f"<p>Pasta de evidências: {reports_dir}</p>")])
    if skips > 0:
        prefix.extend([pytest_html.extras.html(f"<p>⚠️ Skips: {skips} testes pulados.</p>")])

def pytest_sessionfinish(session, exitstatus):
    """
    Hook executado ao final da sessão de testes.
    Garante que os arquivos de relatório sejam gerados/movidos para o local correto.
    """
    try:
        config = session.config
        root_str = getattr(config, "_reports_dir", "")
        if not root_str:
            return
        
        root = Path(root_str)
        
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
        
        # Apenas o processo principal faz a limpeza (não workers)
        if hasattr(config, "workerinput"):
            return
        
        # 1. Move/copia relatorio_renault.html se estiver na raiz ou em outro lugar
        root_html = Path("relatorio_renault.html")
        target_html = root / "relatorio_renault.html"
        if root_html.exists() and root_html.resolve() != target_html.resolve():
            try:
                shutil.copy2(root_html, target_html)
            except Exception:
                pass
        
        # 2. Move/copia junit.xml se estiver em outro lugar
        root_junit = Path("junit.xml")
        target_junit = root / "junit.xml"
        if root_junit.exists() and root_junit.resolve() != target_junit.resolve():
            try:
                shutil.copy2(root_junit, target_junit)
            except Exception:
                pass
        
        # 3. Verifica se há pasta test-results na raiz e move conteúdo para reports
        # Isso garante que vídeos, screenshots e trace.zip sejam coletados
        test_results_root = Path("test-results")
        if test_results_root.exists() and test_results_root.is_dir():
            try:
                # Move todas as pastas de testes para dentro do report_root
                for item in test_results_root.iterdir():
                    if item.is_dir() and not item.name.startswith('.'):
                        target_dir = root / item.name
                        if target_dir.exists():
                            # Se já existe, mescla o conteúdo (especialmente para trace.zip, vídeos, screenshots)
                            for file in item.rglob("*"):
                                if file.is_file():
                                    rel_path = file.relative_to(item)
                                    target_file = target_dir / rel_path
                                    target_file.parent.mkdir(parents=True, exist_ok=True)
                                    # Sempre copia, substituindo se existir (garante que trace.zip seja atualizado)
                                    shutil.copy2(file, target_file)
                        else:
                            # Move a pasta inteira
                            shutil.move(str(item), str(target_dir))
            except Exception:
                # Não falha o teste se não conseguir mover
                pass
        
        # 4. Garante que os arquivos principais existam (mesmo que vazios, para indicar que o teste rodou)
        if not target_html.exists():
            try:
                target_html.touch()
            except Exception:
                pass
        if not target_junit.exists():
            try:
                target_junit.write_text('<?xml version="1.0" encoding="utf-8"?><testsuites></testsuites>')
            except Exception:
                pass
    except Exception:
        # Não falha o teste se houver erro na limpeza
        pass
