# Validação E-Comm Renault (Playwright + Pytest)

Este projeto realiza validações automatizadas da jornada E-Comm da Renault, com geração de relatórios completos (HTML/JUnit + evidências) e execução em CI via GitHub Actions.

[![CI - e2e-tests](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml/badge.svg)](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml)

## 🚀 Stack
- Python + Pytest
- Playwright (pytest-playwright)
- pytest-html (relatório interativo)
- pytest-xdist (paralelismo)
- pytest-rerunfailures (rerun automático para reduzir flakiness)
- GitHub Actions (CI)

---

## ▶️ Execução local

1) Instale dependências e browsers:
```bash
pip install -r requirements.txt
pip install playwright
python -m playwright install --with-deps
```

2) E2E ponta a ponta com evidências (recomendado):
```bash
python run_tests.py -k test_e2e_matriz_jornadas
```

- O runner força:
  - --output=reports/<timestamp>
  - --video=on
  - --screenshot=on
  - --tracing=on
  - --html=reports/<timestamp>/relatorio_renault.html
  - --junitxml=reports/<timestamp>/junit.xml

3) Personalize por ambiente:
- Linux/macOS:
```bash
BASE_URL=https://loja.renault.com.br/ BROWSER=chromium python run_tests.py -k test_e2e_matriz_jornadas
```

- Windows PowerShell:
```powershell
$env:BASE_URL="https://loja.renault.com.br/"; $env:BROWSER="chromium"; python run_tests.py -k test_e2e_matriz_jornadas
```

- Windows CMD:
```bat
set BASE_URL=https://loja.renault.com.br/
set BROWSER=chromium
python run_tests.py -k test_e2e_matriz_jornadas
```

4) Smoke E2E rápido (limitar modelos/versões e workers):
- Linux/macOS:
```bash
MODELOS_LIMIT=1 VERSOES_LIMIT=1 WORKERS=1 python run_tests.py -k test_e2e_matriz_jornadas
```

- Windows PowerShell:
```powershell
$env:MODELOS_LIMIT="1"; $env:VERSOES_LIMIT="1"; $env:WORKERS="1"; python run_tests.py -k test_e2e_matriz_jornadas
```

5) Relatórios serão gerados em reports/<timestamp>/:
- relatorio_renault.html (interativo, auto-contido)
- junit.xml
- Evidências: screenshots/, traces/, videos/, logs/
- Uma cópia rápida do HTML é salva na raiz: relatorio_renault.html

> Para abrir ordenado por resultado:
> file:///C:/git-projetos/renault/br/br-ecomm-validacao/relatorio_renault.html?sort=result

> Observação: O runner adiciona automaticamente --reruns=1 para reduzir flakiness em ambientes locais e de CI.

---

## 🌐 Base URL via --base-url

Os testes usam page.goto("/"). O runner injeta BASE_URL pela CLI, mas você pode usar pytest direto:

- Direto com pytest (Linux/macOS):
```bash
pytest -k test_e2e_matriz_jornadas --base-url https://loja.renault.com.br/ --browser chromium \
  --html=reports/$(date +%F_%H-%M-%S)/relatorio_renault.html --self-contained-html \
  --junitxml=reports/$(date +%F_%H-%M-%S)/junit.xml \
  --video=on --screenshot=on --tracing=on --output=reports/$(date +%F_%H-%M-%S)
```

- Direto com pytest (Windows PowerShell):
```powershell
pytest -k test_e2e_matriz_jornadas --base-url https://loja.renault.com.br/ --browser chromium `
  --html="reports/$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')/relatorio_renault.html" --self-contained-html `
  --junitxml="reports/$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')/junit.xml" `
  --video=on --screenshot=on --tracing=on --output="reports/$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss')"
```

> Nota: Ao rodar pytest direto, inclua sempre --tracing=on e --output apontando para reports/<timestamp> para garantir evidências completas. Com run_tests.py isso já está garantido.

---

## 🤖 CI (GitHub Actions)

Arquivo: .github/workflows/ci.yml

- Matrix de navegadores: chromium, firefox, webkit
- Instala playwright browsers
- Gera relatórios por navegador e faz upload como artifacts
- O runner já inclui --reruns=1 para reduzir flakiness

Badge:
[![CI - e2e-tests](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml/badge.svg)](https://github.com/renault/br-ecomm-validacao/actions/workflows/ci.yml)

---

## 📦 Estrutura do projeto

```
br-ecomm-validacao/
├─ tests/
│  ├─ test_e2e_relatorio_matriz.py   # E2E ponta a ponta
│  ├─ test_jornada_reserva.py        # Jornada específica
│  ├─ test_jornada_concessionaria.py # Jornada específica
│  ├─ test_jornada_pagamento.py      # Jornada específica
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
├─ README.md
└─ relatorio_renault.html (cópia rápida do último relatório)
```

---

## 🧪 Dicas de testes

- Preferir seletores estáveis (ex.: data-testid) para reduzir flakiness
- Utilizar expect(...).to_be_visible() com timeout apropriado
- Evitar asserts em conteúdo não determinístico (ex.: contagem exata de cards)

---

## 🧹 Limpeza de arquivos rastreados indevidos

Se venv/, .pytest_cache/ ou relatórios antigos estiverem versionados, execute:
```bash
git rm -r --cached venv/ .pytest_cache/ reports/ relatorio_renault.html
git add .
git commit -m "chore: aplicar .gitignore e limpar artifacts"
```