import json
import re
import logging
from datetime import date
from pathlib import Path
from groq import Groq
from openai import OpenAI
from config import GROQ_API_KEY, OPENROUTER_API_KEY

logger = logging.getLogger(__name__)

_groq = Groq(api_key=GROQ_API_KEY)

# --- Prompts ---

_CLASSIFY_PROMPT = f"""
Eres un asistente experto en finanzas personales. Hoy es {date.today().isoformat()}.

Tu tarea es analizar un mensaje y devolver ÚNICAMENTE un JSON válido, sin texto adicional ni bloques markdown.

El JSON debe tener obligatoriamente un campo "intent" que puede ser:
  - "add"   → el usuario quiere registrar uno o más gastos nuevos
  - "edit"  → el usuario quiere corregir o modificar el último gasto registrado
  - "query" → el usuario pide un resumen, informe o consulta sobre sus gastos

Ejemplos de edición: "me equivoqué", "corregí el último", "eran 15500", "cambiá la categoría a Transporte".
Ejemplos de consulta: "cuánto gasté", "resumen de marzo", "cómo voy este mes", "estado de mis finanzas", "qué gasté en febrero".

Si el intent es "add", incluye un campo "expenses" con la lista de gastos:
{{
  "intent": "add",
  "expenses": [
    {{
      "fecha": "YYYY-MM-DD",
      "descripcion": "descripción breve",
      "monto": 0.00,
      "categoria": "Categoría",
      "metodo_pago": "Método"
    }}
  ]
}}

Si el intent es "edit", incluye un campo "fields" con SOLO los campos que deben cambiar:
{{
  "intent": "edit",
  "fields": {{
    "monto": 0.00,
    "categoria": "Categoría"
  }}
}}

Si el intent es "query", incluye "month" y "year" con el periodo consultado (números enteros).
Si el usuario dice "este mes" usa el mes y año actuales. Si dice "marzo" usa ese mes del año actual:
{{
  "intent": "query",
  "month": 3,
  "year": 2026
}}

Reglas generales:
- Fecha: si no se menciona, usa la fecha de hoy. Formato: YYYY-MM-DD.
- Monto: número decimal sin símbolo de moneda.
- Categorías válidas: Comida, Transporte, Entretenimiento, Salud, Hogar, Ropa, Educación, Tecnología, Otros.
- Métodos de pago válidos: Efectivo, Débito, Crédito, Transferencia, Otros.
- Si no puedes determinar un campo, usa "Otros" para texto o la fecha de hoy para fecha.
- Para "add": si no hay ningún gasto claro, devuelve {{"intent": "add", "expenses": []}}
"""


# --- Helpers ---

def _parse_response(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_groq(text: str) -> dict:
    response = _groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _CLASSIFY_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
    )
    return _parse_response(response.choices[0].message.content)


def _call_openrouter(text: str) -> dict:
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY no configurada, no hay fallback disponible.")
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )
    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=[
            {"role": "system", "content": _CLASSIFY_PROMPT},
            {"role": "user", "content": text},
        ],
        temperature=0.1,
    )
    return _parse_response(response.choices[0].message.content)


def _call_ai(text: str) -> dict:
    """Llama a Groq; si hay error de cuota, usa OpenRouter como fallback."""
    try:
        return _call_groq(text)
    except Exception as e:
        error_str = str(e).lower()
        if "rate_limit" in error_str or "quota" in error_str or "429" in error_str:
            logger.warning(f"Groq quota alcanzada, usando OpenRouter. Error: {e}")
            return _call_openrouter(text)
        raise


# --- API pública ---

def classify_message(text: str) -> dict:
    """
    Clasifica el mensaje y extrae los datos relevantes.

    Retorna uno de estos formatos:
      {"intent": "add",  "expenses": [...]}
      {"intent": "edit", "fields": {...}}
    """
    result = _call_ai(text)
    if "intent" not in result:
        raise ValueError(f"Respuesta inesperada del modelo: {result}")
    return result


def transcribe_audio(audio_path: str) -> str:
    """Transcribe un archivo de audio usando Whisper Large V3 en Groq."""
    with open(audio_path, "rb") as f:
        transcription = _groq.audio.transcriptions.create(
            file=(Path(audio_path).name, f),
            model="whisper-large-v3",
            language="es",
            response_format="text",
        )
    return transcription


def classify_message_from_audio(audio_path: str) -> dict:
    """Transcribe el audio y luego clasifica el mensaje."""
    text = transcribe_audio(audio_path)
    logger.info(f"Audio transcripto: {text}")
    return classify_message(text)
