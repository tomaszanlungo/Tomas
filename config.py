from dotenv import load_dotenv
import os

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN no encontrado. Agréalo al archivo .env.")
if not SPREADSHEET_ID:
    raise ValueError("SPREADSHEET_ID no encontrado. Agrégalo al archivo .env.")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY no encontrado. Agrégalo al archivo .env.")
