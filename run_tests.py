import os
import sys
import shutil
from datetime import datetime
from pathlib import Path
import pytest

def main():
    # 1. DEFINE O DIRETÓRIO ÚNICO PARA ESSA EXECUÇÃO
    # Gera o timestamp uma única vez aqui no script principal
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Define o caminho absoluto para evitar confusão entre workers
    report_root = (Path.cwd() / "reports" / ts).resolve()
    report_root.mkdir(parents=True, exist_ok=True)

    # 2. COMPARTILHA O CAMINHO COM OS WORKERS
    # Isso impede que cada worker crie sua própria pasta com horários diferentes
    os.environ["REPORTS_DIR"] = str(report_root)

    print(f"--- Configurando Relatórios em: {report_root} ---")

    # Configurações do Ambiente
    browser = os.getenv("BROWSER", "chromium")
    base_url = os.getenv("BASE_URL", "https://loja.renault.com.br/")
    headed = os.getenv("HEADED", "").lower() in ("1", "true", "yes", "on")
    workers_env = os.getenv("WORKERS")
    workers_arg = str(int(workers_env)) if workers_env else "auto"

    # Caminhos dos arquivos
    html_report = report_root / 'relatorio_renault.html'
    junit_report = report_root / 'junit.xml'

    extra_args = sys.argv[1:]

    args = [
        "-q",
        # Removido --maxfail=1 para permitir mapear todas as falhas antes de encerrar
        "-n", workers_arg,
        "--browser", browser,
        "--base-url", base_url,
        
        # ONDE SALVAR:
        f"--html={html_report}",
        "--self-contained-html",
        f"--junitxml={junit_report}",
        f"--output={report_root}",  # <--- FORÇA O PLAYWRIGHT A USAR ESTA PASTA

        # O QUE SALVAR (Mudei para 'on' para atender seu pedido):
        "--video=on",      # Grava vídeo sempre (mesmo se passar)
        "--screenshot=on", # Tira foto sempre (mesmo se passar)
        "--tracing=on",    # Gera trace.zip sempre (CUIDADO: arquivos grandes)
    ]

    if headed:
        args.append("--headed")

    args += extra_args

    # Executa
    code = pytest.main(args)

    # Copia o HTML para a raiz (opcional)
    try:
        shutil.copyfile(html_report, Path("relatorio_renault.html"))
        print(f"\n[SUCESSO] Relatório gerado com sucesso!")
        print(f"Pasta completa: {report_root}")
        print(f"Arquivo HTML atalho: {Path('relatorio_renault.html').resolve()}")
    except Exception as e:
        print(f"Nota: Não foi possível criar atalho na raiz: {e}")

    return code

if __name__ == "__main__":
    raise SystemExit(main())
