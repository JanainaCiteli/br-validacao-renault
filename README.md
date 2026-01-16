# Validação E-Comm Renault (Playwright + Pytest)

Este projeto realiza validações automatizadas da home da Renault, com geração de relatórios completos (HTML/JUnit + evidências) e execução em CI via GitHub Actions.

## 🚀 Stack
- Python + Pytest
- Playwright (pytest-playwright)
- pytest-html (relatório interativo)
- pytest-xdist (paralelismo)
- pytest-rerunfailures (rerun automático para reduzir flakiness)
- GitHub Actions (CI)

---

## ▶️ Execução local

1. Instale dependências e browsers:
```bash
pip install -r requirements.txt
pip install playwright
python -m playwright install --with-deps
```

2. Rode os testes:
```bash
python run_tests.py
```

3. Personalize opcionalmente (Linux/macOS):
```bash
BASE_URL=https://loja.renault.com.br/ BROWSER=chromium python run_tests.py
```

4. Personalize no Windows:

- PowerShell:
```powershell
$env:BASE_URL="https://loja.renault.com.br/"; $env:BROWSER="chromium"; python run_tests.py
```

- CMD (Prompt de Comando):
```bat
set BASE_URL=https://loja.renault.com.br/
set BROWSER=chromium
python run_tests.py
```

Ou em uma única linha no CMD:
```bat
set BASE_URL=https://loja.renault.com.br/ & set BROWSER=chromium & python run_tests.py
```

- Relatórios serão gerados em `reports/<timestamp>/`:
  - `relatorio_renault.html` (interativo, auto-contido)
  - `junit.xml`
  - Evidências: `screenshots/`, `traces/`, `videos/`, `logs/`

- Uma cópia do relatório é salva na raiz do repo para rápida visualização:
  - `relatorio_renault.html`

> Para abrir ordenado por resultado (como no exemplo):
> `file:///C:/git-projetos/renault/br/br-ecomm-validacao/validacao-renault-py/relatorio_renault.html?sort=result`

> Observação: O runner adiciona automaticamente `--reruns=1` para reduzir flakiness em ambientes locais e de CI.

---

## 🌐 Base URL via --base-url

Os testes agora usam `page.goto("/")`. Configure a base URL com a flag `--base-url` do pytest-playwright (o runner já injeta via variável de ambiente):

- Local (via runner):
  - `BASE_URL=https://loja.renault.com.br/ python run_tests.py`

- Direto com pytest (exemplo Linux/macOS):
```bash
pytest --base-url https://loja.renault.com.br/ --browser chromium \
  --html=reports/$(date +%F_%H-%M-%S)/relatorio_renault.html --self-contained-html \
  --junitxml=reports/$(date +%F_%H-%M-%S)/junit.xml
```

- Direto com pytest (exemplo Windows PowerShell):
```powershell
pytest --base-url https://loja.renault.com.br/ --browser chromium `
  --html="reports/$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')/relatorio_renault.html" --self-contained-html `
  --junitxml="reports/$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')/junit.xml"
```

- 🚬 Smoke Test:
```powershell
$env:MODELOS_LIMIT="1"; $env:VERSOES_LIMIT="1"; $env:WORKERS="1"; python run_tests.py -m smoke
---

## 🤖 CI (GitHub Actions)

Arquivo: `.github/workflows/ci.yml`

- Matrix de navegadores: `chromium`, `firefox`, `webkit`
- Instala `playwright` browsers
- Gera relatórios por navegador e faz upload como artifacts
- O runner já inclui `--reruns=1` para reduzir flakiness

Badge (já no topo do README):

[![CI - e2e-tests](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml/badge.svg)](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml)

---

## 📦 Estrutura do projeto

```
validacao-renault-py/
├─ tests/
│  ├─ test_home_renault.py
├─ reports/
│  └─ <timestamp>/
│     ├─ relatorio_renault.html
│     ├─ junit.xml
│     ├─ screenshots/
│     ├─ traces/
│     ├─ videos/
│     └─ logs/
├─ .github/workflows/ci.yml
├─ conftest.py
├─ pytest.ini
├─ requirements.txt
├─ run_tests.py
├─ .gitignore
├─ README.md
└─ relatorio_renault.html (cópia rápida do último relatório)
```

---

## 🧪 Dicas de testes

- Preferir seletores estáveis (ex.: `data-testid`) para reduzir flakiness
- Utilizar `expect(...).to_be_visible()` com timeout apropriado
- Evitar asserts em conteúdo não determinístico (ex.: contagem exata de cards)

---

## 🧹 Limpeza de arquivos rastreados indevidos

Se `venv/`, `.pytest_cache/` ou relatórios antigos estiverem versionados, execute:
```bash
git rm -r --cached venv/ .pytest_cache/ reports/ relatorio_renault.html
git add .
git commit -m "chore: aplicar .gitignore e limpar artifacts"
```

---


