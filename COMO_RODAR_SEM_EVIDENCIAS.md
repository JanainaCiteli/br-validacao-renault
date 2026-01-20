# Como Rodar Testes Sem Armazenar Evidências

Este guia mostra como executar os testes **apenas para validar o processo**, sem gerar screenshots, vídeos, relatórios HTML ou outras evidências.

---

## 🎯 Opções Disponíveis

### Opção 1: Usar pytest diretamente (Recomendado)

Quando você roda pytest **diretamente** (não via `run_tests.py`), pode desabilitar todas as evidências:

#### Linux/macOS:
```bash
# Teste específico sem evidências
pytest tests/test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off \
  --screenshot=off \
  --tracing=off \
  --no-html

# Todos os testes de pagamento
pytest -m pagamento \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off \
  --screenshot=off \
  --tracing=off \
  --no-html

# Teste de matriz E2E
pytest tests/test_e2e_relatorio_matriz.py::test_e2e_matriz_jornadas \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off \
  --screenshot=off \
  --tracing=off \
  --no-html
```

#### Windows PowerShell:
```powershell
# Teste específico sem evidências
pytest tests\test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login `
  --base-url https://loja.renault.com.br `
  --browser chromium `
  --video=off `
  --screenshot=off `
  --tracing=off `
  --no-html

# Todos os testes de pagamento
pytest -m pagamento `
  --base-url https://loja.renault.com.br `
  --browser chromium `
  --video=off `
  --screenshot=off `
  --tracing=off `
  --no-html
```

#### Windows CMD:
```bat
pytest tests\test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login --base-url https://loja.renault.com.br --browser chromium --video=off --screenshot=off --tracing=off --no-html
```

---

### Opção 2: Variáveis de Ambiente + pytest

Você pode criar um arquivo de configuração ou usar variáveis de ambiente:

#### Linux/macOS:
```bash
# Define variáveis e roda
export BASE_URL=https://loja.renault.com.br
export BROWSER=chromium
pytest -m pagamento --video=off --screenshot=off --tracing=off --no-html
```

#### Windows PowerShell:
```powershell
$env:BASE_URL="https://loja.renault.com.br"
$env:BROWSER="chromium"
pytest -m pagamento --video=off --screenshot=off --tracing=off --no-html
```

---

### Opção 3: Criar um Alias/Script Rápido

Crie um arquivo para execução rápida sem evidências:

#### `run_tests_quick.py` (Linux/macOS/Windows):
```python
import pytest
import sys

if __name__ == "__main__":
    args = [
        "--base-url", "https://loja.renault.com.br",
        "--browser", "chromium",
        "--video=off",
        "--screenshot=off",
        "--tracing=off",
        "--no-html",
        "-v",  # Verbose mode
    ] + sys.argv[1:]  # Permite passar argumentos adicionais
    
    sys.exit(pytest.main(args))
```

**Uso:**
```bash
# Roda teste específico
python run_tests_quick.py tests/test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login

# Roda todos os testes de pagamento
python run_tests_quick.py -m pagamento

# Roda teste de matriz
python run_tests_quick.py tests/test_e2e_relatorio_matriz.py::test_e2e_matriz_jornadas
```

---

## 📝 Flags Importantes

### Desabilitar Evidências do Playwright:
- `--video=off` - Não grava vídeos
- `--screenshot=off` - Não captura screenshots
- `--tracing=off` - Não gera trace.zip

### Desabilitar Relatórios:
- `--no-html` - Não gera relatório HTML
- Sem `--junitxml` - Não gera junit.xml (ou use `--junitxml=""` para desabilitar)

### Override do pytest.ini:
O `pytest.ini` define opções padrão, mas flags na linha de comando **sobrescrevem** as opções do arquivo.

---

## ⚠️ Notas Importantes

### 1. Screenshots nos Testes (Função `_anexar_screenshot()`)

**Problema:** Mesmo com `--screenshot=off`, a função `_anexar_screenshot()` nos testes ainda pode tentar anexar screenshots ao relatório HTML.

**Solução:** A função já tem tratamento de erro (`try/except`), então ela apenas não vai anexar se não houver relatório HTML.

### 2. Relatório HTML em Memória

Mesmo com `--no-html`, o pytest-html pode ainda estar ativo. Para garantir desabilitação completa:

```bash
# Linux/macOS
pytest --no-html -p no:html ...

# Windows
pytest --no-html -p no:html ...
```

### 3. Logs do Console

Os logs do console **ainda serão capturados** pela fixture `_attach_logs_extras` em `conftest.py`. Para desabilitar completamente, você precisaria:

1. Desabilitar a fixture (não recomendado - pode quebrar outros testes)
2. Ou aceitar que os logs são mínimos e não ocupam muito espaço

---

## 🚀 Exemplos Práticos

### Exemplo 1: Validar um teste específico rapidamente
```bash
pytest tests/test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off --screenshot=off --tracing=off --no-html \
  -v
```

### Exemplo 2: Rodar suite de pagamento sem evidências
```bash
pytest -m pagamento \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off --screenshot=off --tracing=off --no-html \
  -v
```

### Exemplo 3: Validar teste de matriz sem evidências
```bash
pytest tests/test_e2e_relatorio_matriz.py::test_e2e_matriz_jornadas \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off --screenshot=off --tracing=off --no-html \
  -v
```

### Exemplo 4: Smoke test rápido (sem evidências + limites)
```bash
# Linux/macOS
MODELOS_LIMIT=1 VERSOES_LIMIT=1 pytest tests/test_e2e_relatorio_matriz.py::test_e2e_matriz_jornadas \
  --base-url https://loja.renault.com.br \
  --browser chromium \
  --video=off --screenshot=off --tracing=off --no-html \
  -v

# Windows PowerShell
$env:MODELOS_LIMIT="1"; $env:VERSOES_LIMIT="1"
pytest tests\test_e2e_relatorio_matriz.py::test_e2e_matriz_jornadas `
  --base-url https://loja.renault.com.br `
  --browser chromium `
  --video=off --screenshot=off --tracing=off --no-html `
  -v
```

---

## 🔍 Verificação

Para confirmar que as evidências não estão sendo geradas:

1. **Verifique a saída do pytest:**
   - Não deve aparecer mensagens sobre vídeos/screenshots sendo salvos
   - Não deve aparecer "Generated html report"

2. **Verifique a estrutura de diretórios:**
   - Não deve criar pasta `reports/` com timestamp
   - Não deve criar pasta `test-results/`
   - Não deve criar arquivo `relatorio_renault.html` na raiz

3. **Verifique o tempo de execução:**
   - Testes sem evidências devem rodar mais rápido (especialmente sem vídeo)

---

## 💡 Dica: Criar Comando Rápido

Para facilitar, você pode criar um script/alias:

### Linux/macOS (`.bashrc` ou `.zshrc`):
```bash
alias pytest-quick='pytest --base-url https://loja.renault.com.br --browser chromium --video=off --screenshot=off --tracing=off --no-html -v'
```

**Uso:**
```bash
pytest-quick tests/test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login
```

### Windows PowerShell (Perfil):
```powershell
function pytest-quick {
    pytest --base-url https://loja.renault.com.br --browser chromium --video=off --screenshot=off --tracing=off --no-html -v $args
}
```

**Uso:**
```powershell
pytest-quick tests\test_jornada_pagamento.py::test_pagamento_opcao_financiamento_requer_login
```

---

## 📊 Comparação: Com vs Sem Evidências

| Aspecto | Com Evidências | Sem Evidências |
|---------|----------------|----------------|
| **Tempo de Execução** | Mais lento (gravação de vídeo) | Mais rápido |
| **Espaço em Disco** | ~50-500 MB por execução | ~1-5 MB |
| **Debug** | Fácil (screenshots/vídeos) | Apenas logs |
| **Uso** | Produção/CI | Validação rápida |
| **Comando** | `run_tests.py` ou padrão | `pytest` com flags |

---

## ✅ Checklist Rápido

Para rodar sem evidências, certifique-se de:

- [ ] Usar `pytest` diretamente (não `run_tests.py`)
- [ ] Adicionar `--video=off`
- [ ] Adicionar `--screenshot=off`
- [ ] Adicionar `--tracing=off`
- [ ] Adicionar `--no-html`
- [ ] Não especificar `--html` ou `--junitxml`

---

*Documentação criada em: 2026-01-19*  
*Última atualização: 2026-01-19*