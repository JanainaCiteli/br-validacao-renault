Instruções de execução com logs detalhados
Gerado em: 18/01/2026

Log detalhado (debug) para execução de testes de pagamento

Para facilitar o troubleshooting, rode os testes com logs detalhados:

    • Comando base:
    • `pytest -vv -s --html=relatorio_renault.html --self-contained-html -m pagamento`

    • Explicação:
    • `-vv`: verbose máximo
    • `-s`: não captura stdout (exibe prints)
    • `--html ..`: gera relatório
    • `-m pagamento`: roda apenas a marcação de pagamento

Os prints adicionados no arquivo tests/test_jornada_pagamento.py incluem:
    • "Iniciando navegação dinâmica até Concessionária..."
    • "Detectada tela de Versões. Tentando selecionar..."
    • "Tentando selecionar concessionária..."
    • "Aguardando processamento de rede (networkidle)..."
    • "Validando seleção da concessionária..."
    • "Avançando para Pagamento..."
    • "Pagamento detectado com sucesso!"
    • Correção de navegação quando ainda em Concessionária
    • Fallbacks de URL para pagamento/checkout

Se persistirem falhas:
    • Aumente timeouts em `_esperar_pagamento/_esperar_resumo` para 40000 ms
    • Envie o log completo e o relatório HTML para análise
