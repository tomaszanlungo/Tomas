"""
Ejecuta este script UNA VEZ para configurar tu archivo .env de forma segura.
    python setup_env.py
"""
import getpass
from pathlib import Path

env_path = Path(__file__).parent / ".env"

if env_path.exists():
    overwrite = input(".env ya existe. ¿Sobreescribir? (s/n): ").strip().lower()
    if overwrite != "s":
        print("Cancelado. El archivo .env no fue modificado.")
        exit(0)

token = getpass.getpass("Pega tu TELEGRAM_TOKEN y presiona Enter (no se mostrará): ")

if not token.strip():
    print("Error: el token no puede estar vacío.")
    exit(1)

env_path.write_text(f"TELEGRAM_TOKEN={token.strip()}\n", encoding="utf-8")
print(f".env creado en: {env_path}")
