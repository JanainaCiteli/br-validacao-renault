import os, shutil
from pathlib import Path

root = Path(".").resolve()
targets = ["__pycache__", ".pytest_cache", "reports"]

for path in root.rglob("*"):
    if path.is_dir() and path.name in targets:
        try:
            shutil.rmtree(path, ignore_errors=True)
            print(f"Removido: {path}")
        except Exception as e:
            print(f"Falha ao remover {path}: {e}")

for ext in (".pyc", ".pyo"):
    for f in root.rglob(f"*{ext}"):
        try:
            f.unlink()
            print(f"Removido arquivo: {f}")
        except Exception as e:
            print(f"Falha ao remover {f}: {e}")